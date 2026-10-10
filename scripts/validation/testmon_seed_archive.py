"""Read and place the testmon database from a downloaded artifact zip (issue #6239).

Only one exact member name is read, never a path taken from the archive, and the
bytes must start with the SQLite magic. `scripts/validation/testmon_seed.py`
documents the trust model.
"""

from __future__ import annotations

import os
import secrets
import zipfile
from pathlib import Path

DATABASE_NAME = ".testmondata"
MAX_DATABASE_BYTES = 512 * 1024 * 1024
SQLITE_MAGIC = b"SQLite format 3\x00"


def database_from_zip(archive_path: Path) -> bytes:
    """Read the one expected member by exact name; reject anything else."""
    with zipfile.ZipFile(archive_path) as archive:
        info = archive.getinfo(DATABASE_NAME)
        if info.file_size > MAX_DATABASE_BYTES:
            raise ValueError("database larger than the size cap")
        data = archive.read(info)
    if not data.startswith(SQLITE_MAGIC):
        raise ValueError("artifact is not an SQLite database")
    return data


def write_database(repo_root: Path, data: bytes) -> None:
    """Write ``data`` to ``repo_root/.testmondata`` through a fresh private file.

    The staging file is created with O_CREAT|O_EXCL|O_NOFOLLOW under a random
    name, so a planted file or symlink makes the open fail instead of redirecting
    the write, then renamed over the target.
    """
    target = repo_root / DATABASE_NAME
    partial = repo_root / f"{DATABASE_NAME}.seed.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(partial, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
