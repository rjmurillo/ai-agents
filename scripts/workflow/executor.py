"""Workflow executor for agent pipeline chaining.

Executes workflow definitions by running steps in order, chaining
outputs between steps, and supporting parallel branches and
refinement loops.

Exit Codes (ADR-035):
    0 - Success
    1 - Logic error (step execution failed)
    2 - Config error (invalid workflow)
"""

from __future__ import annotations

import logging
from typing import Protocol

from scripts.workflow.schema import (
    StepResult,
    WorkflowDefinition,
    WorkflowResult,
    WorkflowStatus,
    WorkflowStep,
)

logger = logging.getLogger(__name__)


class StepRunner(Protocol):
    """Interface for executing a single workflow step.

    Implementations receive the step definition, combined input from
    prior steps, and the current iteration number. They return the
    step output as a string.
    """

    def __call__(
        self,
        step: WorkflowStep,
        combined_input: str,
        iteration: int,
    ) -> str: ...


class WorkflowExecutor:
    """Execute workflow definitions with output chaining.

    The executor walks through steps in definition order. Each step
    receives the combined output of its declared input dependencies.
    When a step has no explicit inputs, it receives the output of the
    immediately preceding step (sequential chaining).

    Supports:
    - Sequential chaining: A -> B -> C
    - Parallel merge: steps with shared inputs run independently,
      then a downstream step merges their outputs
    - Refinement loops: repeated execution with max_iterations
    - Conditional steps: skipped when condition evaluates to false
    """

    def __init__(self, runner: StepRunner) -> None:
        self._runner = runner

    def execute(self, workflow: WorkflowDefinition) -> WorkflowResult:
        """Run a workflow definition to completion.

        Validates the workflow first. Returns a WorkflowResult with
        per-step results and overall status.
        """
        errors = workflow.validate()
        if errors:
            logger.error("Workflow validation failed: %s", errors)
            return WorkflowResult(
                workflow_name=workflow.name,
                status=WorkflowStatus.FAILED,
            )

        result = WorkflowResult(
            workflow_name=workflow.name,
            status=WorkflowStatus.RUNNING,
        )

        # Preserve outputs across iterations for refinement loops
        step_outputs: dict[str, str] = {}

        for iteration in range(1, workflow.max_iterations + 1):
            result.iterations_completed = iteration
            failed = False

            for idx, step in enumerate(workflow.steps):
                if failed:
                    result.step_results.append(
                        StepResult(
                            step_name=step.name,
                            status=WorkflowStatus.SKIPPED,
                            iteration=iteration,
                        )
                    )
                    continue

                if step.condition and not self._evaluate_condition(
                    step.condition, step_outputs
                ):
                    result.step_results.append(
                        StepResult(
                            step_name=step.name,
                            status=WorkflowStatus.SKIPPED,
                            iteration=iteration,
                        )
                    )
                    continue

                combined_input = self._gather_inputs(step, idx, step_outputs, workflow)
                step_result = self._run_step(step, combined_input, iteration)
                result.step_results.append(step_result)

                if step_result.succeeded:
                    step_outputs[step.name] = step_result.output
                else:
                    failed = True

            if failed:
                result.status = WorkflowStatus.FAILED
                return result

        result.status = WorkflowStatus.COMPLETED
        return result

    def _gather_inputs(
        self,
        step: WorkflowStep,
        idx: int,
        step_outputs: dict[str, str],
        workflow: WorkflowDefinition,
    ) -> str:
        """Combine outputs from upstream steps into a single input string.

        For refinement loops, the first step of iteration N receives the
        output from the last step of iteration N-1.
        """
        deps = step.depends_on()
        if deps:
            parts = [step_outputs[d] for d in deps if d in step_outputs]
            return "\n---\n".join(parts)

        if idx > 0:
            prev_name = workflow.steps[idx - 1].name
            return step_outputs.get(prev_name, "")

        # First step in a refinement loop gets output from last step
        if idx == 0 and workflow.steps:
            last_step_name = workflow.steps[-1].name
            return step_outputs.get(last_step_name, "")

        return ""

    def _run_step(
        self,
        step: WorkflowStep,
        combined_input: str,
        iteration: int,
    ) -> StepResult:
        """Execute a step with retry logic."""
        last_error = ""
        for attempt in range(step.max_retries + 1):
            try:
                output = self._runner(step, combined_input, iteration)
                return StepResult(
                    step_name=step.name,
                    status=WorkflowStatus.COMPLETED,
                    output=output,
                    iteration=iteration,
                )
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "Step '%s' attempt %d failed: %s",
                    step.name,
                    attempt + 1,
                    last_error,
                )

        return StepResult(
            step_name=step.name,
            status=WorkflowStatus.FAILED,
            error=last_error,
            iteration=iteration,
        )

    @staticmethod
    def _evaluate_condition(condition: str, step_outputs: dict[str, str]) -> bool:
        """Evaluate a simple condition expression.

        Supports:
        - "has:<step_name>" - true if step produced non-empty output
        - "empty:<step_name>" - true if step produced no output or was not run
        """
        if condition.startswith("has:"):
            ref = condition[4:].strip()
            return bool(step_outputs.get(ref, "").strip())
        if condition.startswith("empty:"):
            ref = condition[6:].strip()
            return not step_outputs.get(ref, "").strip()
        return True
