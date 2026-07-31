"""The service tying the game file, the database and the watcher together."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import gamefile, store
from .model import Comparison, IngestResult, Run, SplitsDatabase

#: How often to check the game file for changes, in seconds.
POLL_INTERVAL = 0.5


@dataclass(frozen=True)
class _Fingerprint:
    size: int
    mtime_ns: int

    @classmethod
    def of(cls, path: Path) -> _Fingerprint | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        return cls(stat.st_size, stat.st_mtime_ns)


class SplitsTracker:
    """Owns the comparison database and mediates access to the game file.

    Writes made by this tool are fingerprinted so the watcher does not read its
    own output back in as if it were a newly saved run. That is what allows
    watching and loading to coexist in one process -- the original two scripts
    had to be run one at a time precisely because they lacked this.
    """

    def __init__(self, game_file: Path, root: Path | None = None) -> None:
        self.game_file = Path(game_file)
        self.root = root
        self.database: SplitsDatabase = store.load_database(root)
        self._own_write: str | None = None
        self._fingerprint = _Fingerprint.of(self.game_file)
        self._lock = threading.Lock()

    # -- reading -----------------------------------------------------------

    def ingest_current_file(self) -> IngestResult:
        """Read the game file now and fold it into the database."""
        times = gamefile.read_times(self.game_file)
        with self._lock:
            result = self.database.ingest(Run.from_game_times(times))
            if result.changed:
                store.save_database(self.database, self.root)
        return result

    def poll(self) -> IngestResult | None:
        """Ingest the game file if it changed since the last check.

        Returns ``None`` when nothing changed, or when the change was this
        tool's own write.
        """
        fingerprint = _Fingerprint.of(self.game_file)
        if fingerprint is None or fingerprint == self._fingerprint:
            return None
        self._fingerprint = fingerprint

        try:
            text = self.game_file.read_text(encoding="utf-8-sig")
        except OSError:
            return None

        if self._own_write is not None and text == self._own_write:
            return None

        try:
            times = gamefile.parse_times(text)
        except gamefile.GameFileError:
            # Caught mid-write; the next poll will pick up the finished file.
            self._fingerprint = None
            return None

        with self._lock:
            result = self.database.ingest(Run.from_game_times(times))
            if result.changed:
                store.save_database(self.database, self.root)
        return result

    # -- writing -----------------------------------------------------------

    def load_into_game(self, comparison: Comparison) -> Path | None:
        """Write a comparison into the game file. Returns the backup path."""
        with self._lock:
            times = self.database.segments_for(comparison)
        if not times:
            raise ValueError(f"{comparison.label} has no data yet")

        backup = gamefile.backup_file(self.game_file, store.backup_dir(self.root))
        store.prune_backups(self.root)
        self.game_file.parent.mkdir(parents=True, exist_ok=True)
        self._own_write = gamefile.write_times(self.game_file, times)
        self._fingerprint = _Fingerprint.of(self.game_file)
        return backup


class Watcher:
    """Polls the game file on a background thread.

    Polling rather than filesystem events keeps the tool dependency-free and
    sidesteps the platform-specific path normalisation that made event-based
    watching miss saves.
    """

    def __init__(
        self,
        tracker: SplitsTracker,
        on_result: Callable[[IngestResult], None],
        interval: float = POLL_INTERVAL,
    ) -> None:
        self.tracker = tracker
        self.on_result = on_result
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="gtw-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2 * self.interval + 1)
            self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                result = self.tracker.poll()
            except Exception as exc:  # keep watching despite transient errors
                result = None
                self.on_result(IngestResult(ignored_reason=f"Error: {exc}"))
            if result is not None:
                self.on_result(result)
            self._stop.wait(self.interval)
