"""Tests for override probe-plan construction, issue #5423 step 2.

A plan whose child request cannot differ from the parent value is a probe
that spends a live run and can never verify anything: `classify_override`
returns UNVERIFIED for equal values. These cases pin that such a plan is
unconstructible, and that `Sol Ultra` survives construction unaliased.

Discrimination. Twenty-one mutations were run against `_capability_probes.py`,
each removing or weakening one guard, with `__pycache__` cleared between every
mutation and its rerun. All twenty-one were killed, a behavior-preserving
inverted control survived, and the restored file was byte-compared against the
original. Every case marked NEGATIVE CONTROL below failed under at least one of
those mutations and is named by it. Cases marked CONFIRMATORY survived all
twenty-one, or failed only as collateral of a mutation aimed at a different
case; they are labeled because they are not evidence that any guard works.
"""

from __future__ import annotations

import pytest

from tests.eval._capability_probe_fixtures import (
    HarnessCapabilityError,
    ProbeError,
    _plan,
)


def test_a_plan_selects_the_first_candidate_that_differs_from_the_parent() -> None:
    """NEGATIVE CONTROL: an undiscriminating candidate must never be selected."""
    plan = _plan(candidates=("claude-opus-5", "gpt-5.6-sol"))

    assert plan.parent_value == "claude-opus-5"
    assert plan.child_value == "gpt-5.6-sol"


def test_an_equal_parent_and_child_value_cannot_produce_a_plan() -> None:
    """NEGATIVE CONTROL: the equal-value probe that can never verify anything."""
    with pytest.raises(ProbeError, match="cannot tell an honored override"):
        _plan(candidates=("claude-opus-5",))


def test_a_case_only_difference_cannot_produce_a_plan() -> None:
    """NEGATIVE CONTROL: a case-folding harness would echo the parent back."""
    with pytest.raises(ProbeError, match="cannot tell an honored override"):
        _plan(parent="Sol Ultra", candidates=("sol ultra", "  SOL ULTRA  "))


def test_sol_ultra_survives_plan_construction_unaliased() -> None:
    """NEGATIVE CONTROL: Sol Ultra is a literal, never folded onto a tier."""
    plan = _plan(
        capability_key="effort_override",
        parent="high",
        candidates=("Sol Ultra",),
    )

    assert plan.child_value == "Sol Ultra"
    assert plan.child_value not in {"high", "xhigh", "max"}


def test_sol_ultra_as_the_parent_still_admits_a_genuinely_different_child() -> None:
    """CONFIRMATORY: the guard rejects sameness, not the literal itself."""
    plan = _plan(capability_key="effort_override", parent="Sol Ultra", candidates=("high",))

    assert plan.parent_value == "Sol Ultra"
    assert plan.child_value == "high"


def test_a_plan_rejects_an_unknown_capability() -> None:
    """NEGATIVE CONTROL: only capabilities classify_override covers are probeable."""
    with pytest.raises(ProbeError, match="capability must be one of"):
        _plan(capability_key="concurrency_limit")


def test_a_plan_rejects_an_empty_parent_value() -> None:
    """NEGATIVE CONTROL: an unknown parent cannot discriminate."""
    with pytest.raises(ProbeError, match="parent_value must be"):
        _plan(parent="")


def test_a_plan_rejects_an_empty_harness() -> None:
    """NEGATIVE CONTROL: an unnamed harness cannot be recorded against."""
    with pytest.raises(ProbeError, match="harness must be"):
        _plan(harness="")


def test_a_plan_error_is_a_harness_capability_error() -> None:
    """CONFIRMATORY: callers keep one fail-closed except arm."""
    assert issubclass(ProbeError, HarnessCapabilityError)
