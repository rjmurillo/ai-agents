"""Own and terminate the Copilot subprocess tree."""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
from typing import Any

_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000


def _last_error() -> int:
    get_last_error = getattr(ctypes, "get_last_error", None)
    return int(get_last_error()) if get_last_error is not None else 0


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_ulong),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_ulong),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_ulong),
        ("SchedulingClass", ctypes.c_ulong),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _WindowsJob:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        loader = getattr(ctypes, "WinDLL", None)
        if loader is None:
            raise OSError("Windows job objects are unavailable")
        kernel32: Any = loader("kernel32", use_last_error=True)
        create_job = kernel32.CreateJobObjectW
        create_job.restype = ctypes.c_void_p
        handle = create_job(None, None)
        if not handle:
            raise OSError(_last_error(), "CreateJobObjectW failed")

        self._kernel32 = kernel32
        self._handle: int | None = int(handle)
        try:
            limits = _ExtendedLimitInformation()
            limits.BasicLimitInformation.LimitFlags = (
                _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            )
            configured = kernel32.SetInformationJobObject(
                ctypes.c_void_p(self._handle),
                _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(limits),
                ctypes.sizeof(limits),
            )
            if not configured:
                raise OSError(
                    _last_error(),
                    "SetInformationJobObject failed",
                )
            process_handle = getattr(process, "_handle", None)
            if process_handle is None:
                raise OSError("Windows process handle is unavailable")
            assigned = kernel32.AssignProcessToJobObject(
                ctypes.c_void_p(self._handle),
                ctypes.c_void_p(int(process_handle)),
            )
            if not assigned:
                raise OSError(
                    _last_error(),
                    "AssignProcessToJobObject failed",
                )
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self._handle is None:
            return
        self._kernel32.CloseHandle(ctypes.c_void_p(self._handle))
        self._handle = None


class ProcessTree:
    """Hold the platform process-tree boundary until cleanup completes."""

    def __init__(self, process: subprocess.Popen[str]) -> None:
        self._process = process
        self._windows_job = _WindowsJob(process) if os.name == "nt" else None
        self._closed = False

    def terminate(self, *, force: bool) -> None:
        if self._closed:
            return
        if self._windows_job is not None:
            self.close()
            return
        try:
            os.killpg(
                self._process.pid,
                signal.SIGKILL if force else signal.SIGTERM,
            )
        except ProcessLookupError:
            pass

    def close(self) -> None:
        if self._closed:
            return
        if self._windows_job is not None:
            self._windows_job.close()
        else:
            self.terminate(force=True)
        self._closed = True
