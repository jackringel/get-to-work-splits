"""Finding the game's save folder and the tool's own data folder.

Get To Work is a Unity game from Isto Inc., so its save data lives in the
standard Unity persistent-data path: ``AppData/LocalLow/Isto/Get To Work`` on
Windows, and the Proton/Wine equivalent under a Steam compatdata prefix on
Linux. Auto-detection removes the path prompt the original scripts required.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .gamefile import GAME_FILE_NAME

COMPANY = "Isto"
PRODUCT = "Get To Work"

#: Steam application id, used to locate the Proton prefix on Linux.
STEAM_APP_ID = "2706170"


def _windows_candidates() -> list[Path]:
    local_low = Path.home() / "AppData" / "LocalLow"
    appdata = os.environ.get("APPDATA")
    candidates = [local_low / COMPANY / PRODUCT]
    if appdata:
        candidates.append(Path(appdata).parent / "LocalLow" / COMPANY / PRODUCT)
    return candidates


def _proton_candidates() -> list[Path]:
    """Wine/Proton prefixes where a Windows build stores its LocalLow data."""
    suffix = Path("pfx/drive_c/users/steamuser/AppData/LocalLow") / COMPANY / PRODUCT
    roots = [
        Path.home() / ".steam/steam/steamapps/compatdata",
        Path.home() / ".local/share/Steam/steamapps/compatdata",
        Path.home() / ".var/app/com.valvesoftware.Steam/data/Steam/steamapps/compatdata",
    ]
    candidates = [root / STEAM_APP_ID / suffix for root in roots]
    candidates.append(Path.home() / f".wine/drive_c/users/{os.environ.get('USER', 'user')}"
                     f"/AppData/LocalLow/{COMPANY}/{PRODUCT}")
    return candidates


def _macos_candidates() -> list[Path]:
    return [Path.home() / "Library" / "Application Support" / COMPANY / PRODUCT]


def candidate_save_dirs() -> list[Path]:
    """Every place the game's save folder might live on this platform."""
    if sys.platform == "win32":
        return _windows_candidates()
    if sys.platform == "darwin":
        return _macos_candidates()
    return _proton_candidates()


def find_game_file() -> Path | None:
    """Locate ``best_split_times.txt``, or ``None`` if it cannot be found."""
    for directory in candidate_save_dirs():
        candidate = directory / GAME_FILE_NAME
        if candidate.is_file():
            return candidate
    # The save folder may exist before the file does (splits never saved yet).
    for directory in candidate_save_dirs():
        if directory.is_dir():
            return directory / GAME_FILE_NAME
    return None


def data_dir() -> Path:
    """Where this tool keeps its database and backups."""
    override = os.environ.get("GTW_SPLITS_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "gtw-splits"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "gtw-splits"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "gtw-splits"
