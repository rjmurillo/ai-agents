"""Parallel execution support for agent workflow pipelines.

Provides concurrent execution of independent workflow steps and batch
spawning patterns for multi-agent coordination. Implements ADR-009
parallel-safe multi-agent design patterns.

Exit Codes (ADR-035):
    0 - Success
    1 - Logic error (parallel execution failed)
    2 - Config error (invalid parallelization)
"""

from __future__ import annotations

import concurrent.futures
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from scripts.workflow.schema import (
    StepKind,
    StepResult,
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowStep,
)

logger = logging.getLogger(__name__)


class AggregationStrategy(Enum):
    """How to combine outputs from parallel steps.

    Per ADR-009 aggregation strategies:
    - MERGE: Combine all outputs (non-conflicting)
    - VOTE: Select majority result (redundant execution)
    - ESCALATE: Flag conflicts for human/agent resolution
    """

    MERGE = "merge"
    VOTE = "vote"
    ESCALATE = "escalate"


@dataclass
class ParallelGroup:
    """A set of steps that can execute concurrently.

    Groups are identified by analyzing step dependencies. Steps with
    no unsatisfied dependencies can run in the same group.
    """

    step_names: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.step_names)


@dataclass
class ParallelResult:
    """Result from parallel step execution."""

    step_results: list[StepResult] = field(default_factory=list)
    succeeded: bool = True
    failed_steps: list[str] = field(default_factory=list)

    def outputs(self) -> dict[str, str]:
        """Return mapping of step names to their outputs."""
        return {r.step_name: r.output for r in self.step_results if r.succeeded}


def identify_parallel_groups(workflow: WorkflowDefinition) -> list[ParallelGroup]:
    """Analyze workflow to find steps that can run in parallel.

    Uses topological ordering with dependency analysis. Steps are
    grouped by their "level" in the dependency graph. Steps at the
    same level have no dependencies on each other.

    Returns:
        List of ParallelGroup, ordered by execution sequence.
        Steps in the same group can run concurrently.
    """
    if not workflow.steps:
        return []

    # Build dependency graph
    deps: dict[str, set[str]] = {}
    for step in workflow.steps:
        deps[step.name] = set(step.depends_on())

    # Calculate levels using topological sort
    levels: dict[str, int] = {}
    remaining = set(deps.keys())

    current_level = 0
    while remaining:
        # Find steps with all dependencies satisfied
        ready = {
            name
            for name in remaining
            if all(d in levels for d in deps[name])
        }

        if not ready:
            # Circular dependency, should not happen after validation
            logger.warning("Circular dependency detected in workflow")
            break

        for name in ready:
            levels[name] = current_level
            remaining.remove(name)

        current_level += 1

    # Group by level
    max_level = max(levels.values()) if levels else 0
    groups: list[ParallelGroup] = []
    for level in range(max_level + 1):
        step_names = [name for name, lvl in levels.items() if lvl == level]
        groups.append(ParallelGroup(step_names=step_names))

    return groups


def can_parallelize(workflow: WorkflowDefinition) -> bool:
    """Check if a workflow has opportunities for parallel execution.

    Returns True if any group has more than one step.
    """
    groups = identify_parallel_groups(workflow)
    return any(len(g) > 1 for g in groups)


StepExecutor = Callable[[WorkflowStep, str, int], str]


class ParallelStepExecutor:
    """Execute multiple workflow steps concurrently.

    Uses a thread pool to run independent steps in parallel. Each step
    receives its input (from prior steps) and produces output.

    This implements the batch spawning pattern from Issue #168:
    - Launch multiple agents simultaneously
    - Independent work streams with no blocking dependencies
    - Aggregate results after completion
    """

    def __init__(
        self,
        runner: StepExecutor,
        max_workers: int | None = None,
        aggregation: AggregationStrategy = AggregationStrategy.MERGE,
    ) -> None:
        """Initialize parallel executor.

        Args:
            runner: Function to execute a single step
            max_workers: Maximum concurrent executions (None = CPU count)
            aggregation: Strategy for combining parallel outputs
        """
        self._runner = runner
        self._max_workers = max_workers
        self._aggregation = aggregation

    def execute_parallel(
        self,
        steps: list[WorkflowStep],
        inputs: dict[str, str],
        iteration: int = 1,
    ) -> ParallelResult:
        """Execute a group of steps concurrently.

        Args:
            steps: Steps to execute in parallel
            inputs: Mapping of step name to input string
            iteration: Current refinement loop iteration

        Returns:
            ParallelResult with outputs from all steps
        """
        if not steps:
            return ParallelResult()

        # Single step, no need for threading overhead
        if len(steps) == 1:
            step = steps[0]
            step_input = inputs.get(step.name, "")
            return self._execute_single(step, step_input, iteration)

        # Parallel execution with thread pool
        result = ParallelResult()

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self._max_workers
        ) as pool:
            futures: dict[concurrent.futures.Future[str], WorkflowStep] = {}

            for step in steps:
                step_input = inputs.get(step.name, "")
                future = pool.submit(self._runner, step, step_input, iteration)
                futures[future] = step

            for future in concurrent.futures.as_completed(futures):
                step = futures[future]
                try:
                    output = future.result()
                    result.step_results.append(
                        StepResult(
                            step_name=step.name,
                            status=WorkflowStatus.COMPLETED,
                            output=output,
                            iteration=iteration,
                        )
                    )
                except Exception as exc:
                    logger.warning(
                        "Parallel step '%s' failed: %s",
                        step.name,
                        exc,
                    )
                    result.step_results.append(
                        StepResult(
                            step_name=step.name,
                            status=WorkflowStatus.FAILED,
                            error=str(exc),
                            iteration=iteration,
                        )
                    )
                    result.failed_steps.append(step.name)
                    result.succeeded = False

        return result

    def _execute_single(
        self,
        step: WorkflowStep,
        step_input: str,
        iteration: int,
    ) -> ParallelResult:
        """Execute a single step without threading."""
        result = ParallelResult()
        try:
            output = self._runner(step, step_input, iteration)
            result.step_results.append(
                StepResult(
                    step_name=step.name,
                    status=WorkflowStatus.COMPLETED,
                    output=output,
                    iteration=iteration,
                )
            )
        except Exception as exc:
            logger.warning("Step '%s' failed: %s", step.name, exc)
            result.step_results.append(
                StepResult(
                    step_name=step.name,
                    status=WorkflowStatus.FAILED,
                    error=str(exc),
                    iteration=iteration,
                )
            )
            result.failed_steps.append(step.name)
            result.succeeded = False

        return result

    def aggregate_outputs(
        self,
        outputs: dict[str, str],
        strategy: AggregationStrategy | None = None,
    ) -> str:
        """Combine outputs from parallel steps.

        Args:
            outputs: Mapping of step names to outputs
            strategy: Override aggregation strategy (defaults to instance setting)

        Returns:
            Combined output string
        """
        strategy = strategy or self._aggregation

        if not outputs:
            return ""

        if strategy == AggregationStrategy.MERGE:
            # Combine all outputs with separator
            parts = [f"## {name}\n{output}" for name, output in outputs.items()]
            return "\n\n---\n\n".join(parts)

        if strategy == AggregationStrategy.VOTE:
            # Count identical outputs, return most common
            from collections import Counter
            counts = Counter(outputs.values())
            most_common = counts.most_common(1)
            if most_common:
                return most_common[0][0]
            return ""

        if strategy == AggregationStrategy.ESCALATE:
            # Return all outputs with conflict marker
            if len(set(outputs.values())) > 1:
                header = "## CONFLICT DETECTED - Multiple outputs require resolution\n\n"
                parts = [f"### {name}\n{output}" for name, output in outputs.items()]
                return header + "\n\n---\n\n".join(parts)
            # No conflict, return single value
            return next(iter(outputs.values()), "")

        return ""


def mark_parallel_steps(workflow: WorkflowDefinition) -> WorkflowDefinition:
    """Annotate workflow steps with parallel execution markers.

    Sets step.kind = StepKind.PARALLEL for steps that can run
    concurrently with others in their group.

    Returns a new WorkflowDefinition with updated step kinds.
    """
    groups = identify_parallel_groups(workflow)

    # Create mapping of step name to whether it can be parallel
    parallel_names: set[str] = set()
    for group in groups:
        if len(group) > 1:
            parallel_names.update(group.step_names)

    # Create new steps with updated kind
    new_steps = []
    for step in workflow.steps:
        if step.name in parallel_names:
            new_step = WorkflowStep(
                name=step.name,
                agent=step.agent,
                kind=StepKind.PARALLEL,
                inputs_from=step.inputs_from,
                prompt_template=step.prompt_template,
                max_retries=step.max_retries,
                condition=step.condition,
            )
        else:
            new_step = step
        new_steps.append(new_step)

    return WorkflowDefinition(
        name=workflow.name,
        steps=new_steps,
        max_iterations=workflow.max_iterations,
        metadata=workflow.metadata,
    )
