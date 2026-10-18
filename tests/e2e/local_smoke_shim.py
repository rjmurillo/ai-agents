"""A ``copilot`` that exits non-zero, first on PATH, for the local smoke (issue #6506).

``local_smoke_guard`` reads a fixed set of launchers and shells, so a program started
through any other launcher (``script -c``, ``su -c``, ``find -exec``, ``parallel``) is not
seen. This shim is the backstop that does not depend on parsing: any child that looks
``copilot`` up by name finds it and fails, whichever launcher started it. It does not stop a
launch by absolute path, or on Windows a ``copilot.exe``.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_SHIM_MESSAGE = (
    "The local CLI smoke must not call Copilot. Give the test the copilot marker "
    "so only the CI leg runs it."
)
_SHIM_FILES = {
    "copilot": f"#!/bin/sh\necho '{_SHIM_MESSAGE}' >&2\nexit 126\n",
    "copilot.cmd": f"@echo off\r\necho {_SHIM_MESSAGE} 1>&2\r\nexit /b 126\r\n",
    "copilot.bat": f"@echo off\r\necho {_SHIM_MESSAGE} 1>&2\r\nexit /b 126\r\n",
}
# The shim directory and the PATH value (None when unset) from before ``install_path_shim``.
_shim_dir: tempfile.TemporaryDirectory[str] | None = None
_saved_path: str | None = None


def install_path_shim() -> Path:
    """Put a ``copilot`` that exits 126 first on ``PATH`` and return its directory.

    This is the backstop for a launch the command parser cannot read. Any child that
    looks ``copilot`` up by name finds the shim, so the launch fails whichever launcher
    started it. Calling it again returns the directory already installed.
    """
    global _shim_dir, _saved_path
    if _shim_dir is not None:
        return Path(_shim_dir.name)
    _shim_dir = tempfile.TemporaryDirectory(prefix="local-smoke-shim-")
    shim = Path(_shim_dir.name)
    for name, text in _SHIM_FILES.items():
        (shim / name).write_text(text, encoding="utf-8", newline="")
        (shim / name).chmod(0o755)
    _saved_path = os.environ.get("PATH")
    os.environ["PATH"] = f"{shim}{os.pathsep}{_saved_path}" if _saved_path else str(shim)
    return shim


def remove_path_shim() -> None:
    """Take the shim off ``PATH`` and delete its directory. Does nothing if none is installed."""
    global _shim_dir, _saved_path
    if _shim_dir is None:
        return
    current = os.environ.get("PATH", "")
    prefix = f"{_shim_dir.name}{os.pathsep}"
    if current == _shim_dir.name:  # install set PATH to the shim alone
        restored = _saved_path
    elif current.startswith(prefix):
        restored = current.removeprefix(prefix)
    else:  # a later change to PATH (a monkeypatch) is kept
        restored = current
    if restored is None:
        os.environ.pop("PATH", None)
    else:
        os.environ["PATH"] = restored
    _shim_dir.cleanup()
    _shim_dir, _saved_path = None, None
