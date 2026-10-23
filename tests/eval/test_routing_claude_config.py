"""Claude arms A to F in the checked-in routing config (issue #5426, Amendment 3).

Role mapping, owner decision D10 on 2026-10-23: Sol is `claude-opus-5-5`, Luna is
`claude-haiku-5-5`, Terra is `claude-sonnet-5-5`, efforts unchanged. Every fairness invariant
the Codex arms hold must hold for the Claude arms too.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.eval._routing_runner_test_support import (
    REAL_MATRIX,
    cap,
    cli,
    config_mod,
    full_config_dict,
    parse,
    plan_mod,
    scenarios,
)

ROLE_MODEL = {
    "gpt-5.6-sol": "claude-opus-5-5",
    "gpt-5.6-luna": "claude-haiku-5-5",
    "gpt-5.6-terra": "claude-sonnet-5-5",
}
ARMS = "ABCDEF"


def _routes(strategy: Any) -> list[tuple[str, str, str]]:
    """Every (role, model, effort) a strategy requests, in a stable order."""
    routes = [("orchestrator", strategy.orchestrator.model, strategy.orchestrator.effort)]
    routes += [
        (f"worker:{difficulty.value}", route.model, route.effort)
        for difficulty, route in sorted(strategy.workers.items(), key=lambda i: i[0].value)
    ]
    if strategy.implementer:
        routes.append(("implementer", strategy.implementer.model, strategy.implementer.effort))
    if strategy.reviewer:
        reviewer = strategy.reviewer.route
        routes.append(("reviewer", reviewer.model, reviewer.effort))
    return routes


def test_the_config_names_claude_pinned_to_the_matrix_version() -> None:
    config = parse(full_config_dict())
    matrix = {r.harness: r for r in cap.load_matrix(REAL_MATRIX)}

    refs = {ref.harness: ref.version for ref in config.harnesses}
    assert list(refs) == ["codex", "copilot", "claude"]
    assert refs["claude"] == matrix["claude"].version == "2.1.309 (Claude Code)"


@pytest.mark.parametrize("arm", list(ARMS))
def test_each_claude_route_is_the_codex_route_with_its_role_model_and_the_same_effort(
    arm: str,
) -> None:
    config = parse(full_config_dict())

    codex = _routes(config.strategy_for(arm, "codex"))
    claude = _routes(config.strategy_for(arm, "claude"))

    assert [(role, ROLE_MODEL[model], effort) for role, model, effort in codex] == claude


@pytest.mark.parametrize("arm", list(ARMS))
def test_every_fairness_invariant_holds_across_the_two_harnesses(arm: str) -> None:
    config = parse(full_config_dict())
    codex, claude = config.strategy_for(arm, "codex"), config.strategy_for(arm, "claude")

    for name in (
        "topology",
        "max_concurrency",
        "max_correction_rounds",
        "work_packages",
        "fresh_context_boundary",
        "handoff_artifact",
    ):
        assert getattr(codex, name) == getattr(claude, name), name
    assert (codex.reviewer is None) == (claude.reviewer is None)
    if codex.reviewer and claude.reviewer:
        assert codex.reviewer.isolated == claude.reviewer.isolated


def test_the_claude_arms_name_only_the_three_mapped_models() -> None:
    config = parse(full_config_dict())

    models = {m for arm in ARMS for _, m, _ in _routes(config.strategy_for(arm, "claude"))}

    assert models == set(ROLE_MODEL.values())


def test_the_arm_c_and_d_workers_are_haiku_and_sonnet_at_high() -> None:
    config = parse(full_config_dict())
    ordinary = config_mod.DifficultyClass.ORDINARY_BOUNDED

    c = config.strategy_for("C", "claude").workers[ordinary]
    d = config.strategy_for("D", "claude").workers[ordinary]

    assert (c.model, c.effort) == ("claude-haiku-5-5", "high")
    assert (d.model, d.effort) == ("claude-sonnet-5-5", "high")


# --- planning --------------------------------------------------------------------


def _plan() -> Any:
    return plan_mod.build_plan(parse(full_config_dict()), cap.load_matrix(REAL_MATRIX), scenarios())


def _rows(plan: Any, harness: str) -> list[Any]:
    return [row for row in plan.rows if row.harness == harness]


def test_codex_keeps_36_planned_unmatched_rows() -> None:
    codex = _rows(_plan(), "codex")

    assert len(codex) == 36
    assert {(r.status.value, r.eligibility) for r in codex} == {("PLANNED", "ELIGIBLE_UNMATCHED")}


def test_claude_plans_the_arms_whose_models_have_verified_effort_behavior() -> None:
    claude = _rows(_plan(), "claude")
    planned = [r for r in claude if r.status is plan_mod.RowStatus.PLANNED]
    rejected = [r for r in claude if r.status is plan_mod.RowStatus.REJECTED]

    assert len(claude) == 36 and len(planned) == 24 and len(rejected) == 12
    assert {r.arm for r in planned} == {"A", "B", "E", "F"}
    assert {r.eligibility for r in planned} == {"ELIGIBLE_UNMATCHED"}
    assert {r.arm for r in rejected} == {"C", "D"}
    assert {r.eligibility for r in rejected} == {"UNVERIFIED"}
    assert all("classifies arm" in r.reason for r in rejected)


def test_no_row_is_matched_or_paired_across_harnesses() -> None:
    plan = _plan()

    assert plan.problems == () and plan.matched_pairs == ()
    assert {r.comparison for r in plan.planned} == {plan_mod.HarnessComparison.NONE}
    assert {r.pair_id for r in plan.planned} == {None}


def test_every_planned_claude_row_requests_a_model_and_effort_the_matrix_observed() -> None:
    record = next(r for r in cap.load_matrix(REAL_MATRIX) if r.harness == "claude")

    for row in _rows(_plan(), "claude"):
        if row.status is plan_mod.RowStatus.PLANNED:
            for route in row.routes:
                assert route.route.model in record.supported_models
                assert route.route.effort in record.supported_efforts


def test_a_claude_version_the_matrix_does_not_pin_rejects_every_claude_row() -> None:
    document = full_config_dict()
    next(h for h in document["harnesses"] if h["harness"] == "claude")["version"] = "2.1.307"
    plan = plan_mod.build_plan(parse(document), cap.load_matrix(REAL_MATRIX), scenarios())

    claude = _rows(plan, "claude")

    assert {r.status for r in claude} == {plan_mod.RowStatus.REJECTED}
    assert all("differs from matrix version" in r.reason for r in claude if r.arm in "BF")


def test_the_dry_run_cli_reports_60_planned_rows_across_codex_and_claude(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main([])

    report = json.loads(capsys.readouterr().out)
    planned = [r for r in report["rows"] if r["status"] == "PLANNED"]
    assert exit_code == cli.EXIT_OK and report["model_calls"] == 0
    assert report["planned"] == 60 == len(planned)
    assert {h: sum(1 for r in planned if r["harness"] == h) for h in ("codex", "claude")} == {
        "codex": 36,
        "claude": 24,
    }
    assert report["matched_pairs"] == []


# --- invariants bind the claude arms too ---------------------------------------------------


def _claude_override(document: dict[str, Any], arm: str) -> dict[str, Any]:
    strategy = next(s for s in document["strategies"] if s["arm"] == arm)
    return strategy["harness_overrides"]["claude"]


def test_an_arm_a_parent_that_is_not_the_sol_role_is_refused_on_claude() -> None:
    document = full_config_dict()
    _claude_override(document, "A")["orchestrator"]["model"] = "claude-haiku-5-5"

    with pytest.raises(config_mod.RoutingConfigError, match="arm A on claude"):
        parse(document)


def test_arm_c_must_still_differ_from_arm_a_only_in_the_ordinary_worker_on_claude() -> None:
    document = full_config_dict()
    _claude_override(document, "C")["orchestrator"]["effort"] = "high"

    with pytest.raises(config_mod.RoutingConfigError, match="arm C on claude: C differs from A"):
        parse(document)


def test_arm_b_on_claude_still_needs_an_isolated_reviewer() -> None:
    document = full_config_dict()
    _claude_override(document, "B")["reviewer"]["isolated"] = False

    with pytest.raises(config_mod.RoutingConfigError, match="B needs an isolated reviewer"):
        parse(document)
