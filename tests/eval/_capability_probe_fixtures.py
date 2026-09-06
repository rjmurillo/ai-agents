"""Shared fixtures for the capability-probe tests (issue #5423 step 2).

Recorded runtime output shapes and an injected fake runner. Nothing here
reaches the network, PATH, or a real CLI. The runner dispatches on argv rather
than call order, so a probe that stops issuing a command fails loudly instead
of silently consuming the next entry in a positional list.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from typing import Any

from tests.eval._harness_capability_test_support import capability, probes

CapabilityStatus = capability.CapabilityStatus
EvidenceKind = capability.EvidenceKind
HarnessCapabilityError = capability.HarnessCapabilityError
ProbeError = probes.ProbeError
ProbeCommand = probes.ProbeCommand

TIMEOUT = 5.0


def _jsonl(events: Sequence[Mapping[str, object]]) -> str:
    return "\n".join(json.dumps(event) for event in events) + "\n"


def _answer(text: str, **data: object) -> dict[str, object]:
    """One Copilot answer turn, the shape `copilot_result` already reads."""
    return {"type": "assistant.message", "data": {"content": text, **data}}


def _session_change(**data: object) -> dict[str, object]:
    """A session-state event: the CLI reporting its own configuration."""
    return {"type": "session.model_change", "data": dict(data)}


def _runner(
    stdout: str = "",
    *,
    returncode: int = 0,
    stderr: str = "",
    raises: BaseException | None = None,
    seen: list[list[str]] | None = None,
):
    """Build a fake runner that dispatches on argv rather than call order."""

    def run(argv: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if seen is not None:
            seen.append(list(argv))
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(list(argv), returncode, stdout, stderr)

    return run


def _command(harness: str = "copilot") -> probes.ProbeCommand:
    return ProbeCommand(harness=harness, argv=(harness, "--prompt", "probe"))


def _plan(
    *,
    capability_key: str = "model_override",
    harness: str = "copilot",
    parent: str = "claude-opus-5",
    candidates: Sequence[str] = ("gpt-5.6-sol",),
) -> probes.OverridePlan:
    return probes.build_override_plan(
        capability=capability_key,
        harness=harness,
        parent_value=parent,
        candidates=candidates,
    )


