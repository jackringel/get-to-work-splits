"""Split data model and comparison tracking.

The game stores a run as a flat list of per-segment durations ("deltas"), where
``0.0`` marks a segment with no recorded time. Everything here works in those
same units except best exits, which are held internally as cumulative
time-since-start and only converted back to deltas on export -- see
:class:`SplitsDatabase.best_exits`.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, replace

#: A segment time at or below this is treated as "no data recorded".
EPSILON = 1e-9


class Comparison(enum.Enum):
    """The three comparison sets the tool maintains."""

    PB = "pb"
    BEST_SEGMENTS = "best_segments"
    BEST_EXITS = "best_exits"

    @property
    def label(self) -> str:
        return {
            Comparison.PB: "Personal Best",
            Comparison.BEST_SEGMENTS: "Best Segments",
            Comparison.BEST_EXITS: "Best Exits",
        }[self]


def is_recorded(value: float) -> bool:
    """True if ``value`` is a real time rather than the game's empty marker."""
    return value > EPSILON


def format_time(seconds: float) -> str:
    """Format seconds as ``M:SS.hh``, or ``--`` when there is no time."""
    if not is_recorded(seconds):
        return "--"
    minutes, secs = divmod(seconds, 60.0)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{int(hours)}:{int(minutes):02d}:{secs:05.2f}"
    return f"{int(minutes)}:{secs:05.2f}"


def format_delta(seconds: float) -> str:
    """Format a signed time difference, e.g. ``-2.41s``."""
    return f"{seconds:+.2f}s"


def format_progress(total: float, reach: int, split_count: int) -> str:
    """``2:21.91  (2/11)`` while incomplete, plain ``12:38.66`` once finished.

    Showing the reach alongside the time keeps a partial total from reading as
    a finishing time, which is the only way the two can be confused.
    """
    if reach <= 0:
        return "--"
    if reach >= split_count:
        return format_time(total)
    return f"{format_time(total)}  ({reach}/{split_count})"


@dataclass(frozen=True)
class Run:
    """One attempt as saved by the game."""

    segments: tuple[float, ...]

    @classmethod
    def from_game_times(cls, times: list[float]) -> Run:
        """Build a run from raw game times, keeping every completed segment.

        The game only writes a segment once you have finished it -- its log
        emits one ``Completed: <section>`` line per value written, and the
        section you are currently on is not in the file at all. So every
        recorded time is a real one and none of them are dropped. Anything
        from the first empty segment onward is still discarded, so a stray
        later value can never be read as progress.
        """
        cleaned = [t if is_recorded(t) else 0.0 for t in times]
        for i, value in enumerate(cleaned):
            if not is_recorded(value):
                # The run stopped here; nothing after this is meaningful.
                for j in range(i, len(cleaned)):
                    cleaned[j] = 0.0
                break
        return cls(tuple(cleaned))

    def __len__(self) -> int:
        return len(self.segments)

    @property
    def recorded_prefix(self) -> int:
        """How many segments from the start have real times."""
        count = 0
        for value in self.segments:
            if not is_recorded(value):
                break
            count += 1
        return count

    @property
    def is_complete(self) -> bool:
        """True if every segment has a time, i.e. the run reached the end."""
        return len(self.segments) > 0 and self.recorded_prefix == len(self.segments)

    @property
    def total(self) -> float:
        """Final time, or ``0.0`` if the run was not finished."""
        return sum(self.segments) if self.is_complete else 0.0

    @property
    def reached_total(self) -> float:
        """Time to the end of the recorded prefix, ``0.0`` if it is empty.

        Unlike ``total`` this is defined for an unfinished run: it is how long
        the attempt took to get as far as it got. Ranking two attempts by reach
        and then by this is what makes an incomplete run comparable at all.
        """
        prefix = self.recorded_prefix
        return self.cumulative()[prefix - 1] if prefix else 0.0

    def cumulative(self) -> list[float]:
        """Time-since-start at each split, ``0.0`` past the recorded prefix.

        Cumulative time is only meaningful while every preceding segment is
        present, so this stops at the first gap rather than summing across it.
        """
        out = [0.0] * len(self.segments)
        running = 0.0
        for i in range(self.recorded_prefix):
            running += self.segments[i]
            out[i] = running
        return out


@dataclass(frozen=True)
class IngestResult:
    """What a newly saved run changed."""

    is_new_pb: bool = False
    pb_delta: float = 0.0
    #: True when the new best is an unfinished attempt, so it can be reported
    #: as progress rather than announced as a finished personal best.
    pb_is_partial: bool = False
    improved_segments: tuple[int, ...] = ()
    improved_exits: tuple[int, ...] = ()
    ignored_reason: str | None = None

    @property
    def changed(self) -> bool:
        return bool(self.is_new_pb or self.improved_segments or self.improved_exits)

    def summary(self) -> str:
        if self.ignored_reason:
            return self.ignored_reason
        if not self.changed:
            return "No improvements"
        parts = []
        if self.is_new_pb:
            # An unfinished attempt is real progress, but calling it a PB would
            # hide that the run never reached the end.
            label = "best attempt" if self.pb_is_partial else "PB"
            if self.pb_delta:
                parts.append(f"New {label}! {format_delta(self.pb_delta)}")
            else:
                # No delta means the reach grew, so there is nothing to compare.
                parts.append("Further than ever!" if self.pb_is_partial else "First PB!")
        if self.improved_segments:
            n = len(self.improved_segments)
            parts.append(f"{n} best segment{'s' if n != 1 else ''}")
        if self.improved_exits:
            n = len(self.improved_exits)
            parts.append(f"{n} best exit{'s' if n != 1 else ''}")
        return " | ".join(parts)


@dataclass
class SplitsDatabase:
    """The three comparison sets, accumulated across every saved run."""

    split_count: int
    pb: list[float] = field(default_factory=list)
    best_segments: list[float] = field(default_factory=list)
    #: Best exits are stored as cumulative time-since-start, not as deltas.
    best_exit_cumulative: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.pb = self._sized(self.pb)
        self.best_segments = self._sized(self.best_segments)
        self.best_exit_cumulative = self._sized(self.best_exit_cumulative)

    def _sized(self, values: list[float]) -> list[float]:
        out = list(values[: self.split_count])
        out.extend([0.0] * (self.split_count - len(out)))
        return out

    def resize(self, split_count: int) -> None:
        """Grow or shrink to match a game file with a different split count."""
        if split_count == self.split_count:
            return
        self.split_count = split_count
        self.__post_init__()

    @property
    def best_exits(self) -> list[float]:
        """Best exits as per-segment deltas, for writing back to the game.

        ``best_exit_cumulative`` is non-decreasing (see ``ingest``), so these
        deltas are always non-negative.
        """
        out = [0.0] * self.split_count
        previous = 0.0
        for i, cumulative in enumerate(self.best_exit_cumulative):
            if not is_recorded(cumulative):
                break
            out[i] = cumulative - previous
            previous = cumulative
        return out

    def segments_for(self, comparison: Comparison) -> list[float]:
        """The per-segment times to write to the game for ``comparison``."""
        if comparison is Comparison.PB:
            return list(self.pb)
        if comparison is Comparison.BEST_SEGMENTS:
            return list(self.best_segments)
        return self.best_exits

    def total_for(self, comparison: Comparison) -> float:
        """Total time of a comparison, or ``0.0`` if it is not yet complete."""
        segments = self.segments_for(comparison)
        if not segments or any(not is_recorded(v) for v in segments):
            return 0.0
        return sum(segments)

    def progress_for(self, comparison: Comparison) -> tuple[float, int]:
        """Time so far and how many splits of ``comparison`` have times.

        Where ``total_for`` refuses to total an incomplete comparison, this
        describes one: the reach travels with the time, so a partial total can
        be displayed without being mistaken for a finishing time.
        """
        run = Run(tuple(self.segments_for(comparison)))
        return run.reached_total, run.recorded_prefix

    def ingest(self, run: Run) -> IngestResult:
        """Fold a newly saved run into all three comparisons."""
        if len(run) != self.split_count:
            self.resize(len(run))
        if run.recorded_prefix == 0:
            return IngestResult(ignored_reason="No completed splits in save")

        # PB is the attempt that got furthest, and the fastest of those that
        # got equally far. A complete run has the longest prefix there is, so
        # it always outranks a partial one and a partial can never displace it
        # -- "PB only updates on complete runs" is the special case of this
        # rule, not an exception to it. Until the first completion the slot
        # holds the best attempt so far rather than sitting empty.
        best = Run(tuple(self.pb))
        reach, previous_reach = run.recorded_prefix, best.recorded_prefix
        is_new_pb = reach > previous_reach or (
            reach == previous_reach and run.reached_total < best.reached_total
        )
        pb_delta = 0.0
        if is_new_pb:
            # Only comparable when both attempts reached the same split; across
            # different reaches the difference in seconds means nothing.
            if reach == previous_reach:
                pb_delta = run.reached_total - best.reached_total
            self.pb = list(run.segments)

        improved_segments = []
        for i in range(self.split_count):
            new = run.segments[i]
            if not is_recorded(new):
                continue
            if not is_recorded(self.best_segments[i]) or new < self.best_segments[i]:
                self.best_segments[i] = new
                improved_segments.append(i)

        improved_exits = []
        # Only the recorded prefix has meaningful cumulative times. Because
        # every run's cumulative times increase, taking the per-index minimum
        # across runs keeps the stored series non-decreasing.
        for i, new_cumulative in enumerate(run.cumulative()):
            if not is_recorded(new_cumulative):
                break
            best = self.best_exit_cumulative[i]
            if not is_recorded(best) or new_cumulative < best:
                self.best_exit_cumulative[i] = new_cumulative
                improved_exits.append(i)

        return IngestResult(
            is_new_pb=is_new_pb,
            pb_delta=pb_delta,
            pb_is_partial=is_new_pb and not run.is_complete,
            improved_segments=tuple(improved_segments),
            improved_exits=tuple(improved_exits),
        )

    def copy(self) -> SplitsDatabase:
        return replace(
            self,
            pb=list(self.pb),
            best_segments=list(self.best_segments),
            best_exit_cumulative=list(self.best_exit_cumulative),
        )
