"""Shared types for the required-context lint.

Kept apart from the analysis so the step scanner and the workflow loader can
both name a finding and a producing job without importing each other.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

KIND_STEP = "step-condition"
KIND_RELOCATED = "relocated-condition"
KIND_JOB = "job-condition"
KIND_PRODUCERS = "producer-count"
KIND_UNSCANNED = "unscanned"
KIND_UNATTRIBUTED = "unattributed-job"


class WorkflowLoadError(Exception):
    """A workflow file could not be read or parsed."""


@dataclass(frozen=True, slots=True)
class Finding:
    """One place a required-context chain departs from the property."""

    kind: str
    context: str
    workflow: str
    job: str
    detail: str
    step: str = ""

    def render(self) -> str:
        where = f"{self.workflow}:{self.job}"
        if self.step:
            where = f"{where}:{self.step}"
        return f"[{self.kind}] {self.context}: {where}: {self.detail}"


@dataclass(frozen=True, slots=True)
class ProducingJob:
    """A job whose check-run name is a pinned required context."""

    workflow: str
    job_id: str
    context: str
    body: Mapping[str, Any]
    workflow_env: Mapping[str, Any] = field(default_factory=dict)


def mapping(container: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = container.get(key)
    return value if isinstance(value, Mapping) else {}
