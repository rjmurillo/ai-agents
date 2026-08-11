"""Filesystem transaction for generated hook artifacts."""

from __future__ import annotations

import errno
import hashlib
import importlib
import os
import shutil
import stat
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from typing import BinaryIO

_IS_WINDOWS = os.name == "nt"
_LOCK_TIMEOUT_SECONDS = 10.0
_LOCK_RETRY_INTERVAL_SECONDS = 0.05
_RETRYABLE_LOCK_ERRNOS = frozenset({errno.EACCES, errno.EAGAIN, errno.EDEADLK})


class _FcntlModule(Protocol):
    LOCK_EX: int
    LOCK_NB: int
    LOCK_UN: int

    def flock(self, file_descriptor: int, operation: int) -> None: ...


class _MsvcrtModule(Protocol):
    LK_NBLCK: int
    LK_UNLCK: int

    def locking(self, file_descriptor: int, mode: int, size: int) -> None: ...


class _CtypesModule(Protocol):
    c_void_p: object

    def WinDLL(self, name: str, *, use_last_error: bool) -> object: ...

    def get_last_error(self) -> int: ...

    def FormatError(self, code: int) -> str: ...


class _PosixModule(Protocol):
    def getuid(self) -> int: ...


class HookGenerationTransaction:
    """Back up every target once and restore the full run on failure."""

    def __init__(self, lock_target: Path) -> None:
        self._backups: dict[Path, Path | None] = {}
        self._mutated: list[Path] = []
        self._temporary_paths: set[Path] = set()
        self._temporary_directories: set[Path] = set()
        self._retained_backups: set[Path] = set()
        self._lock_path = _lock_path(lock_target)
        self._lock_handle: BinaryIO | None = None
        self._acquire_lock()

    def new_stage_path(self, directory: Path) -> Path:
        """Allocate a short temporary file beside its final target."""
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, raw_path = tempfile.mkstemp(
            prefix=".hook-stage-",
            suffix=".tmp",
            dir=directory,
        )
        os.close(descriptor)
        path = Path(raw_path)
        self._temporary_paths.add(path)
        return path

    def new_stage_directory(self, directory: Path) -> Path:
        """Allocate a temporary directory on the target filesystem."""
        directory.mkdir(parents=True, exist_ok=True)
        path = Path(tempfile.mkdtemp(prefix=".hook-stage-", dir=directory))
        self._temporary_directories.add(path)
        return path

    def publish_many(self, pairs: Iterable[tuple[Path, Path]]) -> None:
        """Replace staged files only after every target has a backup."""
        publish_order = list(pairs)
        for _staged, target in publish_order:
            self._backup_target(target)
        for staged, target in publish_order:
            self._apply_target_metadata(staged, target)
            replacement_backup = self._replacement_backup(target)
            try:
                _replace_target(staged, target, replacement_backup)
            except OSError:
                if replacement_backup is not None and replacement_backup.is_file():
                    self._mark_mutated(target)
                raise
            self._mark_mutated(target)

    def delete_many(self, targets: Iterable[Path]) -> None:
        """Delete targets while retaining one rollback copy per path."""
        delete_order = list(dict.fromkeys(targets))
        backed_up_targets = {
            target for target in delete_order if target in self._backups
        }
        for target in delete_order:
            self._backup_target(target)
        for target in delete_order:
            backup = self._backups[target]
            if _IS_WINDOWS and target not in backed_up_targets and backup is not None:
                try:
                    os.replace(target, backup)
                except FileNotFoundError:
                    if backup.is_file():
                        self._mark_mutated(target)
                        raise
                    continue
                except OSError:
                    if backup.is_file():
                        self._mark_mutated(target)
                    raise
            else:
                try:
                    target.unlink()
                except FileNotFoundError:
                    continue
            self._mark_mutated(target)

    def rollback(self) -> list[str]:
        """Restore every target changed during this generation run."""
        errors: list[str] = []
        for target in reversed(self._mutated):
            backup = self._backups[target]
            try:
                if backup is None:
                    target.unlink(missing_ok=True)
                else:
                    _restore_backup(backup, target)
            except OSError as exc:
                recovery = ""
                if backup is not None:
                    self._retained_backups.add(backup)
                    recovery = f"; recovery backup retained at {backup}"
                errors.append(f"{target}: {exc}{recovery}")
        errors.extend(self._cleanup_temporary_paths())
        errors.extend(self._release_lock())
        return errors

    def commit(self) -> list[str]:
        """Discard backups after every artifact and config file is published."""
        errors = self._cleanup_temporary_paths()
        errors.extend(self._release_lock())
        return errors

    def _backup_target(self, target: Path) -> None:
        if target in self._backups:
            return
        if not target.is_file():
            self._backups[target] = None
            return

        backup = self.new_stage_path(target.parent)
        backup.unlink()
        # ReplaceFileW creates the Windows backup by moving the original file
        # object, which retains its DACL, named streams, and other metadata.
        if not _IS_WINDOWS:
            try:
                os.link(target, backup)
            except OSError:
                shutil.copy2(target, backup)
        self._backups[target] = backup

    def _replacement_backup(self, target: Path) -> Path | None:
        journal_backup = self._backups[target]
        if not _IS_WINDOWS or not target.is_file():
            return journal_backup
        if journal_backup is not None and not journal_backup.is_file():
            return journal_backup
        disposable_backup = self.new_stage_path(target.parent)
        disposable_backup.unlink()
        return disposable_backup

    @staticmethod
    def _apply_target_metadata(staged: Path, target: Path) -> None:
        """Carry the target's permissions and ownership onto its replacement.

        Times are deliberately NOT carried. ``shutil.copystat`` copies them,
        which left a regenerated hook holding its previous modification time.
        CPython invalidates ``__pycache__`` on modification time and size, so a
        rewrite that keeps both serves the OLD bytecode: measured in issue
        #4764 after repinning a SHA-256 constant, where the digest is a
        fixed-width hex string and the file size therefore did not change. The
        guard ran the stale module and denied a valid invocation.

        Before the guard was split it ran as ``__main__``, which is never
        cached, so nothing in this tree exercised the hazard. Its sibling
        modules are ordinary imports and are cached like any other.
        """
        if not target.is_file():
            return
        target_stat = target.stat(follow_symlinks=False)
        os.chmod(staged, stat.S_IMODE(target_stat.st_mode))
        if not _IS_WINDOWS:
            shutil.chown(
                staged,
                user=target_stat.st_uid,
                group=target_stat.st_gid,
            )

    def _mark_mutated(self, target: Path) -> None:
        if target not in self._mutated:
            self._mutated.append(target)

    def _acquire_lock(self) -> None:
        handle = self._lock_path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            _lock_file(handle)
        except OSError:
            handle.close()
            raise
        self._lock_handle = handle

    def _release_lock(self) -> list[str]:
        handle = self._lock_handle
        if handle is None:
            return []
        errors: list[str] = []
        try:
            _unlock_file(handle)
        except OSError as exc:
            errors.append(f"could not release generation lock {self._lock_path}: {exc}")
        finally:
            handle.close()
            self._lock_handle = None
        return errors

    def _cleanup_temporary_paths(self) -> list[str]:
        errors: list[str] = []
        for temporary_path in self._temporary_paths:
            if temporary_path in self._retained_backups:
                continue
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError as exc:
                errors.append(f"could not remove {temporary_path}: {exc}")
        for temporary_directory in self._temporary_directories:
            try:
                shutil.rmtree(temporary_directory)
            except OSError as exc:
                errors.append(f"could not remove {temporary_directory}: {exc}")
        return errors


def _lock_path(lock_target: Path) -> Path:
    normalized = str(lock_target.resolve())
    if _IS_WINDOWS:
        normalized = normalized.casefold()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return _lock_directory() / f"{digest}.lock"


def _lock_directory() -> Path:
    temp_root = Path(tempfile.gettempdir())
    if _IS_WINDOWS:
        directory = temp_root / "ai-agents-hook-locks"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    posix = cast(_PosixModule, importlib.import_module("posix"))
    user_id = posix.getuid()
    directory = temp_root / f"ai-agents-hook-locks-{user_id}"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory_stat = directory.stat(follow_symlinks=False)
    if not stat.S_ISDIR(directory_stat.st_mode) or directory_stat.st_uid != user_id:
        raise PermissionError(f"unsafe hook lock directory: {directory}")
    directory.chmod(0o700)
    return directory


def _lock_file(
    handle: BinaryIO,
    timeout_seconds: float = _LOCK_TIMEOUT_SECONDS,
) -> None:
    handle.seek(0)
    if _IS_WINDOWS:
        msvcrt = cast(_MsvcrtModule, importlib.import_module("msvcrt"))

        def acquire() -> None:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    else:
        fcntl = cast(_FcntlModule, importlib.import_module("fcntl"))

        def acquire() -> None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    _retry_file_lock(acquire, timeout_seconds)


def _retry_file_lock(
    acquire: Callable[[], None],
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            acquire()
            return
        except OSError as exc:
            if exc.errno not in _RETRYABLE_LOCK_ERRNOS:
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"timed out acquiring hook generation lock after {timeout_seconds:g} seconds"
                ) from exc
            time.sleep(min(_LOCK_RETRY_INTERVAL_SECONDS, remaining))


def _unlock_file(handle: BinaryIO) -> None:
    handle.seek(0)
    if _IS_WINDOWS:
        msvcrt = cast(_MsvcrtModule, importlib.import_module("msvcrt"))

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl = cast(_FcntlModule, importlib.import_module("fcntl"))
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _replace_target(
    source: Path,
    target: Path,
    backup: Path | None = None,
) -> None:
    """Atomically replace a target while retaining its security metadata."""
    if not _IS_WINDOWS or not target.is_file():
        os.replace(source, target)
        return

    ctypes = cast(_CtypesModule, importlib.import_module("ctypes"))
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    replace_file = kernel32.ReplaceFileW
    replace_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
    )
    replace_file.restype = wintypes.BOOL
    replaced = replace_file(
        str(target),
        str(source),
        str(backup) if backup is not None else None,
        0,
        None,
        None,
    )
    if replaced:
        return

    error_code = ctypes.get_last_error()
    raise OSError(error_code, ctypes.FormatError(error_code), str(target))


def _restore_backup(backup: Path, target: Path) -> None:
    """Restore the original file object, including its security metadata."""
    os.replace(backup, target)
