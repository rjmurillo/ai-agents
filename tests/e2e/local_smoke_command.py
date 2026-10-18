"""Which programs a subprocess ``args`` value starts (used by ``local_smoke_guard``).

Reads launcher prefixes (``env``, ``sudo``, ``npx``), shell ``-c`` command lines, and
compound command lines, so the guard sees every program a call would start.

Known limits: a program started through ``eval``, a variable (``$CMD``), a script file,
a launcher outside ``_LAUNCHERS``, or a shell outside ``_SHELLS`` is not seen. A shell
option with a value other than ``-o`` or ``-O`` (``--rcfile f``) before the command line
misreads the value as the command. A quoted Windows path with a space inside a shell's
``/c`` value (``cmd /c "C:\\Program Files\\copilot.exe"``) is cut at the space. The fish
options ``-C`` and ``--init-command`` run a command line that is not read.
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
# A control operator fused with the redirection after it, as in ``;>/dev/null`` or
# ``&&>x``. shlex lexes the pair as one punctuation token.
_FUSED_REDIRECT = re.compile(r"^([;&|()]+)([<>].*)$")
_OPERATOR_SPLIT = re.compile(r"&&|\|\||[<>]\(|[;|&()`\n]")
# A word of a Windows-style line: a double-quoted span (which may hold spaces and
# operator characters, as in ``"C:\Program Files (x86)\copilot.exe"``) or any
# character that is not whitespace, a quote, or the start of an operator.
_WINDOWS_WORD = re.compile(r'(?:"[^"\n]*"|[^\s"&|;()`<>]|[<>](?!\())+')
_WINDOWS_TOKEN = re.compile(f"{_WINDOWS_WORD.pattern}|{_OPERATOR_SPLIT.pattern}")
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
# ``env`` options whose value is a whole command line: ``-S 'copilot -p x'``, the attached
# forms ``--split-string=CMD`` and ``-SCMD``, and a cluster of no-value options before ``S``
# (``-iS``, ``-vS``). Group 1 is the ``=`` value, group 2 the short-option attached value.
_SPLIT_STRING = re.compile(r"^(?:--split-string(?:=(.*))?|-[iv0]*S(.*))$", re.DOTALL)
# Positional words a launcher takes before the program: `timeout 5 copilot`.
_LEADING_POSITIONALS = {"timeout": 1}
# Shell reserved words that can lead a simple command: `then copilot`, `! copilot`.
_KEYWORDS = frozenset({"if", "then", "else", "elif", "fi", "while", "until", "do", "done"})
_KEYWORDS |= frozenset({"!", "{", "}", "case", "esac", "in", "coproc", "function"})
# fish command modifiers: `true; and copilot`, `not copilot`.
_KEYWORDS |= frozenset({"and", "or", "not"})
# A command substitution, even inside double quotes: `"$(copilot)"`, `"`copilot`"`.
_SUBSTITUTION = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
# Options after which a launcher only looks the program up instead of running it.
_LOOKUP_OPTIONS = frozenset({"-v", "-V"})
# A POSIX shell short-option cluster that holds ``c``: ``-c``, ``-lc``, ``-xc``, ``-ec``.
_C_CLUSTER = re.compile(r"^-[A-Za-z]*c[A-Za-z]*$")
# Shell options that take a separate value: ``bash -c -o pipefail 'cmd'``.
_SHELL_VALUE_OPTIONS = frozenset({"-o", "+o", "-O", "+O"})
_POSIX_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "mksh", "ash", "fish"})
# Shells, mapped to the option whose value is a command line to run.
_SHELLS: dict[str, frozenset[str]] = (
    {name: frozenset({"-c"}) for name in _POSIX_SHELLS}
    | {"fish": frozenset({"-c", "--command"})}
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
    return _windows_commands(text)


def _windows_commands(text: str) -> list[list[str]]:
    """Cut a Windows-style line at operators, keeping a double-quoted span as one word.

    POSIX quoting would eat the backslashes, so this reads quotes by hand: a quoted path
    with spaces or parentheses stays whole, and its quotes are dropped.
    """
    commands: list[list[str]] = []
    current: list[str] = []
    for token in _WINDOWS_TOKEN.findall(text):
        if _OPERATOR_SPLIT.fullmatch(token):
            if current:
                commands.append(current)
            current = []
        else:
            current.append(token.replace('"', ""))
    if current:
        commands.append(current)
    return commands


def _split_fused(token: str) -> tuple[str, str] | None:
    """Split ``;>`` into the control operator and the redirection, or return None.

    A lone trailing ``&`` before ``>`` is the ``&>`` redirection, not a background
    operator: ``true&>x copilot`` runs ``true`` with ``copilot`` as an argument.
    """
    match = _FUSED_REDIRECT.match(token)
    if not match:
        return None
    control, redirect = match.groups()
    trailing = len(control) - len(control.rstrip("&"))
    if trailing % 2 and not control[: len(control) - trailing].endswith("|"):
        control, redirect = control[:-1], "&" + redirect
    return (control, redirect) if control else None


def _lex_line(text: str) -> list[list[str]]:
    commands: list[list[str]] = []
    for line in text.replace("`", ";").splitlines():
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        current: list[str] = []
        for token in lexer:
            fused = None if _PROCESS_OPEN.match(token) else _split_fused(token)
            if _CONTROL_TOKEN.match(token) or _PROCESS_OPEN.match(token) or fused:
                if current:
                    commands.append(current)
                current = [fused[1]] if fused else []
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
    """Return the command line a shell runs with ``-c`` or its equivalent.

    A POSIX shell reads the command from the first non-option word after ``-c``, so
    later options (``-x``, ``+e``, ``-o pipefail``) and one ``--`` are skipped.
    """
    flags = _SHELLS[name]
    posix = name in _POSIX_SHELLS
    for index, word in enumerate(rest):
        option, equals, value = word.partition("=")
        if equals and option.startswith("--") and option.lower() in flags:
            return value
        is_flag = word.lower() in flags or (posix and _C_CLUSTER.match(word) is not None)
        if not is_flag:
            continue
        if posix:
            return _first_operand(rest[index + 1 :])
        if index + 1 < len(rest):
            return rest[index + 1]
    return None


def _first_operand(words: list[str]) -> str | None:
    """Return the first non-option word, skipping options and one leading ``--``."""
    index = 0
    while index < len(words):
        word = words[index]
        if word == "--":
            return words[index + 1] if index + 1 < len(words) else None
        if not word.startswith(("-", "+")):
            return word
        index += 1 + (word in _SHELL_VALUE_OPTIONS)
    return None


def _after_prefix(words: list[str], index: int, word: str) -> int | None:
    """Return the index past a ``NAME=VALUE`` or redirection ``word``, or None if it is neither.

    ``index`` is the position after ``word``. A redirection target is the next word unless
    it is attached to the operator (``>/dev/null``). A bare fd number (``2``) belongs to
    the redirection word after it.
    """
    if _ASSIGNMENT.match(word):
        return index
    redirect = _REDIRECT.match(word)
    if redirect:
        return index + (not redirect.group(1))
    if word.isdigit() and index < len(words) and _REDIRECT.match(words[index]):
        return index
    return None


def _option_command_line(launcher: str, word: str, following: list[str]) -> str | None:
    """Return the command line a launcher option carries, or None if it carries none.

    ``command -v`` only looks a program up, so its command line is empty. ``env`` splits the
    value of ``-S`` into words and runs them followed by the words after the option, so the
    returned line holds both.
    """
    if launcher == "command" and word in _LOOKUP_OPTIONS:
        return ""
    match = _SPLIT_STRING.match(word) if launcher == "env" else None
    if not match:
        return None
    attached = match.group(1) if match.group(1) is not None else (match.group(2) or "")
    if attached:
        return f"{attached} {shlex.join(following)}"
    value = following[0] if following else ""
    return f"{value} {shlex.join(following[1:])}"


def _programs(words: list[str]) -> list[str]:
    """Return the programs one simple command starts: its own, or a shell's inner ones."""
    launcher = ""
    positionals = 0
    index = 0
    while index < len(words):
        word = words[index]
        index += 1
        after = _after_prefix(words, index, word)
        if after is not None:
            index = after
            continue
        if word.startswith("-"):
            inner = _option_command_line(launcher, word, words[index:])
            if inner is not None:
                return program_names(inner)
            index += word in _LAUNCHERS.get(launcher, frozenset())
            continue
        name = _basename(word)
        if positionals:
            positionals -= 1
            continue
        if name in _KEYWORDS:
            # ``function NAME`` declares a function: skip the name, so the body is read.
            index += name == "function"
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
    skipped with their targets, even when fused to an operator (``;>x``). A process
    substitution ``<(...)`` starts a command. A POSIX shell option cluster holding
    ``c`` (``-lc``) counts as ``-c``, and later options and one ``--`` are skipped.
    ``command -v`` only looks a program up, so it starts nothing.
    A version suffix on an npm package spec is dropped.
    """
    return [name for words in _commands(args) for name in _programs(words)]


def program_name(args: object) -> str:
    """Return the first program a subprocess call starts, or an empty string."""
    names = program_names(args)
    return names[0] if names else ""
