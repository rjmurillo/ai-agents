"""Which programs a subprocess ``args`` value starts (used by ``local_smoke_guard``).

Reads launcher prefixes (``env``, ``sudo``, ``npx``), shell ``-c`` command lines, and
compound command lines, so the guard sees every program a call would start.

Known limits: a program started through ``eval``, a variable (``$CMD``), a script file,
or a launcher outside ``_LAUNCHERS`` is not seen.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import PurePath, PureWindowsPath

# A control operator ends one simple command and starts the next. Newlines are cut
# before lexing, and a backtick opens a command substitution, so both count.
_CONTROL_TOKEN = re.compile(r"^[;&|()]+$")
# A process substitution opener, ``<(`` or ``>(``, starts a command too. shlex lexes
# it as one punctuation token, so the control pattern above does not see it.
_PROCESS_OPEN = re.compile(r"^[;&|()<>]*[<>]\($")
_OPERATOR_SPLIT = re.compile(r"&&|\|\||[<>]\(|[;|&()`\n]")
# A redirection: an optional fd number or ``&``, the operator, then a target that
# is either attached (``>/dev/null``) or the next word (``> /dev/null``).
_REDIRECT = re.compile(r"^(?:\d*|&)(?:<<<|<<-?|<>|>>|>\||[<>]&?)(.*)$")
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
    "time": frozenset(),
    "timeout": frozenset({"-s", "--signal", "-k", "--kill-after"}),
    "nice": frozenset({"-n", "--adjustment"}),
    "ionice": frozenset({"-c", "-n", "-p"}),
    "stdbuf": frozenset(),
    "setsid": frozenset(),
    "xargs": frozenset({"-I", "-n", "-P", "-s", "-d", "-a", "-E", "-L"}),
    "watch": frozenset({"-n", "--interval", "-q", "--equexit"}),
    "busybox": frozenset(),
}
# Launchers whose program word may be a whole command line: ``watch 'copilot -p x'``.
_COMMAND_LINE_LAUNCHERS = frozenset({"watch"})
# Positional words a launcher takes before the program: `timeout 5 copilot`.
_LEADING_POSITIONALS = {"timeout": 1}
# Shell reserved words that can lead a simple command: `then copilot`, `! copilot`.
_KEYWORDS = frozenset({"if", "then", "else", "elif", "fi", "while", "until", "do", "done"})
_KEYWORDS |= frozenset({"!", "{", "}", "case", "esac", "in", "coproc"})
# A command substitution, even inside double quotes: `"$(copilot)"`, `"`copilot`"`.
_SUBSTITUTION = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
# Options after which a launcher only looks the program up instead of running it.
_LOOKUP_OPTIONS = frozenset({"-v", "-V"})
# A POSIX shell short-option cluster that holds ``c``: ``-c``, ``-lc``, ``-xc``, ``-ec``.
_C_CLUSTER = re.compile(r"^-[A-Za-z]*c[A-Za-z]*$")
_POSIX_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})
# Shells, mapped to the option whose value is a command line to run.
_SHELLS: dict[str, frozenset[str]] = (
    {name: frozenset({"-c"}) for name in _POSIX_SHELLS}
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
    new command. A substitution inside double quotes is read too. A Windows-style
    line (a backslash) is cut with a plain pattern, because POSIX quoting would eat
    the backslashes. A line with an unbalanced quote falls back to the same pattern.
    """
    commands = _cut_line(text)
    for match in _SUBSTITUTION.finditer(text):
        for inner in match.groups():
            if inner:
                commands.extend(_split_line(inner))
    return commands


def _cut_line(text: str) -> list[list[str]]:
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
            if _CONTROL_TOKEN.match(token) or _PROCESS_OPEN.match(token):
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
    posix = name in _POSIX_SHELLS
    for index, word in enumerate(rest):
        is_flag = word.lower() in flags or (posix and _C_CLUSTER.match(word) is not None)
        if is_flag and index + 1 < len(rest):
            return rest[index + 1]
    return None


def _programs(words: list[str]) -> list[str]:
    """Return the programs one simple command starts: its own, or a shell's inner ones."""
    launcher = ""
    positionals = 0
    index = 0
    while index < len(words):
        word = words[index]
        index += 1
        if _ASSIGNMENT.match(word):
            continue
        redirect = _REDIRECT.match(word)
        if redirect:
            # The target is the next word unless it is attached to the operator.
            index += not redirect.group(1)
            continue
        if word.isdigit() and index < len(words) and _REDIRECT.match(words[index]):
            continue
        if word.startswith("-"):
            if launcher == "command" and word in _LOOKUP_OPTIONS:
                return []
            index += word in _LAUNCHERS.get(launcher, frozenset())
            continue
        name = _basename(word)
        if positionals:
            positionals -= 1
            continue
        if name in _KEYWORDS:
            continue
        if name in _LAUNCHERS:
            launcher = name
            positionals = _LEADING_POSITIONALS.get(name, 0)
            continue
        if name in _SHELLS:
            command = _shell_command(name, words[index:])
            return [name] if command is None else program_names(command)
        if launcher in _COMMAND_LINE_LAUNCHERS and " " in word:
            return program_names(word)
        return [name]
    return []


def program_names(args: object) -> list[str]:
    """Return the lowercased basename of every program a subprocess call starts.

    A command line (a string, or a shell's ``-c`` text) can hold several commands
    joined by ``;``, ``&&``, ``||``, ``|``, ``&``, a subshell, a substitution, or a
    newline. Each one counts, and so does a substitution inside double quotes.
    Within a command, leading ``NAME=VALUE`` assignments and shell reserved words
    (``then``, ``do``, ``!``, ``{``) are skipped. A launcher such as ``env``,
    ``sudo``, ``time``, ``timeout`` or ``xargs`` is skipped with its flags and the
    values its known options take. Redirections (``> out``, ``2>&1``) are
    skipped with their targets, a process substitution ``<(...)`` starts a command,
    and a POSIX shell option cluster holding ``c`` (``-lc``) counts as ``-c``.
    ``command -v`` only looks a program up, so it
    starts nothing. A version suffix on an npm package spec is dropped.
    """
    return [name for words in _commands(args) for name in _programs(words)]


def program_name(args: object) -> str:
    """Return the first program a subprocess call starts, or an empty string."""
    names = program_names(args)
    return names[0] if names else ""
