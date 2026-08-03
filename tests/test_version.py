from __future__ import annotations

import gtw_splits
from gtw_splits.version import source_revision, version_string


def test_version_string_always_names_the_package_version():
    assert version_string().startswith(gtw_splits.__version__)


def test_version_string_names_the_commit_when_run_from_a_checkout():
    """The point of the display: identify the code a process is running.

    Skipped rather than failed off a checkout -- an installed copy has no
    revision to report, and that is the documented behaviour.
    """
    revision = source_revision()
    if revision is None:
        return
    assert revision in version_string()
    assert revision.strip() == revision and " " not in revision
