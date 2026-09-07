"""Producer-side contract tests for the typed evidence states (issue #5635).

Covers the five states, both directions of every :class:`CheckOutcome`
invariant, the bool-to-outcome migration seam, and the aggregation precedence.
The gate-side half (policy, exceptions, aggregate summaries, exit codes) is in
``test_evidence_policy.py``.

The negative cases are the point: the defect this contract replaces was a
validator reporting ``True`` for a check that never ran, so every test proving
a non-``PASS`` state cannot become ``PASS`` is a negative control on it.
"""

from __future__ import annotations

import json

import pytest

from scripts.validation.evidence import (
    REASON_BASE_REF_UNRESOLVED,
    REASON_DIFF_FAILED,
    REASON_LEGACY_BOOLEAN,
    REASON_MALFORMED_OUTPUT,
    REASON_SCRIPT_ABSENT,
    REASON_TOOL_ABSENT,
    WORKING_TREE,
    CheckOutcome,
    EvidenceState,
    coerce_outcome,
    worst_state,
)


class TestEvidenceState:
    """The five states and their string identity."""

    def test_defines_exactly_the_five_contract_states(self) -> None:
        """No sixth state creeps in without this test noticing."""
        assert {state.value for state in EvidenceState} == {
            "PASS",
            "FAIL",
            "SKIP",
            "BLOCKED",
            "UNKNOWN",
        }

    def test_compares_equal_to_its_bare_string(self) -> None:
        """Existing code comparing against "PASS" keeps working."""
        assert EvidenceState.PASS == "PASS"
        assert EvidenceState.BLOCKED != "PASS"


class TestCheckOutcomeConstructors:
    """Each constructor reaches its own state with the fields that state needs."""

    def test_passed_records_revision_scope_and_zero_findings(self) -> None:
        """A PASS carries the evidence that makes it falsifiable."""
        outcome = CheckOutcome.passed(
            "validate_session_end", revision="abc1234", scope="2 session logs", examined=2
        )

        assert outcome.state is EvidenceState.PASS
        assert outcome.revision == "abc1234"
        assert outcome.examined == 2
        assert outcome.findings == 0
        assert outcome.reason == ""

    def test_failed_records_a_reason_and_finding_count(self) -> None:
        """A FAIL says what it found."""
        outcome = CheckOutcome.failed("v", reason="lint.violation", findings=3)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.findings == 3

    def test_skipped_blocked_and_unknown_each_reach_their_state(self) -> None:
        """The three non-PASS, non-FAIL states are distinct and reachable."""
        skipped = CheckOutcome.skipped("v", reason=REASON_SCRIPT_ABSENT)
        blocked = CheckOutcome.blocked("v", reason=REASON_BASE_REF_UNRESOLVED)
        unknown = CheckOutcome.unknown("v", reason=REASON_DIFF_FAILED)

        assert skipped.state is EvidenceState.SKIP
        assert blocked.state is EvidenceState.BLOCKED
        assert unknown.state is EvidenceState.UNKNOWN

    def test_with_duration_returns_a_timed_copy(self) -> None:
        """The runner owns the clock and stamps the validator's result."""
        outcome = CheckOutcome.passed("v", revision=WORKING_TREE, scope="tree")

        timed = outcome.with_duration(2.5)

        assert timed.duration_seconds == 2.5
        assert outcome.duration_seconds == 0.0


class TestCheckOutcomeInvariants:
    """A result whose fields contradict its state is rejected at construction."""

    def test_pass_without_a_revision_is_rejected(self) -> None:
        """A PASS that names no revision is an unfalsifiable claim."""
        with pytest.raises(ValueError, match="PASS requires a revision"):
            CheckOutcome(validator="v", state=EvidenceState.PASS, scope="tree")

    def test_pass_without_a_scope_is_rejected(self) -> None:
        """A PASS that names no scope cannot say what it proved."""
        with pytest.raises(ValueError, match="PASS requires a scope"):
            CheckOutcome(validator="v", state=EvidenceState.PASS, revision="HEAD")

    def test_pass_carrying_a_reason_code_is_rejected(self) -> None:
        """A reason explains why a check did not prove its contract."""
        with pytest.raises(ValueError, match="must not carry a reason"):
            CheckOutcome(
                validator="v",
                state=EvidenceState.PASS,
                revision="HEAD",
                scope="tree",
                reason=REASON_DIFF_FAILED,
            )

    def test_pass_reporting_findings_is_rejected(self) -> None:
        """A check that found violations did not prove its contract."""
        with pytest.raises(ValueError, match="must not report 2 finding"):
            CheckOutcome(
                validator="v",
                state=EvidenceState.PASS,
                revision="HEAD",
                scope="tree",
                findings=2,
            )

    @pytest.mark.parametrize(
        "state",
        [
            EvidenceState.FAIL,
            EvidenceState.SKIP,
            EvidenceState.BLOCKED,
            EvidenceState.UNKNOWN,
        ],
    )
    def test_non_pass_without_a_reason_is_rejected(self, state: EvidenceState) -> None:
        """Every blocking or absent state names a machine-readable reason."""
        with pytest.raises(ValueError, match="requires a machine-readable reason"):
            CheckOutcome(validator="v", state=state)

    @pytest.mark.parametrize(
        "reason",
        ["Not A Slug", "UPPER.case", "trailing.", ".leading", "has space", "1leading_digit"],
    )
    def test_reason_that_is_not_a_dotted_slug_is_rejected(self, reason: str) -> None:
        """Machine-readable means a consumer can branch on it."""
        with pytest.raises(ValueError, match="not a machine-readable"):
            CheckOutcome(validator="v", state=EvidenceState.FAIL, reason=reason)

    @pytest.mark.parametrize("reason", ["diff.failed", "timeout", "a.b.c", "base_ref.unresolved"])
    def test_dotted_lowercase_slugs_are_accepted(self, reason: str) -> None:
        """The shapes this tree actually uses must pass the pattern."""
        assert CheckOutcome(validator="v", state=EvidenceState.FAIL, reason=reason).reason == reason

    def test_blank_validator_name_is_rejected(self) -> None:
        """An anonymous result cannot be attributed in a summary."""
        with pytest.raises(ValueError, match="non-empty name"):
            CheckOutcome(validator="   ", state=EvidenceState.FAIL, reason="x.y")

    def test_non_enum_state_is_rejected(self) -> None:
        """A bare string state would bypass every invariant below it."""
        with pytest.raises(TypeError, match="must be an EvidenceState"):
            CheckOutcome(validator="v", state="PASS")  # type: ignore[arg-type]

    @pytest.mark.parametrize("field_name", ["examined", "findings"])
    def test_negative_counts_are_rejected(self, field_name: str) -> None:
        """A negative count is a measurement bug, not evidence."""
        with pytest.raises(ValueError, match=f"{field_name} must not be negative"):
            CheckOutcome(
                validator="v", state=EvidenceState.FAIL, reason="x.y", **{field_name: -1}
            )

    def test_negative_duration_is_rejected(self) -> None:
        """A negative duration means the clock was read wrong."""
        with pytest.raises(ValueError, match="duration_seconds must not be negative"):
            CheckOutcome(validator="v", state=EvidenceState.FAIL, reason="x.y", duration_seconds=-1)

    def test_examined_zero_is_accepted_on_a_pass(self) -> None:
        """"0 violations in 0 files" is a legitimate empty-set pass."""
        outcome = CheckOutcome.passed("v", revision="HEAD", scope="changed files", examined=0)

        assert outcome.examined == 0


class TestCheckOutcomeSerialization:
    """The machine-readable form a consumer parses."""

    def test_to_dict_is_json_serializable_and_uses_state_names(self) -> None:
        """A consumer reads "BLOCKED", not an enum repr."""
        outcome = CheckOutcome.blocked(
            "v", reason=REASON_BASE_REF_UNRESOLVED, detail="origin/main missing"
        )

        payload = json.loads(json.dumps(outcome.to_dict()))

        assert payload["state"] == "BLOCKED"
        assert payload["reason"] == REASON_BASE_REF_UNRESOLVED
        assert payload["detail"] == "origin/main missing"

    def test_summary_line_names_the_reason_and_the_scope(self) -> None:
        """Human output must distinguish "did not apply" from "could not run"."""
        line = CheckOutcome.blocked(
            "validate_session_end", reason=REASON_BASE_REF_UNRESOLVED, scope="branch vs base"
        ).summary_line()

        assert "[BLOCKED]" in line
        assert f"reason={REASON_BASE_REF_UNRESOLVED}" in line
        assert "scope=branch vs base" in line

    def test_summary_line_reports_the_finding_count_on_a_failure(self) -> None:
        """A reader sees how much is broken without opening the log."""
        line = CheckOutcome.failed(
            "v", reason="lint.violation", examined=381, findings=2
        ).summary_line()

        assert "examined=381" in line
        assert "findings=2" in line

    def test_summary_line_reports_the_examined_count_on_an_empty_pass(self) -> None:
        """ci-scripts MUST 12: name the examined count, never a bare OK."""
        line = CheckOutcome.passed(
            "v", revision="HEAD", scope="changed workflow files", examined=0
        ).summary_line()

        assert "examined=0" in line


class TestCoerceOutcome:
    """The migration seam between bool validators and typed ones."""

    def test_check_outcome_passes_through_unchanged(self) -> None:
        """A migrated validator's own evidence is never rewritten."""
        original = CheckOutcome.blocked("v", reason=REASON_TOOL_ABSENT)

        assert coerce_outcome("gate name", original) is original

    def test_true_becomes_pass_tagged_as_an_unmigrated_contract(self) -> None:
        """An unmigrated row stays countable rather than invisible."""
        outcome = coerce_outcome("gate", True)

        assert outcome.state is EvidenceState.PASS
        assert "unmigrated" in outcome.scope

    def test_false_becomes_fail_with_the_legacy_reason_code(self) -> None:
        """A boolean failure is still a failure, and says where it came from."""
        outcome = coerce_outcome("gate", False)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == REASON_LEGACY_BOOLEAN

    @pytest.mark.parametrize("result", [None, "PASS", 0, 1, [], {"state": "PASS"}])
    def test_anything_else_becomes_unknown_never_pass(self, result: object) -> None:
        """A validator that returned None told the runner nothing.

        NEGATIVE CONTROL for issue #5635: the truthy values here (``1``,
        ``"PASS"``, the dict) would each become ``PASS`` under a ``bool(result)``
        coercion. They must not.
        """
        outcome = coerce_outcome("gate", result)

        assert outcome.state is EvidenceState.UNKNOWN
        assert outcome.reason == REASON_MALFORMED_OUTPUT


class TestWorstState:
    """Aggregation precedence, including the empty case."""

    def test_empty_input_is_unknown_not_pass(self) -> None:
        """A run that examined nothing proved nothing."""
        assert worst_state([]) is EvidenceState.UNKNOWN

    @pytest.mark.parametrize(
        ("states", "expected"),
        [
            ([EvidenceState.PASS], EvidenceState.PASS),
            ([EvidenceState.PASS, EvidenceState.SKIP], EvidenceState.SKIP),
            ([EvidenceState.SKIP, EvidenceState.BLOCKED], EvidenceState.BLOCKED),
            ([EvidenceState.BLOCKED, EvidenceState.UNKNOWN], EvidenceState.UNKNOWN),
            ([EvidenceState.UNKNOWN, EvidenceState.FAIL], EvidenceState.FAIL),
            (
                [EvidenceState.PASS, EvidenceState.FAIL, EvidenceState.BLOCKED],
                EvidenceState.FAIL,
            ),
        ],
    )
    def test_worst_wins_by_precedence(
        self, states: list[EvidenceState], expected: EvidenceState
    ) -> None:
        """Worst-wins, so a single bad child cannot be averaged away."""
        assert worst_state(states) is expected

    def test_unrecognized_state_raises_rather_than_defaulting(self) -> None:
        """A state outside the contract must not silently become PASS."""
        with pytest.raises(ValueError, match="unrecognized states"):
            worst_state(["MAYBE"])  # type: ignore[list-item]
