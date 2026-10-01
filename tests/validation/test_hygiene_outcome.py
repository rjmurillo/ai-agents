"""Direct tests for the hygiene-scan to CheckOutcome mapping (issue #5636)."""

from __future__ import annotations

from scripts.validation.evidence import (
    REASON_ADVISORY_FINDINGS,
    REASON_ENTRIES_UNREADABLE,
    REASON_LISTING_FAILED,
    WORKING_TREE,
    EvidenceState,
)
from scripts.validation.hygiene_outcome import hygiene_outcome

_SCOPE = "test scope"


def _run(**overrides: object):
    args: dict[str, object] = {"scope": _SCOPE, "examined": 4, "findings": 0}
    args.update(overrides)
    return hygiene_outcome("validate_x", **args)  # type: ignore[arg-type]


def test_a_clean_scan_is_a_pass_naming_revision_scope_and_count() -> None:
    outcome = _run()

    assert outcome.state is EvidenceState.PASS
    assert (outcome.revision, outcome.scope, outcome.examined) == (WORKING_TREE, _SCOPE, 4)


def test_findings_are_a_fail_with_the_advisory_reason_and_count() -> None:
    outcome = _run(findings=2)

    assert outcome.state is EvidenceState.FAIL
    assert outcome.reason == REASON_ADVISORY_FINDINGS
    assert outcome.findings == 2


def test_a_failed_listing_without_findings_is_blocked() -> None:
    outcome = _run(listing_failed=True)

    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.reason == REASON_LISTING_FAILED


def test_unreadable_entries_without_findings_are_blocked() -> None:
    outcome = _run(unreadable=3)

    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.reason == REASON_ENTRIES_UNREADABLE
    assert "3 item(s)" in outcome.detail


def test_findings_outrank_a_failed_listing() -> None:
    """A proven violation is more actionable than an absent observation."""
    outcome = _run(findings=1, listing_failed=True, unreadable=1)

    assert outcome.state is EvidenceState.FAIL


def test_a_failed_listing_outranks_unreadable_entries() -> None:
    assert _run(listing_failed=True, unreadable=1).reason == REASON_LISTING_FAILED


def test_zero_examined_with_no_findings_is_still_a_pass_that_says_zero() -> None:
    outcome = _run(examined=0)

    assert outcome.state is EvidenceState.PASS
    assert outcome.examined == 0
