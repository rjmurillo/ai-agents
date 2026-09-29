"""Context compaction and truncation counted from a recorded runtime stream.

Issue #5423 capability 10 asks whether a harness makes context compaction,
reset, or restart observable. The matrix rows for both harnesses were
`UNVERIFIED` because no probe had triggered one. Both CLIs already write the
events, so a recorded session answers the question offline.

Observed shapes, read from real session files written by each CLI (trimmed
copies under `tests/eval/fixtures/harness_capability/`):

Copilot `events.jsonl`, copilotVersion 1.0.79-9 (`copilot-1.0.79-9/`):
    {"type": "session.start", "data": {"copilotVersion": "1.0.79-9", ...}}
    {"type": "session.compaction_start", "data": {...}}
    {"type": "session.compaction_complete", "data": {"success": true, ...}}
    {"type": "session.truncation", "data": {"tokenLimit": 200000, ...}}

Codex rollout, cli_version 0.154.0 (`codex-0.154.0-rollouts/`): a top-level
`{"type": "compacted"}` record, and in some versions an
`{"type": "event_msg", "payload": {"type": "context_compacted"}}` event. One
compaction can produce both, so a Codex count is the larger of the two, never
their sum.

Truncation is a Copilot event (`performedBy: BasicTruncator`) that drops
messages without a summary. It is counted apart from compaction because the
context that survives differs.

Stricter/looser/different than canonical: no in-tree document lists these
event names. The vocabulary is what the recorded files contain, at the versions
named above, and a runtime that renames an event yields zero events here, which
`_offline_capability.classify_context_reset` reports as `UNVERIFIED`.

Observation only. Nothing here runs a CLI or decides a `CapabilityStatus`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from _codex_rollout import Rollout


class ContextResetError(ValueError):
    """An event stream is malformed. Raised instead of returning a partial count."""


@dataclass(frozen=True, slots=True)
class ResetObservation:
    """What one recorded session shows about context loss."""

    harness: str
    cli_version: str
    compactions: int
    failed_compactions: int
    truncations: int

    @property
    def events(self) -> int:
        """Total context-loss events seen, failed compactions included."""
        return self.compactions + self.failed_compactions + self.truncations


def _event(line: str, number: int) -> Mapping[str, object]:
    try:
        event = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ContextResetError(f"line {number} is not JSON: {exc}") from exc
    if not isinstance(event, dict):
        raise ContextResetError(f"line {number} is not a JSON object")
    return event


def _data(event: Mapping[str, object]) -> Mapping[str, object]:
    data = event.get("data")
    return data if isinstance(data, dict) else {}


def _session_version(event: Mapping[str, object]) -> str:
    version = _data(event).get("copilotVersion")
    if not isinstance(version, str) or not version.strip():
        raise ContextResetError("session.start has no copilotVersion")
    return version


def _compaction_succeeded(event: Mapping[str, object]) -> bool:
    success = _data(event).get("success")
    if not isinstance(success, bool):
        raise ContextResetError("session.compaction_complete success must be a boolean")
    return success


def observe_copilot_events(lines: Iterable[str]) -> ResetObservation:
    """Count compactions and truncations in a Copilot `events.jsonl` stream.

    The stream must open with `session.start` carrying `copilotVersion`; a
    count with no runtime identity cannot be tied to a version and is refused.
    """
    version: str | None = None
    compactions = failed = truncations = 0
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        event = _event(line, number)
        kind = event.get("type")
        if version is None:
            if kind != "session.start":
                raise ContextResetError("first event must be session.start")
            version = _session_version(event)
        elif kind == "session.compaction_complete":
            if _compaction_succeeded(event):
                compactions += 1
            else:
                failed += 1
        elif kind == "session.truncation":
            truncations += 1
    if version is None:
        raise ContextResetError("event stream is empty")
    return ResetObservation("copilot", version, compactions, failed, truncations)


def observe_codex_rollout(rollout: Rollout) -> ResetObservation:
    """Count compactions in a parsed Codex rollout (larger of record or event)."""
    compactions = max(rollout.compacted_records, rollout.context_compacted_events)
    return ResetObservation("codex", rollout.cli_version, compactions, 0, 0)
