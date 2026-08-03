# Get To Work Splits

Better split comparisons for the in-game speedrun timer in
[Get To Work](https://store.steampowered.com/app/2706170/).

The game's timer only keeps **one** saved set of splits; pressing "save splits" overwrites whatever
was there. You can hold a PB, but you can't also compare against best segments/SoB or best exits.

This tool turns "save splits" into a save-everything button. It watches the game's splits file and
folds every saved run into three comparisons; before a run, you pick which one to load back into the
game.

| Comparison | What it holds |
| --- | --- |
| **Personal Best** | The splits from the run that *finished* fastest. |
| **Best Segments** | The fastest individual time for each split, across all runs. |
| **Best Exits** | The fastest time you've left each level. |

## Install

Requires Python 3.10+. There are no other dependencies.

```
pip install git+https://github.com/jackringel/get-to-work-splits
```

Or, with [pipx](https://pipx.pypa.io/) so it lands in its own environment:

```
pipx install git+https://github.com/jackringel/get-to-work-splits
```

If `gtw-splits` comes back as "not recognized", pip installed it into a `Scripts` folder that isn't
on your PATH; pip says so in a yellow warning during install. Either use the module form, which
always works and takes the same arguments:

```
python -m gtw_splits
```

or add that folder to your PATH once and open a new terminal:

```powershell
$s = python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
$u = [Environment]::GetEnvironmentVariable('PATH','User')
if ($u -notlike "*$s*") { [Environment]::SetEnvironmentVariable('PATH', ($u.TrimEnd(';') + ';' + $s), 'User') }
```

## Use

```
gtw-splits
```

That's it; it finds your save folder automatically and opens a window:

```
┌─ Get To Work Splits -- 1.0.0 (9d83c0e) ─┐
│ ...\Isto\Get To Work\best_spl...        │
│ New PB! -2.41s                          │
│ Recorded from your last save.           │
│ [x] Record saved runs                   │
│                                         │
│ ┌ Compare against ─────────────┐        │
│ │ ( ) Personal Best   24:02.45 │        │
│ │ (•) Best Segments   23:17.71 │        │
│ │ ( ) Best Exits      24:02.45 │        │
│ └──────────────────────────────┘        │
│                        [ Load into game]│
└─────────────────────────────────────────┘
```

Best Exits always totals the same as your PB, which is correct rather than a
display glitch: your best exit from the *final* level is your PB. The two differ
at every split before the last, which is where the comparison earns its keep.

Leave it open while you play. Hit "save splits" in game after every attempt and all three
comparisons stay up to date, including after runs you didn't finish. When you want to race a
different comparison, pick it and press **Load into game**.

Unlike the old two-script setup, recording and loading happen in the same program and can't
interfere with each other, so there's nothing to start and stop between runs.

### Runs you don't want kept

Testing something, running a mod, or messing about with cheats? Untick **Record saved runs**. Saves
are still read and reported, but nothing goes into your comparisons, and loading still works — so
you can race against your real PB while the attempts themselves don't count. The setting is
remembered until you turn it back on, and a paused window says so instead of looking idle.

Nothing else can put times in: the only thing this tool reads is `best_split_times.txt`, and the
game only writes that when you save your splits. There's no way for a run you never saved to end up
in your comparisons.

### Which version is running

The window title carries the version and the commit it was started from, e.g. `1.0.0 (9d83c0e)`, or
`9d83c0e-dirty` with uncommitted edits in the checkout. `gtw-splits status` and `gtw-splits
--version` print the same thing.

This matters more than it looks. The install is editable, so the code that runs is whatever is in
your checkout — but only for a process started *after* you changed it. A window left open keeps
running the code it was launched with no matter what you edit, pull, or commit. If the title doesn't
name the commit you expect, close the window and reopen it; the GUI runs as `pythonw.exe`, so check
for that name and not just `python.exe`.

### Command line

For headless use or scripting:

```
gtw-splits status                  # version, paths, and the three comparisons
gtw-splits watch                   # record saved runs, no GUI
gtw-splits load best-segments      # write a comparison into the game
gtw-splits load pb
gtw-splits load best-exits
gtw-splits record off              # stop keeping saved runs (and `record on`)
gtw-splits load pb --no-record     # or just this once; `watch` takes it too
gtw-splits --version
```

Add `--game-file <path>` if auto-detection can't find your install.

### Upgrading from the old scripts

The previous version kept a `splits.txt` next to the scripts. Import it once:

```
gtw-splits import-legacy path/to/splits.txt
```

Best-exit times are recalculated during the import, because the old column was produced by
arithmetic that summed across gaps in unfinished runs and could record exits faster than anything
actually run. An exit time nothing can beat would stick permanently, so the import forces cumulative
exits to increase and pins the final one to your PB total. Imported intermediate exits may still be
slightly optimistic; they correct themselves as you run.

## Where things are stored

- **Game splits:** `%USERPROFILE%\AppData\LocalLow\Isto\Get To Work\best_split_times.txt`
- **Your comparisons:** `%LOCALAPPDATA%\gtw-splits\splits.json`
- **Backups:** `%LOCALAPPDATA%\gtw-splits\backups\` - the game's file is snapshotted every time this
  tool overwrites it, so a mis-click can't lose your splits. The 20 most recent are kept.
- **Settings:** `%LOCALAPPDATA%\gtw-splits\settings.json` - the game file path and whether recording
  is on. `last_write.txt` next to it is a copy of the last comparison written into the game, so a
  later session can tell that file apart from a run you saved.

Set `GTW_SPLITS_HOME` to relocate the tool's own data.

## Notes

- Times are per-segment durations. `0.0` means "no time recorded".
- The game writes a split only once you *finish* it, so saving partway through a run records every
  section you completed and nothing for the one you're on. An abandoned run still contributes all of
  its completed splits to best segments and best exits.
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
