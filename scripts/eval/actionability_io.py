"""Atomic text writes for the comment actionability eval tools.

Writes to a temporary file in the target directory, then swaps it in with
``os.replace``. A crash before the swap leaves the previous output whole. Same
write-temp-then-replace pattern as ``_report_writer._atomic_write``; kept separate
because that module imports heavy siblings and is private.

The temporary file is created by ``tempfile.mkstemp``, so the published file has
mode 0600.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
