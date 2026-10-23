"""A standalone harness never joins a matched comparison group (issue #5426, Amendment 3)."""

from __future__ import annotations

import dataclasses

from tests.eval._routing_runner_test_support import (
    config_dict,
    make_record,
    parse,
    plan_mod,
    scenarios,
)


def _plan(*, standalone: bool) -> plan_mod.Plan:
    copilot = dataclasses.replace(make_record("copilot"), standalone=standalone)
    return plan_mod.build_plan(parse(config_dict()), [make_record("codex"), copilot], scenarios())


def test_two_active_harnesses_with_one_contract_are_matched() -> None:
    plan = _plan(standalone=False)

    assert plan.matched_pairs
    assert {row.comparison for row in plan.planned} == {plan_mod.HarnessComparison.MATCHED}


def test_a_standalone_harness_gets_no_pair_and_every_row_reads_as_alone() -> None:
    plan = _plan(standalone=True)

    assert plan.planned and not plan.matched_pairs
    assert {row.pair_id for row in plan.planned} == {None}
    assert {row.comparison for row in plan.planned} == {plan_mod.HarnessComparison.NONE}
    assert {row.comparison_reason for row in plan.planned} == {"only one harness is planned"}


def test_a_standalone_harness_changes_no_row_count_or_status() -> None:
    shared, alone = _plan(standalone=False), _plan(standalone=True)

    def shape(plan: plan_mod.Plan) -> list[tuple[str, str, str, str]]:
        return [(r.scenario_id, r.arm, r.harness, r.status.value) for r in plan.rows]

    assert sorted(shape(shared)) == sorted(shape(alone))
