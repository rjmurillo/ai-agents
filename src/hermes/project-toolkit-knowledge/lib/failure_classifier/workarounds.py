"""Workaround candidates, recurring inline programs, and the friction block check.

The friction report asks a model to name, per workaround, what it hit, what it
did instead, and the permanent fix. The first two are computable from the
session transcript, so this module computes them and leaves only the judgment
to the model. Everything here is deterministic: no model call, no network, no
file read, no environment read. Input is the ``FailureEvent`` list that
``events_from_records`` builds, so there is one transcript parser.

Three public functions:

- ``workaround_candidates``: a failed call, then a related success.
- ``inline_script_inventory``: recurring inline programs and scratch scripts.
- ``validate_friction_block``: structural check of the final report text.

Every string that leaves this module passes ``redact_text`` and a length cap.

Stricter than ``scripts/redact_secrets.py``: that script is the canonical
redactor, but it is a top-level script outside the mirrored lib packages, and
the mirror rewrites only ``scripts.<package>`` imports. A lib module cannot
import it in an installed plugin, so a small redactor lives here.
``tests/test_failure_classifier_workarounds.py`` runs both over one corpus and
fails when this one passes a sample the canonical redactor changes.

Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from collections.abc import Iterable
from dataclasses import dataclass

# Same digit, hex, and whitespace normalization that ``failure_fingerprint``
# applies to an error line (classifier.py), applied here to whole texts.
from .classifier import (
    _DIGIT_RUN,
    _HEX_RUN,
    _WHITESPACE_RUN,
    SHELL_TOOLS,
    FailureEvent,
    check_command,
    failure_fingerprint,
    is_check_command,
    is_denial,
)

COMMAND_MAX_CHARS = 300
ERROR_MAX_CHARS = 240
ERROR_MAX_LINES = 2
SAMPLE_MAX_CHARS = 300
SAMPLE_MAX_LINES = 3
FIX_MAX_CALLS = 3

# Same-family calls examined after a failure, and the most events scanned.
LOOKAHEAD = 10
SCAN_MAX_EVENTS = 50

# A later success counts as the same job when it shares this many command
# tokens and at least this share of the shorter command's tokens.
MIN_SHARED_TOKENS = 2
MIN_OVERLAP = 0.6

# An embedded program shorter than this is a one-liner, not a script.
MIN_BODY_CHARS = 20
MIN_GROUP_COUNT = 2
SCRATCH_MARKERS: tuple[str, ...] = ("/scratch/", "/tmp/")
SCRIPT_SUFFIXES: tuple[str, ...] = (".py", ".sh", ".ps1", ".js", ".ts")

KIND_ALTERNATIVE = "alternative"
KIND_FIX_THEN_RETRY = "fix-then-retry"

_REDACTED = "[redacted]"
# A regex over a hostile 100 KB string must stay cheap. Text beyond this is cut
# back to the last whitespace before redaction, so no secret is split in half.
_REDACT_INPUT_MAX_CHARS = 20_000

_SECRET_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"
            r".*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)",
            re.DOTALL,
        ),
        _REDACTED,
    ),
    (
        re.compile(
            r"(?i)\b(authorization[\"']?\s*[:=]\s*[\"']?)"
            r"(?:(?:bearer|basic|token)\s+)?[^\s\"'&|;]+"
        ),
        r"\1" + _REDACTED,
    ),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer " + _REDACTED),
    (re.compile(r"\b(?:ghp|ghs|gho|ghu|ghr)_[A-Za-z0-9]{20,}\b"), _REDACTED),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), _REDACTED),
    (re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{10,}\b"), _REDACTED),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), _REDACTED),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), _REDACTED),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), _REDACTED),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        _REDACTED,
    ),
    (re.compile(r"(://[^\s/:@]+:)[^\s/@]+@"), r"\1" + _REDACTED + "@"),
    (
        re.compile(r"(?i)(--?(?:password|passwd|token|secret|api[-_]?key)[ =]+)(?!-)[^\s]+"),
        r"\1" + _REDACTED,
    ),
    (
        re.compile(
            r"(?i)((?:api[_-]?key|secret|token|passw(?:or)?d|passwd|credential"
            r"|private[_-]?key)[\w.-]{0,24}[\"']?\s*[:=]\s*)"
            r"(\"[^\"\n]*\"|'[^'\n]*'|[^\s\"'&|;<>)]+)"
        ),
        r"\1" + _REDACTED,
    ),
    (
        re.compile(r"(?<![\w.%+\-])[\w.%+\-]+@[\w\-]+(?:\.[A-Za-z][\w\-]*)+", re.UNICODE),
        _REDACTED,
    ),
    (re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32,}(?![0-9a-fA-F])"), _REDACTED),
)


def redact_text(text: str) -> str:
    """Replace secret and PII shapes in ``text`` with ``[redacted]``.

    Covers private keys, ``Authorization`` headers, bearer tokens, GitHub,
    Stripe, AWS, Slack, and JWT shapes, URL passwords, credential flags and
    ``KEY=value`` assignments for credential-named keys, email addresses, and
    hex runs of 32 or more. Over-redacting is the safe failure.
    """
    bounded = text
    if len(bounded) > _REDACT_INPUT_MAX_CHARS:
        bounded = bounded[:_REDACT_INPUT_MAX_CHARS].rsplit(None, 1)[0]
    for pattern, replacement in _SECRET_RULES:
        bounded = pattern.sub(replacement, bounded)
    return bounded


def _clip(text: str, limit: int) -> str:
    """Collapse whitespace runs to one space, then cap at ``limit`` characters."""
    flat = _WHITESPACE_RUN.sub(" ", text).strip()
    if len(flat) <= limit:
        return flat
    return flat[: limit - 3].rstrip() + "..."


def _snippet(text: str, limit: int) -> str:
    """Redact first, then cap, so a cut cannot leave half a secret."""
    return _clip(redact_text(text), limit)


def _normalize(text: str) -> str:
    """Hex runs to ``H``, digit runs to ``N``, whitespace collapsed."""
    return _WHITESPACE_RUN.sub(" ", _DIGIT_RUN.sub("N", _HEX_RUN.sub("H", text))).strip()


def _family(event: FailureEvent) -> str:
    return "shell" if event.tool in SHELL_TOOLS else event.tool


def _call_text(event: FailureEvent) -> str:
    """The text that identifies what a call did: the command, else the input."""
    if event.tool in SHELL_TOOLS:
        command = check_command(event.input)
        if command is not None:
            return command
    return event.input or ""


def _display_text(event: FailureEvent) -> str:
    """The text shown to a reader: the command, else the target, else the input."""
    if event.tool in SHELL_TOOLS:
        return _call_text(event)
    return event.target or event.input or ""


# ---------------------------------------------------------------------------
# Workaround candidates
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkaroundCandidate:
    """One failed call and the call that got the job done.

    ``kind`` is ``alternative`` when a related call with different input
    succeeded, and ``fix-then-retry`` when the same call succeeded after other
    successful calls ran between the failure and the retry. In the second case
    ``succeeded`` holds those intervening calls, not the retry.
    ``count`` is how many failures with the same error collapsed into this one.
    ``index`` is the transcript position of the first failure.
    """

    tool: str
    failed: str
    error: str
    succeeded: str
    kind: str
    count: int = 1
    index: int = 0


def _tokens(text: str) -> frozenset[str]:
    """Word parts of a call. A flag splits on ``-``, so ``--body-file`` shares ``body``."""
    parts = re.split(r"[\s;&|()<>`$\"'{}\[\],=:/.\-]+", text[:4000].lower())
    return frozenset(p for p in parts if len(p) >= 2 and not p.isdigit())


def _related(first: frozenset[str], second: frozenset[str]) -> bool:
    smaller = min(len(first), len(second))
    shared = len(first & second)
    return smaller > 0 and shared >= MIN_SHARED_TOKENS and shared / smaller >= MIN_OVERLAP


_EXIT_CODE_LINE = re.compile(r"exit code \d+", re.IGNORECASE)
_TOOL_ERROR_TAG = re.compile(r"</?tool_use_error>", re.IGNORECASE)


def _error_lines(error: str) -> list[str]:
    """Error lines that carry a diagnostic: no blanks, no bare ``Exit code N``.

    Claude Code opens a failed Bash result with ``Exit code N``, so that line
    alone says nothing. A failure with no other line (``grep`` found no match)
    is not evidence of a gap.
    """
    lines = (_TOOL_ERROR_TAG.sub("", line).strip() for line in error.splitlines())
    return [line for line in lines if line and not _EXIT_CODE_LINE.fullmatch(line)]


# Output that signals a failure. A command can exit non-zero and print help or a
# status table; with none of these words in its output it is not a gap.
_FAILURE_WORDS = re.compile(
    r"\b(?:errors?|fail(?:ed|ure|s)?|denied|refus(?:ed|ing)|rejected|invalid|unknown"
    r"|unrecogni[sz]ed|unable|cannot|can't|not found|no such|no matches|not permitted"
    r"|not allowed|forbidden|unauthori[sz]ed|timed out|timeout|traceback|exception"
    r"|fatal|abort(?:ed)?|panic|missing|required|permission|unsupported|illegal)\b",
    re.IGNORECASE,
)
# The failure word must open the output: a word in the first lines, not one deep
# in help text or a file listing. A `prog: error:` or `Traceback` line counts
# further down, because argparse prints its usage block first.
_FAILURE_HEAD_LINES = 5
_FAILURE_HEAD_CHARS = 100
_FAILURE_SCAN_LINES = 40
_FAILURE_LINE = re.compile(r"(?:^|: )(?:error|fatal)\b|^traceback \(most recent", re.IGNORECASE)

# A rejection by the user, in wording ``DENIAL_MARKERS`` (classifier.py) lacks.
# Seen in local transcripts on 2026-11-27. Not a gap in a tool or process.
_USER_REJECTION_MARKERS: tuple[str, ...] = ("doesn't want to take this action",)

# `set -o pipefail;` and similar lead a command that is still a check.
_SHELL_PRELUDE = re.compile(r"^\s*(?:set\s+[-+][A-Za-z]+(?:\s+[A-Za-z]+)?\s*(?:;|&&)\s*)+")

# A script the agent wrote under a scratch path and then ran. Its failures are
# development of throwaway code, not a gap in a process, script, skill, or tool.
_SCRATCH_SCRIPT_RUN = re.compile(
    r"[^\s\"'=]*(?:" + "|".join(re.escape(m) for m in SCRATCH_MARKERS) + r")"
    r"[^\s\"']*(?:" + "|".join(re.escape(s) for s in SCRIPT_SUFFIXES) + r")(?![\w])"
)


def _is_check(event: FailureEvent) -> bool:
    if event.is_check:
        return True
    return is_check_command(_SHELL_PRELUDE.sub("", _call_text(event)))


def _has_failure_message(error: str) -> bool:
    lines = _error_lines(error)[:_FAILURE_SCAN_LINES]
    head = lines[:_FAILURE_HEAD_LINES]
    return any(_FAILURE_WORDS.search(line[:_FAILURE_HEAD_CHARS]) for line in head) or any(
        _FAILURE_LINE.search(line) for line in lines
    )


def _is_rejection(error: str) -> bool:
    lowered = error.lower()
    return is_denial(error) or any(marker in lowered for marker in _USER_REJECTION_MARKERS)


def _is_candidate_failure(event: FailureEvent) -> bool:
    """A failed shell call that says why it failed and is not normal work.

    Shell only: scripts, hooks, and CLIs run there. A failed Edit, Read, Agent,
    or MCP call is mostly a slip or an outage, and a later success of the same
    tool is rarely a workaround. Not a denial or user rejection, not a check
    command, and not a run of the agent's own scratch script.
    """
    return (
        not event.ok
        and event.tool in SHELL_TOOLS
        and not _is_rejection(event.error)
        and not _is_check(event)
        and _has_failure_message(event.error)
        and _SCRATCH_SCRIPT_RUN.search(_call_text(event)) is None
    )


def _fix_calls(between: list[FailureEvent]) -> str:
    shown = between[:FIX_MAX_CALLS]
    return " ; ".join(_snippet(_display_text(call), COMMAND_MAX_CHARS) for call in shown)


def _resolve(events: list[FailureEvent], index: int) -> tuple[str, str] | None:
    """The ``(kind, succeeded)`` that resolves the failure at ``index``, or None.

    Scans the next ``LOOKAHEAD`` same-family calls, within ``SCAN_MAX_EVENTS``
    events. An identical call that succeeds with nothing between is a transient
    retry: None. An identical retry after other successful calls is
    ``fix-then-retry``, even when one of them is related to the failure. An edit
    between the failure and an identical retry means the code was fixed, which is
    a fix and not a workaround, unless a related call already worked.
    """
    failed = events[index]
    family = _family(failed)
    failed_text = _call_text(failed)
    failed_id = _normalize(failed_text)
    failed_tokens = _tokens(failed_text)
    between: list[FailureEvent] = []
    alternative: tuple[str, str] | None = None
    edited = False
    seen = 0
    for later in events[index + 1 : index + 1 + SCAN_MAX_EVENTS]:
        if _family(later) != family:
            edited = edited or (later.ok and later.edit_tool)
            continue
        seen += 1
        if seen > LOOKAHEAD:
            break
        if not later.ok:
            continue
        later_text = _call_text(later)
        if _normalize(later_text) == failed_id:
            if edited:
                return alternative
            return (KIND_FIX_THEN_RETRY, _fix_calls(between)) if between else None
        if alternative is None and _related(failed_tokens, _tokens(later_text)):
            alternative = (KIND_ALTERNATIVE, _snippet(_display_text(later), COMMAND_MAX_CHARS))
        between.append(later)
    return alternative


def workaround_candidates(events: Iterable[FailureEvent]) -> list[WorkaroundCandidate]:
    """Failed calls that were later worked around, in transcript order.

    A candidate is a failed call that is not a permission denial, not a check
    command, and carries an error line beyond ``Exit code N``, followed by a
    successful call of the same tool family that is either a related call with
    different input or an identical retry that follows other successful calls.
    Failures that share an error collapse into one candidate with a count.

    A candidate is a lead, not a verdict. The model decides which are real
    friction.
    """
    ordered = list(events)
    grouped: dict[str, WorkaroundCandidate] = {}
    for index, event in enumerate(ordered):
        if not _is_candidate_failure(event):
            continue
        resolved = _resolve(ordered, index)
        if resolved is None:
            continue
        kind, succeeded = resolved
        lines = _error_lines(event.error)
        key = failure_fingerprint(event.tool, "\n".join(lines)) or event.tool
        existing = grouped.get(key)
        if existing is not None:
            grouped[key] = _with_count(existing, existing.count + 1)
            continue
        grouped[key] = WorkaroundCandidate(
            tool=event.tool,
            failed=_snippet(_display_text(event), COMMAND_MAX_CHARS),
            error=_snippet(" | ".join(lines[:ERROR_MAX_LINES]), ERROR_MAX_CHARS),
            succeeded=succeeded,
            kind=kind,
            count=1,
            index=index,
        )
    return list(grouped.values())


def _with_count(candidate: WorkaroundCandidate, count: int) -> WorkaroundCandidate:
    return WorkaroundCandidate(
        tool=candidate.tool,
        failed=candidate.failed,
        error=candidate.error,
        succeeded=candidate.succeeded,
        kind=candidate.kind,
        count=count,
        index=candidate.index,
    )


# ---------------------------------------------------------------------------
# Unmarked failures
# ---------------------------------------------------------------------------

UNMARKED_MAX = 20

# A line that states a failure outright. A harness marks a call as failed by
# its exit code, so a pipeline that ends in ``tail``, a background run, or a
# log read reports success while its output says the step failed.
_FAILURE_LINE = re.compile(
    r"(?m)^.*(?:Traceback \(most recent call last\)|\bFAILED \(exit \d+\)"
    r"|\bexited with -?[1-9]\d*|^(?:ERROR|error|fatal): \S|\bRefusing to \w"
    r"|: command not found|\bModuleNotFoundError\b).*$"
)


@dataclass(frozen=True)
class UnmarkedFailure:
    """A shell call the harness marked as success whose output states a failure.

    ``count`` is how many calls printed the same line. ``index`` is the
    transcript position of the first one.
    """

    command: str
    line: str
    count: int = 1
    index: int = 0


def unmarked_failures(events: Iterable[FailureEvent]) -> list[UnmarkedFailure]:
    """Shell calls marked as success whose output carries a failure line.

    A lead for the model, weaker than a candidate: the line can be quoted
    text. Check commands are skipped. Calls that print the same line collapse
    into one entry. At most ``UNMARKED_MAX`` entries, in transcript order.
    """
    grouped: dict[str, UnmarkedFailure] = {}
    for index, event in enumerate(events):
        if not event.ok or event.tool not in SHELL_TOOLS or _is_check(event):
            continue
        match = _FAILURE_LINE.search(event.error or "")
        if match is None:
            continue
        key = _normalize(match.group(0))
        existing = grouped.get(key)
        if existing is not None:
            grouped[key] = UnmarkedFailure(
                existing.command, existing.line, existing.count + 1, existing.index
            )
        elif len(grouped) < UNMARKED_MAX:
            grouped[key] = UnmarkedFailure(
                command=_snippet(_display_text(event), COMMAND_MAX_CHARS),
                line=_snippet(match.group(0), ERROR_MAX_CHARS),
                index=index,
            )
    return list(grouped.values())


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


def _scratch_scripts(events: list[FailureEvent]) -> list[ScratchScript]:
    written: dict[str, list[int]] = {}
    for index, event in enumerate(events):
        if event.ok and event.edit_tool and event.target and _is_scratch_script(event.target):
            entry = written.setdefault(event.target, [index, 0])
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
    with a script suffix that a Write or Edit call wrote to a path containing
    ``/scratch/`` or ``/tmp/``. Both lists run in transcript order.
    """
    ordered = list(events)
    groups = sorted(_inline_groups(ordered), key=lambda group: group.first_index)
    scratch = sorted(_scratch_scripts(ordered), key=lambda script: script.first_index)
    return ScriptInventory(inline=tuple(groups), scratch=tuple(scratch))


# ---------------------------------------------------------------------------
# Friction block check
# ---------------------------------------------------------------------------

HIT = "Hit"
DID_INSTEAD = "Did instead"
PERMANENT_FIX = "Permanent fix"

_LABEL_LINE = re.compile(
    r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?(?:\*\*)?(Hit|Did instead|Permanent fix):(?:\*\*)?[ \t]*(.*?)\s*$"
)
_PLACEHOLDER = re.compile(r"<[^<>]*>")

# Items walk three stages: Hit seen, Did instead seen, Permanent fix seen.
_STAGE_NONE = 0
_STAGE_HIT = 1
_STAGE_DID = 2
_STAGE_DONE = 3


@dataclass
class _Field:
    label: str
    value: str
    line: int


def _fields(text: str) -> list[_Field]:
    """Label lines with their values. Indented lines after a label continue it."""
    lines = text.splitlines()
    fields: list[_Field] = []
    for number, line in enumerate(lines):
        match = _LABEL_LINE.match(line)
        if match is None:
            continue
        parts = [match.group(2)]
        for follow in lines[number + 1 :]:
            if not follow.strip() or _LABEL_LINE.match(follow) or not follow[0].isspace():
                break
            parts.append(follow.strip())
        fields.append(_Field(match.group(1), " ".join(p for p in parts if p).strip(), number + 1))
    return fields


def _value_problems(field: _Field) -> list[str]:
    if not field.value:
        return [f'line {field.line}: "{field.label}:" value is empty']
    if _PLACEHOLDER.fullmatch(field.value):
        return [f'line {field.line}: "{field.label}:" value is still a placeholder: {field.value}']
    return []


def _missing(stage: int) -> str:
    if stage == _STAGE_HIT:
        return f'"{DID_INSTEAD}:" and "{PERMANENT_FIX}:"'
    return f'"{PERMANENT_FIX}:"'


def validate_friction_block(text: str) -> list[str]:
    """Problems in a friction report, one string each; empty when valid.

    Each ``Hit:`` line needs a ``Did instead:`` line and then a
    ``Permanent fix:`` line before the next ``Hit:``. Every value must be
    non-empty and not an angle-bracket placeholder such as ``<...>``. A
    ``Did instead:`` or ``Permanent fix:`` with no ``Hit:`` before it is a
    problem. Text with no friction lines is valid: zero items.
    """
    problems: list[str] = []
    stage = _STAGE_NONE
    hit_line = 0
    for field in _fields(text):
        problems.extend(_value_problems(field))
        if field.label == HIT:
            if stage in (_STAGE_HIT, _STAGE_DID):
                problems.append(f'line {hit_line}: "{HIT}:" is not followed by {_missing(stage)}')
            stage, hit_line = _STAGE_HIT, field.line
        elif stage in (_STAGE_NONE, _STAGE_DONE):
            problems.append(f'line {field.line}: "{field.label}:" has no preceding "{HIT}:"')
        elif field.label == DID_INSTEAD:
            if stage == _STAGE_DID:
                problems.append(f'line {field.line}: duplicate "{DID_INSTEAD}:"')
            stage = _STAGE_DID
        else:
            if stage == _STAGE_HIT:
                problems.append(
                    f'line {field.line}: "{PERMANENT_FIX}:" comes before "{DID_INSTEAD}:"'
                )
            stage = _STAGE_DONE
    if stage in (_STAGE_HIT, _STAGE_DID):
        problems.append(f'line {hit_line}: "{HIT}:" is not followed by {_missing(stage)}')
    return problems
