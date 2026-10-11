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
import re
import shlex
import subprocess
from collections.abc import Callable, Mapping
from pathlib import PurePath, PureWindowsPath
from typing import Any

LOCAL_SMOKE_ENV = "AI_AGENTS_LOCAL_CLI_SMOKE"
_COPILOT_NAMES = frozenset({"copilot", "copilot.exe", "copilot.cmd", "copilot.bat"})
# A leading NAME=VALUE environment assignment, as in ``FOO=1 copilot``.
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# An npm package spec's version suffix, as in ``@github/copilot@1.0.91``.
_VERSION_SUFFIX = re.compile(r"(?<=.)@[^/]*$")
# Launchers that run a later word as the program, mapped to their options that
# take a separate value. ``gh copilot`` is a gh extension, not the Copilot CLI,
# so ``gh`` is not listed.
_LAUNCHERS: dict[str, frozenset[str]] = {
    "env": frozenset({"-u", "--unset", "-C", "--chdir"}),
    "sudo": frozenset({"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "--user", "--group"}),
    "npx": frozenset({"-p", "--package", "-c", "--call"}),
    "nohup": frozenset(),
    "exec": frozenset({"-a"}),
    "command": frozenset(),
}
# Options after which a launcher only looks the program up instead of running it.
_LOOKUP_OPTIONS = frozenset({"-v", "-V"})
# Shells, mapped to the option whose value is a command line to run.
_SHELLS: dict[str, frozenset[str]] = (
    {name: frozenset({"-c"}) for name in ("sh", "bash", "zsh", "dash", "ksh")}
    | {name: frozenset({"/c", "/k"}) for name in ("cmd", "cmd.exe")}
    | {
        name: frozenset({"-c", "-command"})
        for name in ("pwsh", "pwsh.exe", "powershell", "powershell.exe")
    }
)


class CopilotCallRefusedError(AssertionError):
    """Raised when the local smoke tries to start the Copilot CLI."""


def guard_active(environ: Mapping[str, str] | None = None) -> bool:
    """Return True when the local pre-push smoke marked this run."""
    source = os.environ if environ is None else environ
    return source.get(LOCAL_SMOKE_ENV) == "1"


def _words(args: object) -> list[str]:
    """Split a subprocess ``args`` value into words.

    A path object is one program path, as ``Popen`` treats it, even when the
    path holds spaces. A string is split like a shell command line.
    """
    if isinstance(args, os.PathLike):
        return [os.fsdecode(args)]
    if isinstance(args, (str, bytes)):
        text = os.fsdecode(args)
        if "\\" in text:
            return text.split()
        try:
            return shlex.split(text)
        except ValueError:
            return text.split()
    if isinstance(args, (list, tuple)):
        return [os.fsdecode(word) for word in args]
    return []


def _basename(word: str) -> str:
    name = PureWindowsPath(PurePath(word).name).name.lower()
    return _VERSION_SUFFIX.sub("", name)


def _shell_command(name: str, rest: list[str]) -> str | None:
    """Return the command line a shell runs with ``-c`` or its equivalent."""
    flags = _SHELLS[name]
    for index, word in enumerate(rest):
        if word.lower() in flags and index + 1 < len(rest):
            return rest[index + 1]
    return None


def program_name(args: object) -> str:
    """Return the lowercased basename of the program a subprocess call starts.

    Leading ``NAME=VALUE`` assignments are skipped. A launcher such as ``env``,
    ``sudo`` or ``npx`` is skipped with its flags and the values its known
    options take. A shell's ``-c`` command line is read as the real command.
    ``command -v`` only looks a program up, so it starts nothing. A version
    suffix on an npm package spec is dropped.
    """
    words = _words(args)
    launcher = ""
    index = 0
    while index < len(words):
        word = words[index]
        index += 1
        if _ASSIGNMENT.match(word):
            continue
        if word.startswith("-"):
            if launcher == "command" and word in _LOOKUP_OPTIONS:
                return ""
            index += word in _LAUNCHERS.get(launcher, frozenset())
            continue
        name = _basename(word)
        if name in _LAUNCHERS:
            launcher = name
            continue
        if name in _SHELLS:
            command = _shell_command(name, words[index:])
            return name if command is None else program_name(command)
        return name
    return ""


def refuse_copilot(args: object) -> None:
    """Raise when ``args`` would start the Copilot CLI."""
    if program_name(args) in _COPILOT_NAMES:
        raise CopilotCallRefusedError(
            f"The local CLI smoke must not call Copilot (got {args!r}). "
            "Give the test the copilot marker (the requires_copilot decorator in "
            "test_plugin_load_smoke.py and test_cli_hook_e2e.py applies it), so "
            "only the CI leg runs it."
        )


class GuardedPopen(subprocess.Popen[Any]):
    """``subprocess.Popen`` that refuses to start the Copilot CLI.

    ``subprocess.run`` builds its process through the module's ``Popen``, so
    replacing ``subprocess.Popen`` with this subclass covers both entry points.
    A subclass keeps ``isinstance(proc, subprocess.Popen)`` true.
    """

    def __init__(self, args: Any, *rest: Any, **kwargs: Any) -> None:
        refuse_copilot(args)
        # Popen's positional order is (args, bufsize, executable, ...).
        executable = kwargs.get("executable", rest[1] if len(rest) > 1 else None)
        if executable is not None:
            refuse_copilot([executable])
        super().__init__(args, *rest, **kwargs)


def install(setattr_fn: Callable[[object, str, object], None]) -> None:
    """Replace ``subprocess.Popen`` through ``setattr_fn``."""
    setattr_fn(subprocess, "Popen", GuardedPopen)
