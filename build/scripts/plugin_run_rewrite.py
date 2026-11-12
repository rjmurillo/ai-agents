"""Rewrite legacy plugin-root invocations into the ADR-121 locator, as pure text.

The legacy form is::

    python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/NAME/.../FILE.py" ARGS

:func:`rewrite_text` replaces each such site with
``plugin_run_launcher.render_locator("skills/NAME/.../FILE.py", ARGS)``. ARGS stays
as written, minus the whitespace around it.

The locator wraps the command in a subshell and ends it with ``; fi; done; echo ...;
exit 2``. A site is safe to wrap only when the locator can stand where the legacy
command stood and ARGS ends where the command ends. The function refuses every
other site and says why, so a person finishes it by hand:

* the site spans a line continuation;
* the interpreter carries an option (``-I``, ``-u``) or is not ``python3``;
* the interpreter is not in command position (``VAR=1 python3``, ``xargs python3``,
  ``bash -c '...'``), where a subshell would be a syntax error;
* the site is prose, not a fenced block or an inline code span;
* ARGS holds a shell operator (``|``, ``;``, ``&&``, a bare ``&``, a parenthesis, a
  heredoc, a trailing comment), which would end up inside the loop instead of
  after it. Redirections such as ``2>&1`` and a ``$(...)`` substitution are fine;
* the line assigns a variable from the nested form. The locator takes the target
  in one command, so an assignment needs a person (ADR-121, assignment sites).

The text of a line that holds no accepted site is returned byte for byte. Running the
function on its own output changes nothing.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
for _entry in (_SCRIPT_DIR, _REPO_ROOT):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import plugin_run_launcher  # noqa: E402

from scripts.validation import plugin_root_interpreter_sites as sites  # noqa: E402

NESTED_ROOT = "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"
ASSIGNMENT_REASON = (
    "assignment from the nested form: rewrite each follow-on call to the locator and "
    "delete the assignment by hand"
)

_STRICT_SITE = re.compile(
    r'python3 "' + re.escape(NESTED_ROOT) + r'/(?P<script>skills/[A-Za-z0-9_./-]+\.py)"'
)
_OPTION_AFTER_INTERPRETER = re.compile(r"python3[ \t]+-")
_SHELL_C = re.compile(r"\b(?:ba|z|da)?sh[ \t]+-\w*c\b")
_PROMPT_OR_MARKERS = re.compile(r"[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]+|>[ \t]*)*(?:\$[ \t]+)?")
_CHAINERS = ("&&", "||", ";", "|")
_FENCE = re.compile(r"(`{3,}|~{3,})")
_BACKTICK = "`"


@dataclass(frozen=True, slots=True)
class Refusal:
    """One site the rewrite left alone, with the 1-indexed line and the reason."""

    lineno: int
    reason: str


@dataclass(frozen=True, slots=True)
class Rewrite:
    """The rewritten text, the sites fixed, and the sites refused."""

    text: str
    fixed: int
    refusals: tuple[Refusal, ...]


@dataclass(frozen=True, slots=True)
class _Edit:
    start: int
    end: int
    replacement: str


def _fenced_lines(contents: list[str]) -> set[int]:
    """Return the 1-indexed lines inside a fenced code block, fence lines excluded."""
    fenced: set[int] = set()
    opener: str | None = None
    for number, line in enumerate(contents, start=1):
        stripped = line.lstrip()
        marker = _FENCE.match(stripped)
        if opener is None:
            opener = marker.group(1) if marker else None
        elif marker and _closes(marker.group(1), opener, stripped):
            opener = None
        else:
            fenced.add(number)
    return fenced


def _closes(marker: str, opener: str, stripped: str) -> bool:
    return (
        marker[0] == opener[0]
        and len(marker) >= len(opener)
        and not stripped[len(marker) :].strip()
    )


def _quoted_end(args: str, index: int) -> int | None:
    """Return the index past the quote that opens at ``index``, or ``None`` if unclosed."""
    quote = args[index]
    pos = index + 1
    while pos < len(args):
        if args[pos] == "\\" and quote == '"':
            pos += 2
            continue
        if args[pos] == quote:
            return pos + 1
        pos += 1
    return None


def _operator_reason(args: str, index: int, word_start: bool) -> str | None:
    char = args[index]
    if char in "|;":
        return f"ARGS holds the shell operator {char!r}"
    if char == "&" and not (
        args[index - 1 : index] in ("<", ">") or args[index + 1 : index + 2] == ">"
    ):
        return "ARGS holds a bare '&'"
    if char in "()":
        return "ARGS holds a parenthesis outside $(...)"
    if char == "#" and word_start:
        return "ARGS holds a comment, which would swallow the end of the locator"
    if args.startswith("<<", index):
        return "ARGS holds a heredoc"
    return None


def args_refusal(args: str) -> str | None:
    """Return why ``args`` cannot move inside the locator, or ``None`` when it can.

    ``args`` is POSIX shell text. Quoted spans and ``$(...)`` substitutions are
    opaque. A shell operator outside them would end the locator's ``exec`` early.
    """
    depth, index, word_start = 0, 0, True
    while index < len(args):
        char = args[index]
        if char == "\\":
            if index + 1 >= len(args):
                return "ARGS ends in a backslash"
            index, word_start = index + 2, False
        elif char in "'\"":
            end = _quoted_end(args, index)
            if end is None:
                return "ARGS holds an unclosed quote"
            index, word_start = end, False
        elif args.startswith("$(", index):
            depth, index, word_start = depth + 1, index + 2, False
        elif depth and char == ")":
            depth, index = depth - 1, index + 1
        elif depth:
            index += 1
        else:
            reason = _operator_reason(args, index, word_start)
            if reason is not None:
                return reason
            word_start, index = char.isspace(), index + 1
    return "ARGS holds an unclosed $(" if depth else None


def _head_problem(line: str, inv: sites.Invocation) -> re.Match[str] | str:
    """Return the strict site match at ``inv``, or the reason the head has another shape."""
    if inv.interp != "python3":
        return f"interpreter is {inv.interp!r}, not python3"
    match = _STRICT_SITE.match(line, inv.start)
    if match is not None:
        return match
    if _OPTION_AFTER_INTERPRETER.match(line, inv.start):
        return "interpreter option before the script path"
    return 'operand is not the single quoted path "ROOT/skills/...py"'


def _command_position_problem(prefix: str) -> str | None:
    if _SHELL_C.search(prefix):
        return "inside a shell -c string"
    at_start = _PROMPT_OR_MARKERS.fullmatch(prefix) is not None
    if at_start or prefix.endswith(_BACKTICK) or prefix.rstrip().endswith(_CHAINERS):
        return None
    return f"interpreter is not in command position (follows {prefix.strip()[-24:]!r})"


def _context_problem(prefix: str, fenced: bool) -> str | None:
    """Return why the site is not inside a fenced block or an inline code span."""
    if fenced or prefix.count(_BACKTICK) % 2 == 1:
        return None
    return "site is outside a code span and a fenced block"


def _split_args(rest: str, fenced: bool) -> tuple[str, str] | str:
    """Split the text after the script path into ``(args, kept)`` or return a refusal."""
    if rest and not (rest[0].isspace() or rest[0] == _BACKTICK):
        return "text follows the script path with no space"
    if fenced:
        return rest.strip(), ""
    close = rest.find(_BACKTICK)
    if close == -1:
        return "code span does not close on this line"
    return rest[:close].strip(), rest[close:]


def _plan_site(line: str, inv: sites.Invocation, fenced: bool) -> _Edit | str:
    """Return the edit that turns one legacy site into the locator, or why it cannot."""
    head = _head_problem(line, inv)
    if isinstance(head, str):
        return head
    prefix = line[: inv.start]
    problem = _context_problem(prefix, fenced) or _command_position_problem(prefix)
    if problem is not None:
        return problem
    split = _split_args(line[head.end() :], fenced)
    if isinstance(split, str):
        return split
    args, kept = split
    problem = args_refusal(args)
    if problem is not None:
        return problem
    try:
        locator = plugin_run_launcher.render_locator(head.group("script"), args)
    except plugin_run_launcher.LauncherError as exc:
        return str(exc)
    return _Edit(inv.start, len(line) - len(kept), locator)


def _rewrite_line(
    line: str, found: list[sites.Invocation], fenced: bool, lineno: int
) -> tuple[str, int, list[Refusal]]:
    """Rewrite the sites of one physical line, last first so earlier offsets hold."""
    refusals: list[Refusal] = []
    fixed = 0
    for inv in sorted(found, key=lambda item: item.start, reverse=True):
        plan = _plan_site(line, inv, fenced)
        if isinstance(plan, str):
            refusals.append(Refusal(lineno, plan))
            continue
        line = line[: plan.start] + plan.replacement + line[plan.end :]
        fixed += 1
    return line, fixed, refusals


def _split_eol(raw: str) -> tuple[str, str]:
    """Split one ``splitlines(keepends=True)`` line into its content and its terminator."""
    content = raw.splitlines()[0]
    return content, raw[len(content) :]


def rewrite_text(text: str) -> Rewrite:
    """Rewrite every fixable legacy site in ``text``; report the rest."""
    split = [_split_eol(raw) for raw in text.splitlines(keepends=True)]
    contents = [content for content, _ in split]
    fenced = _fenced_lines(contents)
    refusals = [
        Refusal(number, ASSIGNMENT_REASON)
        for number, content in enumerate(contents, start=1)
        if sites.ASSIGNMENT_RE.search(content)
    ]
    fixed = 0
    logical_lines, line_maps = sites.join_continuations(text)
    for logical, char_map in zip(logical_lines, line_maps, strict=True):
        found = list(sites.find_legacy_invocations(logical))
        if not found:
            continue
        first, last = char_map[0], char_map[-1]
        if first != last or contents[last - 1].endswith("\\"):
            refusals += [Refusal(first, "site spans a line continuation") for _ in found]
            continue
        contents[first - 1], count, refused = _rewrite_line(
            contents[first - 1], found, first in fenced, first
        )
        fixed += count
        refusals += refused
    new_text = "".join(content + eol for content, (_, eol) in zip(contents, split, strict=True))
    return Rewrite(new_text, fixed, tuple(sorted(refusals, key=lambda r: r.lineno)))
