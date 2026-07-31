from __future__ import annotations

import pytest

from gtw_splits import store
from gtw_splits.model import Comparison, SplitsDatabase

from .conftest import REAL_TIMES


def test_round_trips_database(data_root):
    database = SplitsDatabase(
        split_count=11,
        pb=list(REAL_TIMES),
        best_segments=list(REAL_TIMES),
        best_exit_cumulative=[sum(REAL_TIMES[: i + 1]) for i in range(11)],
    )
    store.save_database(database, data_root)
    loaded = store.load_database(data_root)
    assert loaded.pb == pytest.approx(REAL_TIMES)
    assert loaded.total_for(Comparison.PB) == pytest.approx(sum(REAL_TIMES))


def test_missing_database_returns_empty(data_root):
    assert store.load_database(data_root).total_for(Comparison.PB) == 0.0


def test_corrupt_database_falls_back_to_empty(data_root):
    store.database_path(data_root).parent.mkdir(parents=True, exist_ok=True)
    store.database_path(data_root).write_text("{not json", encoding="utf-8")
    assert store.load_database(data_root).total_for(Comparison.PB) == 0.0


def test_migrates_legacy_csv(tmp_path, data_root):
    """Legacy rows are pb,best_segment,best_exit deltas with 0.0 for no data."""
    legacy = tmp_path / "splits.txt"
    legacy.write_text("10.0,10.0,10.0\n20.0,15.0,20.0\n30.0,25.0,30.0", encoding="utf-8")

    database = store.migrate_legacy_csv(legacy, data_root)

    assert database is not None
    assert database.split_count == 3
    assert database.pb == pytest.approx([10.0, 20.0, 30.0])
    assert database.best_segments == pytest.approx([10.0, 15.0, 25.0])
    # Legacy best-exit deltas become cumulative time-since-start, with the
    # final exit pinned to the PB total.
    assert database.best_exit_cumulative == pytest.approx([10.0, 30.0, 60.0])
    assert store.load_database(data_root).split_count == 3


def test_migration_pins_final_exit_to_pb(tmp_path, data_root):
    """Legacy best-exit arithmetic could beat the PB, which is impossible."""
    legacy = tmp_path / "splits.txt"
    # PB totals 60; the legacy exit column accumulates to an impossible 30.
    legacy.write_text("10.0,10.0,5.0\n20.0,15.0,10.0\n30.0,25.0,15.0", encoding="utf-8")

    database = store.migrate_legacy_csv(legacy, data_root)

    assert database is not None
    assert database.total_for(Comparison.BEST_EXITS) == pytest.approx(
        database.total_for(Comparison.PB)
    )


def test_migration_makes_exits_non_decreasing(tmp_path, data_root):
    legacy = tmp_path / "splits.txt"
    # A negative legacy delta would make cumulative exits go backwards.
    legacy.write_text("10.0,10.0,10.0\n20.0,15.0,-5.0\n30.0,25.0,0.0", encoding="utf-8")

    database = store.migrate_legacy_csv(legacy, data_root)

    assert database is not None
    recorded = [v for v in database.best_exit_cumulative if v > 0]
    assert recorded == sorted(recorded)
    assert all(d >= 0 for d in database.best_exits)


def test_migrate_missing_file_returns_none(tmp_path, data_root):
    assert store.migrate_legacy_csv(tmp_path / "absent.txt", data_root) is None


def test_migrate_malformed_csv_returns_none(tmp_path, data_root):
    legacy = tmp_path / "splits.txt"
    legacy.write_text("not,enough\n", encoding="utf-8")
    assert store.migrate_legacy_csv(legacy, data_root) is None


def test_settings_round_trip(data_root):
    store.save_settings({"game_file": "C:/x/best_split_times.txt"}, data_root)
    assert store.load_settings(data_root)["game_file"] == "C:/x/best_split_times.txt"
