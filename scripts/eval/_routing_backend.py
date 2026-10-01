"""Execution backends for the routing benchmark (issue #5424).

A `Backend` runs one invocation and grades the repository state a round left
behind. `ScriptedBackend` is the deterministic fake: it returns honest,
fully-observed values by default and lets a test override any field of any
invocation, so each mismatch the runner must detect can be produced on demand.
It grades with the real deterministic grader and the real corpus, using the
control overlays (`known_good`, `known_bad`) as the state a driver left.

`ScriptedBackend` makes no model call, starts no process, and reads no
credential. The gated live backend lives in `_routing_live.py`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Protocol, cast

from _harness_capability import EvidenceKind
from _routing_grader import GradeResult, grade_overlay
from _routing_result import SESSION_MARKER_FRESH, InvocationRequest, Observation
from _routing_scenario import Scenario

DEFAULT_ELAPSED_SECONDS = 5.0
PHASE_STRIDE_SECONDS = 10.0
_PHASE_DEPTH = {"plan": 0, "implement": 1, "integrate": 2, "review": 3}
_CORRECTION_BASE_DEPTH = 4
PLAN_INVOCATION_ID = "planner-plan"
IMPLEMENT_INVOCATION_ID = "implementer-implement"


class Backend(Protocol):
    def invoke(self, request: InvocationRequest, scenario: Scenario) -> Observation:
        """Run one invocation and report what the harness observed."""
        ...

    def grade(self, scenario: Scenario, round_index: int) -> GradeResult:
        """Grade the repository state after round `round_index` (0 is the first attempt)."""
        ...


@dataclass(frozen=True, slots=True)
class Script:
    """What a scripted driver does for one scenario.

    `overlays[i]` is the control overlay left in the repository after round
    `i`; the last entry repeats. `None` means the untouched initial state.
    `overrides` maps an invocation id, or `role:<role>`, to `Observation`
    fields that replace the honest default.
    """

    overlays: tuple[str | None, ...] = ("known_good",)
    overrides: Mapping[str, Mapping[str, object]] = field(default_factory=dict)


def _depth(phase_id: str) -> int:
    if phase_id.startswith("correct-"):
        return _CORRECTION_BASE_DEPTH + int(phase_id.removeprefix("correct-"))
    return _PHASE_DEPTH[phase_id]


def _artifact_sha(scenario: Scenario) -> str:
    return hashlib.sha256(f"implementation-plan:{scenario.scenario_id}".encode()).hexdigest()


class ScriptedBackend:
    """Deterministic fake backend. `calls` records every invocation it served."""

    def __init__(
        self,
        scripts: Mapping[str, Script] | None = None,
        default: Script | None = None,
    ) -> None:
        self._scripts = dict(scripts or {})
        self._default = default or Script()
        self.calls: list[str] = []

    def _script(self, scenario: Scenario) -> Script:
        return self._scripts.get(scenario.scenario_id, self._default)

    def _honest(self, request: InvocationRequest, scenario: Scenario) -> Observation:
        sha = _artifact_sha(scenario)
        return Observation(
            session_id=request.session_id,
            start_offset_seconds=_depth(request.phase_id) * PHASE_STRIDE_SECONDS,
            elapsed_seconds=DEFAULT_ELAPSED_SECONDS,
            observed_model=request.model,
            observed_effort=request.effort,
            evidence=EvidenceKind.BACKEND,
            input_tokens=1000,
            output_tokens=500,
            tool_sandbox="sandbox:workspace-write",
            context_markers=(SESSION_MARKER_FRESH,) if request.fresh_context else (),
            artifact_sha=sha if request.invocation_id == PLAN_INVOCATION_ID else None,
            consumed_artifact_sha=sha if request.invocation_id == IMPLEMENT_INVOCATION_ID else None,
            reviewer_context_leak=False if request.role == "reviewer" else None,
        )

    def invoke(self, request: InvocationRequest, scenario: Scenario) -> Observation:
        self.calls.append(request.invocation_id)
        observation = self._honest(request, scenario)
        overrides = self._script(scenario).overrides
        for key in (f"role:{request.role}", request.invocation_id):
            patch = overrides.get(key)
            if patch:
                observation = replace(observation, **cast("dict[str, Any]", dict(patch)))
        return observation

    def grade(self, scenario: Scenario, round_index: int) -> GradeResult:
        overlays = self._script(scenario).overlays
        overlay = overlays[min(round_index, len(overlays) - 1)]
        return grade_overlay(scenario, *([overlay] if overlay else []))
