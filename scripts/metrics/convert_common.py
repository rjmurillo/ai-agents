"""Shared output-safety helpers for the session converters.

Codex, Copilot, and Droid converters name each output file after a session id
read from untrusted transcript data. Both helpers below are the one place that
keeps a hostile id or a planted symlink from steering a write.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
FILE_MODE = 0o600


def safe_session_id(value: object) -> str | None:
    """Return ``value`` when it is a safe output file stem, else None.

    The pattern needs an alphanumeric first character, so ``..``, an empty id,
    a hidden-file name, and any id holding ``/`` all fail.
    """
    if isinstance(value, str) and SAFE_ID.fullmatch(value):
        return value
    return None


def write_private(path: Path, text: str) -> None:
    """Write ``text`` with mode 0o600, replacing any existing entry at ``path``.

    ``unlink`` removes a planted symlink itself (it never follows it), and
    ``O_EXCL`` makes ``open`` fail if one reappears before the create, so the
    write never goes through a link.
    """
    path.unlink(missing_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
