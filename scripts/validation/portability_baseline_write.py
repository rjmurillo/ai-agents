"""Serialized, atomic writes for portability baseline artifacts."""

from __future__ import annotations

import os
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

if sys.platform == "win32":
    import msvcrt

    def _lock_file(file_descriptor: int) -> None:
        msvcrt.locking(file_descriptor, msvcrt.LK_NBLCK, 1)

    def _unlock_file(file_descriptor: int) -> None:
        msvcrt.locking(file_descriptor, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock_file(file_descriptor: int) -> None:
        fcntl.flock(file_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock_file(file_descriptor: int) -> None:
        fcntl.flock(file_descriptor, fcntl.LOCK_UN)


@contextmanager
def baseline_write_lock(
    lock_path: Path,
    *,
    _lock: Callable[[int], None] | None = None,
    _unlock: Callable[[int], None] | None = None,
) -> Iterator[None]:
    """Serialize baseline writes with an injectable cross-platform file lock."""
    lock = _lock if _lock is not None else _lock_file
    unlock = _unlock if _unlock is not None else _unlock_file

    if lock_path.is_dir():
        try:
            lock_path.rmdir()
        except OSError:
            pass

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        deadline = time.monotonic() + 10.0
        while True:
            try:
                lock(file_descriptor)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"timed out waiting for baseline lock {lock_path}"
                    ) from None
                time.sleep(0.05)
        try:
            yield
        finally:
            unlock(file_descriptor)
    finally:
        os.close(file_descriptor)


def replace_baseline_atomically(baseline_path: Path, text: str) -> None:
    """Replace a baseline without letting cleanup hide the write failure."""
    temporary_path: Path | None = None
    first_error: OSError | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=baseline_path.parent,
            prefix=f".{baseline_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(text)
        temporary_path.replace(baseline_path)
    except OSError as write_error:
        first_error = write_error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                if first_error is None:
                    raise
    if first_error is not None:
        raise first_error
