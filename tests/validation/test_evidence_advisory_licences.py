"""Each advisory licence in the pre-PR policy stays one validator, one state, one reason.

Issue #5636: an advisory gate keeps its non-blocking verdict but reports it
through the typed states. The licence that keeps it non-blocking must not be
widenable by another validator, another state, or a reason nobody reviewed.
"""

from __future__ import annotations

import pytest

from scripts.validation.evidence import (
    REASON_ADVISORY_FINDINGS,
    REASON_DIFF_FAILED,
    CheckOutcome,
    EvidenceState,
    PolicyException,
    default_pre_pr_policy,
    pre_pr_policy,
)

_NAMED_EXCEPTIONS = 3  # SKIP for every validator, and the two absent-linter licences.
_ADVISORY = pre_pr_policy().exceptions[_NAMED_EXCEPTIONS:]

_BUILDERS = {
    EvidenceState.FAIL: CheckOutcome.failed,
    EvidenceState.BLOCKED: CheckOutcome.blocked,
}


def _outcome(validator: str, state: EvidenceState, reason: str) -> CheckOutcome:
    return _BUILDERS[state](validator, reason=reason)


def _only(exception: PolicyException) -> tuple[str, EvidenceState, str]:
    (state,) = exception.states
    (reason,) = exception.reasons
    return exception.validator, state, reason


def test_the_advisory_rows_exist() -> None:
    """Negative control: an empty slice would make every test below vacuous."""
    assert len(_ADVISORY) >= 10


@pytest.mark.parametrize("exception", _ADVISORY, ids=lambda e: "-".join(map(str, _only(e))))
def test_each_licence_names_one_validator_one_state_and_one_reason(
    exception: PolicyException,
) -> None:
    validator, state, reason = _only(exception)

    assert validator != "*"
    assert state in _BUILDERS
    assert reason
    assert exception.justification.strip()
    assert exception.reference == ".agents/governance/FAIL-OPEN-INVENTORY.md"


@pytest.mark.parametrize("exception", _ADVISORY, ids=lambda e: "-".join(map(str, _only(e))))
def test_a_licensed_pair_does_not_block(exception: PolicyException) -> None:
    validator, state, reason = _only(exception)

    assert pre_pr_policy().accepts(_outcome(validator, state, reason))


@pytest.mark.parametrize("exception", _ADVISORY, ids=lambda e: "-".join(map(str, _only(e))))
def test_the_licence_does_not_extend_to_an_unreviewed_reason(
    exception: PolicyException,
) -> None:
    validator, state, _ = _only(exception)

    assert not pre_pr_policy().accepts(_outcome(validator, state, REASON_DIFF_FAILED))


@pytest.mark.parametrize("exception", _ADVISORY, ids=lambda e: "-".join(map(str, _only(e))))
def test_the_licence_does_not_extend_to_another_validator(exception: PolicyException) -> None:
    _, state, reason = _only(exception)

    assert not pre_pr_policy().accepts(_outcome("validate_some_other_gate", state, reason))


def test_the_base_policy_is_unchanged_and_leads_the_runtime_policy() -> None:
    """The three named exceptions keep their positions and count."""
    base = default_pre_pr_policy().exceptions

    assert len(base) == _NAMED_EXCEPTIONS
    assert pre_pr_policy().exceptions[:_NAMED_EXCEPTIONS] == base


def test_unknown_is_licensed_by_nothing_in_the_runtime_policy() -> None:
    """Issue #5646: UNKNOWN is the state that would put unreadable evidence on the accept side."""
    for exception in pre_pr_policy().exceptions:
        assert EvidenceState.UNKNOWN not in exception.states


def test_an_unknown_result_from_a_licensed_validator_still_blocks() -> None:
    outcome = CheckOutcome.unknown("validate_tmp_worktrees", reason=REASON_ADVISORY_FINDINGS)

    assert not pre_pr_policy().accepts(outcome)


def test_a_blocked_run_of_a_gate_licensed_only_for_findings_still_blocks() -> None:
    """tmp worktrees may FAIL on findings; a BLOCKED result there is not licensed."""
    outcome = CheckOutcome.blocked("validate_tmp_worktrees", reason=REASON_ADVISORY_FINDINGS)

    assert not pre_pr_policy().accepts(outcome)
