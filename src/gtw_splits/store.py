"""Persistence for the comparison database and user settings."""

from __future__ import annotations

import json
from pathlib import Path

from .locate import data_dir
from .model import SplitsDatabase, is_recorded

SCHEMA_VERSION = 1

DATABASE_NAME = "splits.json"
SETTINGS_NAME = "settings.json"
BACKUP_DIR_NAME = "backups"
#: Copy of the last comparison this tool wrote into the game file, so a later
#: session can still recognise it as ours rather than as a saved attempt.
LAST_WRITE_NAME = "last_write.txt"

#: The 3-column CSV written by the original update_personal_splits.py.
LEGACY_NAME = "splits.txt"

#: Keys in settings.json.
SETTING_GAME_FILE = "game_file"
SETTING_RECORDING = "recording"

#: How many game-file snapshots to keep before pruning the oldest.
MAX_BACKUPS = 20


def database_path(root: Path | None = None) -> Path:
    return (root or data_dir()) / DATABASE_NAME


def settings_path(root: Path | None = None) -> Path:
    return (root or data_dir()) / SETTINGS_NAME


def backup_dir(root: Path | None = None) -> Path:
    return (root or data_dir()) / BACKUP_DIR_NAME


def load_database(root: Path | None = None, *, split_count: int = 11) -> SplitsDatabase:
    """Load the comparison database, creating an empty one if absent."""
    path = database_path(root)
    if not path.is_file():
        return SplitsDatabase(split_count=split_count)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return SplitsDatabase(split_count=split_count)
    return SplitsDatabase(
        split_count=int(payload.get("split_count", split_count)),
        pb=[float(v) for v in payload.get("pb", [])],
        best_segments=[float(v) for v in payload.get("best_segments", [])],
        best_exit_cumulative=[float(v) for v in payload.get("best_exit_cumulative", [])],
    )


def save_database(database: SplitsDatabase, root: Path | None = None) -> Path:
    """Write the database atomically so a crash cannot truncate it."""
    path = database_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": SCHEMA_VERSION,
        "split_count": database.split_count,
        "pb": database.pb,
        "best_segments": database.best_segments,
        "best_exit_cumulative": database.best_exit_cumulative,
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)
    return path


def last_write_path(root: Path | None = None) -> Path:
    return (root or data_dir()) / LAST_WRITE_NAME


def load_last_write(root: Path | None = None) -> str | None:
    """The exact text this tool last wrote into the game file, if any."""
    path = last_write_path(root)
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def save_last_write(text: str, root: Path | None = None) -> Path:
    """Remember a write so it is not read back in as an attempt later."""
    path = last_write_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".txt.tmp")
    temporary.write_text(text, encoding="utf-8", newline="")
    temporary.replace(path)
    return path


def load_settings(root: Path | None = None) -> dict:
    path = settings_path(root)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(settings: dict, root: Path | None = None) -> Path:
    path = settings_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    temporary.replace(path)
    return path


def prune_backups(root: Path | None = None, keep: int = MAX_BACKUPS) -> int:
    """Delete all but the ``keep`` newest game-file snapshots."""
    directory = backup_dir(root)
    if not directory.is_dir():
        return 0
    snapshots = sorted(directory.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for stale in snapshots[keep:]:
        try:
            stale.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def _repair_legacy_exits(cumulative: list[float], pb: list[float]) -> None:
    """Restore the best-exit invariants that the legacy data could violate.

    The old best-exit column was produced by arithmetic that summed across
    gaps, so imported values can be optimistic -- and an exit time faster than
    anything actually achievable would never be beaten, sticking permanently.
    Two invariants are enforced in place:

    1. Cumulative exits never decrease.
    2. The final exit equals the PB total. Both are the fastest *complete* run,
       so they are the same number by definition.
    """
    running_max = 0.0
    for i, value in enumerate(cumulative):
        if not is_recorded(value):
            continue
        cumulative[i] = max(value, running_max)
        running_max = cumulative[i]

    if pb and all(is_recorded(v) for v in pb):
        cumulative[-1] = sum(pb)


def migrate_legacy_csv(csv_path: Path, root: Path | None = None) -> SplitsDatabase | None:
    """Import an old ``splits.txt`` into the JSON database.

    The legacy format is headerless ``pb,best_segment,best_exit`` rows holding
    per-segment deltas. Best exits move to cumulative storage here, and because
    the legacy best-exit column was produced by buggy arithmetic its deltas are
    re-accumulated rather than trusted as-is.
    """
    if not csv_path.is_file():
        return None
    rows = [line for line in csv_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        return None

    pb, best_segments, legacy_exits = [], [], []
    for row in rows:
        fields = row.split(",")
        if len(fields) < 3:
            return None
        try:
            pb.append(float(fields[0]))
            best_segments.append(float(fields[1]))
            legacy_exits.append(float(fields[2]))
        except ValueError:
            return None

    cumulative, running = [], 0.0
    for value in legacy_exits:
        if not is_recorded(value):
            cumulative.append(0.0)
            continue
        running += value
        cumulative.append(running)

    _repair_legacy_exits(cumulative, pb)

    database = SplitsDatabase(
        split_count=len(rows),
        pb=pb,
        best_segments=best_segments,
        best_exit_cumulative=cumulative,
    )
    save_database(database, root)
    return database
