"""Command-line interface.

Running ``gtw-splits`` with no arguments launches the GUI; the subcommands
exist for headless use and scripting.
"""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from . import store
from .locate import data_dir, find_game_file
from .model import Comparison, format_progress
from .tracker import SplitsTracker, Watcher
from .version import version_string

_CHOICES = {
    "pb": Comparison.PB,
    "best-segments": Comparison.BEST_SEGMENTS,
    "best-exits": Comparison.BEST_EXITS,
}


def resolve_game_file(explicit: str | None) -> Path:
    """Pick the game file from the flag, saved settings, or auto-detection."""
    if explicit:
        return Path(explicit).expanduser()
    saved = store.load_settings().get(store.SETTING_GAME_FILE)
    if saved and Path(saved).is_file():
        return Path(saved)
    found = find_game_file()
    if found is None:
        raise SystemExit(
            "Could not find the Get To Work save folder. Pass --game-file with the "
            "path to best_split_times.txt."
        )
    return found


def _print_status(tracker: SplitsTracker) -> None:
    print(f"Version:   {version_string()}")
    print(f"Game file: {tracker.game_file}")
    print(f"Data dir:  {data_dir()}")
    print(f"Recording: {'on' if tracker.recording else 'PAUSED'}")
    print()
    database = tracker.database
    for comparison in Comparison:
        total, reach = database.progress_for(comparison)
        print(f"  {comparison.label:<15} {format_progress(total, reach, database.split_count)}")


def _command_status(args: argparse.Namespace) -> int:
    tracker = SplitsTracker(resolve_game_file(args.game_file))
    _print_status(tracker)
    return 0


def _command_watch(args: argparse.Namespace) -> int:
    tracker = SplitsTracker(resolve_game_file(args.game_file))
    if args.no_record:
        tracker.recording = False  # this run only; the saved setting stands
    print(f"Watching {tracker.game_file}")
    if not tracker.recording:
        print("Recording is PAUSED -- saves will be reported but not kept.")
    print("Save your splits in game after each attempt. Ctrl-C to stop.\n")

    def report(result) -> None:
        print(f"  {result.summary()}")

    watcher = Watcher(tracker, report)
    watcher.start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()
        print("\nStopped.")
    return 0


def _command_load(args: argparse.Namespace) -> int:
    tracker = SplitsTracker(resolve_game_file(args.game_file))
    comparison = _CHOICES[args.comparison]
    if args.no_record:
        tracker.recording = False  # this run only; the saved setting stands

    # Record whatever is in the file before overwriting it; with no watcher
    # running, this is the only chance to keep a run saved since last time.
    recorded = tracker.ingest_current_file()
    if recorded.changed:
        print(f"Recorded from the current file: {recorded.summary()}")

    database = tracker.database
    total, reach = database.progress_for(comparison)
    if reach < database.split_count and comparison is not Comparison.BEST_SEGMENTS:
        print(f"Warning: {comparison.label} is incomplete.", file=sys.stderr)
    backup = tracker.load_into_game(comparison)
    shown = format_progress(total, reach, database.split_count)
    print(f"Loaded {comparison.label} ({shown}) into {tracker.game_file}")
    if backup:
        print(f"Previous file backed up to {backup}")
    return 0


def _command_record(args: argparse.Namespace) -> int:
    enabled = args.state == "on"
    settings = store.load_settings()
    settings[store.SETTING_RECORDING] = enabled
    store.save_settings(settings)
    print(f"Recording {'on' if enabled else 'PAUSED'}. Remembered for next time.")
    if not enabled:
        print("Saved runs will be ignored until you turn it back on.")
    return 0


def _command_import(args: argparse.Namespace) -> int:
    csv_path = Path(args.path).expanduser()
    database = store.migrate_legacy_csv(csv_path)
    if database is None:
        print(f"Nothing to import from {csv_path}", file=sys.stderr)
        return 1
    print(f"Imported {database.split_count} splits from {csv_path}")
    print(f"Saved to {store.database_path()}")
    return 0


def _command_gui(args: argparse.Namespace) -> int:
    from .gui import run_gui

    return run_gui(args.game_file)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gtw-splits",
        description="Better split comparisons for the Get To Work in-game timer.",
    )
    parser.add_argument(
        "--game-file",
        help="Path to best_split_times.txt (auto-detected when omitted).",
    )
    parser.add_argument("--version", action="version", version=version_string())
    subparsers = parser.add_subparsers(dest="command")

    pause_help = "Do not record saved runs this time (for modded or test attempts)."

    subparsers.add_parser("gui", help="Launch the graphical interface (default).")
    subparsers.add_parser("status", help="Show the current comparisons.")

    watch = subparsers.add_parser("watch", help="Record saved runs into all three comparisons.")
    watch.add_argument("--no-record", action="store_true", help=pause_help)

    load = subparsers.add_parser("load", help="Write a comparison into the game.")
    load.add_argument("comparison", choices=sorted(_CHOICES))
    load.add_argument("--no-record", action="store_true", help=pause_help)

    record = subparsers.add_parser("record", help="Turn recording of saved runs on or off.")
    record.add_argument("state", choices=["on", "off"])

    legacy = subparsers.add_parser("import-legacy", help="Import an old splits.txt.")
    legacy.add_argument("path", nargs="?", default=store.LEGACY_NAME)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        None: _command_gui,
        "gui": _command_gui,
        "watch": _command_watch,
        "status": _command_status,
        "load": _command_load,
        "record": _command_record,
        "import-legacy": _command_import,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
