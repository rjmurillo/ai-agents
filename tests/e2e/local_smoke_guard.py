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

The command parser reads a fixed set of launchers and shells, so a program started
through any other launcher (``script -c``, ``su -c``, ``find -exec``, ``parallel``) is
not seen. ``install_path_shim`` is the backstop that does not depend on parsing: it puts a
``copilot`` that exits non-zero first on ``PATH``, so a launch by bare name fails whatever
started it. It does not stop a launch by absolute path, or on Windows a ``copilot.exe``.

The refusal derives from ``BaseException``. A broad ``except Exception`` in the
code under test would otherwise turn the refusal into a pass.
"""

from __future__ import annotations

import inspect
import os
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
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


def _bind(
    signature: inspect.Signature | None, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Mapping[int, Any]:
    """Map a call to its values by position, binding keywords through ``signature``.

    ``execve(path=..., argv=...)`` and ``spawnv(0, file=..., args=...)`` pass the program by
    keyword, so reading only ``args`` would miss them. ``posix_spawn`` and ``execv`` take their
    first parameters positional-only, so Python itself rejects a keyword there. A call the
    signature cannot bind is left to the original, which raises its own ``TypeError``.
    """
    if signature is None or not kwargs:
        return dict(enumerate(args))
    try:
        bound = signature.bind_partial(*args, **kwargs)
    except TypeError:
        return dict(enumerate(args))
    names = list(signature.parameters)
    return {i: bound.arguments[n] for i, n in enumerate(names) if n in bound.arguments}


def _signature_of(function: Callable[..., Any]) -> inspect.Signature | None:
    try:
        return inspect.signature(function)
    except (TypeError, ValueError):
        return None


# Read from the real functions at import: a test may later swap ``_ORIGINAL_OS`` entries for
# stand-ins whose ``(*args, **kwargs)`` signature names no parameter.
_SIGNATURES = {name: _signature_of(original) for name, original in _ORIGINAL_OS.items()}


_RESOLVE: Any = object()  # "no signature given": read it from the original


def _names_parameters(signature: inspect.Signature | None) -> bool:
    """Return True when keywords can be mapped to positions through ``signature``."""
    variadic = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    return signature is not None and all(
        p.kind not in variadic for p in signature.parameters.values()
    )


def _guarded_os(
    original: Callable[..., Any],
    program: int,
    argv: int | None,
    signature: inspect.Signature | None = _RESOLVE,
) -> Callable[..., Any]:
    if signature is _RESOLVE:
        signature = _signature_of(original)

    def guarded(*args: Any, **kwargs: Any) -> Any:
        values = _bind(signature, args, kwargs)
        if kwargs and not _names_parameters(signature):
            # Keyword names cannot be mapped to positions, so fail closed.
            if argv is None and "command" in kwargs:  # os.system(command=...)
                refuse_copilot(kwargs["command"])
            raise CopilotCallRefusedError(
                "The local CLI smoke cannot read keyword arguments of this os spawn function "
                f"(got {sorted(kwargs)!r}), so it refuses the call. Pass the arguments by position."
            )
        if program in values:
            refuse_copilot(values[program] if argv is None else [values[program]])
        if argv is not None and isinstance(values.get(argv), (list, tuple)):
            refuse_copilot(list(values[argv]))
        return original(*args, **kwargs)

    return guarded


def install(setattr_fn: Callable[[object, str, object], None]) -> None:
    """Replace ``subprocess.Popen`` and the ``os`` spawn entry points through ``setattr_fn``."""
    setattr_fn(subprocess, "Popen", GuardedPopen)
    for name, original in _ORIGINAL_OS.items():
        program, argv = _OS_ENTRY_POINTS[name]
        setattr_fn(os, name, _guarded_os(original, program, argv, _SIGNATURES[name]))


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
    if current.startswith(_shim_dir.name):
        # A later change to PATH (a monkeypatch) is kept; only our prefix is removed.
        if _saved_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = current.removeprefix(f"{_shim_dir.name}{os.pathsep}")
    _shim_dir.cleanup()
    _shim_dir, _saved_path = None, None


def uninstall() -> None:
    """Put back the real ``subprocess.Popen``, the ``os`` entry points, and ``PATH``."""
    setattr(subprocess, "Popen", _ORIGINAL_POPEN)  # noqa: B010
    for name, original in _ORIGINAL_OS.items():
        setattr(os, name, original)
    remove_path_shim()
