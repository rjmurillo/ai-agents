# _split_command and _strip_unquoted_redirections are lexer state machines: one
# branch per quoting state, per escape form, and per redirection shape. Each
# branch is a distinct lexical state with its own fail-closed reason, so
# collapsing them into a table would merge states that must stay separable.
# taste-lint: ignore complexity, flattening would merge lexical states.
"""Shell lexing primitives for the push-pr identity guard (issue #4764).

Owns the command-text layer: the POSIX-subset tokenizer, redirection
stripping, segment splitting on shell operators, and the small predicates that
read one token (assignment, command name, expansion markers). Nothing here
touches the filesystem or policy; the layers above decide what a token means.

``_split_command`` is the single parser. Every caller works from its
:class:`ShellToken` output rather than re-splitting text, so quoting state
cannot desynchronize between the relevance gate and the policy check.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

_SHELL_EXPANSION_MARKERS = ("$", "`", "\\\n", "{", "[", "*", "?")


_NEW_PR_TARGET = "new_pr.py"


class GuardViolationError(ValueError):
    """A command shape the push-pr identity policy rejects."""


class ShellToken(NamedTuple):
    """One shell word with both source spelling and interpreted value."""

    raw: str
    value: str


def _split_command(command: str) -> list[ShellToken]:
    tokens: list[ShellToken] = []
    raw: list[str] = []
    value: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(command):
        char = command[index]
        if char in "\r\n\0":
            raise GuardViolationError("command contains a line break or null byte")
        if quote == "'":
            raw.append(char)
            if char == "'":
                quote = None
            else:
                value.append(char)
            index += 1
            continue
        if quote == '"':
            raw.append(char)
            if char == '"':
                quote = None
            elif char == "`":
                raise GuardViolationError("command substitution is not allowed")
            elif char == "$" and command[index + 1 : index + 2] == "(":
                raise GuardViolationError("command substitution is not allowed")
            elif char == "\\":
                index += 1
                if index >= len(command):
                    raise GuardViolationError("command has incomplete shell quoting")
                raw.append(command[index])
                if command[index] in {"$", "`", '"', "\\"}:
                    value.append(command[index])
                else:
                    value.extend(("\\", command[index]))
            else:
                value.append(char)
            index += 1
            continue
        if char.isspace():
            if raw:
                tokens.append(ShellToken("".join(raw), "".join(value)))
                raw.clear()
                value.clear()
            index += 1
            continue
        if char == "\\":
            raw.append(char)
            index += 1
            if index >= len(command):
                raise GuardViolationError("command has incomplete shell quoting")
            raw.append(command[index])
            value.append(command[index])
            index += 1
            continue
        if char in ("'", '"'):
            raw.append(char)
            quote = char
        elif char in ";&|<>()":
            raise GuardViolationError("shell operators are not allowed")
        elif char == "`":
            raise GuardViolationError("command substitution is not allowed")
        elif char == "#" and not raw:
            raise GuardViolationError("shell comments are not allowed")
        else:
            raw.append(char)
            value.append(char)
        index += 1

    if quote is not None:
        raise GuardViolationError("command has incomplete shell quoting")
    if raw:
        tokens.append(ShellToken("".join(raw), "".join(value)))
    return tokens


def _could_target_new_pr(value: str) -> bool:
    literal = value.replace("\\\r\n", "").replace("\\\n", "").casefold()
    variants = {literal, literal.replace("\\", "/"), literal.replace("\\", "")}
    for normalized in variants:
        compacted = normalized.translate(str.maketrans("", "", "'\"+ \t"))
        if "new_pr.py" in compacted:
            return True
    return False


def _contains_shell_expansion(value: str) -> bool:
    return any(marker in value for marker in _SHELL_EXPANSION_MARKERS)


def _strip_unquoted_redirections(command: str) -> str:
    """Remove redirections that sit outside quotes.

    ``_split_command`` rejects ``<`` and ``>`` as policy, and a rejected
    segment used to be skipped, so ``./attacker/pr/?ew_pr.py >out`` reached no
    relevance rule (issue #4825). A redirection never changes which file runs,
    so dropping it preserves execution position while letting the segment
    parse. Quoted text is copied through untouched, because a redirection
    operator inside quotes is data.
    """
    out: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(command):
        char = command[index]
        if quote is None and char == "\\":
            out.append(char)
            if index + 1 < len(command):
                out.append(command[index + 1])
                index += 2
                continue
            index += 1
            continue
        if quote is not None:
            out.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "'\"":
            quote = char
            out.append(char)
            index += 1
            continue
        if char in "<>":
            while out and out[-1].isdigit():
                out.pop()
            while index < len(command) and command[index] in "<>&":
                index += 1
            while index < len(command) and command[index] in " \t":
                index += 1
            while index < len(command) and command[index] not in " \t;&|<>\n":
                index += 1
            out.append(" ")
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _split_shell_segments(command: str) -> list[str]:
    """Split on shell operators that sit outside quotes.

    A regex split matched operators inside quoted arguments, so
    ``./attacker/pr/?ew_pr.py "x && y"`` was torn into fragments that no longer
    parsed and the execution was never classified (issue #4825).
    """
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(command):
        char = command[index]
        if quote is None and char == "\\":
            current.append(char)
            if index + 1 < len(command):
                current.append(command[index + 1])
                index += 2
                continue
            index += 1
            continue
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "'\"":
            quote = char
            current.append(char)
            index += 1
            continue
        if char in ";&|\n":
            segments.append("".join(current))
            current = []
            if index + 1 < len(command) and command[index + 1] == char:
                index += 1
            index += 1
            continue
        current.append(char)
        index += 1
    segments.append("".join(current))
    return segments


def _contains_active_parameter_expansion(raw: str) -> bool:
    quote: str | None = None
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "\\" and quote != "'":
            index += 2
            continue
        if char == "'":
            quote = None if quote == "'" else "'" if quote is None else quote
        elif char == '"':
            quote = None if quote == '"' else '"' if quote is None else quote
        elif char in {"$", "`"} and quote != "'":
            return True
        index += 1
    return False


def _contains_active_shell_expansion(raw: str) -> bool:
    quote: str | None = None
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "\\" and quote != "'":
            index += 2
            continue
        if char == "'":
            quote = None if quote == "'" else "'" if quote is None else quote
        elif char == '"':
            quote = None if quote == '"' else '"' if quote is None else quote
        elif char in {"$", "`"} and quote != "'":
            return True
        elif quote is None and char in {"{", "[", "*", "?", "~"}:
            return True
        index += 1
    return False


def _is_assignment(token: str) -> bool:
    name, separator, _ = token.partition("=")
    return bool(separator and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name))


def _command_name(value: str) -> str:
    return Path(value).name.casefold().removesuffix(".exe")


def _unversioned_command_name(value: str) -> str:
    return re.sub(
        r"[._-]?\d+(?:\.\d+)*(?:[a-z][a-z0-9.-]*)?$",
        "",
        _command_name(value),
    ).rstrip("._-")
