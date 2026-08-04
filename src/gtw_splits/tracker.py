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
    watching and loading to coexist -- the original two scripts had to be run
    one at a time precisely because they lacked this. The text written is
    remembered on disk as well as in memory, and checked in both places, so the
    guard holds across a restart *and* across a second instance running at the
    same time. Either way the file may hold a comparison this tool put there,
    and neither is a run.
    """

    def __init__(self, game_file: Path, root: Path | None = None) -> None:
        self.game_file = Path(game_file)
        self.root = root
        #: While false, saves are read but not recorded. Only you can tell a
        #: modded or cheated attempt from a real one, so this is a switch
        #: rather than a guess about which times look plausible.
        self.recording: bool = bool(
            store.load_settings(root).get(store.SETTING_RECORDING, True)
        )
        self.database: SplitsDatabase = store.load_database(root)
        self._own_write: str | None = store.load_last_write(root)
        # Deliberately unset: the game may have saved a run before this process
        # started, and the first poll has to pick it up rather than treat the
        # file as already seen. A file we wrote ourselves is skipped by the
        # ``_own_write`` check instead.
        self._fingerprint: _Fingerprint | None = None
        self._lock = threading.Lock()

    def set_recording(self, enabled: bool) -> None:
        """Turn recording on or off, and remember it for the next session."""
        self.recording = bool(enabled)
        settings = store.load_settings(self.root)
        settings[store.SETTING_RECORDING] = self.recording
        store.save_settings(settings, self.root)

    # -- reading -----------------------------------------------------------

    def ingest_current_file(self) -> IngestResult:
        """Read the game file now and fold it into the database.

        Never raises: an unreadable or half-written file is reported as an
        ignored result, because the callers of this are workflows (starting up,
        loading a comparison) that must carry on regardless.
        """
        self._fingerprint = _Fingerprint.of(self.game_file)
        try:
            text = self.game_file.read_text(encoding="utf-8-sig")
        except OSError:
            return IngestResult(ignored_reason="No splits file to read yet")
        result = self._ingest_text(text)
        if result is None:
            # Either our own comparison or a half-written save; neither is a run.
            return IngestResult(ignored_reason="Nothing new in the splits file")
        return result

    def _is_own_write(self, text: str) -> bool:
        """True if ``text`` is a comparison this tool wrote, in any session.

        The in-memory copy only knows about writes *this* instance made. Nothing
        stops the window being opened twice, and a second instance writing a
        comparison looks exactly like a newly saved run to the first -- which
        then records best exits as an attempt and installs an unbeatable fake
        PB. Falling back to the record on disk closes that, at the cost of one
        small read, and only when the file has really changed underneath us.
        """
        if self._own_write is not None and text == self._own_write:
            return True
        recorded = store.load_last_write(self.root)
        if recorded is not None and text == recorded:
            self._own_write = recorded
            return True
        return False

    def _ingest_text(self, text: str) -> IngestResult | None:
        """Fold splits-file text into the database, or ``None`` if it is ours."""
        if self._is_own_write(text):
            return None
        if not self.recording:
            # Reported rather than silent: a save that is being deliberately
            # ignored should still show up as one, not look like a missed save.
            return IngestResult(ignored_reason="Recording paused -- not saved")

        try:
            times = gamefile.parse_times(text)
        except gamefile.GameFileError:
            # Caught mid-write; force the next poll to look again.
            self._fingerprint = None
            return None

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

        return self._ingest_text(text)

    # -- writing -----------------------------------------------------------

    def load_into_game(self, comparison: Comparison) -> Path | None:
        """Write a comparison into the game file. Returns the backup path.

        Whatever the file holds is recorded first. The game may have saved a
        run the watcher has not polled yet -- or may not be running at all --
        and the write below would otherwise destroy it.
        """
        self.ingest_current_file()
        with self._lock:
            times = self.database.segments_for(comparison)
        if not times:
            raise ValueError(f"{comparison.label} has no data yet")

        backup = gamefile.backup_file(self.game_file, store.backup_dir(self.root))
        store.prune_backups(self.root)
        self.game_file.parent.mkdir(parents=True, exist_ok=True)
        self._own_write = gamefile.write_times(self.game_file, times)
        store.save_last_write(self._own_write, self.root)
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
