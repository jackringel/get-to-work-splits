from __future__ import annotations

import pytest

from gtw_splits import gamefile, store
from gtw_splits.model import Comparison
from gtw_splits.tracker import SplitsTracker

from .conftest import REAL_TIMES


def test_ingests_current_file(real_game_file, data_root):
    tracker = SplitsTracker(real_game_file, root=data_root)
    result = tracker.ingest_current_file()
    assert result.is_new_pb
    assert tracker.database.total_for(Comparison.PB) == pytest.approx(sum(REAL_TIMES))


def test_poll_detects_a_new_save(real_game_file, data_root):
    tracker = SplitsTracker(real_game_file, root=data_root)
    tracker.ingest_current_file()

    faster = [t * 0.9 for t in REAL_TIMES]
    gamefile.write_times(real_game_file, faster)
    result = tracker.poll()

    assert result is not None
    assert result.is_new_pb


def test_poll_ignores_our_own_write(real_game_file, data_root):
    """Loading a comparison must not be read back in as a new attempt.

    This is what lets watching and loading run at the same time; the original
    two scripts had to be run separately because of it.
    """
    tracker = SplitsTracker(real_game_file, root=data_root)
    tracker.ingest_current_file()
    before = list(tracker.database.best_segments)

    tracker.load_into_game(Comparison.BEST_SEGMENTS)

    assert tracker.poll() is None
    assert tracker.database.best_segments == pytest.approx(before)


def test_poll_returns_none_when_unchanged(real_game_file, data_root):
    tracker = SplitsTracker(real_game_file, root=data_root)
    tracker.ingest_current_file()
    assert tracker.poll() is None


def test_load_writes_comparison_and_backs_up(real_game_file, data_root):
    tracker = SplitsTracker(real_game_file, root=data_root)
    tracker.ingest_current_file()

    backup = tracker.load_into_game(Comparison.PB)

    assert backup is not None and backup.is_file()
    assert gamefile.read_times(real_game_file) == pytest.approx(REAL_TIMES)


def test_load_persists_across_restart(real_game_file, data_root):
    tracker = SplitsTracker(real_game_file, root=data_root)
    tracker.ingest_current_file()

    reopened = SplitsTracker(real_game_file, root=data_root)
    assert reopened.database.total_for(Comparison.PB) == pytest.approx(sum(REAL_TIMES))


def test_load_rejects_missing_comparison(tmp_path, data_root):
    tracker = SplitsTracker(tmp_path / "best_split_times.txt", root=data_root)
    tracker.database.resize(0)
    with pytest.raises(ValueError):
        tracker.load_into_game(Comparison.PB)


def test_prune_backups_keeps_newest(real_game_file, data_root):
    tracker = SplitsTracker(real_game_file, root=data_root)
    tracker.ingest_current_file()
    for _ in range(5):
        gamefile.backup_file(real_game_file, store.backup_dir(data_root))
    store.prune_backups(data_root, keep=2)
    assert len(list(store.backup_dir(data_root).glob("*.txt"))) <= 2
