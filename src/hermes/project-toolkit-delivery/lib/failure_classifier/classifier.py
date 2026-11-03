"""The shared FailureClassifier: one definition of every tool-failure signal.

REQ-048, whose AC numbers the comments cite:
https://github.com/rjmurillo/ai-agents/blob/main/.project-toolkit/specs/requirements/REQ-048-friction-triggered-retrospective-nudge.md
Consumer A (`stuck_detection.py check-failures`) feeds it caller events; a
planned, unshipped Stop nudge (consumer B) will feed it transcript events via
``transcript``. A parity test keeps the two adapters in step.

Adapted from the failure-loop guard in microsoft/TokenEconomizer (arXiv
2610.22732, Apache-2.0); no code copied, no judge model. Stdlib only: nothing
here reads a file, the environment, or the network, or prints event text.
"""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

FINGERPRINT_MAX_CHARS = 200
TARGET_MAX_CHARS = 512

# AC-32: the tools whose successful calls open a ChurnCycle.
EDIT_TOOLS: frozenset[str] = frozenset(
    {"edit", "write", "multiedit", "str_replace", "create", "apply_patch", "notebookedit"}
)

# An errored result holding one of these (any case) is a permission_denial,
# not a tool_error. Provisional: not checked against a labeled corpus, and the
# bare words also match ordinary errors such as a rejected git push.
DENIAL_MARKERS: tuple[str, ...] = (
    "permission denied",
    "user doesn't want to proceed",
    "was denied",
    "rejected",
)

# AC-29 step 3: `0x` plus 7 or more hex digits, or a bare run of 7 or more that
# holds a digit and a letter, so plain numbers fall to step 4 and a word such
# as "defaced" stays a word.
_HEX_RUN = re.compile(r"\b0x[0-9a-f]{7,}\b|\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,}\b")
_DIGIT_RUN = re.compile(r"\d+")
_WHITESPACE_RUN = re.compile(r"\s+")

# AC-40: the shell tools whose commands the derived check rule reads.
SHELL_TOOLS: frozenset[str] = frozenset({"bash", "shell", "powershell"})

# AC-40 wrappers, stripped from the front of a command before the head match.
# Neither pattern starts with `^`: `match(text, pos)` anchors at pos, and `^`
# would anchor at the string start instead.
_CHECK_WRAPPER = re.compile(
    r"(?:cd\s+\S+\s*&&|[A-Za-z_][A-Za-z0-9_]*=\S*|uv\s+run|npx|python3?\s+-m|timeout\s+\S+)\s+",
    re.IGNORECASE,
)
# AC-40 heads. Each must be followed by whitespace or the end of the command;
# only the markdownlint prefix may also be followed by `-`.
_CHECK_HEAD = re.compile(
    r"(?:pytest|py\.test|unittest|tox|nox|jest|vitest|mocha"
    r"|make|mvn|gradle"
    r"|(?:npm|yarn|pnpm)\s+(?:run\s+)?(?:test|build|lint|typecheck)"
    r"|cargo\s+(?:test|build|check|clippy)|go\s+(?:test|build|vet)|dotnet\s+(?:test|build)"
    r"|tsc|eslint|ruff|mypy|pyright|shellcheck|markdownlint(?:-\S*)?"
    r"|python3?\s+(?:\S*[/\\])?(?:(?:test_|check_|validate_)[^\s/\\]*|pre_pr\.py)"
    r"|lefthook\s+run|pre-commit\s+run)(?:\s|$)",
    re.IGNORECASE,
)

ProgressKey = tuple[str, str] | None


def normalize_tool(tool: str) -> str:
    """Lowercase and trim a tool name. The one place tool names are compared."""
    return tool.strip().lower()


def normalize_target(target: str) -> str:
    """AC-32: backslashes become forward slashes, then normpath, capped at 512."""
    return posixpath.normpath(target.replace("\\", "/"))[:TARGET_MAX_CHARS]


def canonical_input(value: object) -> str:
    """AC-38: sorted keys, `,` and `:` separators, non-ASCII escaped as `\\uXXXX`."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _reject_constant(name: str) -> object:
    raise ValueError(f"{name} is not RFC 8259 JSON")


def _parse_json(text: str) -> tuple[bool, object]:
    """RFC 8259 parse: ``(True, value)``, or ``(False, None)`` for any other text.

    ``NaN`` and ``Infinity`` are rejected, and a repeated key keeps its last value.
    """
    try:
        return True, json.loads(text, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        return False, None


def canonicalize_input_text(text: str) -> str:
    """AC-39: a JSON document gets AC-38's form; any other text is trimmed.

    So a caller passing the tool input as JSON gets the transcript adapter's
    ProgressKey, whatever its key order or spacing.
    """
    trimmed = text.strip()
    parsed, value = _parse_json(trimmed)
    return canonical_input(value) if parsed else trimmed


def check_command(input_text: str | None) -> str | None:
    """AC-40: the command a derived check reads, or None when there is none.

    A JSON object's string ``command`` field, or the input text itself when it
    is not JSON. A non-object document, or a missing or non-string
    ``command``, gives None. The ProgressKey keeps the full input either way.
    """
    if input_text is None:
        return None
    trimmed = input_text.strip()
    parsed, value = _parse_json(trimmed)
    if not parsed:
        return trimmed
    if isinstance(value, dict):
        command = value.get("command")
        if isinstance(command, str):
            return command.strip()
    return None


def is_check_command(command: str) -> bool:
    """AC-40: the command starts with a check head once wrappers are stripped."""
    text = command.strip()
    # Advance an offset rather than slicing, so a long run of wrappers stays
    # linear in the command length (CWE-400).
    pos = 0
    while (match := _CHECK_WRAPPER.match(text, pos)) is not None:
        pos = match.end()
    return _CHECK_HEAD.match(text, pos) is not None


def fingerprint_tool(fingerprint: str) -> str:
    """The tool part of a fingerprint built by ``failure_fingerprint``."""
    return fingerprint.split("|", 1)[0]


def failure_fingerprint(tool: str, error: str) -> str | None:
    """AC-29: ``<tool>|<normalized first error line>``, or None with no error text."""
    first = next((line for line in error.splitlines() if line.strip()), "")
    line = first.strip().lower()
    if not line:
        return None
    line = _HEX_RUN.sub("H", line)
    line = _DIGIT_RUN.sub("N", line)
    line = _WHITESPACE_RUN.sub(" ", line)[:FINGERPRINT_MAX_CHARS]
    return f"{normalize_tool(tool)}|{line}"


def is_denial(error: str) -> bool:
    """REQ-048 Definitions: errored text holding a DENIAL_MARKERS entry."""
    lowered = error.lower()
    return any(marker in lowered for marker in DENIAL_MARKERS)


@dataclass(frozen=True)
class FailureEvent:
    """One normalized tool call (REQ-048 Ontology).

    Build events with ``FailureEvent.build``: it is the only constructor that
    normalizes. A direct call keeps fields as given, so its keys may not match.

    ``error`` is held only to classify the event. It is never part of any
    output: the fingerprint carries its normalized first line, and the
    denial check reads it once.
    """

    tool: str
    ok: bool
    error: str = ""
    input: str | None = None
    target: str | None = None
    check: bool | None = None

    @classmethod
    def build(
        cls,
        tool: str,
        ok: bool,
        error: str | None = None,
        input: str | None = None,  # the REQ-048 field name
        target: str | None = None,
        check: bool | None = None,
    ) -> FailureEvent:
        """Normalize raw fields: trim strings, drop blanks, normalize the target.

        ``check`` is the caller's AC-40 mark; None means derive it.
        """
        command = input.strip() if input else ""
        path = target.strip() if target else ""
        return cls(
            tool=normalize_tool(tool),
            ok=ok,
            error=error or "",
            input=command or None,
            target=normalize_target(path) if path else None,
            check=check,
        )

    @property
    def edit_tool(self) -> bool:
        return self.tool in EDIT_TOOLS

    @property
    def is_check(self) -> bool:
        """AC-40: a verification step, caller-marked or derived from the command.

        An edit is never a check, whatever its ``check`` field says.
        """
        if self.edit_tool:
            return False
        if self.check is not None:
            return self.check
        if self.tool not in SHELL_TOOLS:
            return False
        command = check_command(self.input)
        return command is not None and is_check_command(command)

    @property
    def cycle_target(self) -> str | None:
        """AC-32: the target whose ChurnCycle this event opens, if any.

        Only a successful edit with a target opens one.
        """
        return self.target if self.ok and self.edit_tool else None

    @property
    def progress_key(self) -> ProgressKey:
        """REQ-048 Ontology: ``(tool, input)``, or None when input is absent."""
        return None if self.input is None else (self.tool, self.input)

    @property
    def fingerprint(self) -> str | None:
        return None if self.ok else failure_fingerprint(self.tool, self.error)


# FailureTally: progress key -> fingerprint -> count of errored events still
# counted (AC-30 removes a key's entries when that key succeeds).
Tally = dict[ProgressKey, dict[str, int]]


@dataclass
class FailureSignals:
    """Everything the classifier knows about one event sequence (REQ-048 Ontology).

    Read the tallies through ``repeat_totals``, ``churn_totals``, and
    ``churned_targets``. ``tally`` and ``churn`` are the raw state behind them,
    and their shape may change.
    """

    tool_error: int = 0
    permission_denial: int = 0
    failed_retry: int = 0
    unfingerprinted: int = 0
    tally: Tally = field(default_factory=dict)
    churn: dict[str, Tally] = field(default_factory=dict)

    def repeat_totals(self) -> dict[str, int]:
        """FailureTally summed across keys: one count per fingerprint (AC-33)."""
        return _sum_by_fingerprint(self.tally)

    def churn_totals(self) -> dict[str, dict[str, int]]:
        """Per-target ChurnCycle outcome counts, summed across keys (AC-32, AC-36).

        Targets whose every cycle outcome was removed by a reset are left out.
        """
        totals = {target: _sum_by_fingerprint(per_key) for target, per_key in self.churn.items()}
        return {target: counts for target, counts in totals.items() if counts}

    def churned_targets(self, threshold: int) -> dict[str, tuple[str, int]]:
        """Targets with ``threshold`` or more cycles sharing one fingerprint.

        Returns target -> (fingerprint, count) for the most frequent outcome.
        Consumer B counts these as its ``edit_churn`` FrictionSignal.
        """
        hits: dict[str, tuple[str, int]] = {}
        for target, counts in sorted(self.churn_totals().items()):
            fingerprint, count = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
            if count >= threshold:
                hits[target] = (fingerprint, count)
        return hits


def _sum_by_fingerprint(tally: Tally) -> dict[str, int]:
    totals: dict[str, int] = {}
    for per_key in tally.values():
        for fingerprint, count in per_key.items():
            totals[fingerprint] = totals.get(fingerprint, 0) + count
    return totals


def _bump(tally: Tally, key: ProgressKey, fingerprint: str) -> None:
    per_key = tally.setdefault(key, {})
    per_key[fingerprint] = per_key.get(fingerprint, 0) + 1


def _record_success(
    signals: FailureSignals,
    retry_seen: dict[tuple[str, str], set[str]],
    pending: set[str],
    event: FailureEvent,
) -> None:
    key = event.progress_key
    if key is not None:
        retry_seen.pop(key, None)
        # AC-30: a success for a key removes only that key's entries.
        if signals.tally.pop(key, None) is not None:
            for per_key in signals.churn.values():
                per_key.pop(key, None)
    # Closing on success: a successful check (AC-40) ends every pending cycle
    # with no outcome, keyed or not (Devin's case). Any other success, such as
    # `ls` or a read, leaves them open.
    if event.is_check:
        pending.clear()
    # Opening: a successful edit with a target. Other targets' pending cycles
    # stay in place.
    target = event.cycle_target
    if target is not None:
        pending.add(target)


def _record_failure(
    signals: FailureSignals,
    retry_seen: dict[tuple[str, str], set[str]],
    pending: set[str],
    event: FailureEvent,
) -> None:
    if is_denial(event.error):
        signals.permission_denial += 1
    else:
        signals.tool_error += 1
    fingerprint = event.fingerprint
    if fingerprint is None:
        signals.unfingerprinted += 1
        return
    key = event.progress_key
    if key is not None:
        seen = retry_seen.setdefault(key, set())
        if fingerprint in seen:
            signals.failed_retry += 1
        seen.add(fingerprint)
    _bump(signals.tally, key, fingerprint)
    # Only a check closes a cycle (AC-40). A failed edit is never a check, and
    # a non-check failure, such as a failed `cat`, leaves cycles open.
    if not event.is_check:
        return
    # Closing on failure: the first fingerprinted check failure records its
    # fingerprint as the outcome of every pending cycle.
    for target in pending:
        _bump(signals.churn.setdefault(target, {}), key, fingerprint)
    pending.clear()


def classify(events: Iterable[FailureEvent]) -> FailureSignals:
    """Classify one event sequence in a single pass.

    The caller applies its own window first: consumer A slices to
    ``--window``, consumer B passes the whole scan.

    - tool_error, permission_denial (AC-01, AC-02, AC-37): every errored
      event is one or the other; one with no error text is a tool_error and
      also counts as unfingerprinted.
    - failed_retry (AC-03, AC-04, AC-31): an errored event whose progress key
      and fingerprint match an earlier errored event, with no success for that
      key between them. A keyless or unfingerprinted event never matches.
    - FailureTally (AC-30, AC-33): fingerprinted errors by key; a success for
      a key removes only that key's entries, here and in the churn tallies.
    - ChurnCycles (AC-32, AC-40): only a check event ends or closes a
      cycle; see the comments in the two handlers.
    """
    signals = FailureSignals()
    retry_seen: dict[tuple[str, str], set[str]] = {}
    pending: set[str] = set()
    for event in events:
        record = _record_success if event.ok else _record_failure
        record(signals, retry_seen, pending, event)
    return signals
