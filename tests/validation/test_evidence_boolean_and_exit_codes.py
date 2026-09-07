"""The two contract edges #5641 left unenforced (issue #5646 items 1, 4, 5).

Item 1: ``CheckOutcome`` defined no ``__bool__``, so a dataclass instance was
truthy in every state. The migration path is where that bites. 60 of the 64
pre-PR gates still return ``bool`` and are called from boolean-context code, so
converting one to return a ``CheckOutcome`` without converting its call site
produced a gate that always passes, and mypy could not object because both
types are legal in a boolean context. Every test below that asserts a raise is
a negative control on that fail-open.

Item 5: ``REASON_AUTH_UNAVAILABLE`` was defined and exported and mapped to no
exit code, so ADR-035's code 4 was unreachable and an expired token exited 1,
sending the reader to fix a violation that does not exist.

Item 4: ``default_pre_pr_policy``'s docstring described a policy with one
exception licensing only SKIP. The function it documents returns three, two of
which license BLOCKED. The last class here pins the description to the object
so the two cannot drift apart again.
"""

from __future__ import annotations

import re

import pytest

from scripts.validation.evidence import (
    REASON_AUTH_UNAVAILABLE,
    REASON_DIFF_FAILED,
    REASON_SCRIPT_ABSENT,
    REASON_TOOL_ABSENT,
    WORKING_TREE,
    CheckOutcome,
    EvidenceState,
    GatePolicy,
    PolicyException,
    aggregate,
    default_pre_pr_policy,
    exit_code_for,
)

_ONE_PER_STATE: dict[EvidenceState, CheckOutcome] = {
    EvidenceState.PASS: CheckOutcome.passed(
        "v", revision=WORKING_TREE, scope="the tree", examined=1
    ),
    EvidenceState.FAIL: CheckOutcome.failed("v", reason="lint.violation", findings=1),
    EvidenceState.SKIP: CheckOutcome.skipped("v", reason=REASON_SCRIPT_ABSENT),
    EvidenceState.BLOCKED: CheckOutcome.blocked("v", reason=REASON_TOOL_ABSENT),
    EvidenceState.UNKNOWN: CheckOutcome.unknown("v", reason=REASON_DIFF_FAILED),
}


class TestCheckOutcomeHasNoTruthValue:
    """A five-state result must refuse a two-state question, in every state."""

    @pytest.mark.parametrize("state", list(EvidenceState))
    def test_bool_raises_for_every_state(self, state: EvidenceState) -> None:
        """PASS raises too.

        Answering ``True`` for PASS would keep the stale call site running and
        silently re-collapse five states to two, which is the whole defect.
        Refusing uniformly is what makes the raise a migration signal rather
        than a special case someone can route around.
        """
        with pytest.raises(TypeError):
            bool(_ONE_PER_STATE[state])

    @pytest.mark.parametrize("state", list(EvidenceState))
    def test_the_message_names_the_state_and_the_validator(
        self, state: EvidenceState
    ) -> None:
        """The reader has to learn which gate to fix from the traceback alone."""
        with pytest.raises(TypeError) as excinfo:
            bool(_ONE_PER_STATE[state])

        message = str(excinfo.value)
        assert state.value in message
        assert "v" in message

    def test_the_message_names_the_two_replacements(self) -> None:
        """A refusal with no alternative teaches the reader to cast around it."""
        with pytest.raises(TypeError) as excinfo:
            bool(_ONE_PER_STATE[EvidenceState.FAIL])

        message = str(excinfo.value)
        assert "outcome.state is EvidenceState.PASS" in message
        assert "policy.accepts(outcome)" in message

    def test_an_if_statement_on_a_failing_outcome_raises(self) -> None:
        """The discriminating case: this read as success before the fix.

        This is the exact shape a half-migrated gate leaves behind, written out
        rather than described, because the defect is in the syntax and not in
        an explicit ``bool()`` call anybody would notice in review.
        """
        outcome = _ONE_PER_STATE[EvidenceState.FAIL]

        with pytest.raises(TypeError):
            if outcome:
                pytest.fail("a FAIL outcome must never reach the success branch")

    def test_negation_raises_too(self) -> None:
        """``not outcome`` is the same question inverted, and gets the same answer."""
        with pytest.raises(TypeError):
            not _ONE_PER_STATE[EvidenceState.BLOCKED]

    def test_the_state_comparison_the_message_recommends_still_works(self) -> None:
        """Positive control. The refusal must not break the supported reads."""
        assert _ONE_PER_STATE[EvidenceState.PASS].state is EvidenceState.PASS
        assert _ONE_PER_STATE[EvidenceState.FAIL].state is not EvidenceState.PASS
        assert GatePolicy().accepts(_ONE_PER_STATE[EvidenceState.PASS])
        assert not GatePolicy().accepts(_ONE_PER_STATE[EvidenceState.FAIL])

    def test_an_outcome_is_still_usable_where_no_truth_value_is_asked_for(self) -> None:
        """Edge: containers test identity and equality, not truthiness.

        ``AggregateOutcome`` holds outcomes in tuples and ``rejected`` filters
        them, so a ``__bool__`` that raised on any container operation would
        take the runner down instead of the stale call site.
        """
        outcomes = tuple(_ONE_PER_STATE.values())
        summary = aggregate("gate", outcomes)

        assert len(summary.outcomes) == len(outcomes)
        assert summary.outcomes[0] in outcomes
        assert summary.to_dict()["counts"]["PASS"] == 1


def _auth_blocked(validator: str = "gh_auth") -> CheckOutcome:
    """Return the outcome a gate produces when its credential is gone."""
    return CheckOutcome.blocked(
        validator,
        reason=REASON_AUTH_UNAVAILABLE,
        scope="the GitHub API",
        detail="gh reported an expired token, so no PR state was read",
    )


class TestAuthExitCode:
    """ADR-035 line 58 reserves 4 for auth so the reader re-authenticates."""

    def test_a_blocked_auth_gate_exits_four(self) -> None:
        """The discriminating case: this returned 1 before the fix."""
        summary = aggregate("pre_pr", [_auth_blocked()])

        assert exit_code_for(summary) == 4

    def test_a_blocked_non_auth_gate_still_exits_three(self) -> None:
        """Negative control. A missing binary is an external dependency, not a login."""
        summary = aggregate(
            "pre_pr", [CheckOutcome.blocked("v", reason=REASON_TOOL_ABSENT)]
        )

        assert exit_code_for(summary) == 3

    def test_a_fail_outranks_an_auth_block(self) -> None:
        """A proven violation is more actionable than a credential.

        Reporting 4 here would send the reader to a login prompt while a real
        defect went unmentioned, which inverts ``_PRECEDENCE``.
        """
        summary = aggregate(
            "pre_pr",
            [_auth_blocked(), CheckOutcome.failed("v", reason="lint.violation")],
        )

        assert exit_code_for(summary) == 1

    def test_an_unknown_carrying_the_auth_reason_does_not_exit_four(self) -> None:
        """Edge: 4 specializes BLOCKED, not the reason code in isolation.

        UNKNOWN means an observation was attempted and came back untrustworthy.
        That is a logic error whatever the reason string says, and mapping it to
        4 would tell the reader to authenticate when the evidence is the problem.
        """
        summary = aggregate(
            "pre_pr", [CheckOutcome.unknown("v", reason=REASON_AUTH_UNAVAILABLE)]
        )

        assert exit_code_for(summary) == 1

    def test_a_licensed_auth_block_exits_zero(self) -> None:
        """Edge: only rejected outcomes decide the code.

        A policy that licenses the auth block has declared it non-blocking, so
        promoting it to 4 would fail a run the policy accepted.
        """
        policy = GatePolicy(
            exceptions=(
                PolicyException(
                    validator="gh_auth",
                    states=frozenset({EvidenceState.BLOCKED}),
                    reasons=frozenset({REASON_AUTH_UNAVAILABLE}),
                    justification="test fixture: this gate is advisory",
                ),
            )
        )
        summary = aggregate("pre_pr", [_auth_blocked()], policy)

        assert exit_code_for(summary) == 0

    def test_every_adr_035_code_the_runner_can_reach_is_reachable(self) -> None:
        """The defect class, not the instance.

        ``REASON_NO_OUTCOMES`` shipped in #5641 the same way: defined,
        exported, wired to nothing. This asserts the whole 0-to-4 range the
        runner claims, so the next unreachable code fails here rather than in
        a review six weeks later.
        """
        reachable = {
            exit_code_for(aggregate("pre_pr", outcomes))
            for outcomes in (
                [_ONE_PER_STATE[EvidenceState.PASS]],
                [_ONE_PER_STATE[EvidenceState.FAIL]],
                [CheckOutcome.skipped("v", reason=REASON_SCRIPT_ABSENT)],
                [_ONE_PER_STATE[EvidenceState.BLOCKED]],
                [_auth_blocked()],
            )
        }

        assert reachable == {0, 1, 2, 3, 4}


_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


class TestPolicyDocstringMatchesThePolicy:
    """The shipped description of the policy must match the policy.

    ``default_pre_pr_policy``'s docstring claimed "One exception" and that
    ``BLOCKED`` got none, three lines above a return statement constructing
    three exceptions, two of them licensing ``BLOCKED``. Prose is the only part
    of a policy a reviewer reads at speed, so a wrong description is a wrong
    policy for review purposes (issue #5646 item 4).
    """

    def test_the_stated_exception_count_matches_the_returned_one(self) -> None:
        """The claim that was false when #5641 shipped."""
        doc = default_pre_pr_policy.__doc__ or ""
        match = re.search(
            rf"\b({'|'.join(_NUMBER_WORDS)})\b exceptions?", doc, re.IGNORECASE
        )

        assert match is not None, "the docstring must state how many exceptions there are"
        assert _NUMBER_WORDS[match.group(1).lower()] == len(
            default_pre_pr_policy().exceptions
        )

    def test_the_docstring_names_every_validator_it_licenses(self) -> None:
        """A licence nobody can find in the prose is an unreviewed licence."""
        doc = default_pre_pr_policy.__doc__ or ""

        for exception in default_pre_pr_policy().exceptions:
            if exception.validator != "*":
                assert exception.validator in doc

    def test_the_docstring_names_every_state_it_licenses(self) -> None:
        """"BLOCKED gets no exception" was false; this is what makes it stay false."""
        doc = default_pre_pr_policy.__doc__ or ""
        licensed = {
            state.value
            for exception in default_pre_pr_policy().exceptions
            for state in exception.states
        }

        assert licensed == {"SKIP", "BLOCKED"}
        for state_name in licensed:
            assert state_name in doc

    def test_unknown_is_licensed_by_nothing(self) -> None:
        """Negative control on the two tests above.

        They assert the docstring keeps up with the policy. This asserts the
        policy itself has not quietly grown the one exception that would put
        unreadable evidence back on the PASS side.
        """
        for exception in default_pre_pr_policy().exceptions:
            assert EvidenceState.UNKNOWN not in exception.states
