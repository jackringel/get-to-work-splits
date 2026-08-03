"""Reporting which build of the tool is actually running.

The install is editable, so the code that runs is whatever is in the checkout
-- but only for a process started after an edit. A window opened beforehand
keeps running the old code from memory however many times the files change,
which is exactly how a fixed bug went on corrupting saves for two hours. Naming
the commit in the window title turns that from something you have to remember
to check into something you can see.
"""

from __future__ import annotations

import subprocess
from functools import cache
from pathlib import Path

from . import __version__

#: Long enough to identify a commit, short enough for a title bar.
ABBREV = 7


@cache
def source_revision() -> str | None:
    """Short commit of the checkout this module was imported from.

    ``None`` when it was not imported from a git checkout -- an ordinary
    install has no revision to report and does not drift the way an editable
    one does. A dirty tree is marked, since uncommitted edits are the case
    where "which commit" answers the wrong question.
    """
    repository = Path(__file__).resolve().parents[2]
    if not (repository / ".git").exists():
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), "describe", "--always", "--dirty", f"--abbrev={ABBREV}"],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None  # no git on PATH, or it took too long to be worth waiting for
    return completed.stdout.strip() or None


def version_string() -> str:
    """``1.0.0 (9d83c0e)`` in a checkout, plain ``1.0.0`` otherwise."""
    revision = source_revision()
    return f"{__version__} ({revision})" if revision else __version__
