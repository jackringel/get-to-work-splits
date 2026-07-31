# Get To Work Splits

Better split comparisons for the in-game speedrun timer in
[Get To Work](https://store.steampowered.com/app/2706170/).

The game's timer only keeps **one** saved set of splits — pressing "save splits" overwrites whatever
was there. That's fine for chasing a PB, but it means you can't also keep best segments, or see how
your best exit out of each level compares.

This tool turns that one button into a save-everything button. It watches the game's splits file and
folds every saved run into three comparisons; before a run, you pick which one to load back into the
game.

| Comparison | What it holds |
| --- | --- |
| **Personal Best** | The splits from the run that *finished* fastest. |
| **Best Segments** | The fastest individual time for each split, across all runs. |
| **Best Exits** | The fastest time-since-start you've ever left each level. |

## Install

Requires Python 3.10+. There are no other dependencies.

```
pip install git+https://github.com/jackringel/get-to-work-splits
```

Or, with [pipx](https://pipx.pypa.io/) so it lands in its own environment:

```
pipx install git+https://github.com/jackringel/get-to-work-splits
```

## Use

```
gtw-splits
```

That's it — it finds your save folder automatically and opens a window:

```
┌─ Get To Work Splits ─────────────┐
│ ...\Isto\Get To Work\best_spl... │
│ New PB! -2.41s                   │
│ Recorded from your last save.    │
│                                  │
│ ┌ Compare against ─────────────┐ │
│ │ ( ) Personal Best   24:02.45 │ │
│ │ (•) Best Segments   23:17.71 │ │
│ │ ( ) Best Exits      23:44.09 │ │
│ └──────────────────────────────┘ │
│                 [ Load into game]│
└──────────────────────────────────┘
```

Leave it open while you play. Hit "save splits" in game after every attempt and all three
comparisons stay up to date — including after runs you didn't finish. When you want to race a
different comparison, pick it and press **Load into game**.

Unlike the old two-script setup, recording and loading happen in the same program and can't
interfere with each other, so there's nothing to start and stop between runs.

### Command line

For headless use or scripting:

```
gtw-splits status                  # show the three comparisons
gtw-splits watch                   # record saved runs, no GUI
gtw-splits load best-segments      # write a comparison into the game
gtw-splits load pb
gtw-splits load best-exits
```

Add `--game-file <path>` if auto-detection can't find your install.

### Upgrading from the old scripts

The previous version kept a `splits.txt` next to the scripts. Import it once:

```
gtw-splits import-legacy path/to/splits.txt
```

Best-exit times are recalculated during the import, because the old column was produced by
arithmetic that summed across gaps in unfinished runs and could record exits faster than anything
actually run.

## Where things are stored

- **Game splits:** `%USERPROFILE%\AppData\LocalLow\Isto\Get To Work\best_split_times.txt`
- **Your comparisons:** `%LOCALAPPDATA%\gtw-splits\splits.json`
- **Backups:** `%LOCALAPPDATA%\gtw-splits\backups\` — the game's file is snapshotted every time this
  tool overwrites it, so a mis-click can't lose your splits. The 20 most recent are kept.

Set `GTW_SPLITS_HOME` to relocate the tool's own data.

## Notes

- Times are per-segment durations. `0.0` means "no time recorded".
- The game writes the split you're *currently* on when you save, so that partial time is discarded
  along with everything after it — an abandoned run still contributes its completed splits to best
  segments and best exits without polluting them.
- Loading a comparison overwrites the game's splits file. That's the intended workflow (your data
  lives in `splits.json`), and a backup is taken first either way.

## Development

```
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
.venv\Scripts\python -m ruff check src tests
```

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
