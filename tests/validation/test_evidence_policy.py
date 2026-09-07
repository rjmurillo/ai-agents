"""Gate-side contract tests for the typed evidence states (issue #5635).

Covers what a blocking gate does with a set of observations: which states it
accepts, how a bounded :class:`PolicyException` licenses one that would block,
how child states reduce to a parent state without being lost, and which
ADR-035 exit code each blocking state maps to. The producer-side half is in
``test_evidence_contract.py``.
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from scripts.validation.evidence import (
    REASON_BASE_REF_UNRESOLVED,
    REASON_DIFF_FAILED,
    REASON_SCRIPT_ABSENT,
    REASON_TOOL_ABSENT,
    AggregateOutcome,
    CheckOutcome,
    EvidenceState,
    GatePolicy,
    PolicyException,
    aggregate,
    default_pre_pr_policy,
    exit_code_for,
)


class TestPolicyException:
    """A licence to not block has to be reviewable."""

    def test_covers_a_matching_validator_state_and_reason(self) -> None:
        """The happy path: an exception licenses exactly what it names."""
        exception = PolicyException(
            validator="v",
            states=frozenset({EvidenceState.BLOCKED}),
            reasons=frozenset({REASON_TOOL_ABSENT}),
            justification="actionlint is optional on developer machines",
        )

        assert exception.covers(CheckOutcome.blocked("v", reason=REASON_TOOL_ABSENT))

    def test_wildcard_validator_covers_every_validator(self) -> None:
        """One row can license a state across the whole sequence."""
        exception = PolicyException(
            validator="*",
            states=frozenset({EvidenceState.SKIP}),
            justification="a gate that does not apply does not block",
        )

        assert exception.covers(CheckOutcome.skipped("anything", reason=REASON_SCRIPT_ABSENT))

    def test_does_not_cover_another_validator(self) -> None:
        """Bounded means bounded."""
        exception = PolicyException(
            validator="v",
            states=frozenset({EvidenceState.BLOCKED}),
            justification="reason",
        )

        assert not exception.covers(CheckOutcome.blocked("other", reason=REASON_TOOL_ABSENT))

    def test_does_not_cover_an_unnamed_reason(self) -> None:
        """Naming reasons narrows the licence to the ones reviewed."""
        exception = PolicyException(
            validator="v",
            states=frozenset({EvidenceState.BLOCKED}),
            reasons=frozenset({REASON_TOOL_ABSENT}),
            justification="reason",
        )

        assert not exception.covers(CheckOutcome.blocked("v", reason=REASON_BASE_REF_UNRESOLVED))

    def test_empty_reasons_covers_any_reason(self) -> None:
        """An unrestricted exception still has to name its states."""
        exception = PolicyException(
            validator="v",
            states=frozenset({EvidenceState.BLOCKED}),
            justification="reason",
        )

        assert exception.covers(CheckOutcome.blocked("v", reason=REASON_BASE_REF_UNRESOLVED))

    def test_exception_without_a_justification_is_rejected(self) -> None:
        """An unexplained exception cannot be reviewed."""
        with pytest.raises(ValueError, match="requires a justification"):
            PolicyException(
                validator="v", states=frozenset({EvidenceState.SKIP}), justification="  "
            )

    def test_exception_naming_no_states_is_rejected(self) -> None:
        """An exception that licenses nothing is dead policy."""
        with pytest.raises(ValueError, match="licenses nothing"):
            PolicyException(validator="v", states=frozenset(), justification="because")

    def test_exception_naming_pass_is_rejected(self) -> None:
        """PASS is already accepted; naming it reads as policy and is not."""
        with pytest.raises(ValueError, match="names PASS"):
            PolicyException(
                validator="v", states=frozenset({EvidenceState.PASS}), justification="because"
            )

    def test_exception_without_a_validator_is_rejected(self) -> None:
        """Every licence names who it applies to."""
        with pytest.raises(ValueError, match="must name a validator"):
            PolicyException(
                validator="", states=frozenset({EvidenceState.SKIP}), justification="because"
            )


class TestGatePolicy:
    """A blocking gate accepts only PASS unless an exception says otherwise."""

    def test_default_policy_accepts_pass(self) -> None:
        """The one state that always passes."""
        assert GatePolicy().accepts(CheckOutcome.passed("v", revision="HEAD", scope="tree"))

    @pytest.mark.parametrize(
        "outcome",
        [
            CheckOutcome.failed("v", reason="lint.violation"),
            CheckOutcome.skipped("v", reason=REASON_SCRIPT_ABSENT),
            CheckOutcome.blocked("v", reason=REASON_TOOL_ABSENT),
            CheckOutcome.unknown("v", reason=REASON_DIFF_FAILED),
        ],
    )
    def test_default_policy_rejects_every_non_pass_state(self, outcome: CheckOutcome) -> None:
        """The acceptance criterion: SKIP, BLOCKED, and UNKNOWN block by default."""
        assert not GatePolicy().accepts(outcome)

    def test_rejected_preserves_input_order(self) -> None:
        """A reader follows the summary in run order."""
        first = CheckOutcome.blocked("a", reason=REASON_TOOL_ABSENT)
        second = CheckOutcome.unknown("b", reason=REASON_DIFF_FAILED)
        passing = CheckOutcome.passed("c", revision="HEAD", scope="tree")

        assert GatePolicy().rejected([first, passing, second]) == (first, second)

    def test_to_dict_publishes_the_exceptions_for_audit(self) -> None:
        """A policy nobody can read is not auditable."""
        payload = json.loads(json.dumps(default_pre_pr_policy().to_dict()))

        assert payload["accepted_without_exception"] == ["PASS"]
        assert payload["exceptions"][0]["states"] == ["SKIP"]
        assert payload["exceptions"][0]["justification"]


class TestDefaultPrePrPolicy:
    """The documented pre-PR exception, and only that one."""

    def test_skip_does_not_block_the_push(self) -> None:
        """SHIFT-LEFT.md already documents this; the policy encodes it."""
        policy = default_pre_pr_policy()

        assert policy.accepts(CheckOutcome.skipped("v", reason=REASON_SCRIPT_ABSENT))

    @pytest.mark.parametrize(
        "outcome",
        [
            CheckOutcome.blocked("v", reason=REASON_BASE_REF_UNRESOLVED),
            CheckOutcome.unknown("v", reason=REASON_DIFF_FAILED),
        ],
    )
    def test_blocked_and_unknown_get_no_exception(self, outcome: CheckOutcome) -> None:
        """These are the states that used to arrive as True."""
        assert not default_pre_pr_policy().accepts(outcome)

    def test_every_exception_carries_a_justification_and_a_reference(self) -> None:
        """A bounded exception points at what a reviewer reads to evaluate it."""
        exceptions = default_pre_pr_policy().exceptions

        assert len(exceptions) == 3
        assert all(exception.justification.strip() for exception in exceptions)
        assert all(exception.reference.strip() for exception in exceptions)
        assert exceptions[0].reference == ".agents/devops/SHIFT-LEFT.md"

    @pytest.mark.parametrize(
        "validator", ["validate_workflow_yaml", "validate_yaml_style"]
    )
    def test_an_absent_optional_linter_is_licensed_by_name(self, validator: str) -> None:
        """actionlint and yamllint are optional, so their absence must not block.

        The state is still BLOCKED and still appears in the summary, which is
        the difference from the pre-#5635 behavior of returning True.
        """
        blocked = CheckOutcome.blocked(validator, reason=REASON_TOOL_ABSENT)

        assert default_pre_pr_policy().accepts(blocked)

    @pytest.mark.parametrize(
        "validator", ["validate_workflow_yaml", "validate_yaml_style"]
    )
    def test_the_licence_does_not_extend_to_another_reason(self, validator: str) -> None:
        """Bounded by reason: only a missing tool is licensed, not a missing base ref."""
        blocked = CheckOutcome.blocked(validator, reason=REASON_BASE_REF_UNRESOLVED)

        assert not default_pre_pr_policy().accepts(blocked)

    def test_the_licence_does_not_extend_to_another_validator(self) -> None:
        """Bounded by validator: a third gate's missing tool still blocks."""
        blocked = CheckOutcome.blocked("validate_session_end", reason=REASON_TOOL_ABSENT)

        assert not default_pre_pr_policy().accepts(blocked)


class TestAggregate:
    """The parent state, the preserved children, and the exit code."""

    def test_preserves_every_child_outcome(self) -> None:
        """Acceptance criterion: aggregators preserve child states."""
        children = [
            CheckOutcome.passed("a", revision="HEAD", scope="tree"),
            CheckOutcome.skipped("b", reason=REASON_SCRIPT_ABSENT),
            CheckOutcome.blocked("c", reason=REASON_BASE_REF_UNRESOLVED),
        ]

        summary = aggregate("pre_pr", children, default_pre_pr_policy())

        assert summary.outcomes == tuple(children)
        assert [outcome.validator for outcome in summary.rejected] == ["c"]

    def test_parent_state_is_the_worst_child(self) -> None:
        """One BLOCKED child makes the parent BLOCKED, not PASS."""
        summary = aggregate(
            "pre_pr",
            [
                CheckOutcome.passed("a", revision="HEAD", scope="tree"),
                CheckOutcome.blocked("b", reason=REASON_TOOL_ABSENT),
            ],
        )

        assert summary.state is EvidenceState.BLOCKED

    def test_empty_child_set_aggregates_to_unknown(self) -> None:
        """A sequence that ran nothing did not pass.

        NEGATIVE CONTROL: an aggregator that starts from ``passed = True`` and
        never flips reports PASS here.
        """
        summary = aggregate("pre_pr", [])

        assert summary.state is EvidenceState.UNKNOWN

    def test_counts_report_every_state_including_zeroes(self) -> None:
        """A consumer can read the shape without knowing which states occurred."""
        summary = aggregate("pre_pr", [CheckOutcome.passed("a", revision="HEAD", scope="tree")])

        assert summary.counts() == {"PASS": 1, "FAIL": 0, "SKIP": 0, "BLOCKED": 0, "UNKNOWN": 0}

    def test_blocking_is_false_when_the_policy_accepts_every_child(self) -> None:
        """A SKIP under the documented exception does not block."""
        summary = aggregate(
            "pre_pr",
            [
                CheckOutcome.passed("a", revision="HEAD", scope="tree"),
                CheckOutcome.skipped("b", reason=REASON_SCRIPT_ABSENT),
            ],
            default_pre_pr_policy(),
        )

        assert summary.state is EvidenceState.SKIP
        assert summary.blocking is False

    def test_to_dict_round_trips_through_json_with_children_and_policy(self) -> None:
        """The machine-readable summary the acceptance criterion requires."""
        summary = aggregate(
            "pre_pr",
            [
                CheckOutcome.passed("a", revision="HEAD", scope="tree", examined=7),
                CheckOutcome.unknown("b", reason=REASON_DIFF_FAILED),
            ],
            default_pre_pr_policy(),
            duration_seconds=12.5,
        )

        payload = json.loads(json.dumps(summary.to_dict()))

        assert payload["state"] == "UNKNOWN"
        assert payload["blocking"] is True
        assert payload["exit_code"] == 1
        assert payload["duration_seconds"] == 12.5
        assert [row["validator"] for row in payload["results"]] == ["a", "b"]
        assert [row["validator"] for row in payload["rejected"]] == ["b"]
        assert payload["policy"]["exceptions"][0]["states"] == ["SKIP"]

    def test_accepts_a_generator_of_outcomes(self) -> None:
        """Callers stream results; the aggregate must not consume them twice."""
        summary = aggregate(
            "pre_pr",
            (CheckOutcome.passed(name, revision="HEAD", scope="tree") for name in ("a", "b")),
        )

        assert len(summary.outcomes) == 2


class TestExitCodeFor:
    """ADR-035 codes, chosen by the worst blocking state."""

    def test_no_rejection_is_zero(self) -> None:
        """Nothing blocked, so the gate passes."""
        summary = aggregate("g", [CheckOutcome.passed("a", revision="HEAD", scope="tree")])

        assert exit_code_for(summary) == 0

    @pytest.mark.parametrize(
        ("outcome", "expected"),
        [
            (CheckOutcome.failed("a", reason="lint.violation"), 1),
            (CheckOutcome.unknown("a", reason=REASON_DIFF_FAILED), 1),
            (CheckOutcome.blocked("a", reason=REASON_TOOL_ABSENT), 3),
            (CheckOutcome.skipped("a", reason=REASON_SCRIPT_ABSENT), 2),
        ],
    )
    def test_each_blocking_state_maps_to_its_adr_035_code(
        self, outcome: CheckOutcome, expected: int
    ) -> None:
        """Logic, external, and config errors stay distinguishable."""
        summary = aggregate("g", [outcome], GatePolicy())

        assert exit_code_for(summary) == expected

    def test_fail_outranks_blocked_when_both_are_rejected(self) -> None:
        """A proven violation is the more actionable of the two."""
        summary = aggregate(
            "g",
            [
                CheckOutcome.blocked("a", reason=REASON_TOOL_ABSENT),
                CheckOutcome.failed("b", reason="lint.violation"),
            ],
            GatePolicy(),
        )

        assert exit_code_for(summary) == 1

    def test_an_accepted_skip_does_not_change_the_exit_code(self) -> None:
        """Only rejected children decide the code."""
        summary = aggregate(
            "g",
            [CheckOutcome.skipped("a", reason=REASON_SCRIPT_ABSENT)],
            default_pre_pr_policy(),
        )

        assert exit_code_for(summary) == 0


class TestAggregateOutcomeIsImmutable:
    """A summary handed to a consumer cannot be edited underneath it."""

    def test_frozen_dataclass_rejects_assignment(self) -> None:
        """Evidence is a record, not a mutable scratchpad."""
        summary: AggregateOutcome = aggregate("g", [])
        mutable = cast(Any, summary)

        with pytest.raises((AttributeError, TypeError)):
            mutable.state = EvidenceState.PASS
