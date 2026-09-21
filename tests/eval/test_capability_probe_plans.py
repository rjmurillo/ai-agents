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

import json

import pytest

from tests.eval._capability_probe_fixtures import (
    HarnessCapabilityError,
    ProbeError,
    _plan,
)
from tests.eval._harness_capability_test_support import probes


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


def test_json_behavioral_plan_loads_an_override_command(tmp_path) -> None:
    plan_path = tmp_path / "probes.json"
    plan_path.write_text(
        json.dumps(
            {
                "probes": [
                    {
                        "harness": "copilot",
                        "capability": "model_override",
                        "parent_value": "gpt-5.6-sol",
                        "child_value": "claude-opus-5",
                        "argv": ["copilot", "--model", "claude-opus-5"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    probes_loaded = probes.load_behavioral_probes(plan_path)

    assert len(probes_loaded) == 1
    assert probes_loaded[0].command.argv[-1] == "claude-opus-5"


@pytest.mark.parametrize(
    ("parent_value", "child_value"),
    [
        ("gpt-5.6-sol", "gpt-5.6-sol"),
        ("Sol Ultra", "sol ultra"),
        ("Sol Ultra", "  Sol Ultra  "),
    ],
)
def test_behavioral_probe_rejects_an_inheriting_override(
    parent_value: str, child_value: str
) -> None:
    command = probes.ProbeCommand(
        harness="copilot",
        argv=("copilot", "--model", child_value),
    )

    with pytest.raises(ProbeError, match="does not differ from parent"):
        probes.BehavioralProbe(
            capability="model_override",
            harness="copilot",
            command=command,
            parent_value=parent_value,
            child_value=child_value,
        )


def test_json_behavioral_plan_rejects_an_inheriting_override(tmp_path) -> None:
    plan_path = tmp_path / "probes.json"
    plan_path.write_text(
        json.dumps(
            {
                "probes": [
                    {
                        "harness": "copilot",
                        "capability": "model_override",
                        "parent_value": "gpt-5.6-sol",
                        "child_value": "gpt-5.6-sol",
                        "argv": ["copilot", "--model", "gpt-5.6-sol"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ProbeError, match="does not differ from parent"):
        probes.load_behavioral_probes(plan_path)


def test_json_behavioral_plan_rejects_duplicate_capabilities(tmp_path) -> None:
    plan_path = tmp_path / "probes.json"
    probe = {
        "harness": "copilot",
        "capability": "subagent_support",
        "argv": ["copilot", "--prompt", "probe"],
    }
    plan_path.write_text(json.dumps({"probes": [probe, probe]}), encoding="utf-8")

    with pytest.raises(ProbeError, match="duplicate harness and capability"):
        probes.load_behavioral_probes(plan_path)


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
