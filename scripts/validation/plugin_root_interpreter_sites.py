"""Find the plugin-root command sites that check_plugin_root_interpreter.py judges.

A site is text that runs a plugin script. Two forms exist (ADR-121):

* The **legacy form**: an interpreter token followed by an operand that starts
  with ``${COPILOT_PLUGIN_ROOT`` or ``${CLAUDE_PLUGIN_ROOT``, quoted or bare.
  ``python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/x/scripts/y.py"``
* The **locator**: the shell text ``build/scripts/plugin_run_launcher.py`` renders.
  The script path sits in the text after the resolver path.

This module only finds sites. It reads no files and judges nothing, so the
validator, the ratchet, and ``build/scripts/plugin_run_fix.py`` share one
definition of what a site is. A backslash-newline continuation is collapsed
before matching, and each match maps back to the source line the reader would
open.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

_BUILD_SCRIPTS = Path(__file__).resolve().parents[2] / "build" / "scripts"
if str(_BUILD_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_BUILD_SCRIPTS))

import plugin_run_launcher  # noqa: E402

PLUGIN_ROOT_VARS = ("COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT")

# One interpreter token: `python`, `python3`, or a pinned `python3.11`-style
# name. Matched identically inside and outside a `uv run` prefix so both
# offending shapes (`uv run python`, bare `python3.11`) are recognized by one
# sub-pattern.
_INTERP_TOKEN = r"python3?(?:\.\d+)?"

# The interpreter phrase, up to and including the opening `${` of a
# plugin-root variable reference. Two alternatives:
#   - `uv run [uv options/values] python[3]` (always a rule-1 violation); the
#     option tokens exclude shell separators so `uv run pytest; python3 ...`
#     stays one canonical invocation, not a `uv run` one
#   - a bare interpreter token (canonical only when it is exactly `python3`)
# Either is optionally followed by short options (`-u`, `-B`), then the
# operand: an optional opening quote, then the literal `${COPILOT_PLUGIN_ROOT`
# or `${CLAUDE_PLUGIN_ROOT`. `\b` stops the variable-name match before the
# `:-` fallback separator so the balanced-brace scan below starts from a known
# position.
INTERP_PHRASE = (
    r"(?<![\w./-])"
    r"(?P<interp>"
    rf"uv[ \t]+run(?:[ \t]+[^\s;&|`]+)*?[ \t]+{_INTERP_TOKEN}"
    r"|"
    rf"{_INTERP_TOKEN}"
    r")"
    r"(?:[ \t]+-[\w-]+)*"
    r"[ \t]+"
    r'(?P<quote>["\'])?'
)
_INVOCATION_HEAD = re.compile(INTERP_PHRASE + r"\$\{(?:" + "|".join(PLUGIN_ROOT_VARS) + r")\b")

# The `skills/...py` tail once the plugin-root expansion is behind us.
_PATH_TAIL = re.compile(r"/skills/[A-Za-z0-9_./-]*\.py")

# An assignment from the nested form, such as `SCRIPTS_DIR=...`. The pattern is
# the one ADR-121 prints for its inventory, so a count here and a `git grep -nE`
# count agree. It matches one physical line.
ASSIGNMENT_RE = re.compile(r"^\s*[A-Za-z_]+=.*COPILOT_PLUGIN_ROOT:-\$\{CLAUDE_PLUGIN_ROOT:-")

LEGACY = "legacy"
LOCATOR = "locator"


@dataclass(frozen=True, slots=True)
class Invocation:
    """One recognized plugin-root command on a single logical line."""

    start: int
    interp: str
    tail: str  # e.g. "skills/foo/scripts/bar.py" (leading "/" stripped)
    form: str = LEGACY
    problem: str | None = None  # set on a locator that does not read back


def match_balanced_braces(line: str, start: int) -> int | None:
    """Return the index just past the ``}`` that closes the brace before ``start``.

    ``start`` is the position right after ``${VARNAME`` was matched, so one
    brace is already open (``depth`` begins at 1). The fallback chain nests one
    level deep (``${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}``);
    this scans character by character rather than assuming a fixed nesting
    depth, so it tolerates a bare ``${VAR}`` or a deeper chain equally.
    Returns ``None`` when the line ends before the brace closes (malformed or
    truncated input), which the caller treats as "not an invocation".
    """
    depth = 1
    index = start
    length = len(line)
    while index < length:
        char = line[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return None


def find_legacy_invocations(line: str) -> Iterator[Invocation]:
    """Yield every legacy-form plugin-root invocation on one logical line."""
    pos = 0
    while True:
        match = _INVOCATION_HEAD.search(line, pos)
        if match is None:
            return
        pos = match.end()
        brace_end = match_balanced_braces(line, match.end())
        if brace_end is None:
            continue
        quote = match.group("quote")
        quote_closes_at_brace = quote is not None and line[brace_end : brace_end + 1] == quote
        path_start = brace_end + 1 if quote_closes_at_brace else brace_end
        tail_match = _PATH_TAIL.match(line, path_start)
        if tail_match is None:
            continue
        tail_end = tail_match.end()
        if quote is not None and not quote_closes_at_brace:
            # Whole-operand quoting: the closing quote must follow the path.
            if line[tail_end : tail_end + 1] != quote:
                continue
        yield Invocation(
            start=match.start(),
            interp=match.group("interp"),
            tail=tail_match.group(0).lstrip("/"),
        )


def find_locator_invocations(line: str) -> Iterator[Invocation]:
    """Yield every locator on one logical line, with its target read out of the text.

    A locator that no longer reads back (a bad target, a missing end) is yielded
    with ``problem`` set, so the validator reports it instead of skipping it.
    """
    for match in plugin_run_launcher.find_locators(line):
        yield Invocation(
            start=match.start,
            interp="python3",
            tail=match.script_rel or "",
            form=LOCATOR,
            problem=match.problem,
        )


def find_invocations(line: str) -> Iterator[Invocation]:
    """Yield every plugin-root invocation on one logical line, legacy form then locator."""
    yield from find_legacy_invocations(line)
    yield from find_locator_invocations(line)


def join_continuations(text: str) -> tuple[list[str], list[list[int]]]:
    """Collapse backslash-newline continuations; keep each char's source line.

    Returns parallel lists: logical lines with continuations joined, and for
    each logical line a same-length list mapping every character index back to
    the 1-indexed original line it came from. A regex match against a logical
    line can then be attributed to the real line the reader would open.
    """
    logical_lines: list[str] = []
    line_no_maps: list[list[int]] = []
    parts: list[str] = []
    char_map: list[int] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if raw.endswith("\\"):
            content = raw[:-1]
            parts.append(content)
            char_map.extend([lineno] * len(content))
            continue
        parts.append(raw)
        char_map.extend([lineno] * len(raw))
        logical_lines.append("".join(parts))
        line_no_maps.append(char_map)
        parts, char_map = [], []
    if parts:  # trailing continuation with no following line to close it
        logical_lines.append("".join(parts))
        line_no_maps.append(char_map)
    return logical_lines, line_no_maps


def lineno_at(char_map: list[int], index: int) -> int:
    """Return the source line of the character at ``index`` in a logical line."""
    if not char_map:
        return 1
    if index < len(char_map):
        return char_map[index]
    return char_map[-1]


@dataclass(frozen=True, slots=True)
class LegacyCounts:
    """Legacy-form sites in one file: invocations, and assignments from the nested form."""

    invocations: int = 0
    assignments: int = 0


def count_legacy_sites(text: str) -> LegacyCounts:
    """Count the legacy-form invocations and assignment lines in ``text``.

    A suppression marker (``plugin-root-interpreter:``) hides an offense from the
    validator. It does not hide a site, so a marked site still counts.
    """
    logical_lines, _ = join_continuations(text)
    invocations = sum(1 for line in logical_lines for _ in find_legacy_invocations(line))
    assignments = sum(1 for line in text.splitlines() if ASSIGNMENT_RE.search(line))
    return LegacyCounts(invocations, assignments)
