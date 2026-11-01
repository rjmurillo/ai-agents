"""The shared FailureClassifier: one definition of every tool-failure signal.

REQ-048 (amendment 2026-11-01) names this module the single owner of
`tool_error`, `permission_denial`, `failed_retry`, and `edit_churn`. Consumer A
(`stuck_detection.py check-failures`) feeds it caller-supplied events; consumer
B (the Stop retrospective nudge) feeds it transcript events through
`scripts.failure_classifier.transcript`. Both read the same output, so neither
holds a second definition.

The signal definitions are adapted from the failure-loop guard in
microsoft/TokenEconomizer (arXiv 2610.22732, Apache-2.0). No code was copied.
This module uses deterministic counts only: no judge model.

Stdlib only. Nothing here reads a file, the environment, or the network, and
nothing here emits event text: callers decide what to print.
"""

from __future__ import annotations

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

# REQ-048 Definitions: an errored result whose text holds one of these,
# case-insensitive, is a permission_denial rather than a tool_error. TASK-001
# checks the set against the corpus.
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

ProgressKey = tuple[str, str] | None


def normalize_tool(tool: str) -> str:
    """Lowercase and trim a tool name. The one place tool names are compared."""
    return tool.strip().lower()


def normalize_target(target: str) -> str:
    """AC-32: backslashes become forward slashes, then normpath, capped at 512."""
    return posixpath.normpath(target.replace("\\", "/"))[:TARGET_MAX_CHARS]


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

    ``error`` is held only to classify the event. It is never part of any
    output: the fingerprint carries its normalized first line, and the
    denial check reads it once.
    """

    tool: str
    ok: bool
    error: str = ""
    input: str | None = None
    target: str | None = None

    @classmethod
    def build(
        cls,
        tool: str,
        ok: bool,
        error: str | None = None,
        input: str | None = None,  # the REQ-048 field name
        target: str | None = None,
    ) -> FailureEvent:
        """Normalize raw fields: trim strings, drop blanks, normalize the target."""
        command = input.strip() if input else ""
        path = target.strip() if target else ""
        return cls(
            tool=normalize_tool(tool),
            ok=ok,
            error=error or "",
            input=command or None,
            target=normalize_target(path) if path else None,
        )

    @property
    def edit_tool(self) -> bool:
        return self.tool in EDIT_TOOLS

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
    """Everything the classifier knows about one event sequence (REQ-048 Ontology)."""

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
    # Closing on success: any successful non-edit event ends every pending
    # cycle with no outcome, keyed or not (Devin's case).
    if not event.edit_tool:
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
    # A failed edit closes no cycle.
    if event.edit_tool:
        return
    # Closing on failure: the first fingerprinted non-edit failure records its
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
    - ChurnCycles (AC-32): see the comments in the two handlers.
    """
    signals = FailureSignals()
    retry_seen: dict[tuple[str, str], set[str]] = {}
    pending: set[str] = set()
    for event in events:
        record = _record_success if event.ok else _record_failure
        record(signals, retry_seen, pending, event)
    return signals
