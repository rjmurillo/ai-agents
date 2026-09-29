"""Deterministic fake-runner tests for the routing benchmark (issue #5424).

Every case drives `run_planned` through `ScriptedBackend`, which grades with
the real grader and the real corpus. No model is called.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest

from tests.eval._routing_runner_test_support import (
    BOUNDED,
    MODELS,
    backend_mod,
    cap,
    config_dict,
    dag_mod,
    make_record,
    matched_records,
    parse,
    plan_mod,
    result_mod,
    run_mod,
    scenarios,
)

Status = result_mod.RunStatus
Script = backend_mod.Script


def _scenario(scenario_id: str = BOUNDED) -> Any:
    return next(s for s in scenarios() if s.scenario_id == scenario_id)


def _plan(document: dict[str, Any] | None = None, records: Any = None) -> tuple[Any, Any]:
    config = parse(document or config_dict())
    return config, plan_mod.build_plan(config, records or matched_records(), scenarios())


def _run(
    arm: str,
    harness: str = "codex",
    *,
    scenario_id: str = BOUNDED,
    script: backend_mod.Script | None = None,
    document: dict[str, Any] | None = None,
    records: Any = None,
) -> Any:
    config, plan = _plan(document, records)
    row = next(
        r for r in plan.rows if (r.arm, r.harness, r.scenario_id) == (arm, harness, scenario_id)
    )
    backend = backend_mod.ScriptedBackend(default=script or Script())
    return run_mod.run_planned(
        row, config.strategy_for(arm, harness), _scenario(scenario_id), backend
    )


def _by_id(result: Any) -> dict[str, Any]:
    return {r.request.invocation_id: r for r in result.invocations}


def _with_work_packages(document: dict[str, Any], count: int) -> dict[str, Any]:
    for item in document["strategies"]:
        if item["topology"] == "fan_out":
            item["work_packages"] = count
    return document


@pytest.mark.parametrize("arm", ["A", "B", "C", "D", "E", "F"])
def test_every_arm_runs_to_an_accepted_result_with_honored_routes(arm: str) -> None:
    result = _run(arm)

    assert result.status is Status.ACCEPTED
    assert result.violations == () and result.validation is not None
    assert result.validation.verdict == "PASS"
    for record in result.invocations:
        assert record.model_verdict is result_mod.Verdict.HONORED
        assert record.effort_verdict is result_mod.Verdict.HONORED


@pytest.mark.parametrize(
    ("arm", "expected"),
    [
        ("A", ["orchestrator-plan", "worker-wp-1", "orchestrator-integrate"]),
        ("B", ["orchestrator-plan", "worker-wp-1", "orchestrator-integrate", "reviewer-review"]),
        ("E", ["agent-implement"]),
        ("F", ["planner-plan", "implementer-implement"]),
    ],
)
def test_invocation_order_follows_the_topology(arm: str, expected: list[str]) -> None:
    result = _run(arm)

    assert [r.request.invocation_id for r in result.invocations] == expected


def test_worker_route_follows_scenario_difficulty() -> None:
    ordinary = _run("C", scenario_id=BOUNDED)
    fallback = _run("C", scenario_id="RB-03-investigate-before-edit")

    assert _by_id(ordinary)["worker-wp-1"].request.model == "gpt-5.6-luna"
    assert _by_id(ordinary)["worker-wp-1"].request.difficulty == "ordinary_bounded"
    assert _by_id(fallback)["worker-wp-1"].request.model == "gpt-5.6-sol"
    assert _by_id(fallback)["worker-wp-1"].request.difficulty == "fallback_reasoning"


def test_same_strategy_under_two_matched_harnesses_is_a_matched_comparison() -> None:
    first, second = _run("A", "codex"), _run("A", "copilot")

    verdict = run_mod.compare_pair(first, second)

    assert verdict.status == "MATCHED" and verdict.reasons == ()
    assert verdict.telemetry_comparable
    assert first.pair_id == second.pair_id and first.comparison == "matched"


def test_same_model_label_with_different_harness_capability_is_unmatched() -> None:
    records = [make_record("codex", concurrency=3), make_record("copilot", concurrency=2)]

    verdict = run_mod.compare_pair(
        _run("A", "codex", records=records), _run("A", "copilot", records=records)
    )

    assert verdict.status == "UNMATCHED"
    assert any(reason.startswith("plan_unmatched:codex") for reason in verdict.reasons)


@pytest.mark.parametrize("field", ["model", "effort"])
def test_silent_inheritance_from_the_parent_is_detected(field: str) -> None:
    parent_value = "gpt-5.6-sol" if field == "model" else "medium"
    patch = {f"observed_{field}": parent_value}
    result = _run("C", script=Script(overrides={"worker-wp-1": patch}))

    assert result.status is Status.CONTRACT_VIOLATION
    assert f"silent_{field}_inheritance:worker-wp-1" in result.violations


def test_a_mismatch_that_is_not_the_parent_value_is_a_plain_mismatch() -> None:
    patch = {"observed_model": "gpt-6-luna"}
    result = _run("C", script=Script(overrides={"worker-wp-1": patch}))

    assert result.violations == ("model_mismatch:worker-wp-1",)
    assert result.status is Status.CONTRACT_VIOLATION


def test_client_echo_or_missing_values_are_unverified_not_honored() -> None:
    echo = {"evidence": cap.EvidenceKind.CLIENT_ECHO}
    absent = {"observed_model": None, "observed_effort": None, "evidence": cap.EvidenceKind.NONE}

    echoed = _run("A", script=Script(overrides={"role:worker": echo}))
    missing = _run("A", script=Script(overrides={"role:worker": absent}))

    for result in (echoed, missing):
        assert _by_id(result)["worker-wp-1"].model_verdict is result_mod.Verdict.UNVERIFIED
        assert "unverified_model:worker-wp-1" in result.notes
        assert result.violations == () and result.status is Status.ACCEPTED


def test_an_unverified_route_keeps_a_pair_from_reading_as_matched() -> None:
    echo = Script(overrides={"role:worker": {"evidence": cap.EvidenceKind.CLIENT_ECHO}})

    verdict = run_mod.compare_pair(_run("A", "codex", script=echo), _run("A", "copilot"))

    assert verdict.status == "UNVERIFIED"
    assert verdict.reasons[0].startswith("codex:unverified_")


def test_more_children_at_once_than_allowed_is_detected() -> None:
    document = _with_work_packages(config_dict(), 4)
    result = _run("A", document=document)

    assert result.peak_concurrency == 4
    assert result.violations == ("concurrency_ceiling_exceeded:4>3",)
    assert result.status is Status.CONTRACT_VIOLATION


def test_children_within_the_ceiling_are_not_flagged() -> None:
    result = _run("A", document=_with_work_packages(config_dict(), 3))

    assert result.peak_concurrency == 3 and result.violations == ()


def test_a_concurrency_difference_between_harnesses_is_detected() -> None:
    document = _with_work_packages(config_dict(), 3)
    serial = Script(
        overrides={
            f"worker-wp-{i}": {"start_offset_seconds": 10.0 + 6 * (i - 1)} for i in (1, 2, 3)
        }
    )

    first = _run("A", "codex", document=document)
    second = _run("A", "copilot", document=document, script=serial)
    verdict = run_mod.compare_pair(first, second)

    assert (first.peak_concurrency, second.peak_concurrency) == (3, 1)
    assert verdict.status == "UNMATCHED"
    assert "concurrency_peak_differs:3!=1" in verdict.reasons


def test_windows_that_only_touch_are_not_concurrent() -> None:
    def record(start: float) -> Any:
        request = dag_mod.build_requests(parse(config_dict()).strategies[0], _scenario())[1]
        seen = backend_mod.ScriptedBackend().invoke(request, _scenario())
        return result_mod.InvocationRecord(
            request, replace(seen, start_offset_seconds=start, elapsed_seconds=5.0),
            result_mod.Verdict.HONORED, result_mod.Verdict.HONORED, None,
        )  # fmt: skip

    assert run_mod.peak_concurrency([record(0.0), record(5.0)]) == 1
    assert run_mod.peak_concurrency([record(0.0), record(4.9)]) == 2
    assert run_mod.peak_concurrency([]) == 0


def test_a_broken_reviewer_isolation_is_a_violation() -> None:
    leak = Script(overrides={"role:reviewer": {"reviewer_context_leak": True}})

    result = _run("B", script=leak)

    assert "reviewer_isolation_broken:reviewer-review" in result.violations
    assert result.status is Status.CONTRACT_VIOLATION


def test_a_reviewer_isolation_difference_between_harnesses_is_detected() -> None:
    unobserved = Script(overrides={"role:reviewer": {"reviewer_context_leak": None}})

    first = _run("B", "codex")
    second = _run("B", "copilot", script=unobserved)
    verdict = run_mod.compare_pair(first, second)

    assert "reviewer_isolation_unobserved:reviewer-review" in second.notes
    assert verdict.status == "UNMATCHED" and "reviewer_isolation_differs" in verdict.reasons


def test_a_tool_sandbox_difference_is_recorded_and_makes_the_pair_unmatched() -> None:
    other = Script(overrides={"role:worker": {"tool_sandbox": "sandbox:read-only"}})

    first, second = _run("A", "codex"), _run("A", "copilot", script=other)
    verdict = run_mod.compare_pair(first, second)

    assert first.tool_sandbox == ("sandbox:workspace-write",)
    assert second.tool_sandbox == ("sandbox:read-only", "sandbox:workspace-write")
    assert any(reason.startswith("tool_sandbox_differs") for reason in verdict.reasons)
    assert verdict.status == "UNMATCHED"


def test_fresh_session_and_artifact_handoff_mismatches_are_detected() -> None:
    reused = Script(overrides={"implementer-implement": {"session_id": "planner"}})
    stale = Script(overrides={"implementer-implement": {"consumed_artifact_sha": "0" * 64}})
    no_marker = Script(overrides={"implementer-implement": {"context_markers": ()}})
    no_artifact = Script(overrides={"planner-plan": {"artifact_sha": None}})

    assert "fresh_session_reused:implementer-implement" in _run("F", script=reused).violations
    assert _run("F", script=stale).violations == ("handoff_mismatch:implementer-implement",)
    assert _run("F", script=no_marker).violations == (
        "fresh_context_missing:implementer-implement",
    )
    assert _run("F", script=no_artifact).violations == ("handoff_missing:planner-plan",)


def test_plan_artifact_hash_and_deviations_are_recorded_for_arm_f() -> None:
    deviations = Script(
        overrides={"implementer-implement": {"plan_deviations": ("skipped step 3",)}}
    )

    result = _run("F", script=deviations)
    payload = result_mod.result_to_dict(result)

    assert payload["plan_artifact"] == {
        "sha256": result.plan_artifact_sha,
        "deviations": ["skipped step 3"],
    }
    assert result.plan_artifact_sha and len(result.plan_artifact_sha) == 64
    assert result_mod.result_to_dict(_run("A"))["plan_artifact"] is None


def test_unavailable_telemetry_is_recorded_without_inventing_values() -> None:
    dark = Script(overrides={"role:worker": {"input_tokens": None, "output_tokens": None}})

    result = _run("A", "copilot", script=dark)

    assert not result.telemetry_available
    assert result.total_input_tokens is None and result.total_output_tokens is None
    assert result.total_cost_usd is None
    assert "telemetry_unavailable:worker-wp-1" in result.notes
    assert result.status is Status.ACCEPTED
    verdict = run_mod.compare_pair(_run("A", "codex"), result)
    assert verdict.telemetry_comparable is False


def test_known_tokens_and_a_priced_model_produce_a_cost_and_an_unpriced_one_does_not() -> None:
    models = (*MODELS, "gpt-6-sol")
    records = [make_record("codex", models=models), make_record("copilot", models=models)]
    result = _run("E", document=replace_strategy_models("gpt-6-sol"), records=records)

    assert result.total_input_tokens == 1000 and result.total_output_tokens == 500
    assert result.total_cost_usd == pytest.approx((1000 * 0.002 + 500 * 0.010) / 1000)
    assert _run("E").total_cost_usd is None


def replace_strategy_models(model: str) -> dict[str, Any]:
    document = config_dict()
    strategy = next(s for s in document["strategies"] if s["arm"] == "E")
    strategy["orchestrator"]["model"] = model
    return document


def test_a_harness_failure_is_distinct_from_a_task_failure() -> None:
    harness = {"failure": result_mod.FailureKind.HARNESS, "failure_detail": "exit code 1"}
    backend = backend_mod.ScriptedBackend(
        default=Script(overrides={"worker-wp-1": harness}, overlays=("known_bad",))
    )
    config, plan = _plan()
    row = next(r for r in plan.rows if (r.arm, r.harness, r.scenario_id) == ("A", "codex", BOUNDED))

    result = run_mod.run_planned(row, config.strategy_for("A", "codex"), _scenario(), backend)

    assert result.status is Status.HARNESS_FAILED
    assert result.validation is None and result.correction_rounds == 0
    assert backend.calls == ["orchestrator-plan", "worker-wp-1"]
    task = _run("A", script=Script(overlays=("known_bad",)))
    assert task.status is Status.TASK_FAILED and task.validation is not None
    assert task.validation.verdict == "FAIL"


def test_a_task_level_failure_report_is_a_task_failure() -> None:
    failed = {"failure": result_mod.FailureKind.TASK, "failure_detail": "gave up"}

    result = _run("E", script=Script(overrides={"agent-implement": failed}))

    assert result.status is Status.TASK_FAILED


def test_a_harness_failure_makes_a_pair_incomparable() -> None:
    down = Script(overrides={"role:worker": {"failure": result_mod.FailureKind.HARNESS}})

    verdict = run_mod.compare_pair(_run("A", "codex"), _run("A", "copilot", script=down))

    assert verdict.status == "INCOMPARABLE"
    assert verdict.reasons == ("harness_failure:copilot",)


def test_a_correction_round_can_repair_a_failed_first_attempt() -> None:
    result = _run("A", script=Script(overlays=("known_bad", "known_good")))

    assert result.status is Status.ACCEPTED and result.correction_rounds == 1
    ids = [r.request.invocation_id for r in result.invocations]
    assert ids[-1] == "worker-correct-1"
    assert result.invocations[-1].request.correction_round == 1


def test_correction_rounds_stop_at_the_budget() -> None:
    result = _run("A", script=Script(overlays=("known_bad",)))

    assert result.status is Status.TASK_FAILED and result.correction_rounds == 2
    assert result.violations == ()


def test_a_zero_correction_budget_grades_once() -> None:
    document = config_dict()
    for item in document["strategies"]:
        item["max_correction_rounds"] = 0

    result = _run("A", script=Script(overlays=("known_bad", "known_good")), document=document)

    assert result.status is Status.TASK_FAILED and result.correction_rounds == 0


def test_a_rejected_plan_row_never_reaches_the_backend() -> None:
    records = [
        make_record("codex"),
        make_record("copilot", statuses={"subagent_support": cap.CapabilityStatus.UNSUPPORTED}),
    ]
    config, plan = _plan(records=records)
    row = next(r for r in plan.rows if (r.arm, r.harness) == ("A", "copilot"))
    backend = backend_mod.ScriptedBackend()

    with pytest.raises(ValueError, match="REJECTED"):
        run_mod.run_planned(row, config.strategy_for("A", "copilot"), _scenario(), backend)

    assert backend.calls == []


def test_result_records_identity_eligibility_and_per_invocation_evidence() -> None:
    payload = result_mod.result_to_dict(_run("B", "copilot"))

    assert json.loads(json.dumps(payload)) == payload
    assert payload["harness"] == {"name": "copilot", "version": "GitHub Copilot CLI 1.0.89-1."}
    assert payload["eligibility"] == "ELIGIBLE_MATCHED"
    assert payload["comparison"] == {
        "class": "matched",
        "reason": "same semantic contract",
        "pair_id": f"{BOUNDED}:B",
    }
    invocation = payload["invocations"][1]
    assert invocation["requested"] == {"model": "gpt-5.6-luna", "effort": "medium"}
    assert invocation["observed"]["evidence"] == "backend"
    assert invocation["window"] == {"start": 10.0, "end": 15.0}
    assert invocation["depends_on"] == ["orchestrator-plan"]
    assert payload["validation"]["verdict"] == "PASS"


def test_value_verdict_and_cost_helpers() -> None:
    backend = cap.EvidenceKind.BACKEND
    assert result_mod.value_verdict("a", "a", backend) is result_mod.Verdict.HONORED
    assert result_mod.value_verdict("a", "b", backend) is result_mod.Verdict.MISMATCH
    assert result_mod.value_verdict("a", None, backend) is result_mod.Verdict.UNVERIFIED
    assert (
        result_mod.value_verdict("a", "a", cap.EvidenceKind.CONFIG) is result_mod.Verdict.UNVERIFIED
    )
    assert result_mod.estimate_cost_usd("gpt-6-sol", None, 5) is None
    assert result_mod.estimate_cost_usd("no-such-model", 1, 1) is None
    assert result_mod.sum_known([]) is None and result_mod.sum_known([1, None]) is None
    assert result_mod.sum_known([1, 2]) == 3


def test_dag_correction_request_targets_the_role_that_implements() -> None:
    config = parse(config_dict())
    scenario = _scenario()
    fan = dag_mod.correction_request(config.strategy_for("A", "codex"), scenario, 1, "prev")
    single = dag_mod.correction_request(config.strategy_for("E", "codex"), scenario, 2, "prev")
    plan_fresh = dag_mod.correction_request(config.strategy_for("F", "codex"), scenario, 1, "prev")

    assert (fan.role, fan.phase_id, fan.depends_on) == ("worker", "correct-1", ("prev",))
    assert (single.role, single.session_id, single.correction_round) == ("orchestrator", "agent", 2)
    assert (plan_fresh.role, plan_fresh.session_id, plan_fresh.fresh_context) == (
        "implementer", "implementer", False
    )  # fmt: skip


def test_a_pair_must_be_one_scenario_and_arm_on_two_harnesses() -> None:
    codex_a = _run("A", "codex")
    other_arm = _run("C", "codex")
    other_scenario = _run("A", "copilot", scenario_id="RB-04-scope-expansion")

    for other in (codex_a, other_arm, other_scenario):
        verdict = run_mod.compare_pair(codex_a, other)
        assert verdict.status == "INCOMPARABLE"
        assert verdict.reasons == ("not_a_pair_of_harness_runs",)
    assert run_mod.compare_pair(codex_a, _run("A", "copilot")).status == "MATCHED"


def test_cost_uses_the_model_backend_evidence_says_ran() -> None:
    models = (*MODELS, "gpt-6-sol", "gpt-6-luna")
    records = [make_record("codex", models=models), make_record("copilot", models=models)]
    document = replace_strategy_models("gpt-6-sol")
    swapped = Script(overrides={"agent-implement": {"observed_model": "gpt-6-luna"}})
    echo = Script(overrides={"agent-implement": {"evidence": cap.EvidenceKind.CLIENT_ECHO}})

    honored = _run("E", document=document, records=records)
    mismatch = _run("E", document=document, records=records, script=swapped)
    unknown = _run("E", document=document, records=records, script=echo)

    assert honored.total_cost_usd == pytest.approx((1000 * 0.002 + 500 * 0.010) / 1000)
    assert mismatch.total_cost_usd == pytest.approx((1000 * 0.0001 + 500 * 0.0005) / 1000)
    assert unknown.total_cost_usd is None
