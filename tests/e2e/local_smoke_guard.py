"""Refuse a Copilot CLI launch during the local pre-push smoke.

The local smoke runs on the harness the developer uses, on their own login. The
pre-push gate passes ``-m "not copilot"``, which only deselects tests that carry
the ``copilot`` marker. A Copilot call added without that marker would still run
locally. This guard closes that gap: when the gate sets ``LOCAL_SMOKE_ENV``, any
``subprocess.run`` or ``subprocess.Popen`` whose program is ``copilot`` fails
the test before the process starts.

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
import re
import shlex
import subprocess
from collections.abc import Callable, Mapping
from pathlib import PurePath, PureWindowsPath
from typing import Any

LOCAL_SMOKE_ENV = "AI_AGENTS_LOCAL_CLI_SMOKE"
# A control operator ends one simple command and starts the next. Newlines are cut
# before lexing, and a backtick opens a command substitution, so both count.
_CONTROL_TOKEN = re.compile(r"^[;&|()]+$")
_OPERATOR_SPLIT = re.compile(r"&&|\|\||[;|&()`\n]")
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


class CopilotCallRefusedError(BaseException):
    """Raised when the local smoke tries to start the Copilot CLI.

    A ``BaseException`` on purpose, so a broad ``except Exception`` cannot swallow it.
    pytest still reports it as a test failure.
    """


def guard_active(environ: Mapping[str, str] | None = None) -> bool:
    """Return True when the local pre-push smoke marked this run."""
    source = os.environ if environ is None else environ
    return source.get(LOCAL_SMOKE_ENV) == "1"


def _split_line(text: str) -> list[list[str]]:
    """Split a command line into simple commands at control operators.

    ``a; b``, ``a && b``, ``a || b``, ``a | b``, ``a & b``, a subshell ``(a)``, a
    command substitution ``$(a)`` or a backtick pair, and a newline each start a
    new command. A Windows-style line (a backslash) is cut with a plain pattern,
    because POSIX quoting would eat the backslashes. A line with an unbalanced
    quote falls back to the same pattern.
    """
    if "\\" not in text:
        try:
            return _lex_line(text)
        except ValueError:
            pass
    return [part.split() for part in _OPERATOR_SPLIT.split(text) if part.strip()]


def _lex_line(text: str) -> list[list[str]]:
    commands: list[list[str]] = []
    for line in text.replace("`", ";").splitlines():
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        current: list[str] = []
        for token in lexer:
            if _CONTROL_TOKEN.match(token):
                if current:
                    commands.append(current)
                current = []
            else:
                current.append(token)
        if current:
            commands.append(current)
    return commands


def _commands(args: object) -> list[list[str]]:
    """Split a subprocess ``args`` value into simple commands, each a word list.

    A path object is one program path, as ``Popen`` treats it, even when the
    path holds spaces. A sequence is one command. A string is a command line and
    may hold several commands, as a shell would read it.
    """
    if isinstance(args, os.PathLike):
        return [[os.fsdecode(args)]]
    if isinstance(args, (str, bytes)):
        return _split_line(os.fsdecode(args))
    if isinstance(args, (list, tuple)):
        return [[os.fsdecode(word) for word in args]]
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


def _programs(words: list[str]) -> list[str]:
    """Return the programs one simple command starts: its own, or a shell's inner ones."""
    launcher = ""
    index = 0
    while index < len(words):
        word = words[index]
        index += 1
        if _ASSIGNMENT.match(word):
            continue
        if word.startswith("-"):
            if launcher == "command" and word in _LOOKUP_OPTIONS:
                return []
            index += word in _LAUNCHERS.get(launcher, frozenset())
            continue
        name = _basename(word)
        if name in _LAUNCHERS:
            launcher = name
            continue
        if name in _SHELLS:
            command = _shell_command(name, words[index:])
            return [name] if command is None else program_names(command)
        return [name]
    return []


def program_names(args: object) -> list[str]:
    """Return the lowercased basename of every program a subprocess call starts.

    A command line (a string, or a shell's ``-c`` text) can hold several commands
    joined by ``;``, ``&&``, ``||``, ``|``, ``&``, a subshell, a substitution, or a
    newline. Each one counts. Within a command, leading ``NAME=VALUE`` assignments
    are skipped. A launcher such as ``env``, ``sudo`` or ``npx`` is skipped with
    its flags and the values its known options take. ``command -v`` only looks a
    program up, so it starts nothing. A version suffix on an npm package spec is
    dropped.
    """
    return [name for words in _commands(args) for name in _programs(words)]


def program_name(args: object) -> str:
    """Return the first program a subprocess call starts, or an empty string."""
    names = program_names(args)
    return names[0] if names else ""


def refuse_copilot(args: object) -> None:
    """Raise when ``args`` would start the Copilot CLI."""
    if any(name in _COPILOT_NAMES for name in program_names(args)):
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
        # With shell=True the first item of a sequence is a command line, not a program.
        shell = kwargs.get("shell", rest[7] if len(rest) > 7 else False)
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
