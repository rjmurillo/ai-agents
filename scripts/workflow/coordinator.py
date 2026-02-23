"""Coordination strategies for multi-agent workflow execution.

Implements different coordination modes for agent pipelines:
- Centralized: Single orchestrator manages all agents (default)
- Hierarchical: Tree structure with nested coordinators
- Mesh: Peer-to-peer collaboration with shared task queue

Exit Codes (ADR-035):
    0 - Success
    1 - Logic error (coordination failure)
    2 - Config error (invalid mode configuration)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import deque

from scripts.workflow.schema import (
    CoordinationMode,
    WorkflowDefinition,
    WorkflowStep,
)

logger = logging.getLogger(__name__)


class CoordinationStrategy(ABC):
    """Base interface for coordination strategies."""

    @abstractmethod
    def order_steps(
        self,
        workflow: WorkflowDefinition,
    ) -> list[WorkflowStep]:
        """Determine execution order for steps based on coordination mode."""

    @abstractmethod
    def can_execute_parallel(
        self,
        step: WorkflowStep,
        completed: set[str],
        workflow: WorkflowDefinition,
    ) -> bool:
        """Check if a step can be executed in parallel with others."""


class CentralizedStrategy(CoordinationStrategy):
    """Single orchestrator manages all agents sequentially.

    Steps execute in definition order. Each step waits for the previous
    step to complete before starting.
    """

    def order_steps(
        self,
        workflow: WorkflowDefinition,
    ) -> list[WorkflowStep]:
        """Return steps in definition order."""
        return list(workflow.steps)

    def can_execute_parallel(
        self,
        step: WorkflowStep,
        completed: set[str],
        workflow: WorkflowDefinition,
    ) -> bool:
        """Centralized mode does not support parallel execution."""
        return False


class HierarchicalStrategy(CoordinationStrategy):
    """Tree structure with nested coordinators.

    Coordinator steps manage their subordinates. A coordinator executes
    after all its subordinates complete. Subordinates can run in parallel
    within their group.
    """

    def order_steps(
        self,
        workflow: WorkflowDefinition,
    ) -> list[WorkflowStep]:
        """Order steps so subordinates execute before their coordinators."""
        by_name = {s.name: s for s in workflow.steps}
        ordered: list[WorkflowStep] = []
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visited or name not in by_name:
                return
            step = by_name[name]
            for sub in step.subordinates:
                visit(sub)
            visited.add(name)
            ordered.append(step)

        for step in workflow.steps:
            visit(step.name)

        return ordered

    def can_execute_parallel(
        self,
        step: WorkflowStep,
        completed: set[str],
        workflow: WorkflowDefinition,
    ) -> bool:
        """Allow parallel execution for steps under the same coordinator."""
        if step.is_coordinator:
            return False

        deps = step.depends_on()
        return all(d in completed for d in deps)


class MeshStrategy(CoordinationStrategy):
    """Peer-to-peer collaboration with shared task queue.

    Steps can execute in any order once their dependencies are met.
    All steps are peers; no hierarchy. Enables maximum parallelism.
    """

    def order_steps(
        self,
        workflow: WorkflowDefinition,
    ) -> list[WorkflowStep]:
        """Topological sort based on dependencies."""
        by_name = {s.name: s for s in workflow.steps}
        in_degree = {s.name: len(s.depends_on()) for s in workflow.steps}
        queue: deque[str] = deque()

        for name, deg in in_degree.items():
            if deg == 0:
                queue.append(name)

        ordered: list[WorkflowStep] = []
        while queue:
            name = queue.popleft()
            step = by_name[name]
            ordered.append(step)

            for other in workflow.steps:
                if name in other.depends_on():
                    in_degree[other.name] -= 1
                    if in_degree[other.name] == 0:
                        queue.append(other.name)

        return ordered

    def can_execute_parallel(
        self,
        step: WorkflowStep,
        completed: set[str],
        workflow: WorkflowDefinition,
    ) -> bool:
        """All steps can execute in parallel once dependencies are met."""
        return all(d in completed for d in step.depends_on())


def get_strategy(mode: CoordinationMode) -> CoordinationStrategy:
    """Factory function to get the appropriate coordination strategy."""
    strategies: dict[CoordinationMode, CoordinationStrategy] = {
        CoordinationMode.CENTRALIZED: CentralizedStrategy(),
        CoordinationMode.HIERARCHICAL: HierarchicalStrategy(),
        CoordinationMode.MESH: MeshStrategy(),
    }
    return strategies[mode]


def find_ready_steps(
    workflow: WorkflowDefinition,
    completed: set[str],
    running: set[str],
) -> list[WorkflowStep]:
    """Find steps that are ready to execute based on coordination mode.

    Returns a list of steps whose dependencies are satisfied and that
    are not currently running or already completed.
    """
    strategy = get_strategy(workflow.coordination_mode)
    ready: list[WorkflowStep] = []

    for step in workflow.steps:
        if step.name in completed or step.name in running:
            continue
        if strategy.can_execute_parallel(step, completed, workflow):
            ready.append(step)
        elif not ready and step.name not in running:
            deps = step.depends_on()
            if all(d in completed for d in deps):
                ready.append(step)
                break

    return ready


def aggregate_subordinate_outputs(
    coordinator: WorkflowStep,
    step_outputs: dict[str, str],
) -> str:
    """Combine outputs from subordinate steps for a coordinator.

    The coordinator receives a merged view of all subordinate outputs
    separated by section headers.
    """
    parts: list[str] = []
    for sub_name in coordinator.subordinates:
        if sub_name in step_outputs:
            output = step_outputs[sub_name]
            parts.append(f"## Output from {sub_name}\n\n{output}")
    return "\n\n---\n\n".join(parts)


def build_execution_plan(
    workflow: WorkflowDefinition,
) -> list[list[str]]:
    """Build a parallel execution plan showing which steps can run together.

    Returns a list of phases. Each phase contains step names that can
    execute in parallel.
    """
    strategy = get_strategy(workflow.coordination_mode)
    ordered = strategy.order_steps(workflow)

    if workflow.coordination_mode == CoordinationMode.CENTRALIZED:
        return [[s.name] for s in ordered]

    phases: list[list[str]] = []
    completed: set[str] = set()

    remaining = set(s.name for s in workflow.steps)
    by_name = {s.name: s for s in workflow.steps}

    while remaining:
        phase: list[str] = []
        for name in list(remaining):
            step = by_name[name]
            deps = step.depends_on()
            if all(d in completed for d in deps):
                if strategy.can_execute_parallel(step, completed, workflow):
                    phase.append(name)

        if not phase:
            leftover = list(remaining)
            if leftover:
                phase = [leftover[0]]

        for name in phase:
            remaining.discard(name)
            completed.add(name)

        if phase:
            phases.append(phase)

    return phases
