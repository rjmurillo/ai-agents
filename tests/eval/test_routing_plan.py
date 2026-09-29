"""Tests for the zero-spend routing plan and matched-harness classification (issue #5424)."""

from __future__ import annotations

import socket
import subprocess
from typing import Any

import pytest

from tests.eval._routing_runner_test_support import (
    BOUNDED,
    CODEX_VERSION,
    cap,
    config_dict,
    make_record,
    matched_records,
    parse,
    plan_mod,
    scenarios,
)

RowStatus = plan_mod.RowStatus
Comparison = plan_mod.HarnessComparison
Status = cap.CapabilityStatus


def _plan(document: dict[str, Any] | None = None, records: Any = None) -> Any:
    config = parse(document or config_dict())
    return plan_mod.build_plan(config, records or matched_records(), scenarios())


def _rows(plan: Any, arm: str, scenario: str = BOUNDED) -> dict[str, Any]:
    return {r.harness: r for r in plan.rows if r.arm == arm and r.scenario_id == scenario}


def _doc_with_override(arm: str, override: dict[str, Any]) -> dict[str, Any]:
    """Override `arm` on copilot. C and D must track A, so an A override covers them too."""
    document = config_dict()
    tied = {"A", "C", "D"} if arm == "A" else {arm}
    for item in document["strategies"]:
        if item["arm"] in tied:
            item["harness_overrides"] = {"copilot": override}
    return document


def test_plan_expands_exactly_strategy_x_scenario_x_harness() -> None:
    plan = _plan()

    assert len(plan.rows) == 6 * len(scenarios()) * 2
    keys = {(r.scenario_id, r.arm, r.harness) for r in plan.rows}
    assert len(keys) == len(plan.rows)


def test_fully_verified_matched_harnesses_plan_every_combination() -> None:
    plan = _plan()

    assert plan.problems == ()
    assert all(row.status is RowStatus.PLANNED for row in plan.rows)
    assert all(row.eligibility == "ELIGIBLE_MATCHED" for row in plan.rows)


def test_two_matched_harnesses_form_an_explicit_matched_pair() -> None:
    plan = _plan()
    rows = _rows(plan, "A")

    assert {r.comparison for r in rows.values()} == {Comparison.MATCHED}
    assert rows["codex"].pair_id == rows["copilot"].pair_id == f"{BOUNDED}:A"
    assert rows["codex"].contract_sha == rows["copilot"].contract_sha
    assert f"{BOUNDED}:A" in plan.matched_pairs
    assert len(plan.matched_pairs) == 6 * len(scenarios())


@pytest.mark.parametrize(
    ("arm", "override", "field"),
    [
        ("A", {"max_concurrency": 2}, "max_concurrency"),
        ("A", {"max_correction_rounds": 1}, "max_correction_rounds"),
        ("A", {"work_packages": 2}, "work_packages"),
        (
            "B",
            {"reviewer": {"model": "gpt-5.6-terra", "effort": "high", "isolated": True}},
            "reviewer",
        ),
        ("E", {"orchestrator": {"model": "gpt-5.6-sol", "effort": "medium"}}, "routes"),
    ],
)
def test_a_config_difference_makes_the_pair_unmatched_and_names_the_field(
    arm: str, override: dict[str, Any], field: str
) -> None:
    rows = _rows(_plan(_doc_with_override(arm, override)), arm)

    assert {r.status for r in rows.values()} == {RowStatus.PLANNED}
    assert {r.comparison for r in rows.values()} == {Comparison.UNMATCHED}
    assert field in rows["codex"].comparison_reason
    assert (
        rows["codex"].pair_id is None and rows["codex"].contract_sha != rows["copilot"].contract_sha
    )


def test_same_model_label_with_different_harness_capability_is_unmatched() -> None:
    records = [make_record("codex", concurrency=3), make_record("copilot", concurrency=2)]

    rows = _rows(_plan(records=records), "A")

    assert {r.eligibility for r in rows.values()} == {"ELIGIBLE_UNMATCHED"}
    assert {r.status for r in rows.values()} == {RowStatus.PLANNED}
    assert {r.comparison for r in rows.values()} == {Comparison.UNMATCHED}
    assert "ELIGIBLE_UNMATCHED" in rows["codex"].comparison_reason


def test_unsupported_harness_arm_combination_is_rejected_before_spend() -> None:
    records = [
        make_record("codex"),
        make_record("copilot", statuses={"subagent_support": Status.UNSUPPORTED}),
    ]

    plan = _plan(records=records)
    rows = _rows(plan, "A")

    assert rows["copilot"].status is RowStatus.REJECTED
    assert rows["copilot"].eligibility == "UNSUPPORTED"
    assert rows["codex"].status is RowStatus.REJECTED
    assert plan.planned == () or all(row.arm in {"E"} for row in plan.planned)


def test_unverified_capability_rejects_the_arm_that_needs_it() -> None:
    records = [
        make_record("codex"),
        make_record("copilot", statuses={"reviewer_isolation": Status.UNVERIFIED}),
    ]

    plan = _plan(records=records)

    assert all(r.status is RowStatus.REJECTED for r in plan.rows if r.arm == "B")
    assert all(r.eligibility == "UNVERIFIED" for r in plan.rows if r.arm == "B")
    assert all(r.status is RowStatus.PLANNED for r in plan.rows if r.arm == "A")


def test_a_single_eligible_harness_has_no_harness_comparison() -> None:
    records = [make_record("codex"), make_record("copilot", version="other 9.9.9")]

    rows = _rows(_plan(records=records), "A")

    assert rows["copilot"].status is RowStatus.REJECTED
    assert "differs from matrix version" in rows["copilot"].reason
    assert rows["codex"].status is RowStatus.PLANNED
    assert rows["codex"].comparison is Comparison.NONE
    assert rows["codex"].pair_id is None


def test_a_requested_model_the_harness_never_ran_is_rejected() -> None:
    # gpt-6-terra satisfies the Terra family, so the matrix accepts the arm, but the
    # config asks for gpt-5.6-terra, which this harness was never seen running.
    observed = ("gpt-5.6-sol", "gpt-5.6-luna", "gpt-6-terra")
    records = [make_record("codex"), make_record("copilot", models=observed)]

    rows = _rows(_plan(records=records), "D")

    assert rows["copilot"].status is RowStatus.REJECTED
    assert rows["copilot"].eligibility == "UNVERIFIED"
    assert "gpt-5.6-terra" in rows["copilot"].reason and "not observed" in rows["copilot"].reason


def test_a_requested_effort_the_harness_never_ran_is_rejected() -> None:
    records = [make_record("codex"), make_record("copilot", efforts=("low", "medium"))]

    rows = _rows(_plan(records=records), "C")

    assert rows["copilot"].status is RowStatus.REJECTED
    assert "effort 'high' not observed on copilot" in rows["copilot"].reason
    assert rows["codex"].status is RowStatus.PLANNED


def test_a_harness_the_matrix_does_not_classify_is_unsupported() -> None:
    plan = _plan(records=[make_record("codex")])

    assert plan.problems == ("harness 'copilot' is not classified by the capability matrix",)
    rows = _rows(plan, "A")
    assert rows["copilot"].status is RowStatus.REJECTED
    assert rows["copilot"].eligibility == "UNSUPPORTED"
    assert "not classified" in rows["copilot"].reason


def test_only_eligible_classes_are_ever_planned() -> None:
    plan = _plan(
        records=[make_record("codex", concurrency=3), make_record("copilot", concurrency=2)]
    )

    for row in plan.rows:
        assert (row.status is RowStatus.PLANNED) == (
            row.eligibility in {"ELIGIBLE_MATCHED", "ELIGIBLE_UNMATCHED"}
        )


def test_routes_follow_the_scenario_difficulty_class() -> None:
    plan = _plan()
    ordinary = _rows(plan, "C", "RB-01-bounded-implementation")["codex"]
    fallback = _rows(plan, "C", "RB-02-multi-file-invariants")["codex"]

    assert [r.route.model for r in ordinary.routes if r.role == "worker"] == ["gpt-5.6-luna"]
    assert [r.route.model for r in fallback.routes if r.role == "worker"] == ["gpt-5.6-sol"]


def test_contract_covers_what_matched_comparison_must_hold_constant() -> None:
    scenario = next(s for s in scenarios() if s.scenario_id == BOUNDED)
    contract = plan_mod.semantic_contract(strategy_for("B"), scenario)

    assert set(contract) == {
        "scenario_id", "scenario_state", "task_text", "grader", "difficulty", "routes",
        "work_packages", "max_concurrency", "max_correction_rounds", "reviewer",
        "fresh_context_boundary", "handoff_artifact",
    }  # fmt: skip
    assert plan_mod.contract_differences(contract, dict(contract, task_text="x")) == ["task_text"]
    assert plan_mod.contract_differences(contract, contract) == []


def strategy_for(arm: str) -> Any:
    return parse(config_dict()).strategy_for(arm, "codex")


def test_scenario_state_and_grader_feed_the_contract_hash() -> None:
    by_id = {s.scenario_id: s for s in scenarios()}
    first = plan_mod.semantic_contract(strategy_for("A"), by_id[BOUNDED])
    second = plan_mod.semantic_contract(strategy_for("A"), by_id["RB-03-investigate-before-edit"])

    for key in ("scenario_id", "scenario_state", "task_text", "grader"):
        assert first[key] != second[key]


def test_planning_makes_zero_model_calls_and_starts_no_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("dry-run plan reached a process or network boundary")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    import _providers

    monkeypatch.setattr(_providers, "resolve_provider", forbidden)

    plan = _plan()

    assert plan.planned


def test_unknown_config_version_reason_names_both_versions() -> None:
    records = [make_record("codex", version="codex-cli 9.9.9"), make_record("copilot")]

    row = _rows(_plan(records=records), "A")["codex"]

    assert CODEX_VERSION in row.reason and "codex-cli 9.9.9" in row.reason
