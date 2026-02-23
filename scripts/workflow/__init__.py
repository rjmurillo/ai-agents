"""Workflow execution and chaining for agent pipelines.

Supports sequential chaining, parallel execution, and refinement loops.
"""

from scripts.workflow.executor import WorkflowExecutor
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
    StepResult,
    WorkflowDefinition,
    WorkflowResult,
    WorkflowStatus,
    WorkflowStep,
)

__all__ = [
    "AggregationStrategy",
    "ParallelGroup",
    "ParallelStepExecutor",
    "StepKind",
    "StepResult",
    "WorkflowDefinition",
    "WorkflowExecutor",
    "WorkflowResult",
    "WorkflowStatus",
    "WorkflowStep",
    "can_parallelize",
    "identify_parallel_groups",
    "mark_parallel_steps",
]
