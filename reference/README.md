# Reference files

Real files produced by Get To Work, kept locally for working out formats. Everything in this
directory except this README and the `.gitignore` is ignored by git — these are your own save
files, they are large and noisy, and nothing in the test suite may depend on them.

**Tests must not read from here.** Anything a test needs has to be committed, or the suite breaks
for anyone else. `tests/conftest.py` holds a byte-exact copy of a real `best_split_times.txt` for
exactly that reason. If you find a new format worth pinning, copy a small sample into a fixture
rather than pointing a test at this directory.

## Capturing

The game's data lives in the standard Unity persistent-data path:

```
%USERPROFILE%\AppData\LocalLow\Isto\Get To Work\
```

To snapshot the whole thing (PowerShell, from the repo root):

```powershell
$src = "$env:USERPROFILE\AppData\LocalLow\Isto\Get To Work"
Copy-Item -Recurse -Force $src\* reference\
```

Or just the splits file, which is the only one the tool touches:

```powershell
Copy-Item "$env:USERPROFILE\AppData\LocalLow\Isto\Get To Work\best_split_times.txt" reference\
```

Copying is safe — the tool never writes back here.

## What's in there

| File | Why it's interesting |
| --- | --- |
| `best_split_times.txt` | The only file this tool reads or writes. .NET `XmlSerializer` output: one `<float>` per split, per-segment durations, `0.0` for no time. Note there is no trailing newline — `gamefile.render_times` reproduces that exactly. |
| `SaveSlot*/gamestate_data.xml` | Overall progress for a save slot. Small; a good starting point for anything needing run context. |
| `SaveSlot*/level_data.xml` | Per-level state. The largest of the save files. |
| `SaveSlot*/player_data.xml` | Player position, inventory, and similar. |
| `SaveSlot*/doinkler_level_data.xml` | Present in some slots only. |
| `GTWCustomControlMap.xml` | Keybindings. Would matter if the tool ever grew a hotkey to swap comparisons without alt-tabbing. |
| `Player.log` / `Player-prev.log` | Unity log from the last two sessions. Useful for confirming class and scene names if the splits format ever changes, or for spotting when the game writes its splits. |

## Splits format

Verified against a real file, 11 splits in the current game version — though nothing in the code
hardcodes that count:

```xml
<?xml version="1.0" encoding="utf-8"?>
<SpeedrunTimerData xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <times>
    <float>72.10753</float>
    <float>68.0</float>
    ...
  </times>
</SpeedrunTimerData>
```

The game writes the split you are *currently* on when you save, so the last recorded segment of an
unfinished run is a partial time. See `Run.from_game_times` in `src/gtw_splits/model.py`.
