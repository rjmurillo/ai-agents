"""Refuse a Copilot CLI launch during the local pre-push smoke.

The local smoke runs on the harness the developer uses, on their own login. The
pre-push gate passes ``-m "not copilot"``, which only deselects tests that carry
the ``copilot`` marker. A Copilot call added without that marker would still run
locally. This guard closes that gap: when the gate sets ``LOCAL_SMOKE_ENV``, any
``subprocess.run`` or ``subprocess.Popen`` whose program is ``copilot`` fails
the test before the process starts.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping
from pathlib import PurePath, PureWindowsPath
from typing import Any

LOCAL_SMOKE_ENV = "AI_AGENTS_LOCAL_CLI_SMOKE"
_COPILOT_NAMES = frozenset({"copilot", "copilot.exe", "copilot.cmd"})


class CopilotCallRefusedError(AssertionError):
    """Raised when the local smoke tries to start the Copilot CLI."""


def guard_active(environ: Mapping[str, str] | None = None) -> bool:
    """Return True when the local pre-push smoke marked this run."""
    source = os.environ if environ is None else environ
    return source.get(LOCAL_SMOKE_ENV) == "1"


def program_name(args: object) -> str:
    """Return the lowercased basename of the program a subprocess call starts."""
    if isinstance(args, (str, bytes, os.PathLike)):
        words = os.fsdecode(args).split()
        first = words[0] if words else ""
    elif isinstance(args, (list, tuple)) and args:
        first = os.fsdecode(args[0])
    else:
        return ""
    return PureWindowsPath(PurePath(first).name).name.lower()


def refuse_copilot(args: object) -> None:
    """Raise when ``args`` would start the Copilot CLI."""
    if program_name(args) in _COPILOT_NAMES:
        raise CopilotCallRefusedError(
            f"The local CLI smoke must not call Copilot (got {args!r}). "
            "Mark the test with requires_copilot so only the CI leg runs it."
        )


class GuardedPopen(subprocess.Popen):  # type: ignore[type-arg]
    """``subprocess.Popen`` that refuses to start the Copilot CLI.

    ``subprocess.run`` builds its process through the module's ``Popen``, so
    replacing ``subprocess.Popen`` with this subclass covers both entry points.
    A subclass keeps ``isinstance(proc, subprocess.Popen)`` true.
    """

    def __init__(self, args: Any, *rest: Any, **kwargs: Any) -> None:
        refuse_copilot(args)
        if kwargs.get("executable") is not None:
            refuse_copilot([kwargs["executable"]])
        super().__init__(args, *rest, **kwargs)


def install(setattr_fn: Callable[[object, str, object], None]) -> None:
    """Replace ``subprocess.Popen`` through ``setattr_fn``."""
    setattr_fn(subprocess, "Popen", GuardedPopen)
