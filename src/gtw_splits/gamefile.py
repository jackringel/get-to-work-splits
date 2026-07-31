"""Reading and writing the game's ``best_split_times.txt``.

The file is .NET ``XmlSerializer`` output holding one ``<float>`` per split::

    <?xml version="1.0" encoding="utf-8"?>
    <SpeedrunTimerData xmlns:xsd="..." xmlns:xsi="...">
      <times>
        <float>72.10753</float>
        ...
      </times>
    </SpeedrunTimerData>

Reads go through a real XML parser rather than fixed character offsets, so the
game changing its indentation cannot silently corrupt a run. Writes reproduce
the observed layout byte-for-byte, including the absent trailing newline.
"""

from __future__ import annotations

import shutil
import time
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

#: Default name of the game's splits file inside the save folder.
GAME_FILE_NAME = "best_split_times.txt"

_HEADER = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    "<SpeedrunTimerData "
    'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
    "  <times>\n"
)
_FOOTER = "  </times>\n</SpeedrunTimerData>"


class GameFileError(Exception):
    """The splits file could not be read or did not look like splits data."""


def _format_float(value: float) -> str:
    """Render a float the way .NET's round-trip formatter does.

    Python's ``repr`` is also shortest-round-trip, so ``68.0`` stays ``68.0``
    and ``24.639858199999992`` keeps its full precision.
    """
    return repr(float(value))


def parse_times(text: str) -> list[float]:
    """Extract the split times from splits-file XML."""
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise GameFileError(f"not valid XML: {exc}") from exc

    times_node = root.find("times")
    if times_node is None:
        raise GameFileError("no <times> element found")

    values = []
    for node in times_node.findall("float"):
        raw = (node.text or "").strip()
        try:
            values.append(float(raw))
        except ValueError as exc:
            raise GameFileError(f"non-numeric split time {raw!r}") from exc

    if not values:
        raise GameFileError("<times> contained no split times")
    return values


def render_times(times: list[float]) -> str:
    """Render split times back into the game's exact file layout."""
    body = "".join(f"    <float>{_format_float(t)}</float>\n" for t in times)
    return _HEADER + body + _FOOTER


def read_times(path: Path, *, retries: int = 5, delay: float = 0.05) -> list[float]:
    """Read split times, retrying briefly if the game is mid-write.

    A save caught halfway through produces truncated XML; rather than treating
    that as corruption, back off and try again before giving up.
    """
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return parse_times(path.read_text(encoding="utf-8-sig"))
        except (GameFileError, OSError) as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(delay)
    raise GameFileError(f"could not read {path}: {last_error}")


def backup_file(path: Path, backup_dir: Path) -> Path | None:
    """Snapshot the current splits file before it gets overwritten."""
    if not path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = backup_dir / f"{path.stem}-{stamp}{path.suffix}"
    shutil.copy2(path, destination)
    return destination


def write_times(path: Path, times: list[float]) -> str:
    """Atomically overwrite the game's splits file. Returns the text written.

    The write goes to a temporary file in the same directory and is then moved
    into place, so a crash mid-write cannot leave the game with a half-written
    splits file.
    """
    text = render_times(times)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="")
    temporary.replace(path)
    return text
