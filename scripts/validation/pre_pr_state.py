#!/usr/bin/env python3
"""Per-run result records for the pre-PR runner (extracted from ``pre_pr.py``).

Extracted because ``pre_pr.py`` sits under a 500-line ceiling (issue #3073,
pinned by ``tests/validation/test_pre_pr_model_pin_wiring.py``) and the
``--compact`` flag for issue #6734 crossed it. ``pre_pr`` re-imports both
classes, so ``pre_pr.ValidationState`` keeps its name.

Import discipline: the contract module comes in by its PACKAGE path, so
``EvidenceState`` keeps one identity across the flat and package import routes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.validation.evidence import REASON_ALREADY_RUN, CheckOutcome, EvidenceState


@dataclass
class ValidationRecord:
    """Result of a single validation step.

    ``status`` is the :class:`EvidenceState` value as a bare string, kept for
    the many callers and tests that read ``record.status`` against ``"PASS"``.
    ``outcome`` is the typed evidence behind it: the reason code, the scope, the
    revision, and the counts (issue #5635).
    """

    name: str
    status: str  # PASS, FAIL, SKIP, BLOCKED, UNKNOWN
    duration: float = 0.0
    message: str = ""
    outcome: CheckOutcome | None = None


_COUNTER_FOR_STATE: dict[EvidenceState, str] = {
    EvidenceState.PASS: "passed",
    EvidenceState.FAIL: "failed",
    EvidenceState.SKIP: "skipped",
    EvidenceState.BLOCKED: "blocked",
    EvidenceState.UNKNOWN: "unknown",
}


@dataclass
class ValidationState:
    """Tracks overall validation results.

    ``blocked`` and ``unknown`` are separate counters rather than folded into
    ``passed``: before issue #5635 a gate that could not run and a gate whose
    evidence was unreadable both incremented ``passed``, which is the defect
    this contract removes.
    """

    results: list[ValidationRecord] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    blocked: int = 0
    unknown: int = 0
    # Issue #6734: print only the gates that did not pass (``--compact``).
    compact: bool = False

    def record(self, name: str, outcome: CheckOutcome) -> CheckOutcome:
        """Append one gate's outcome and update the counter for its state.

        Every gate lands here, including the ones the sequence short-circuits,
        so no child state is lost from the summary.
        """
        self.total += 1
        self.results.append(
            ValidationRecord(
                name=name,
                status=outcome.state.value,
                duration=outcome.duration_seconds,
                message=outcome.detail,
                outcome=outcome,
            )
        )
        counter = _COUNTER_FOR_STATE[outcome.state]
        setattr(self, counter, getattr(self, counter) + 1)
        return outcome

    def hides(self, outcome: CheckOutcome) -> bool:
        """Return True when ``--compact`` leaves ``outcome`` unprinted."""
        return self.compact and is_quiet(outcome)

    def outcomes(self) -> tuple[CheckOutcome, ...]:
        """Return the typed outcomes recorded so far, in run order."""
        return tuple(record.outcome for record in self.results if record.outcome is not None)


def is_quiet(outcome: CheckOutcome) -> bool:
    """Return True for an outcome ``--compact`` leaves unprinted.

    A PASS proved its contract. A SKIP with ``REASON_ALREADY_RUN`` names a gate
    the pre-push fast stage ran and passed. Every other SKIP stays visible, such
    as a validator script that is absent, because that run did not prove what a
    full run proves.
    """
    if outcome.state is EvidenceState.PASS:
        return True
    return outcome.state is EvidenceState.SKIP and outcome.reason == REASON_ALREADY_RUN
