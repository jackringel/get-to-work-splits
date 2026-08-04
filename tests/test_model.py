from __future__ import annotations

import pytest

from gtw_splits.model import (
    Comparison,
    Run,
    SplitsDatabase,
    format_progress,
    format_time,
)

from .conftest import REAL_TIMES, REAL_UNFINISHED_TIMES


def db(split_count=3):
    return SplitsDatabase(split_count=split_count)


def ingest(database, times):
    return database.ingest(Run.from_game_times(list(times)))


# -- unfinished-run handling ----------------------------------------------


def test_every_written_segment_is_kept():
    """Regression: the last written segment used to be discarded as partial.

    The game writes a segment only once you finish it, so an unfinished run
    contributes all of its written times -- dropping the last one silently
    lost a completed split from every save made mid-run.
    """
    run = Run.from_game_times([10.0, 10.0, 3.0, 0.0, 0.0])
    assert run.segments == (10.0, 10.0, 3.0, 0.0, 0.0)
    assert run.recorded_prefix == 3
    assert not run.is_complete


def test_times_after_a_gap_are_discarded():
    run = Run.from_game_times([10.0, 0.0, 5.0])
    assert run.segments == (10.0, 0.0, 0.0)
    assert run.recorded_prefix == 1


def test_real_unfinished_save_keeps_every_completed_section():
    """Pinned to a real capture: four completed sections, four times kept."""
    database = SplitsDatabase(split_count=11)
    ingest(database, REAL_UNFINISHED_TIMES)
    assert database.best_segments == pytest.approx(REAL_UNFINISHED_TIMES)
    assert database.total_for(Comparison.PB) == 0.0


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


def test_incomplete_run_sets_a_provisional_pb_with_no_total():
    """The slot fills with the best attempt so far, but it is not a finish."""
    database = db()
    result = ingest(database, [1.0, 1.0, 0.0])
    assert result.is_new_pb and result.pb_is_partial
    assert database.pb == pytest.approx([1.0, 1.0, 0.0])
    assert database.total_for(Comparison.PB) == 0.0
    assert database.progress_for(Comparison.PB) == (pytest.approx(2.0), 2)


def test_partial_run_never_displaces_a_complete_pb():
    """The whole point of ranking by reach first: a finish outranks any partial."""
    database = db()
    ingest(database, [10.0, 10.0, 10.0])
    result = ingest(database, [1.0, 1.0, 0.0])  # far faster, but never finished
    assert not result.is_new_pb
    assert database.pb == pytest.approx([10.0, 10.0, 10.0])


def test_further_attempt_beats_a_faster_shorter_one():
    database = db()
    ingest(database, [1.0, 0.0, 0.0])
    result = ingest(database, [50.0, 50.0, 0.0])
    assert result.is_new_pb and result.pb_is_partial
    assert result.pb_delta == 0.0  # different reaches are not comparable
    assert database.progress_for(Comparison.PB) == (pytest.approx(100.0), 2)


def test_faster_attempt_to_the_same_reach_wins_with_a_delta():
    database = db()
    ingest(database, [10.0, 10.0, 0.0])
    result = ingest(database, [8.0, 9.0, 0.0])
    assert result.is_new_pb and result.pb_delta == pytest.approx(-3.0)
    assert database.pb == pytest.approx([8.0, 9.0, 0.0])


def test_first_complete_run_supersedes_the_provisional_pb():
    database = db()
    ingest(database, [1.0, 1.0, 0.0])
    result = ingest(database, [10.0, 10.0, 10.0])
    assert result.is_new_pb and not result.pb_is_partial
    assert database.total_for(Comparison.PB) == pytest.approx(30.0)


# -- best segments --------------------------------------------------------


def test_best_segments_take_minimum_per_index():
    database = db()
    ingest(database, [10.0, 20.0, 30.0])
    ingest(database, [30.0, 5.0, 40.0])
    assert database.best_segments == pytest.approx([10.0, 5.0, 30.0])


def test_best_segments_ignore_missing_times():
    database = db()
    ingest(database, [10.0, 20.0, 30.0])
    # Died during split 2, so splits 0 and 1 count and the last does not.
    ingest(database, [4.0, 5.0, 0.0])
    assert database.best_segments == pytest.approx([4.0, 5.0, 30.0])


def test_run_abandoned_after_first_split_still_records_it():
    database = db()
    ingest(database, [10.0, 20.0, 30.0])
    ingest(database, [4.0, 0.0, 0.0])  # split 0 finished, then the run ended
    assert database.best_segments == pytest.approx([4.0, 20.0, 30.0])


# -- best exits (the logic that was broken) -------------------------------


def test_best_exits_take_minimum_cumulative():
    database = db()
    ingest(database, [10.0, 10.0, 10.0])  # cumulative 10 / 20 / 30
    ingest(database, [5.0, 20.0, 5.0])  # cumulative  5 / 25 / 30
    assert database.best_exit_cumulative == pytest.approx([5.0, 20.0, 30.0])
    assert database.best_exits == pytest.approx([5.0, 15.0, 10.0])


def test_partial_run_does_not_poison_later_exits():
    """Regression: summing deltas across a gap produced fake-fast cumulatives.

    A run that stopped after split 1 must improve the exits it reached and
    leave the later ones untouched, rather than carrying its deltas across
    the gap and making those look impossibly fast.
    """
    database = db()
    ingest(database, [10.0, 10.0, 10.0])
    ingest(database, [1.0, 1.0, 0.0])  # cumulative 1 / 2 / --
    assert database.best_exit_cumulative == pytest.approx([1.0, 2.0, 30.0])
    assert database.best_exits == pytest.approx([1.0, 1.0, 28.0])


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


def test_best_exit_total_equals_pb_total():
    """The best exit from the *final* level is, by definition, the PB.

    Both are the minimum total over complete runs, so they are the same
    number -- any divergence means one of them is being fed wrong data.
    """
    database = db()
    ingest(database, [10.0, 10.0, 10.0])
    ingest(database, [12.0, 8.0, 9.0])  # faster overall, different shape
    ingest(database, [1.0, 1.0, 0.0])  # abandoned; must not affect either
    assert database.total_for(Comparison.BEST_EXITS) == pytest.approx(
        database.total_for(Comparison.PB)
    )


def test_intermediate_best_exits_may_beat_pb():
    """Only the *final* exit is pinned to the PB; earlier ones can be faster."""
    database = db()
    ingest(database, [10.0, 10.0, 10.0])
    ingest(database, [1.0, 50.0, 1.0])
    assert database.best_exit_cumulative[0] == pytest.approx(1.0)
    assert database.best_exit_cumulative[0] < database.pb[0]


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


def test_progress_is_formatted_with_its_reach_until_complete():
    assert format_progress(0.0, 0, 11) == "--"
    assert format_progress(141.9, 2, 11) == "2:21.90  (2/11)"
    assert format_progress(141.9, 11, 11) == "2:21.90"


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
