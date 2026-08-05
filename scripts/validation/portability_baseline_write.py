"""Serialized, atomic writes for portability baseline artifacts."""

from __future__ import annotations

import os
import secrets
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


def _write_all(file_descriptor: int, payload: bytes) -> None:
    """Write a complete payload to an open file descriptor."""
    offset = 0
    while offset < len(payload):
        offset += os.write(file_descriptor, payload[offset:])


def _replace_baseline_relative_to_parent(
    repo_root: Path,
    baseline_path: Path,
    text: str,
) -> None:
    """Replace through a pinned parent directory without following links."""
    root = Path(os.path.abspath(repo_root))
    target = Path(os.path.abspath(baseline_path))
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise OSError(f"baseline path leaves repository root: {target}") from exc

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    parent_descriptor = os.open(root, directory_flags)
    temporary_name: str | None = None
    first_error: OSError | None = None
    try:
        for component in relative.parent.parts:
            next_descriptor = os.open(
                component,
                directory_flags,
                dir_fd=parent_descriptor,
            )
            os.close(parent_descriptor)
            parent_descriptor = next_descriptor

        temporary_name = f".{target.name}.{secrets.token_hex(8)}.tmp"
        temporary_descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=parent_descriptor,
        )
        try:
            _write_all(temporary_descriptor, text.encode("utf-8"))
            os.fsync(temporary_descriptor)
        finally:
            os.close(temporary_descriptor)
        os.replace(
            temporary_name,
            target.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
    except OSError as write_error:
        first_error = write_error
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
            except OSError:
                if first_error is None:
                    raise
        os.close(parent_descriptor)
    if first_error is not None:
        raise first_error


def _replace_baseline_by_path(baseline_path: Path, text: str) -> None:
    """Use the portable path API where directory descriptors are unavailable."""
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


def replace_baseline_atomically(
    repo_root: Path,
    baseline_path: Path,
    text: str,
) -> None:
    """Replace a baseline without allowing a checked parent to be swapped."""
    if os.name == "posix":
        _replace_baseline_relative_to_parent(repo_root, baseline_path, text)
        return
    _replace_baseline_by_path(baseline_path, text)
