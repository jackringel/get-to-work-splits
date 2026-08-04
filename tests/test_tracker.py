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


def test_first_poll_ingests_a_run_saved_before_startup(real_game_file, data_root):
    """A run already on disk when the tool starts must still be recorded.

    Seeding the fingerprint at construction meant the tool only ever saw the
    *next* save, so starting it after a run silently threw that run away.
    """
    tracker = SplitsTracker(real_game_file, root=data_root)

    result = tracker.poll()

    assert result is not None and result.is_new_pb
    assert tracker.database.total_for(Comparison.PB) == pytest.approx(sum(REAL_TIMES))


def test_load_records_a_run_that_was_never_polled(real_game_file, data_root):
    """Loading must not destroy a save the watcher has not seen yet."""
    SplitsTracker(real_game_file, root=data_root).ingest_current_file()

    faster = [t * 0.9 for t in REAL_TIMES]
    gamefile.write_times(real_game_file, faster)  # the game saves a better run

    tracker = SplitsTracker(real_game_file, root=data_root)  # then the tool opens
    tracker.load_into_game(Comparison.PB)

    assert tracker.database.pb == pytest.approx(faster)
    assert gamefile.read_times(real_game_file) == pytest.approx(faster)


def test_a_loaded_comparison_is_not_ingested_after_restart(real_game_file, data_root):
    """The own-write guard has to survive the process that made the write.

    Best exits are faster than any single run, so ingesting an exported
    comparison as an attempt would install an unbeatable fake PB.
    """
    tracker = SplitsTracker(real_game_file, root=data_root)
    tracker.ingest_current_file()
    quicker_second_half = [t * 0.5 for t in REAL_TIMES[:5]] + REAL_TIMES[5:]
    gamefile.write_times(real_game_file, quicker_second_half)
    tracker.poll()
    tracker.load_into_game(Comparison.BEST_EXITS)

    reopened = SplitsTracker(real_game_file, root=data_root)
    before = list(reopened.database.pb)

    assert reopened.poll() is None
    assert reopened.database.pb == pytest.approx(before)


def test_a_second_instance_does_not_ingest_the_first_instances_write(
    real_game_file, data_root
):
    """Two open windows must not feed each other's comparisons back as runs.

    The in-memory guard only covers writes the *same* instance made, so a
    second window loading a comparison looked like a newly saved run to the
    first. Observed in the wild: a loaded best-exits series was recorded as an
    attempt and, reaching further than the PB of the day did, installed a PB no
    real run could beat.
    """
    watching = SplitsTracker(real_game_file, root=data_root)  # opened first
    watching.ingest_current_file()  # a complete run
    part_run = [t * 0.5 for t in REAL_TIMES[:4]] + [0.0] * 7
    gamefile.write_times(real_game_file, part_run)  # then a faster part-run
    watching.poll()

    loading = SplitsTracker(real_game_file, root=data_root)  # opened second
    pb_before = list(watching.database.pb)
    segments_before = list(watching.database.best_segments)

    loading.load_into_game(Comparison.BEST_EXITS)
    # Exits splice both runs, so the file now holds neither of them. Without a
    # real change on disk the poll below would return None for the wrong reason.
    assert gamefile.read_times(real_game_file) != pytest.approx(part_run)

    # The load-bearing assertion: a comparison is not an attempt, whoever wrote
    # it. What it would have gone on to corrupt depends on the data; that it is
    # read as a run at all is the bug.
    assert watching.poll() is None
    assert watching.database.pb == pytest.approx(pb_before)
    assert watching.database.best_segments == pytest.approx(segments_before)


def test_paused_recording_reads_a_save_without_keeping_it(real_game_file, data_root):
    """A modded or cheated attempt is still a save; only you can tell it apart."""
    tracker = SplitsTracker(real_game_file, root=data_root)
    tracker.set_recording(False)

    result = tracker.poll()

    assert result is not None and result.ignored_reason  # reported, not silent
    assert not result.changed
    assert tracker.database.total_for(Comparison.PB) == 0.0
    assert not store.database_path(data_root).is_file()


def test_paused_recording_survives_a_restart(real_game_file, data_root):
    SplitsTracker(real_game_file, root=data_root).set_recording(False)

    reopened = SplitsTracker(real_game_file, root=data_root)

    assert reopened.recording is False
    assert reopened.poll() is not None
    assert reopened.database.total_for(Comparison.PB) == 0.0


def test_paused_recording_still_loads_comparisons(real_game_file, data_root):
    tracker = SplitsTracker(real_game_file, root=data_root)
    tracker.ingest_current_file()
    tracker.set_recording(False)

    faster = [t * 0.9 for t in REAL_TIMES]
    gamefile.write_times(real_game_file, faster)
    tracker.load_into_game(Comparison.PB)

    assert tracker.database.pb == pytest.approx(REAL_TIMES)  # the faster run was ignored
    assert gamefile.read_times(real_game_file) == pytest.approx(REAL_TIMES)


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
