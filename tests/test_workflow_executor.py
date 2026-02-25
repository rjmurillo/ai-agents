"""Tests for workflow executor, schema, and loader.

Covers sequential chaining, parallel merge, conditional steps,
refinement loops, retry logic, and YAML loading.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.workflow.executor import WorkflowExecutor
from scripts.workflow.loader import load_workflow, parse_workflow
from scripts.workflow.schema import (
    CoordinationMode,
    StepRef,
    StepResult,
    WorkflowDefinition,
    WorkflowResult,
    WorkflowStatus,
    WorkflowStep,
)

# -- Schema tests --


class TestWorkflowDefinition:
    def test_validate_empty_name(self) -> None:
        wd = WorkflowDefinition(name="", steps=[])
        errors = wd.validate()
        assert "Workflow name is required" in errors

    def test_validate_no_steps(self) -> None:
        wd = WorkflowDefinition(name="test", steps=[])
        errors = wd.validate()
        assert "Workflow must have at least one step" in errors

    def test_validate_duplicate_step_names(self) -> None:
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="a", agent="critic"),
        ]
        wd = WorkflowDefinition(name="test", steps=steps)
        errors = wd.validate()
        assert any("Duplicate step name: a" in e for e in errors)

    def test_validate_missing_agent(self) -> None:
        steps = [WorkflowStep(name="a", agent="")]
        wd = WorkflowDefinition(name="test", steps=steps)
        errors = wd.validate()
        assert any("requires an agent type" in e for e in errors)

    def test_validate_forward_dependency(self) -> None:
        steps = [
            WorkflowStep(
                name="a",
                agent="analyst",
                inputs_from=[StepRef(name="b")],
            ),
            WorkflowStep(name="b", agent="critic"),
        ]
        wd = WorkflowDefinition(name="test", steps=steps)
        errors = wd.validate()
        assert any("not defined before it" in e for e in errors)

    def test_validate_valid_workflow(self) -> None:
        steps = [
            WorkflowStep(name="analyze", agent="analyst"),
            WorkflowStep(
                name="review",
                agent="critic",
                inputs_from=[StepRef(name="analyze")],
            ),
        ]
        wd = WorkflowDefinition(name="feature", steps=steps)
        assert wd.validate() == []

    def test_step_names(self) -> None:
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic"),
        ]
        wd = WorkflowDefinition(name="test", steps=steps)
        assert wd.step_names() == ["a", "b"]

    def test_get_step_found(self) -> None:
        step = WorkflowStep(name="a", agent="analyst")
        wd = WorkflowDefinition(name="test", steps=[step])
        assert wd.get_step("a") is step

    def test_get_step_not_found(self) -> None:
        wd = WorkflowDefinition(name="test", steps=[])
        assert wd.get_step("missing") is None

    def test_max_iterations_validation(self) -> None:
        steps = [WorkflowStep(name="a", agent="analyst")]
        wd = WorkflowDefinition(name="test", steps=steps, max_iterations=0)
        errors = wd.validate()
        assert any("max_iterations" in e for e in errors)


class TestStepResult:
    def test_succeeded_when_completed(self) -> None:
        r = StepResult(step_name="a", status=WorkflowStatus.COMPLETED)
        assert r.succeeded is True

    def test_not_succeeded_when_failed(self) -> None:
        r = StepResult(step_name="a", status=WorkflowStatus.FAILED)
        assert r.succeeded is False


class TestWorkflowResult:
    def test_final_output_from_last_completed(self) -> None:
        wr = WorkflowResult(
            workflow_name="test",
            status=WorkflowStatus.COMPLETED,
            step_results=[
                StepResult(step_name="a", status=WorkflowStatus.COMPLETED, output="first"),
                StepResult(step_name="b", status=WorkflowStatus.COMPLETED, output="second"),
            ],
        )
        assert wr.final_output == "second"

    def test_final_output_empty_when_no_completed(self) -> None:
        wr = WorkflowResult(
            workflow_name="test",
            status=WorkflowStatus.FAILED,
            step_results=[
                StepResult(step_name="a", status=WorkflowStatus.FAILED),
            ],
        )
        assert wr.final_output == ""

    def test_get_step_result(self) -> None:
        sr = StepResult(step_name="a", status=WorkflowStatus.COMPLETED)
        wr = WorkflowResult(
            workflow_name="test",
            status=WorkflowStatus.COMPLETED,
            step_results=[sr],
        )
        assert wr.get_step_result("a") is sr
        assert wr.get_step_result("missing") is None


# -- Executor tests --


def _make_runner(outputs: dict[str, str] | None = None):
    """Create a step runner that returns canned outputs by step name."""
    defaults = outputs or {}

    def runner(step: WorkflowStep, combined_input: str, iteration: int) -> str:
        if step.name in defaults:
            return defaults[step.name]
        return f"output-from-{step.name}(input={combined_input!r})"

    return runner


class TestWorkflowExecutor:
    def test_sequential_chaining(self) -> None:
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic"),
        ]
        wd = WorkflowDefinition(name="seq", steps=steps)
        runner = _make_runner({"a": "analysis-result"})
        executor = WorkflowExecutor(runner=runner)
        result = executor.execute(wd)

        assert result.succeeded
        assert result.iterations_completed == 1
        b_result = result.get_step_result("b")
        assert b_result is not None
        assert "analysis-result" in b_result.output

    def test_parallel_merge(self) -> None:
        steps = [
            WorkflowStep(name="research", agent="analyst"),
            WorkflowStep(name="security", agent="security"),
            WorkflowStep(
                name="merge",
                agent="orchestrator",
                inputs_from=[StepRef(name="research"), StepRef(name="security")],
            ),
        ]
        wd = WorkflowDefinition(name="parallel", steps=steps)
        runner = _make_runner({"research": "R-output", "security": "S-output"})
        executor = WorkflowExecutor(runner=runner)
        result = executor.execute(wd)

        assert result.succeeded
        merge_result = result.get_step_result("merge")
        assert merge_result is not None
        assert "R-output" in merge_result.output
        assert "S-output" in merge_result.output

    def test_conditional_skip(self) -> None:
        steps = [
            WorkflowStep(name="check", agent="analyst"),
            WorkflowStep(name="fix", agent="implementer", condition="has:check"),
        ]
        wd = WorkflowDefinition(name="cond", steps=steps)
        runner = _make_runner({"check": ""})
        executor = WorkflowExecutor(runner=runner)
        result = executor.execute(wd)

        assert result.succeeded
        fix_result = result.get_step_result("fix")
        assert fix_result is not None
        assert fix_result.status == WorkflowStatus.SKIPPED

    def test_conditional_execute(self) -> None:
        steps = [
            WorkflowStep(name="check", agent="analyst"),
            WorkflowStep(name="fix", agent="implementer", condition="has:check"),
        ]
        wd = WorkflowDefinition(name="cond", steps=steps)
        runner = _make_runner({"check": "issues-found"})
        executor = WorkflowExecutor(runner=runner)
        result = executor.execute(wd)

        assert result.succeeded
        fix_result = result.get_step_result("fix")
        assert fix_result is not None
        assert fix_result.status == WorkflowStatus.COMPLETED

    def test_refinement_loop(self) -> None:
        call_count = 0

        def counting_runner(step: WorkflowStep, inp: str, iteration: int) -> str:
            nonlocal call_count
            call_count += 1
            return f"iter-{iteration}"

        steps = [WorkflowStep(name="refine", agent="implementer")]
        wd = WorkflowDefinition(name="loop", steps=steps, max_iterations=3)
        executor = WorkflowExecutor(runner=counting_runner)
        result = executor.execute(wd)

        assert result.succeeded
        assert result.iterations_completed == 3
        assert call_count == 3

    def test_step_failure_stops_pipeline(self) -> None:
        def failing_runner(step: WorkflowStep, inp: str, iteration: int) -> str:
            if step.name == "b":
                raise RuntimeError("step b failed")
            return "ok"

        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic"),
            WorkflowStep(name="c", agent="implementer"),
        ]
        wd = WorkflowDefinition(name="fail", steps=steps)
        executor = WorkflowExecutor(runner=failing_runner)
        result = executor.execute(wd)

        assert not result.succeeded
        assert result.get_step_result("b").status == WorkflowStatus.FAILED
        assert result.get_step_result("c").status == WorkflowStatus.SKIPPED

    def test_retry_succeeds_on_second_attempt(self) -> None:
        attempts = 0

        def flaky_runner(step: WorkflowStep, inp: str, iteration: int) -> str:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("transient error")
            return "recovered"

        steps = [WorkflowStep(name="flaky", agent="analyst", max_retries=1)]
        wd = WorkflowDefinition(name="retry", steps=steps)
        executor = WorkflowExecutor(runner=flaky_runner)
        result = executor.execute(wd)

        assert result.succeeded
        assert result.final_output == "recovered"

    def test_invalid_workflow_returns_failed(self) -> None:
        wd = WorkflowDefinition(name="", steps=[])
        executor = WorkflowExecutor(runner=_make_runner())
        result = executor.execute(wd)
        assert not result.succeeded

    def test_empty_condition_evaluates_true(self) -> None:
        steps = [
            WorkflowStep(name="a", agent="analyst", condition=""),
        ]
        wd = WorkflowDefinition(name="test", steps=steps)
        executor = WorkflowExecutor(runner=_make_runner({"a": "done"}))
        result = executor.execute(wd)
        assert result.succeeded


# -- Loader tests --


class TestParseWorkflow:
    def test_parse_minimal(self) -> None:
        data = {
            "name": "simple",
            "steps": [{"name": "analyze", "agent": "analyst"}],
        }
        wd = parse_workflow(data)
        assert wd.name == "simple"
        assert len(wd.steps) == 1
        assert wd.steps[0].agent == "analyst"

    def test_parse_with_inputs_from(self) -> None:
        data = {
            "name": "chained",
            "steps": [
                {"name": "a", "agent": "analyst"},
                {"name": "b", "agent": "critic", "inputs_from": ["a"]},
            ],
        }
        wd = parse_workflow(data)
        assert wd.steps[1].inputs_from == [StepRef(name="a")]

    def test_parse_with_max_iterations(self) -> None:
        data = {
            "name": "refine",
            "steps": [{"name": "a", "agent": "implementer"}],
            "max_iterations": 5,
        }
        wd = parse_workflow(data)
        assert wd.max_iterations == 5

    def test_parse_invalid_not_dict(self) -> None:
        with pytest.raises(ValueError, match="YAML mapping"):
            parse_workflow("not a dict")

    def test_parse_missing_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            parse_workflow({"steps": []})

    def test_parse_steps_not_list(self) -> None:
        with pytest.raises(ValueError, match="list"):
            parse_workflow({"name": "test", "steps": "bad"})

    def test_parse_step_not_dict(self) -> None:
        with pytest.raises(ValueError, match="mapping"):
            parse_workflow({"name": "test", "steps": ["bad"]})


class TestLoadWorkflow:
    def test_load_from_file(self, tmp_path: Path) -> None:
        workflow_yaml = {
            "name": "file-test",
            "steps": [
                {"name": "a", "agent": "analyst"},
                {"name": "b", "agent": "critic", "inputs_from": ["a"]},
            ],
            "max_iterations": 2,
        }
        path = tmp_path / "workflow.yaml"
        path.write_text(yaml.dump(workflow_yaml), encoding="utf-8")

        wd = load_workflow(path)
        assert wd.name == "file-test"
        assert len(wd.steps) == 2
        assert wd.max_iterations == 2

    def test_load_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_workflow(tmp_path / "missing.yaml")


class TestParseCoordinationMode:
    def test_parse_centralized(self) -> None:
        data = {
            "name": "test",
            "steps": [{"name": "a", "agent": "analyst"}],
            "coordination_mode": "centralized",
        }
        wd = parse_workflow(data)
        assert wd.coordination_mode == CoordinationMode.CENTRALIZED

    def test_parse_hierarchical(self) -> None:
        data = {
            "name": "test",
            "steps": [
                {"name": "worker", "agent": "analyst"},
                {
                    "name": "lead",
                    "agent": "orchestrator",
                    "is_coordinator": True,
                    "subordinates": ["worker"],
                },
            ],
            "coordination_mode": "hierarchical",
        }
        wd = parse_workflow(data)
        assert wd.coordination_mode == CoordinationMode.HIERARCHICAL
        assert wd.steps[1].is_coordinator is True
        assert wd.steps[1].subordinates == ["worker"]

    def test_parse_mesh(self) -> None:
        data = {
            "name": "test",
            "steps": [
                {"name": "a", "agent": "analyst"},
                {"name": "b", "agent": "critic"},
            ],
            "coordination_mode": "mesh",
        }
        wd = parse_workflow(data)
        assert wd.coordination_mode == CoordinationMode.MESH

    def test_parse_invalid_coordination_mode(self) -> None:
        data = {
            "name": "test",
            "steps": [{"name": "a", "agent": "analyst"}],
            "coordination_mode": "invalid",
        }
        with pytest.raises(ValueError, match="Invalid coordination_mode"):
            parse_workflow(data)

    def test_default_coordination_mode(self) -> None:
        data = {
            "name": "test",
            "steps": [{"name": "a", "agent": "analyst"}],
        }
        wd = parse_workflow(data)
        assert wd.coordination_mode == CoordinationMode.CENTRALIZED
