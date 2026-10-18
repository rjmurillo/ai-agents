"""Which programs a subprocess ``args`` value starts (used by ``local_smoke_guard``).

Reads launcher prefixes (``env``, ``sudo``, ``npx``), shell ``-c`` command lines, and
compound command lines, so the guard sees every program a call would start.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import PurePath, PureWindowsPath

# A control operator ends one simple command and starts the next. Newlines are cut
# before lexing, and a backtick opens a command substitution, so both count.
_CONTROL_TOKEN = re.compile(r"^[;&|()]+$")
_OPERATOR_SPLIT = re.compile(r"&&|\|\||[;|&()`\n]")
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
