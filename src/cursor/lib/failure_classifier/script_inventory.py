"""Recurring inline programs and scratch script files in a session.

Input is the ``FailureEvent`` list that ``events_from_records`` builds. Every
string that leaves this module passes ``redact_text`` and a length cap.
Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from collections.abc import Iterable
from dataclasses import dataclass

from .classifier import SHELL_TOOLS, FailureEvent
from .command_shape import shell_write_targets
from .workarounds import (
    COMMAND_MAX_CHARS,
    MIN_BODY_CHARS,
    MIN_GROUP_COUNT,
    SAMPLE_MAX_CHARS,
    SAMPLE_MAX_LINES,
    SCRATCH_MARKERS,
    SCRIPT_SUFFIXES,
    _call_text,
    _normalize,
    _snippet,
)

# ---------------------------------------------------------------------------
# Inline script inventory
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InlineScriptGroup:
    """An inline program seen ``count`` times, grouped by normalized body hash."""

    interpreter: str
    body_hash: str
    count: int
    sample: str
    first_index: int


@dataclass(frozen=True)
class ScratchScript:
    """A script file written under a scratch path, and how often it was used.

    ``references`` counts later shell or code-tool calls that name the file's
    base name. Two scratch files with one base name share that count.
    """

    path: str
    writes: int
    references: int
    first_index: int


@dataclass(frozen=True)
class ScriptInventory:
    inline: tuple[InlineScriptGroup, ...]
    scratch: tuple[ScratchScript, ...]


_INTERPRETERS: dict[str, str] = {
    "node": "node",
    "nodejs": "node",
    "perl": "perl",
    "ruby": "ruby",
    "bash": "shell",
    "sh": "shell",
    "zsh": "shell",
    "pwsh": "powershell",
    "powershell": "powershell",
    "deno": "deno",
    "bun": "bun",
}
_PYTHON_NAME = re.compile(r"python[\d.]*")
_LANGUAGE_NAMES: dict[str, str] = {
    "shell": "shell",
    "bash": "shell",
    "sh": "shell",
    "zsh": "shell",
    "python": "python",
    "javascript": "node",
    "js": "node",
    "typescript": "typescript",
    "ts": "typescript",
}
# A tool whose name ends this way runs the code in its ``code`` input.
_CODE_TOOL_SUFFIX = "ctx_execute"

_HEREDOC_OPEN = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1([^\n]*)\n")
_INLINE_FLAG = re.compile(
    r"""\b(?P<interp>python[\d.]*|nodejs|node|perl|ruby|bash|sh|zsh|pwsh|powershell)\b"""
    r"""(?:[ \t]+-[A-Za-z-]+)*?[ \t]+(?:-[A-Za-z]*c|-e|--eval|-command)[ \t]+"""
    r"""(?P<q>["'])(?P<body>(?:\\.|(?!(?P=q))[^\\])*)(?P=q)""",
    re.DOTALL | re.IGNORECASE,
)
_SHELL_WORD = re.compile(r"[^\s|&;()<>]+")


def _interpreter(token: str) -> str | None:
    name = posixpath.basename(token).lower()
    if _PYTHON_NAME.fullmatch(name):
        return "python"
    return _INTERPRETERS.get(name)


def _line_interpreter(prefix: str, tail: str) -> str | None:
    """The interpreter that reads a heredoc: last one before ``<<``, else after a pipe."""
    found = [i for i in map(_interpreter, _SHELL_WORD.findall(prefix)) if i]
    if found:
        return found[-1]
    for piped in tail.split("|")[1:]:
        found = [i for i in map(_interpreter, _SHELL_WORD.findall(piped)) if i]
        if found:
            return found[0]
    return None


def _heredoc_programs(command: str) -> list[tuple[str, str]]:
    programs: list[tuple[str, str]] = []
    pos = 0
    while (opener := _HEREDOC_OPEN.search(command, pos)) is not None:
        rest = command[opener.end() :]
        closer = re.search(rf"^[ \t]*{re.escape(opener.group(2))}[ \t]*$", rest, re.MULTILINE)
        body = rest[: closer.start()] if closer else rest
        pos = opener.end() + (closer.end() if closer else len(rest))
        line_start = command.rfind("\n", 0, opener.start()) + 1
        interpreter = _line_interpreter(command[line_start : opener.start()], opener.group(3))
        if interpreter and len(body.strip()) >= MIN_BODY_CHARS:
            programs.append((interpreter, body))
    return programs


def _flag_programs(command: str) -> list[tuple[str, str]]:
    programs: list[tuple[str, str]] = []
    for match in _INLINE_FLAG.finditer(command):
        interpreter = _interpreter(match.group("interp"))
        body = match.group("body")
        if interpreter and len(body.strip()) >= MIN_BODY_CHARS:
            programs.append((interpreter, body))
    return programs


def _command_programs(command: str) -> list[tuple[str, str]]:
    return _heredoc_programs(command) + _flag_programs(command)


def _code_tool_input(event: FailureEvent) -> tuple[str, str] | None:
    """The ``(language, code)`` of a code-running tool call, or None."""
    if not event.tool.endswith(_CODE_TOOL_SUFFIX) or event.input is None:
        return None
    try:
        data = json.loads(event.input)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    language, code = data.get("language"), data.get("code")
    if isinstance(language, str) and isinstance(code, str):
        return language.strip().lower(), code
    return None


def _command_text(event: FailureEvent) -> str:
    """The text a call ran: the shell command, or a code tool's code."""
    if event.tool in SHELL_TOOLS:
        return _call_text(event)
    code_input = _code_tool_input(event)
    return code_input[1] if code_input else ""


def _event_programs(event: FailureEvent) -> list[tuple[str, str]]:
    """Inline programs one call carries, as ``(interpreter, body)`` pairs."""
    if event.tool in SHELL_TOOLS:
        return _command_programs(_call_text(event))
    code_input = _code_tool_input(event)
    if code_input is None:
        return []
    language, code = code_input
    interpreter = _LANGUAGE_NAMES.get(language, language)
    if interpreter == "shell":
        embedded = _command_programs(code)
        if embedded:
            return embedded
    return [(interpreter, code)] if len(code.strip()) >= MIN_BODY_CHARS else []


def _sample(body: str) -> str:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    return _snippet(" | ".join(lines[:SAMPLE_MAX_LINES]), SAMPLE_MAX_CHARS)


@dataclass
class _Tally:
    sample: str
    first_index: int
    count: int = 0


def _inline_groups(events: list[FailureEvent]) -> list[InlineScriptGroup]:
    tallies: dict[tuple[str, str], _Tally] = {}
    for index, event in enumerate(events):
        for interpreter, body in _event_programs(event):
            digest = hashlib.sha256(_normalize(body).encode("utf-8")).hexdigest()[:12]
            key = (interpreter, digest)
            if key not in tallies:
                tallies[key] = _Tally(_sample(body), index)
            tallies[key].count += 1
    return [
        InlineScriptGroup(interpreter, digest, tally.count, tally.sample, tally.first_index)
        for (interpreter, digest), tally in tallies.items()
        if tally.count >= MIN_GROUP_COUNT
    ]


def _is_scratch_script(path: str) -> bool:
    rooted = "/" + path
    in_scratch = any(marker in rooted for marker in SCRATCH_MARKERS)
    return in_scratch and posixpath.splitext(path)[1].lower() in SCRIPT_SUFFIXES


def _written_paths(event: FailureEvent) -> list[str]:
    """Files a successful call wrote: an edit tool's target, or a shell redirect."""
    if not event.ok:
        return []
    if event.edit_tool:
        return [event.target] if event.target else []
    if event.tool in SHELL_TOOLS:
        return shell_write_targets(_call_text(event))
    return []


def _scratch_scripts(events: list[FailureEvent]) -> list[ScratchScript]:
    written: dict[str, list[int]] = {}
    for index, event in enumerate(events):
        for target in _written_paths(event):
            if _is_scratch_script(target):
                entry = written.setdefault(target, [index, 0])
                entry[1] += 1
    texts = [_command_text(event) for event in events]
    scripts: list[ScratchScript] = []
    for path, (first, writes) in written.items():
        base = re.compile(r"(?<![\w.-])" + re.escape(posixpath.basename(path)) + r"(?!\w)")
        references = sum(1 for text in texts[first + 1 :] if text and base.search(text))
        scripts.append(ScratchScript(_snippet(path, COMMAND_MAX_CHARS), writes, references, first))
    return scripts


def inline_script_inventory(events: Iterable[FailureEvent]) -> ScriptInventory:
    """Recurring inline programs, and script files written under a scratch path.

    An inline program is a heredoc body fed to an interpreter, the body of
    ``python -c``, ``node -e``, ``bash -c`` and similar, or the ``code`` of a
    code-running tool call. Bodies are grouped by a hash of the body with hex
    runs, digit runs, and whitespace normalized, and a group seen
    ``MIN_GROUP_COUNT`` times or more is reported. A scratch script is a file
    with a script suffix that a Write or Edit call, a shell redirect, or ``tee``
    wrote to a path containing ``/scratch/`` or ``/tmp/``. Both lists run in transcript order.
    """
    ordered = list(events)
    groups = sorted(_inline_groups(ordered), key=lambda group: group.first_index)
    scratch = sorted(_scratch_scripts(ordered), key=lambda script: script.first_index)
    return ScriptInventory(inline=tuple(groups), scratch=tuple(scratch))
