"""Open Copilot transcript files safely on Windows."""

from __future__ import annotations

import ctypes
import os
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

_GENERIC_READ = 0x80000000
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_OPEN_EXISTING = 3
_FILE_ATTRIBUTE_NORMAL = 0x00000080
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_ATTRIBUTE_DIRECTORY = 0x00000010
_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_FILE_ATTRIBUTE_TAG_INFO = 9


class _FileAttributeTagInfo(ctypes.Structure):
    _fields_ = [
        ("FileAttributes", ctypes.c_ulong),
        ("ReparseTag", ctypes.c_ulong),
    ]


class _CFunction(Protocol):
    restype: object

    def __call__(self, *args: object) -> object: ...


class _Kernel32(Protocol):
    CreateFileW: _CFunction
    GetFileInformationByHandleEx: _CFunction
    GetFinalPathNameByHandleW: _CFunction
    CloseHandle: _CFunction


class _WindowsHandle:
    def __init__(self, kernel32: _Kernel32, handle: int) -> None:
        self._kernel32 = kernel32
        self.value: int | None = handle

    def close(self) -> None:
        if self.value is None:
            return
        self._kernel32.CloseHandle(ctypes.c_void_p(self.value))
        self.value = None


def _kernel32() -> _Kernel32:
    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise OSError("Windows file APIs are unavailable")
    return cast(_Kernel32, loader("kernel32", use_last_error=True))


def _last_error() -> int:
    get_last_error = getattr(ctypes, "get_last_error", None)
    return int(get_last_error()) if get_last_error is not None else 0


def _open_handle(
    kernel32: _Kernel32,
    path: Path,
    *,
    directory: bool,
) -> _WindowsHandle:
    create_file = kernel32.CreateFileW
    create_file.restype = ctypes.c_void_p
    flags = _FILE_FLAG_OPEN_REPARSE_POINT
    flags |= _FILE_FLAG_BACKUP_SEMANTICS if directory else _FILE_ATTRIBUTE_NORMAL
    raw_handle = cast(
        int | None,
        create_file(
            str(path),
            _GENERIC_READ,
            _FILE_SHARE_READ | _FILE_SHARE_WRITE,
            None,
            _OPEN_EXISTING,
            flags,
            None,
        ),
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if not raw_handle or int(raw_handle) == invalid_handle:
        raise OSError(_last_error(), "CreateFileW failed")
    return _WindowsHandle(kernel32, int(raw_handle))


def _attributes(kernel32: _Kernel32, handle: _WindowsHandle) -> int:
    if handle.value is None:
        raise OSError("Windows handle is closed")
    info = _FileAttributeTagInfo()
    success = kernel32.GetFileInformationByHandleEx(
        ctypes.c_void_p(handle.value),
        _FILE_ATTRIBUTE_TAG_INFO,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )
    if not success:
        raise OSError(_last_error(), "GetFileInformationByHandleEx failed")
    return int(info.FileAttributes)


def _final_path(kernel32: _Kernel32, handle: _WindowsHandle) -> str:
    if handle.value is None:
        raise OSError("Windows handle is closed")
    get_path = kernel32.GetFinalPathNameByHandleW
    length = cast(
        int,
        get_path(ctypes.c_void_p(handle.value), None, 0, 0),
    )
    if length <= 0:
        raise OSError(_last_error(), "GetFinalPathNameByHandleW failed")
    buffer = ctypes.create_unicode_buffer(length + 1)
    written = cast(
        int,
        get_path(
            ctypes.c_void_p(handle.value),
            buffer,
            len(buffer),
            0,
        )
    )
    if written <= 0:
        raise OSError(_last_error(), "GetFinalPathNameByHandleW failed")
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return os.path.normcase(os.path.normpath(value))


def _is_child(parent: str, child: str) -> bool:
    try:
        return os.path.commonpath([parent, child]) == parent
    except ValueError:
        return False


def _validate_handle(
    kernel32: _Kernel32,
    handle: _WindowsHandle,
    *,
    directory: bool,
    parent_path: str | None,
    provider_label: str,
) -> str:
    attributes = _attributes(kernel32, handle)
    is_directory = bool(attributes & _FILE_ATTRIBUTE_DIRECTORY)
    if attributes & _FILE_ATTRIBUTE_REPARSE_POINT or is_directory != directory:
        kind = "directory" if directory else "transcript"
        raise RuntimeError(
            f"{provider_label} session {kind} is not a regular {kind}"
        )
    final_path = _final_path(kernel32, handle)
    if parent_path is not None and not _is_child(parent_path, final_path):
        raise RuntimeError(
            f"{provider_label} session transcript escaped the session root"
        )
    return final_path


def open_windows_transcript(
    root: Path,
    session_name: str,
    provider_label: str,
) -> tuple[int, os.stat_result]:
    """Open one transcript without following reparse points or path swaps."""
    if os.name != "nt":
        raise OSError("Windows transcript opener used on another platform")
    import msvcrt

    kernel32 = _kernel32()
    root_handle = _open_handle(kernel32, root, directory=True)
    session_handle: _WindowsHandle | None = None
    file_handle: _WindowsHandle | None = None
    try:
        root_path = _validate_handle(
            kernel32,
            root_handle,
            directory=True,
            parent_path=None,
            provider_label=provider_label,
        )
        session_handle = _open_handle(
            kernel32,
            root / session_name,
            directory=True,
        )
        session_path = _validate_handle(
            kernel32,
            session_handle,
            directory=True,
            parent_path=root_path,
            provider_label=provider_label,
        )
        file_handle = _open_handle(
            kernel32,
            root / session_name / "events.jsonl",
            directory=False,
        )
        _validate_handle(
            kernel32,
            file_handle,
            directory=False,
            parent_path=session_path,
            provider_label=provider_label,
        )
        if file_handle.value is None:
            raise OSError("Windows transcript handle is closed")
        open_osfhandle = cast(
            Callable[[int, int], int],
            vars(msvcrt)["open_osfhandle"],
        )
        descriptor = open_osfhandle(file_handle.value, os.O_RDONLY)
        file_handle.value = None
        try:
            metadata = os.fstat(descriptor)
        except BaseException:
            os.close(descriptor)
            raise
        return descriptor, metadata
    finally:
        if file_handle is not None:
            file_handle.close()
        if session_handle is not None:
            session_handle.close()
        root_handle.close()
