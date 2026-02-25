"""Workflow definition types for agent pipeline execution.

Provides dataclasses that model workflow pipelines with typed steps,
chaining patterns, and execution constraints. Workflows are loaded
from YAML definitions and validated before execution.

Exit Codes (ADR-035):
    0 - Success
    1 - Logic error (invalid workflow definition)
    2 - Config error (missing required fields)
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class StepKind(enum.Enum):
    """Classification of a workflow step."""

    AGENT = "agent"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"


class CoordinationMode(enum.Enum):
    """Coordination pattern for multi-agent workflows.

    Centralized: Single orchestrator manages all agents (default).
    Hierarchical: Tree structure with nested coordinators.
    Mesh: Peer-to-peer collaboration with shared task queue.
    """

    CENTRALIZED = "centralized"
    HIERARCHICAL = "hierarchical"
    MESH = "mesh"


class WorkflowStatus(enum.Enum):
    """Execution status of a workflow or step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class StepRef:
    """Reference to another step by name.

    Used to express dependencies and chaining relationships.
    """

    name: str


@dataclass
class WorkflowStep:
    """Single step in a workflow pipeline.

    Each step has an agent type, optional inputs from prior steps,
    and a maximum retry count.
    """

    name: str
    agent: str
    kind: StepKind = StepKind.AGENT
    inputs_from: list[StepRef] = field(default_factory=list)
    prompt_template: str = ""
    max_retries: int = 0
    condition: str = ""
    is_coordinator: bool = False
    subordinates: list[str] = field(default_factory=list)

    def depends_on(self) -> list[str]:
        """Return names of steps this step depends on."""
        return [ref.name for ref in self.inputs_from]


@dataclass
class WorkflowDefinition:
    """Complete workflow pipeline definition.

    A workflow has a name, ordered steps, and optional configuration
    for maximum iterations (refinement loops) and parallel execution.
    """

    name: str
    steps: list[WorkflowStep] = field(default_factory=list)
    max_iterations: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    coordination_mode: CoordinationMode = CoordinationMode.CENTRALIZED

    def step_names(self) -> list[str]:
        """Return ordered list of step names."""
        return [s.name for s in self.steps]

    def get_step(self, name: str) -> WorkflowStep | None:
        """Find a step by name. Returns None if not found."""
        for step in self.steps:
            if step.name == name:
                return step
        return None

    def validate(self) -> list[str]:
        """Check the definition for structural errors.

        Returns a list of error messages. Empty list means valid.
        """
        errors: list[str] = []
        if not self.name:
            errors.append("Workflow name is required")
        if not self.steps:
            errors.append("Workflow must have at least one step")

        seen: set[str] = set()
        for step in self.steps:
            if not step.name:
                errors.append("Step name is required")
            if step.name in seen:
                errors.append(f"Duplicate step name: {step.name}")
            seen.add(step.name)

            if not step.agent:
                errors.append(f"Step '{step.name}' requires an agent type")

            for dep in step.depends_on():
                if dep not in seen:
                    errors.append(
                        f"Step '{step.name}' depends on '{dep}' "
                        f"which is not defined before it"
                    )

            # Validate condition references (e.g., has:step_name, empty:step_name)
            if step.condition and ":" in step.condition:
                ref = step.condition.split(":", 1)[1].strip()
                if ref not in seen:
                    errors.append(
                        f"Step '{step.name}' references unknown step '{ref}' in condition"
                    )

        if self.max_iterations < 1:
            errors.append("max_iterations must be at least 1")

        # Validate coordination mode constraints
        if self.coordination_mode == CoordinationMode.HIERARCHICAL:
            coordinators = [s for s in self.steps if s.is_coordinator]
            if not coordinators:
                errors.append(
                    "Hierarchical mode requires at least one step "
                    "with is_coordinator=True"
                )
            for coord in coordinators:
                for sub in coord.subordinates:
                    if sub not in seen:
                        errors.append(
                            f"Coordinator '{coord.name}' references "
                            f"unknown subordinate '{sub}'"
                        )

        if self.coordination_mode == CoordinationMode.MESH:
            # Mesh mode requires at least 2 steps for peer collaboration
            if len(self.steps) < 2:
                errors.append("Mesh mode requires at least 2 steps")

        return errors


@dataclass
class StepResult:
    """Output from executing a single workflow step."""

    step_name: str
    status: WorkflowStatus
    output: str = ""
    error: str = ""
    iteration: int = 1

    @property
    def succeeded(self) -> bool:
        """Return True when the step completed without error."""
        return self.status == WorkflowStatus.COMPLETED


@dataclass
class WorkflowResult:
    """Aggregated result from a complete workflow execution."""

    workflow_name: str
    status: WorkflowStatus
    step_results: list[StepResult] = field(default_factory=list)
    iterations_completed: int = 0

    @property
    def succeeded(self) -> bool:
        """Return True when the workflow completed without error."""
        return self.status == WorkflowStatus.COMPLETED

    def get_step_result(self, name: str) -> StepResult | None:
        """Find the result for a step by name."""
        for r in self.step_results:
            if r.step_name == name:
                return r
        return None

    @property
    def final_output(self) -> str:
        """Return the output from the last completed step."""
        for r in reversed(self.step_results):
            if r.succeeded:
                return r.output
        return ""
