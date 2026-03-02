"""Tests for parallel workflow execution.

Covers parallel group identification, concurrent step execution,
and output aggregation strategies per ADR-009.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from scripts.workflow.parallel import (
    AggregationStrategy,
    ParallelGroup,
    ParallelStepExecutor,
    can_parallelize,
    identify_parallel_groups,
    mark_parallel_steps,
)
from scripts.workflow.schema import (
    StepKind,
    StepRef,
    WorkflowDefinition,
    WorkflowStep,
)


class TestIdentifyParallelGroups:
    def test_sequential_steps_in_separate_groups(self) -> None:
        """Each dependent step gets its own group."""
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic", inputs_from=[StepRef(name="a")]),
            WorkflowStep(name="c", agent="qa", inputs_from=[StepRef(name="b")]),
        ]
        wd = WorkflowDefinition(name="seq", steps=steps)

        groups = identify_parallel_groups(wd)

        assert len(groups) == 3
        assert groups[0].step_names == ["a"]
        assert groups[1].step_names == ["b"]
        assert groups[2].step_names == ["c"]

    def test_independent_steps_in_same_group(self) -> None:
        """Steps with no dependencies can run together."""
        steps = [
            WorkflowStep(name="research", agent="analyst"),
            WorkflowStep(name="security", agent="security"),
            WorkflowStep(name="devops", agent="devops"),
        ]
        wd = WorkflowDefinition(name="parallel", steps=steps)

        groups = identify_parallel_groups(wd)

        assert len(groups) == 1
        assert set(groups[0].step_names) == {"research", "security", "devops"}

    def test_diamond_dependency(self) -> None:
        """Diamond pattern: A -> B,C -> D."""
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic", inputs_from=[StepRef(name="a")]),
            WorkflowStep(name="c", agent="security", inputs_from=[StepRef(name="a")]),
            WorkflowStep(
                name="d",
                agent="orchestrator",
                inputs_from=[StepRef(name="b"), StepRef(name="c")],
            ),
        ]
        wd = WorkflowDefinition(name="diamond", steps=steps)

        groups = identify_parallel_groups(wd)

        assert len(groups) == 3
        assert groups[0].step_names == ["a"]
        assert set(groups[1].step_names) == {"b", "c"}
        assert groups[2].step_names == ["d"]

    def test_empty_workflow(self) -> None:
        """Empty workflow returns no groups."""
        wd = WorkflowDefinition(name="empty", steps=[])
        groups = identify_parallel_groups(wd)
        assert groups == []

    def test_priority_ordering_within_group(self) -> None:
        """Steps in the same group are ordered by priority (highest first)."""
        steps = [
            WorkflowStep(name="low", agent="analyst", priority=1),
            WorkflowStep(name="high", agent="security", priority=10),
            WorkflowStep(name="mid", agent="devops", priority=5),
        ]
        wd = WorkflowDefinition(name="priority", steps=steps)

        groups = identify_parallel_groups(wd)

        assert len(groups) == 1
        assert groups[0].step_names == ["high", "mid", "low"]

    def test_circular_dependency_raises_error(self) -> None:
        """Circular dependency raises ValueError."""
        # Create A -> B -> A cycle
        steps = [
            WorkflowStep(name="a", agent="analyst", inputs_from=[StepRef(name="b")]),
            WorkflowStep(name="b", agent="critic", inputs_from=[StepRef(name="a")]),
        ]
        wd = WorkflowDefinition(name="circular", steps=steps)

        with pytest.raises(ValueError, match="Circular dependency detected"):
            identify_parallel_groups(wd)


class TestCanParallelize:
    def test_true_for_independent_steps(self) -> None:
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="security"),
        ]
        wd = WorkflowDefinition(name="test", steps=steps)
        assert can_parallelize(wd) is True

    def test_false_for_sequential_chain(self) -> None:
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic", inputs_from=[StepRef(name="a")]),
        ]
        wd = WorkflowDefinition(name="test", steps=steps)
        assert can_parallelize(wd) is False

    def test_false_for_single_step(self) -> None:
        steps = [WorkflowStep(name="a", agent="analyst")]
        wd = WorkflowDefinition(name="test", steps=steps)
        assert can_parallelize(wd) is False


class TestParallelStepExecutor:
    def test_single_step_no_threading(self) -> None:
        """Single step executes without thread pool overhead."""
        runner = MagicMock(return_value="output")
        executor = ParallelStepExecutor(runner=runner)
        step = WorkflowStep(name="single", agent="analyst")

        result = executor.execute_parallel([step], {"single": "input"})

        assert result.succeeded
        assert len(result.step_results) == 1
        assert result.step_results[0].output == "output"
        runner.assert_called_once()

    def test_parallel_execution_runs_concurrently(self) -> None:
        """Multiple steps execute in parallel."""
        execution_times: dict[str, float] = {}
        lock = threading.Lock()

        def slow_runner(step: WorkflowStep, inp: str, iteration: int) -> str:
            with lock:
                execution_times[step.name] = time.time()
            time.sleep(0.1)
            return f"done-{step.name}"

        executor = ParallelStepExecutor(runner=slow_runner, max_workers=3)
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="security"),
            WorkflowStep(name="c", agent="devops"),
        ]

        start = time.time()
        result = executor.execute_parallel(steps, {})
        elapsed = time.time() - start

        assert result.succeeded
        assert len(result.step_results) == 3
        # Parallel execution should take ~0.1s, not ~0.3s
        assert elapsed < 0.25

    def test_failed_step_marks_result_failed(self) -> None:
        """A failing step sets succeeded=False."""

        def failing_runner(step: WorkflowStep, inp: str, iteration: int) -> str:
            if step.name == "fail":
                raise RuntimeError("intentional failure")
            return "ok"

        executor = ParallelStepExecutor(runner=failing_runner)
        steps = [
            WorkflowStep(name="ok", agent="analyst"),
            WorkflowStep(name="fail", agent="security"),
        ]

        result = executor.execute_parallel(steps, {})

        assert not result.succeeded
        assert "fail" in result.failed_steps
        assert result.outputs() == {"ok": "ok"}

    def test_priority_ordering_in_execution(self) -> None:
        """Higher-priority steps are submitted first to the thread pool."""
        submission_order: list[str] = []
        lock = threading.Lock()

        def tracking_runner(step: WorkflowStep, inp: str, iteration: int) -> str:
            with lock:
                submission_order.append(step.name)
            return "ok"

        executor = ParallelStepExecutor(runner=tracking_runner, max_workers=1)
        steps = [
            WorkflowStep(name="low", agent="analyst", priority=1),
            WorkflowStep(name="high", agent="security", priority=10),
        ]

        executor.execute_parallel(steps, {})

        # With max_workers=1, execution is serial in submission order
        assert submission_order == ["high", "low"]

    def test_outputs_method(self) -> None:
        """outputs() returns completed step outputs."""
        runner = MagicMock(return_value="result")
        executor = ParallelStepExecutor(runner=runner)
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic"),
        ]

        result = executor.execute_parallel(steps, {})

        assert result.outputs() == {"a": "result", "b": "result"}


class TestAggregationStrategies:
    def test_merge_combines_outputs(self) -> None:
        executor = ParallelStepExecutor(
            runner=MagicMock(),
            aggregation=AggregationStrategy.MERGE,
        )
        outputs = {"analyst": "analysis", "security": "findings"}

        merged = executor.aggregate_outputs(outputs)

        assert "## analyst" in merged
        assert "analysis" in merged
        assert "## security" in merged
        assert "findings" in merged

    def test_vote_returns_majority(self) -> None:
        executor = ParallelStepExecutor(
            runner=MagicMock(),
            aggregation=AggregationStrategy.VOTE,
        )
        outputs = {"a": "yes", "b": "yes", "c": "no"}

        result = executor.aggregate_outputs(outputs)

        assert result == "yes"

    def test_escalate_marks_conflict(self) -> None:
        executor = ParallelStepExecutor(
            runner=MagicMock(),
            aggregation=AggregationStrategy.ESCALATE,
        )
        outputs = {"a": "option1", "b": "option2"}

        result = executor.aggregate_outputs(outputs)

        assert "CONFLICT DETECTED" in result
        assert "high-level-advisor" in result
        assert "option1" in result
        assert "option2" in result

    def test_escalate_no_conflict(self) -> None:
        executor = ParallelStepExecutor(
            runner=MagicMock(),
            aggregation=AggregationStrategy.ESCALATE,
        )
        outputs = {"a": "same", "b": "same"}

        result = executor.aggregate_outputs(outputs)

        assert "CONFLICT" not in result
        assert result == "same"

    def test_empty_outputs(self) -> None:
        executor = ParallelStepExecutor(runner=MagicMock())
        assert executor.aggregate_outputs({}) == ""


class TestMarkParallelSteps:
    def test_marks_concurrent_steps(self) -> None:
        """Steps that can run in parallel get PARALLEL kind."""
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="security"),
            WorkflowStep(
                name="c",
                agent="orchestrator",
                inputs_from=[StepRef(name="a"), StepRef(name="b")],
            ),
        ]
        wd = WorkflowDefinition(name="test", steps=steps)

        marked = mark_parallel_steps(wd)

        assert marked.get_step("a").kind == StepKind.PARALLEL
        assert marked.get_step("b").kind == StepKind.PARALLEL
        assert marked.get_step("c").kind == StepKind.AGENT

    def test_sequential_steps_not_marked(self) -> None:
        """Dependent steps keep AGENT kind."""
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic", inputs_from=[StepRef(name="a")]),
        ]
        wd = WorkflowDefinition(name="test", steps=steps)

        marked = mark_parallel_steps(wd)

        assert marked.get_step("a").kind == StepKind.AGENT
        assert marked.get_step("b").kind == StepKind.AGENT


class TestParallelGroup:
    def test_len(self) -> None:
        group = ParallelGroup(step_names=["a", "b", "c"])
        assert len(group) == 3

    def test_empty(self) -> None:
        group = ParallelGroup()
        assert len(group) == 0
