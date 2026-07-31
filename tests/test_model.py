from __future__ import annotations

import pytest

from gtw_splits.model import Comparison, Run, SplitsDatabase, format_time

from .conftest import REAL_TIMES


def db(split_count=3):
    return SplitsDatabase(split_count=split_count)


def ingest(database, times):
    return database.ingest(Run.from_game_times(list(times)))


# -- partial-run handling -------------------------------------------------


def test_in_progress_segment_is_discarded():
    """The game saves the split you are on; that partial time must not count."""
    run = Run.from_game_times([10.0, 10.0, 3.0, 0.0, 0.0])
    assert run.segments == (10.0, 10.0, 0.0, 0.0, 0.0)
    assert run.recorded_prefix == 2
    assert not run.is_complete


def test_run_with_no_progress_is_empty_not_wrapped():
    """A leading gap must not wipe the *last* split via negative indexing."""
    run = Run.from_game_times([0.0, 5.0, 5.0])
    assert run.segments == (0.0, 0.0, 0.0)
    assert run.recorded_prefix == 0


def test_empty_run_is_ignored():
    database = db()
    result = ingest(database, [0.0, 0.0, 0.0])
    assert not result.changed
    assert result.ignored_reason


def test_complete_run_has_total():
    run = Run.from_game_times([1.0, 2.0, 3.0])
    assert run.is_complete
    assert run.total == pytest.approx(6.0)


# -- personal best --------------------------------------------------------


def test_pb_set_by_first_complete_run():
    database = db()
    result = ingest(database, [10.0, 10.0, 10.0])
    assert result.is_new_pb
    assert database.total_for(Comparison.PB) == pytest.approx(30.0)


def test_pb_not_replaced_by_slower_run():
    database = db()
    ingest(database, [10.0, 10.0, 10.0])
    result = ingest(database, [11.0, 11.0, 11.0])
    assert not result.is_new_pb
    assert database.total_for(Comparison.PB) == pytest.approx(30.0)


def test_pb_replaced_by_faster_run_with_delta():
    database = db()
    ingest(database, [10.0, 10.0, 10.0])
    result = ingest(database, [9.0, 9.0, 9.0])
    assert result.is_new_pb
    assert result.pb_delta == pytest.approx(-3.0)


def test_incomplete_run_never_sets_pb():
    database = db()
    ingest(database, [1.0, 1.0, 0.0])
    assert database.total_for(Comparison.PB) == 0.0


# -- best segments --------------------------------------------------------


def test_best_segments_take_minimum_per_index():
    database = db()
    ingest(database, [10.0, 20.0, 30.0])
    ingest(database, [30.0, 5.0, 40.0])
    assert database.best_segments == pytest.approx([10.0, 5.0, 30.0])


def test_best_segments_ignore_missing_times():
    database = db()
    ingest(database, [10.0, 20.0, 30.0])
    # Died during split 1, so split 0 counts and the rest do not.
    ingest(database, [4.0, 5.0, 0.0])
    assert database.best_segments == pytest.approx([4.0, 20.0, 30.0])


def test_run_abandoned_in_first_split_records_nothing():
    database = db()
    ingest(database, [10.0, 20.0, 30.0])
    ingest(database, [4.0, 0.0, 0.0])  # 4.0 was still in progress
    assert database.best_segments == pytest.approx([10.0, 20.0, 30.0])


# -- best exits (the logic that was broken) -------------------------------


def test_best_exits_take_minimum_cumulative():
    database = db()
    ingest(database, [10.0, 10.0, 10.0])  # cumulative 10 / 20 / 30
    ingest(database, [5.0, 20.0, 5.0])  # cumulative  5 / 25 / 30
    assert database.best_exit_cumulative == pytest.approx([5.0, 20.0, 30.0])
    assert database.best_exits == pytest.approx([5.0, 15.0, 10.0])


def test_partial_run_does_not_poison_later_exits():
    """Regression: summing deltas across a gap produced fake-fast cumulatives.

    A run that only reached split 1 must improve that exit and leave the
    later ones untouched, rather than making them look impossibly fast.
    """
    database = db()
    ingest(database, [10.0, 10.0, 10.0])
    ingest(database, [1.0, 1.0, 0.0])  # trims to [1, 0, 0]
    assert database.best_exit_cumulative == pytest.approx([1.0, 20.0, 30.0])
    assert database.best_exits == pytest.approx([1.0, 19.0, 10.0])


def test_best_exit_deltas_are_never_negative():
    database = db(4)
    runs = [
        [20.0, 20.0, 20.0, 20.0],
        [1.0, 50.0, 1.0, 50.0],
        [50.0, 1.0, 50.0, 1.0],
        [5.0, 5.0, 0.0, 0.0],
        [30.0, 30.0, 30.0, 1.0],
    ]
    for times in runs:
        ingest(database, times)
        cumulative = [c for c in database.best_exit_cumulative if c > 0]
        assert cumulative == sorted(cumulative), "cumulative exits must not decrease"
        assert all(d >= 0 for d in database.best_exits)


def test_best_exits_property_returns_a_fresh_list():
    """Regression: the old code aliased the stored list and mutated it."""
    database = db()
    ingest(database, [10.0, 10.0, 10.0])
    first = database.best_exits
    first[0] = 999.0
    assert database.best_exits[0] == pytest.approx(10.0)


def test_best_exits_total_matches_last_cumulative():
    database = db()
    ingest(database, [10.0, 10.0, 10.0])
    ingest(database, [5.0, 20.0, 4.0])
    assert database.total_for(Comparison.BEST_EXITS) == pytest.approx(
        database.best_exit_cumulative[-1]
    )


def test_best_exits_never_slower_than_pb():
    database = db()
    ingest(database, [10.0, 10.0, 10.0])
    ingest(database, [12.0, 8.0, 9.0])
    assert database.total_for(Comparison.BEST_EXITS) <= database.total_for(Comparison.PB)


# -- comparison selection -------------------------------------------------


def test_segments_for_each_comparison_has_right_length():
    database = db()
    ingest(database, [10.0, 10.0, 10.0])
    for comparison in Comparison:
        assert len(database.segments_for(comparison)) == 3


def test_incomplete_comparison_reports_zero_total():
    database = db()
    ingest(database, [10.0, 0.0, 0.0])
    assert database.total_for(Comparison.PB) == 0.0


def test_resizes_to_match_game_file():
    database = db(3)
    ingest(database, REAL_TIMES)
    assert database.split_count == 11
    assert database.total_for(Comparison.PB) == pytest.approx(sum(REAL_TIMES))


def test_real_file_round_trips_through_pb():
    database = SplitsDatabase(split_count=11)
    ingest(database, REAL_TIMES)
    assert database.segments_for(Comparison.PB) == pytest.approx(REAL_TIMES)
    assert database.segments_for(Comparison.BEST_EXITS) == pytest.approx(REAL_TIMES)


# -- formatting -----------------------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0.0, "--"), (9.0, "0:09.00"), (72.10753, "1:12.11"), (3661.5, "1:01:01.50")],
)
def test_format_time(seconds, expected):
    assert format_time(seconds) == expected
