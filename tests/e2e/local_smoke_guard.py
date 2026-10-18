"""Refuse a Copilot CLI launch during the local pre-push smoke.

The local smoke runs on the harness the developer uses, on their own login. The
pre-push gate passes ``-m "not copilot"``, which only deselects tests that carry
the ``copilot`` marker. A Copilot call added without that marker would still run
locally. This guard closes that gap: when the gate sets ``LOCAL_SMOKE_ENV``, any
``subprocess.run`` or ``subprocess.Popen`` that would start ``copilot``, as the
program or anywhere in a compound command line, fails the test before the
process starts.

The guard also wraps the ``os`` spawn entry points (``system``, ``posix_spawn``,
``posix_spawnp``, the ``exec*`` and ``spawn*`` families). It cannot see a launch
that skips Python's ``os`` module: a C extension, ``ctypes`` calling ``system``,
or a program the test starts that itself starts Copilot. Those stay a review
concern.

The threat is an unmarked test a contributor wrote by mistake, not an adversary. The
command parser reads a fixed set of launchers and shells, and its scope is frozen at the
forms such a test is likely to use. A program started through any other launcher
(``script -c``, ``su -c``, ``find -exec``, ``parallel``) is not seen. The backstop is
``local_smoke_shim``: a ``copilot`` that exits non-zero, first on ``PATH``, so a launch by
bare name fails whatever started it. It does not stop a launch by absolute path.

The refusal derives from ``BaseException``. A broad ``except Exception`` in the
code under test would otherwise turn the refusal into a pass.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping
from typing import Any

from local_smoke_os import _ORIGINAL_OS, install_os
from local_smoke_refuse import (
    LOCAL_SMOKE_ENV,
    CopilotCallRefusedError,
    guard_active,
    refuse_copilot,
)
from local_smoke_shim import install_path_shim, remove_path_shim

__all__ = [
    "LOCAL_SMOKE_ENV",
    "CopilotCallRefusedError",
    "GuardedPopen",
    "guard_active",
    "install",
    "install_path_shim",
    "refuse_copilot",
    "remove_path_shim",
    "restore",
    "snapshot",
    "uninstall",
]

_ORIGINAL_POPEN = subprocess.Popen

# Popen's `shell` position among the arguments after `args`: bufsize, executable, stdin,
# stdout, stderr, preexec_fn, close_fds, then shell.
_POPEN_SHELL_INDEX = 7


class GuardedPopen(subprocess.Popen[Any]):
    """``subprocess.Popen`` that refuses to start the Copilot CLI.

    ``subprocess.run`` builds its process through the module's ``Popen``, so
    replacing ``subprocess.Popen`` with this subclass covers both entry points.
    A subclass keeps ``isinstance(proc, subprocess.Popen)`` true.
    """

    def __init__(self, args: Any, *rest: Any, **kwargs: Any) -> None:
        refuse_copilot(args)
        # With shell=True the first item of a sequence is a command line, not a program.
        shell = kwargs.get("shell") or (len(rest) > _POPEN_SHELL_INDEX and rest[_POPEN_SHELL_INDEX])
        if shell and isinstance(args, (list, tuple)) and args:
            refuse_copilot(args[0])
        # Popen's positional order is (args, bufsize, executable, ...).
        executable = kwargs.get("executable", rest[1] if len(rest) > 1 else None)
        if executable is not None:
            refuse_copilot([executable])
        super().__init__(args, *rest, **kwargs)


def install(setattr_fn: Callable[[object, str, object], None]) -> None:
    """Replace ``subprocess.Popen`` and the ``os`` spawn entry points through ``setattr_fn``."""
    setattr_fn(subprocess, "Popen", GuardedPopen)
    install_os(setattr_fn)


def snapshot() -> dict[str, Any]:
    """Return what ``install`` and the PATH shim change, for ``restore``."""
    return {
        "popen": subprocess.Popen,
        "os": {name: getattr(os, name) for name in _ORIGINAL_OS},
        "path": os.environ.get("PATH"),
    }


def restore(state: Mapping[str, Any]) -> None:
    """Put back a ``snapshot``. The PATH shim itself is removed by ``remove_path_shim``."""
    setattr(subprocess, "Popen", state["popen"])  # noqa: B010
    for name, value in state["os"].items():
        setattr(os, name, value)
    if state["path"] is None:
        os.environ.pop("PATH", None)
    else:
        os.environ["PATH"] = state["path"]


def uninstall() -> None:
    """Put back the real ``subprocess.Popen``, the ``os`` entry points, and ``PATH``."""
    setattr(subprocess, "Popen", _ORIGINAL_POPEN)  # noqa: B010
    for name, original in _ORIGINAL_OS.items():
        setattr(os, name, original)
    remove_path_shim()
