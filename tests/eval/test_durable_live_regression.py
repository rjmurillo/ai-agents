"""Tests for the hidden-regression path of the live durable driver (issue #5768).

A fake process runner stands in for `claude`. These tests prove that a change
which passes its local check and fails the post-integration check is recorded
as `ACCEPTED_NOT_DURABLE`, that rework is measured from correction rounds, and
that the correction prompt never names the integration check. They do not
prove a real model produces such a change; the live run is that evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._durable_live_test_support import (
    Verdict,
    classify,
    fake_runner,
    grader_mod,
    live_mod,
    record_mod,
    stream_mod,
    stream_text,
)
from tests.eval._routing_integration_test_support import (
    EXTENSION_CORPUS,
    MERGE_SETTINGS,
    TASKS,
    TOP_SCORES,
    load_extension,
)

SETTINGS = live_mod.RunSettings("haiku", "low", retry_budget=1)
BASE = {
    "harness": "claude",
    "context_bytes": 0,
    "retry_budget": 1,
    "reviewer": "none",
    "control": "current",
}


def _run(task: str, overlays: list[str | None], tmp_path: Path, **kwargs: Any) -> Any:
    scenario = load_extension(task)
    control_file = tmp_path / "control.md"
    control_file.write_text("rules", encoding="utf-8")
    runner = fake_runner(scenario, overlays, **kwargs)
    budget = live_mod.InvocationBudget(10)
    return live_mod.run_task(
        scenario, "current", control_file, BASE, SETTINGS, budget, runner=runner
    )


def _invocation(round_index: int, wall: float) -> Any:
    facts = stream_mod.parse_stream(stream_text())
    return stream_mod.Invocation("current", "t", round_index, 0, wall, facts)


class TestHiddenRegressionRecord:
    @pytest.mark.parametrize("task", TASKS)
    def test_a_regression_that_passes_locally_is_accepted_not_durable(
        self, task: str, tmp_path: Path
    ) -> None:
        run = _run(task, ["hidden_regression"], tmp_path)

        assert run.record is not None
        assert run.record.execution.deterministic_acceptance.value == "PASS"
        assert run.record.durable.followup_validation.value == "FAIL"
        assert run.record.durable.objective_satisfied.value == "FAIL"
        assert run.record.durable.residual_defects and run.record.durable.residual_defects > 0
        assert classify(run.record) is Verdict.ACCEPTED_NOT_DURABLE

    @pytest.mark.parametrize("task", TASKS)
    def test_a_correct_change_is_accepted_durable(self, task: str, tmp_path: Path) -> None:
        run = _run(task, ["known_good"], tmp_path)

        assert run.record is not None
        assert run.record.durable.followup_validation.value == "PASS"
        assert run.record.durable.objective_satisfied.value == "PASS"
        assert classify(run.record) is Verdict.ACCEPTED_DURABLE

    @pytest.mark.parametrize("task", TASKS)
    def test_a_locally_wrong_change_is_rejected(self, task: str, tmp_path: Path) -> None:
        run = _run(task, ["known_bad"], tmp_path)

        assert run.record is not None
        assert classify(run.record) is Verdict.REJECTED

    def test_a_correction_round_can_repair_the_regression_the_check_never_named(
        self, tmp_path: Path
    ) -> None:
        run = _run(TOP_SCORES, ["known_bad", "hidden_regression"], tmp_path)

        assert run.record is not None and run.record.execution.retries == 1
        assert classify(run.record) is Verdict.ACCEPTED_NOT_DURABLE

    def test_the_correction_prompt_does_not_name_the_integration_check(
        self, tmp_path: Path
    ) -> None:
        run = _run(MERGE_SETTINGS, ["known_bad", "known_good"], tmp_path)
        scenario = load_extension(MERGE_SETTINGS)
        bad = grader_mod.grade(scenario, _materialized(scenario, "known_bad", tmp_path))

        prompt = live_mod.correction_prompt(scenario, bad)

        assert run.record is not None
        assert "INTEGRATION_REGRESSION" not in prompt and "verify_" not in prompt

    def test_an_unsupported_claim_is_counted_when_integration_breaks(self, tmp_path: Path) -> None:
        claim = "All tests pass."
        run = _run(
            TOP_SCORES,
            ["hidden_regression"],
            tmp_path,
            stdout=lambda _i: stream_text(text=claim),
        )

        assert run.record is not None and run.record.risk.unsupported_claims == 1

    def test_no_claim_means_no_unsupported_claim_even_when_integration_breaks(
        self, tmp_path: Path
    ) -> None:
        run = _run(TOP_SCORES, ["hidden_regression"], tmp_path)

        assert run.record is not None and run.record.risk.unsupported_claims == 0


def _materialized(scenario: Any, overlay: str, tmp_path: Path) -> Path:
    work = tmp_path / f"state-{overlay}"
    grader_mod.materialize(scenario, work, overlay)
    return work


class TestReworkMinutes:
    def test_round_zero_is_not_rework(self) -> None:
        assert record_mod.rework_minutes([_invocation(0, 600.0)]) == 0.0

    def test_correction_rounds_count_as_minutes(self) -> None:
        rounds = [_invocation(0, 100.0), _invocation(1, 90.0), _invocation(2, 30.0)]

        assert record_mod.rework_minutes(rounds) == 2.0

    def test_no_invocations_is_zero(self) -> None:
        assert record_mod.rework_minutes([]) == 0.0

    def test_a_recovered_task_records_nonnegative_rework_and_zero_human_time(
        self, tmp_path: Path
    ) -> None:
        run = _run(TOP_SCORES, ["known_bad", "known_good"], tmp_path)

        assert run.record is not None
        assert run.record.durable.rework_minutes is not None
        assert run.record.durable.rework_minutes >= 0.0
        assert run.record.economics.human_correction_minutes == 0.0

    def test_a_first_pass_task_has_no_rework(self, tmp_path: Path) -> None:
        run = _run(TOP_SCORES, ["known_good"], tmp_path)

        assert run.record is not None and run.record.durable.rework_minutes == 0.0


class TestFirstRepeat:
    def test_repeat_indices_start_at_first_repeat(self, tmp_path: Path) -> None:
        scenario = load_extension(TOP_SCORES)
        runner = fake_runner(scenario, ["known_good"])

        result = live_mod.run_experiment(
            [scenario],
            {"current": "rules"},
            SETTINGS,
            live_mod.InvocationBudget(10),
            repeats=2,
            first_repeat=3,
            runner=runner,
        )

        assert [r.repeat for r in result.records["current"]] == [3, 4]

    def test_the_default_first_repeat_is_zero(self) -> None:
        scenario = load_extension(TOP_SCORES)

        result = live_mod.run_experiment(
            [scenario],
            {"current": "rules"},
            SETTINGS,
            live_mod.InvocationBudget(10),
            runner=fake_runner(scenario, ["known_good"]),
        )

        assert [r.repeat for r in result.records["current"]] == [0]


def test_extension_corpus_path_is_the_committed_directory() -> None:
    assert (EXTENSION_CORPUS / TOP_SCORES / "scenario.json").is_file()
    document = json.loads((EXTENSION_CORPUS / TOP_SCORES / "scenario.json").read_text("utf-8"))
    assert document["category"] == "post_integration_regression"
