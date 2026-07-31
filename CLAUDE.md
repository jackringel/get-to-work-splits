# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A zero-dependency Python tool that gives the speedrun game *Get To Work* three split comparisons
instead of the one its built-in timer can hold. It watches the game's splits file, accumulates PB /
best segments / best exits across every saved run, and writes a chosen comparison back into the game.

## Commands

```
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest              # full suite (fast, no I/O beyond tmp_path)
.venv\Scripts\python -m pytest tests/test_model.py::test_partial_run_does_not_poison_later_exits
.venv\Scripts\python -m ruff check src tests
```

Runtime deps are deliberately empty — only stdlib, including tkinter for the GUI. Don't add a
dependency without a strong reason; the install story is a feature (see "Design decisions").

`GTW_SPLITS_HOME` relocates the tool's data dir, which is how tests and manual runs stay away from
real user data. Always set it when exercising the tool by hand.

## Architecture

Layered, each module depending only on those above it:

- `model.py` — pure logic, no I/O. `Run` (one attempt) and `SplitsDatabase` (the three comparisons).
  All comparison rules live here, which is why the test suite is concentrated on this module.
- `gamefile.py` — parse/render the game's XML, atomic writes, backups.
- `locate.py` — auto-detect the game save folder and this tool's data folder.
- `store.py` — JSON persistence, backup pruning, legacy CSV migration.
- `tracker.py` — `SplitsTracker` (database + game file) and `Watcher` (polling thread).
- `cli.py` / `gui.py` — entry points. `gui.py` imports from `cli.py`, never the reverse.

## Data formats

**Game file** (`best_split_times.txt`, .NET `XmlSerializer` output) holds one `<float>` per split —
11 in the current game version, but nothing hardcodes that; `SplitsDatabase.resize` adapts to
whatever the file contains. Times are **per-segment durations**, not cumulative.

`gamefile.render_times` reproduces the game's layout byte-for-byte, including the absent trailing
newline; `test_render_round_trips_real_file_byte_for_byte` pins this against a real file captured
from the game. If you change rendering, that test is the guard.

**`splits.json`** stores `pb` and `best_segments` as per-segment deltas, but `best_exit_cumulative`
as **cumulative time-since-start**. Deltas are derived on export via the `best_exits` property.

## Invariants worth preserving

These encode bugs that existed in the original version; breaking them silently corrupts users' data.

- **`0.0` means "no time recorded"**, never a real time. Test with `is_recorded`, not truthiness on
  raw floats.
- **Cumulative times stop at the first gap.** `Run.cumulative` only sums the recorded prefix.
  Summing deltas across a gap yields impossibly fast exits that can never be beaten, which is what
  the original code did.
- **Best exits are stored cumulatively.** Taking the per-index minimum of cumulative times across
  runs keeps the series non-decreasing (for any run, `cum[i] > cum[i-1] >= min cum[i-1]`), so
  exported deltas are always non-negative. Storing deltas directly loses this guarantee.
- **Every recorded segment of an unfinished run counts.** The game writes a segment only once you
  finish it — `Player.log` emits one `Speedrun Mode- Completed:<section>, Split: <time>` line per
  value in the file, and the section you're on is absent — so there is no partial time to strip.
  `Run.from_game_times` keeps the whole recorded prefix and only zeroes what follows the first gap.
  An earlier version dropped the last recorded segment as "in progress", which silently lost a
  completed split from every save made mid-run; `test_every_written_segment_is_kept` guards it.
- **PB only updates on complete runs.**
- **`SplitsTracker` fingerprints its own writes** (`_own_write`) so `Watcher` doesn't ingest them as
  new attempts. Without this, loading a comparison would be recorded as a run — which is exactly why
  the original two scripts couldn't be run at the same time. `test_poll_ignores_our_own_write`
  guards it; anything that changes the write path must keep it passing.

## Design decisions

- **Polling, not `watchdog`.** The original used filesystem events and compared `event.src_path` to
  the user's typed path by string equality, so any path form mismatch meant saves were silently
  never detected. Polling one small file every 0.5s is cheap, has no dependency, and has no path
  normalisation problem.
- **Real XML parsing, not character offsets.** The original sliced `line[11:-8]` and took
  `lines[3:-2]`, so any reformatting by the game would have silently produced garbage times.
- **Backups before every write.** Overwriting the game's file is the normal workflow, so it has to
  be non-destructive by default.

## Testing against real data

The user's actual game file lives at
`%USERPROFILE%\AppData\LocalLow\Isto\Get To Work\best_split_times.txt`. `tests/conftest.py` contains
a byte-exact copy as a fixture. **Never write to the real file when testing** — copy it to a temp
directory and point `--game-file` at the copy.
