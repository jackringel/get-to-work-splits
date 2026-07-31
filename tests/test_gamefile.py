from __future__ import annotations

import pytest

from gtw_splits import gamefile

from .conftest import REAL_GAME_FILE, REAL_TIMES


def test_parses_real_game_file(real_game_file):
    assert gamefile.read_times(real_game_file) == REAL_TIMES


def test_render_round_trips_real_file_byte_for_byte():
    assert gamefile.render_times(REAL_TIMES) == REAL_GAME_FILE


def test_render_preserves_float_precision():
    text = gamefile.render_times([68.0, 24.639858199999992])
    assert "<float>68.0</float>" in text
    assert "<float>24.639858199999992</float>" in text


def test_parse_tolerates_reindented_file():
    """Layout changes must not break parsing the way offset slicing did."""
    text = REAL_GAME_FILE.replace("    <float>", "\t<float>")
    assert gamefile.parse_times(text) == REAL_TIMES


def test_parse_rejects_truncated_file():
    with pytest.raises(gamefile.GameFileError):
        gamefile.parse_times(REAL_GAME_FILE[: len(REAL_GAME_FILE) // 2])


def test_parse_rejects_file_without_times():
    with pytest.raises(gamefile.GameFileError):
        gamefile.parse_times('<?xml version="1.0"?><SpeedrunTimerData />')


def test_write_is_atomic_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "best_split_times.txt"
    gamefile.write_times(path, REAL_TIMES)
    assert gamefile.read_times(path) == REAL_TIMES
    assert list(tmp_path.glob("*.tmp")) == []


def test_backup_copies_existing_file(real_game_file, tmp_path):
    backup_dir = tmp_path / "backups"
    backup = gamefile.backup_file(real_game_file, backup_dir)
    assert backup is not None
    assert backup.read_text(encoding="utf-8") == REAL_GAME_FILE


def test_backup_of_missing_file_returns_none(tmp_path):
    assert gamefile.backup_file(tmp_path / "nope.txt", tmp_path / "backups") is None
