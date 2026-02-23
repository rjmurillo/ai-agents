"""Load workflow definitions from YAML files.

Parses YAML workflow definitions into WorkflowDefinition objects.

Exit Codes (ADR-035):
    0 - Success
    1 - Logic error (invalid YAML structure)
    2 - Config error (file not found, parse error)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from scripts.workflow.schema import (
    CoordinationMode,
    StepKind,
    StepRef,
    WorkflowDefinition,
    WorkflowStep,
)


def load_workflow(path: Path) -> WorkflowDefinition:
    """Load a workflow definition from a YAML file.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the YAML structure is invalid.
    """
    text = path.read_text(encoding="utf-8")
    return parse_workflow(yaml.safe_load(text))


def parse_workflow(data: dict[str, Any]) -> WorkflowDefinition:
    """Parse a dict (from YAML) into a WorkflowDefinition.

    Raises:
        ValueError: If required fields are missing or malformed.
    """
    if not isinstance(data, dict):
        raise ValueError("Workflow definition must be a YAML mapping")

    name = data.get("name", "")
    if not name:
        raise ValueError("Workflow 'name' is required")

    raw_steps = data.get("steps", [])
    if not isinstance(raw_steps, list):
        raise ValueError("'steps' must be a list")

    steps = [_parse_step(s) for s in raw_steps]
    max_iterations = int(data.get("max_iterations", 1))
    metadata = data.get("metadata", {})

    mode_str = data.get("coordination_mode", "centralized")
    try:
        coordination_mode = CoordinationMode(mode_str)
    except ValueError as exc:
        raise ValueError(f"Invalid coordination_mode '{mode_str}'") from exc

    return WorkflowDefinition(
        name=name,
        steps=steps,
        max_iterations=max_iterations,
        metadata=metadata if isinstance(metadata, dict) else {},
        coordination_mode=coordination_mode,
    )


def _parse_step(data: Any) -> WorkflowStep:
    """Parse a single step dict into a WorkflowStep."""
    if not isinstance(data, dict):
        raise ValueError(f"Each step must be a mapping, got {type(data).__name__}")

    name = data.get("name", "")
    agent = data.get("agent", "")
    kind_str = data.get("kind", "agent")
    try:
        kind = StepKind(kind_str)
    except ValueError as exc:
        raise ValueError(f"Invalid step kind '{kind_str}' for step '{name}'") from exc

    inputs_from_raw = data.get("inputs_from", [])
    if isinstance(inputs_from_raw, list):
        inputs_from = [StepRef(name=str(r)) for r in inputs_from_raw]
    else:
        inputs_from = []

    subordinates_raw = data.get("subordinates", [])
    subordinates = (
        [str(s) for s in subordinates_raw]
        if isinstance(subordinates_raw, list)
        else []
    )

    return WorkflowStep(
        name=name,
        agent=agent,
        kind=kind,
        inputs_from=inputs_from,
        prompt_template=str(data.get("prompt_template", "")),
        max_retries=int(data.get("max_retries", 0)),
        condition=str(data.get("condition", "")),
        is_coordinator=bool(data.get("is_coordinator", False)),
        subordinates=subordinates,
    )
