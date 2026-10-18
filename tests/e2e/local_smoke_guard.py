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

The refusal derives from ``BaseException``. A broad ``except Exception`` in the
code under test would otherwise turn the refusal into a pass.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping
from typing import Any

from local_smoke_command import program_names

LOCAL_SMOKE_ENV = "AI_AGENTS_LOCAL_CLI_SMOKE"
_COPILOT_NAMES = frozenset({"copilot", "copilot.exe", "copilot.cmd", "copilot.bat"})


class CopilotCallRefusedError(BaseException):
    """Raised when the local smoke tries to start the Copilot CLI.

    A ``BaseException`` on purpose, so a broad ``except Exception`` cannot swallow it.
    pytest still reports it as a test failure.
    """


def guard_active(environ: Mapping[str, str] | None = None) -> bool:
    """Return True when the local pre-push smoke marked this run."""
    source = os.environ if environ is None else environ
    return source.get(LOCAL_SMOKE_ENV) == "1"


def refuse_copilot(args: object) -> None:
    """Raise when ``args`` would start the Copilot CLI."""
    if any(name in _COPILOT_NAMES for name in program_names(args)):
        raise CopilotCallRefusedError(
            f"The local CLI smoke must not call Copilot (got {args!r}). "
            "Give the test the copilot marker (the requires_copilot decorator in "
            "test_plugin_load_smoke.py and test_cli_hook_e2e.py applies it), so "
            "only the CI leg runs it."
        )


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


# The os spawn entry points, mapped to the positions of the program and of the argv
# (None when the entry point takes a command line instead). The ``exec*`` and
# ``spawn*`` names with an ``l`` call these through the os module, so they are covered.
_OS_ENTRY_POINTS: dict[str, tuple[int, int | None]] = {
    "system": (0, None),
    "posix_spawn": (0, 1),
    "posix_spawnp": (0, 1),
    "execv": (0, 1),
    "execve": (0, 1),
    "execvp": (0, 1),
    "execvpe": (0, 1),
    "spawnv": (1, 2),
    "spawnve": (1, 2),
    "spawnvp": (1, 2),
    "spawnvpe": (1, 2),
}
_ORIGINAL_POPEN = subprocess.Popen
_ORIGINAL_OS = {name: getattr(os, name) for name in _OS_ENTRY_POINTS if hasattr(os, name)}


def _guarded_os(original: Callable[..., Any], program: int, argv: int | None) -> Callable[..., Any]:
    def guarded(*args: Any, **kwargs: Any) -> Any:
        if argv is None and not args and "command" in kwargs:  # os.system(command=...)
            refuse_copilot(kwargs["command"])
        if len(args) > program:
            refuse_copilot(args[program] if argv is None else [args[program]])
        if argv is not None and len(args) > argv and isinstance(args[argv], (list, tuple)):
            refuse_copilot(list(args[argv]))
        return original(*args, **kwargs)

    return guarded


def install(setattr_fn: Callable[[object, str, object], None]) -> None:
    """Replace ``subprocess.Popen`` and the ``os`` spawn entry points through ``setattr_fn``."""
    setattr_fn(subprocess, "Popen", GuardedPopen)
    for name, original in _ORIGINAL_OS.items():
        program, argv = _OS_ENTRY_POINTS[name]
        setattr_fn(os, name, _guarded_os(original, program, argv))


def uninstall() -> None:
    """Put back the real ``subprocess.Popen`` and ``os`` entry points."""
    setattr(subprocess, "Popen", _ORIGINAL_POPEN)  # noqa: B010
    for name, original in _ORIGINAL_OS.items():
        setattr(os, name, original)
