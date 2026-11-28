"""Workaround candidates, recurring inline programs, and the friction block check.

The friction report asks a model to name, per workaround, what it hit, what it
did instead, and the permanent fix. The first two are computable from the
session transcript, so this module computes them and leaves only the judgment
to the model. Everything here is deterministic: no model call, no network, no
file read, no environment read. Input is the ``FailureEvent`` list that
``events_from_records`` builds, so there is one transcript parser.

Public functions here: ``workaround_candidates`` (a failed call, then a related
success) and ``unmarked_failures`` (a call marked as success whose output
states a failure). ``script_inventory.py`` holds the recurring inline programs
and scratch scripts. ``friction_block.py`` holds the check of the final text.

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
