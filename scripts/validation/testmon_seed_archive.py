"""Read and place the testmon database from a downloaded artifact zip (issue #6239).

Only one exact member name is read, never a path taken from the archive, and the
bytes must start with the SQLite magic. `scripts/validation/testmon_seed.py`
documents the trust model.
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

DATABASE_NAME = ".testmondata"
MAX_DATABASE_BYTES = 512 * 1024 * 1024
SQLITE_MAGIC = b"SQLite format 3\x00"


def database_from_zip(payload: bytes) -> bytes:
    """Read the one expected member by exact name; reject anything else."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        info = archive.getinfo(DATABASE_NAME)
        if info.file_size > MAX_DATABASE_BYTES:
            raise ValueError("database larger than the size cap")
        data = archive.read(info)
    if not data.startswith(SQLITE_MAGIC):
        raise ValueError("artifact is not an SQLite database")
    return data


def write_database(repo_root: Path, data: bytes) -> None:
    target = repo_root / DATABASE_NAME
    partial = repo_root / f"{DATABASE_NAME}.seed.{os.getpid()}.tmp"
    try:
        partial.write_bytes(data)
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
