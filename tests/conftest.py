from __future__ import annotations

import pytest

#: Byte-for-byte copy of a real best_split_times.txt written by the game,
#: including the round-tripped float precision and absent trailing newline.
REAL_GAME_FILE = """<?xml version="1.0" encoding="utf-8"?>
<SpeedrunTimerData xmlns:xsd="http://www.w3.org/2001/XMLSchema" \
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <times>
    <float>72.10753</float>
    <float>68.0</float>
    <float>24.639858199999992</float>
    <float>165.0</float>
    <float>146.872525</float>
    <float>88.37282999999996</float>
    <float>73.46070000000009</float>
    <float>289.0</float>
    <float>160.0</float>
    <float>346.0</float>
    <float>9.0</float>
  </times>
</SpeedrunTimerData>"""

REAL_TIMES = [
    72.10753,
    68.0,
    24.639858199999992,
    165.0,
    146.872525,
    88.37282999999996,
    73.46070000000009,
    289.0,
    160.0,
    346.0,
    9.0,
]


#: A real save made partway through a run. The game's log had recorded four
#: completed sections (Applying For Jobs / Your First Interview / Warehouse
#: Trainee / Warehouse Worker) and the file holds exactly those four times --
#: the section in progress at save time is absent from it entirely.
REAL_UNFINISHED_TIMES = [84.16977, 69.97287, 22.8181782, 274.35376] + [0.0] * 7


@pytest.fixture
def real_game_file(tmp_path):
    path = tmp_path / "best_split_times.txt"
    path.write_text(REAL_GAME_FILE, encoding="utf-8", newline="")
    return path


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / "appdata"
    root.mkdir()
    return root
