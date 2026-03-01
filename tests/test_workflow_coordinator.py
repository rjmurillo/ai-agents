"""Tests for workflow coordination modes.

Covers centralized, hierarchical, and mesh coordination patterns,
execution planning, and step ordering.
"""

from __future__ import annotations

from scripts.workflow.coordinator import (
    CentralizedStrategy,
    HierarchicalStrategy,
    MeshStrategy,
    aggregate_subordinate_outputs,
    build_execution_plan,
    find_ready_steps,
    get_strategy,
)
from scripts.workflow.schema import (
    CoordinationMode,
    StepRef,
    WorkflowDefinition,
    WorkflowStep,
)


class TestCoordinationMode:
    def test_centralized_is_default(self) -> None:
        wd = WorkflowDefinition(
            name="test",
            steps=[WorkflowStep(name="a", agent="analyst")],
        )
        assert wd.coordination_mode == CoordinationMode.CENTRALIZED

    def test_hierarchical_requires_coordinator(self) -> None:
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic"),
        ]
        wd = WorkflowDefinition(
            name="test",
            steps=steps,
            coordination_mode=CoordinationMode.HIERARCHICAL,
        )
        errors = wd.validate()
        assert any("is_coordinator=True" in e for e in errors)

    def test_hierarchical_valid_with_coordinator(self) -> None:
        steps = [
            WorkflowStep(name="worker1", agent="analyst"),
            WorkflowStep(name="worker2", agent="critic"),
            WorkflowStep(
                name="lead",
                agent="orchestrator",
                is_coordinator=True,
                subordinates=["worker1", "worker2"],
            ),
        ]
        wd = WorkflowDefinition(
            name="test",
            steps=steps,
            coordination_mode=CoordinationMode.HIERARCHICAL,
        )
        errors = wd.validate()
        assert errors == []

    def test_hierarchical_unknown_subordinate(self) -> None:
        steps = [
            WorkflowStep(name="worker", agent="analyst"),
            WorkflowStep(
                name="lead",
                agent="orchestrator",
                is_coordinator=True,
                subordinates=["worker", "missing"],
            ),
        ]
        wd = WorkflowDefinition(
            name="test",
            steps=steps,
            coordination_mode=CoordinationMode.HIERARCHICAL,
        )
        errors = wd.validate()
        assert any("unknown subordinate 'missing'" in e for e in errors)

    def test_mesh_requires_two_steps(self) -> None:
        steps = [WorkflowStep(name="single", agent="analyst")]
        wd = WorkflowDefinition(
            name="test",
            steps=steps,
            coordination_mode=CoordinationMode.MESH,
        )
        errors = wd.validate()
        assert any("at least 2 steps" in e for e in errors)

    def test_mesh_valid_with_two_steps(self) -> None:
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic"),
        ]
        wd = WorkflowDefinition(
            name="test",
            steps=steps,
            coordination_mode=CoordinationMode.MESH,
        )
        errors = wd.validate()
        assert errors == []


class TestGetStrategy:
    def test_centralized(self) -> None:
        strategy = get_strategy(CoordinationMode.CENTRALIZED)
        assert isinstance(strategy, CentralizedStrategy)

    def test_hierarchical(self) -> None:
        strategy = get_strategy(CoordinationMode.HIERARCHICAL)
        assert isinstance(strategy, HierarchicalStrategy)

    def test_mesh(self) -> None:
        strategy = get_strategy(CoordinationMode.MESH)
        assert isinstance(strategy, MeshStrategy)


class TestCentralizedStrategy:
    def test_order_preserves_definition_order(self) -> None:
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic"),
            WorkflowStep(name="c", agent="implementer"),
        ]
        wd = WorkflowDefinition(name="test", steps=steps)
        strategy = CentralizedStrategy()
        ordered = strategy.order_steps(wd)
        assert [s.name for s in ordered] == ["a", "b", "c"]

    def test_no_parallel_execution(self) -> None:
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic"),
        ]
        wd = WorkflowDefinition(name="test", steps=steps)
        strategy = CentralizedStrategy()
        completed: set[str] = set()
        assert strategy.can_execute_parallel(steps[0], completed, wd) is False


class TestHierarchicalStrategy:
    def test_subordinates_ordered_before_coordinator(self) -> None:
        steps = [
            WorkflowStep(
                name="lead",
                agent="orchestrator",
                is_coordinator=True,
                subordinates=["worker1", "worker2"],
            ),
            WorkflowStep(name="worker1", agent="analyst"),
            WorkflowStep(name="worker2", agent="critic"),
        ]
        wd = WorkflowDefinition(
            name="test",
            steps=steps,
            coordination_mode=CoordinationMode.HIERARCHICAL,
        )
        strategy = HierarchicalStrategy()
        ordered = strategy.order_steps(wd)
        names = [s.name for s in ordered]
        assert names.index("worker1") < names.index("lead")
        assert names.index("worker2") < names.index("lead")

    def test_coordinator_cannot_run_parallel(self) -> None:
        steps = [
            WorkflowStep(name="worker", agent="analyst"),
            WorkflowStep(
                name="lead",
                agent="orchestrator",
                is_coordinator=True,
                subordinates=["worker"],
            ),
        ]
        wd = WorkflowDefinition(
            name="test",
            steps=steps,
            coordination_mode=CoordinationMode.HIERARCHICAL,
        )
        strategy = HierarchicalStrategy()
        completed = {"worker"}
        lead_step = steps[1]
        assert strategy.can_execute_parallel(lead_step, completed, wd) is False

    def test_workers_can_run_parallel(self) -> None:
        steps = [
            WorkflowStep(name="worker1", agent="analyst"),
            WorkflowStep(name="worker2", agent="critic"),
            WorkflowStep(
                name="lead",
                agent="orchestrator",
                is_coordinator=True,
                subordinates=["worker1", "worker2"],
            ),
        ]
        wd = WorkflowDefinition(
            name="test",
            steps=steps,
            coordination_mode=CoordinationMode.HIERARCHICAL,
        )
        strategy = HierarchicalStrategy()
        completed: set[str] = set()
        assert strategy.can_execute_parallel(steps[0], completed, wd) is True
        assert strategy.can_execute_parallel(steps[1], completed, wd) is True


class TestMeshStrategy:
    def test_topological_order_respects_dependencies(self) -> None:
        steps = [
            WorkflowStep(name="c", agent="implementer", inputs_from=[StepRef("b")]),
            WorkflowStep(name="b", agent="critic", inputs_from=[StepRef("a")]),
            WorkflowStep(name="a", agent="analyst"),
        ]
        wd = WorkflowDefinition(
            name="test",
            steps=steps,
            coordination_mode=CoordinationMode.MESH,
        )
        strategy = MeshStrategy()
        ordered = strategy.order_steps(wd)
        names = [s.name for s in ordered]
        assert names.index("a") < names.index("b")
        assert names.index("b") < names.index("c")

    def test_independent_steps_can_run_parallel(self) -> None:
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic"),
        ]
        wd = WorkflowDefinition(
            name="test",
            steps=steps,
            coordination_mode=CoordinationMode.MESH,
        )
        strategy = MeshStrategy()
        completed: set[str] = set()
        assert strategy.can_execute_parallel(steps[0], completed, wd) is True
        assert strategy.can_execute_parallel(steps[1], completed, wd) is True

    def test_dependent_step_waits(self) -> None:
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic", inputs_from=[StepRef("a")]),
        ]
        wd = WorkflowDefinition(
            name="test",
            steps=steps,
            coordination_mode=CoordinationMode.MESH,
        )
        strategy = MeshStrategy()
        completed: set[str] = set()
        assert strategy.can_execute_parallel(steps[1], completed, wd) is False
        completed.add("a")
        assert strategy.can_execute_parallel(steps[1], completed, wd) is True


class TestFindReadySteps:
    def test_centralized_one_at_a_time(self) -> None:
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic"),
        ]
        wd = WorkflowDefinition(name="test", steps=steps)
        ready = find_ready_steps(wd, completed=set(), running=set())
        assert [s.name for s in ready] == ["a"]

    def test_mesh_finds_multiple_ready(self) -> None:
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic"),
            WorkflowStep(
                name="c",
                agent="implementer",
                inputs_from=[StepRef("a"), StepRef("b")],
            ),
        ]
        wd = WorkflowDefinition(
            name="test",
            steps=steps,
            coordination_mode=CoordinationMode.MESH,
        )
        ready = find_ready_steps(wd, completed=set(), running=set())
        names = {s.name for s in ready}
        assert "a" in names
        assert "b" in names
        assert "c" not in names


class TestBuildExecutionPlan:
    def test_centralized_sequential_phases(self) -> None:
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic"),
            WorkflowStep(name="c", agent="implementer"),
        ]
        wd = WorkflowDefinition(name="test", steps=steps)
        plan = build_execution_plan(wd)
        assert plan == [["a"], ["b"], ["c"]]

    def test_mesh_parallel_phases(self) -> None:
        steps = [
            WorkflowStep(name="a", agent="analyst"),
            WorkflowStep(name="b", agent="critic"),
            WorkflowStep(
                name="merge",
                agent="orchestrator",
                inputs_from=[StepRef("a"), StepRef("b")],
            ),
        ]
        wd = WorkflowDefinition(
            name="test",
            steps=steps,
            coordination_mode=CoordinationMode.MESH,
        )
        plan = build_execution_plan(wd)
        assert len(plan) == 2
        assert set(plan[0]) == {"a", "b"}
        assert plan[1] == ["merge"]

    def test_hierarchical_workers_then_coordinator(self) -> None:
        steps = [
            WorkflowStep(name="worker1", agent="analyst"),
            WorkflowStep(name="worker2", agent="critic"),
            WorkflowStep(
                name="lead",
                agent="orchestrator",
                is_coordinator=True,
                subordinates=["worker1", "worker2"],
            ),
        ]
        wd = WorkflowDefinition(
            name="test",
            steps=steps,
            coordination_mode=CoordinationMode.HIERARCHICAL,
        )
        plan = build_execution_plan(wd)
        flat = [name for phase in plan for name in phase]
        assert flat.index("worker1") < flat.index("lead")
        assert flat.index("worker2") < flat.index("lead")


class TestAggregateSubordinateOutputs:
    def test_merges_outputs_with_headers(self) -> None:
        coord = WorkflowStep(
            name="lead",
            agent="orchestrator",
            is_coordinator=True,
            subordinates=["worker1", "worker2"],
        )
        outputs = {
            "worker1": "Analysis complete",
            "worker2": "Review findings",
        }
        merged = aggregate_subordinate_outputs(coord, outputs)
        assert "## Output from worker1" in merged
        assert "Analysis complete" in merged
        assert "## Output from worker2" in merged
        assert "Review findings" in merged

    def test_skips_missing_outputs(self) -> None:
        coord = WorkflowStep(
            name="lead",
            agent="orchestrator",
            is_coordinator=True,
            subordinates=["worker1", "worker2"],
        )
        outputs = {"worker1": "Only this one"}
        merged = aggregate_subordinate_outputs(coord, outputs)
        assert "worker1" in merged
        assert "worker2" not in merged
