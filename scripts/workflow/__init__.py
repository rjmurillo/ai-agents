"""Workflow execution and chaining for agent pipelines.

Supports sequential chaining, parallel execution, and refinement loops.
"""

from scripts.workflow.coordinator import (
    CentralizedStrategy,
    CoordinationStrategy,
    HierarchicalStrategy,
    MeshStrategy,
    aggregate_subordinate_outputs,
    build_execution_plan,
    find_ready_steps,
    get_strategy,
)
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
    CoordinationMode,
    StepKind,
    StepRef,
    StepResult,
    WorkflowDefinition,
    WorkflowResult,
    WorkflowStatus,
    WorkflowStep,
)

__all__ = [
    "AggregationStrategy",
    "CentralizedStrategy",
    "CoordinationMode",
    "CoordinationStrategy",
    "HierarchicalStrategy",
    "MeshStrategy",
    "ParallelGroup",
    "ParallelStepExecutor",
    "StepKind",
    "StepRef",
    "StepResult",
    "WorkflowDefinition",
    "WorkflowExecutor",
    "WorkflowResult",
    "WorkflowStatus",
    "WorkflowStep",
    "aggregate_subordinate_outputs",
    "build_execution_plan",
    "can_parallelize",
    "find_ready_steps",
    "get_strategy",
    "identify_parallel_groups",
    "mark_parallel_steps",
]
