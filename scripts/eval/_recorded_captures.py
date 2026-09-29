"""Apply recorded runtime captures to the capability matrix.

A capture plan lists files a past run left on disk. Each entry names one
harness capability and the files that bear on it. The plan is data: the
classifiers in `_offline_capability` decide, and this module only reads files
and routes them.

Plan entry shapes (paths resolve against the plan file's directory):

    {"harness": "codex", "capability": "concurrency_limit",
     "parent": "<rollout>", "children": ["<rollout>", ...],
     "configured_max_threads": <int, optional>}
    {"harness": "codex", "capability": "context_reset_observability",
     "rollout": "<rollout>"}
    {"harness": "copilot", "capability": "context_reset_observability",
     "events": "<events.jsonl>"}

`configured_max_threads` states the `-c agents.max_threads=N` the captured
session ran with. Leave it out when unknown: the cell then cannot verify.

Only a `VERIFIED` result replaces a matrix cell. Any other result is reported
under `recorded_captures` and leaves the checked-in cell alone, so a capture
from another version can never overwrite a hand-written cell that carries a
probe command and an evidence trail.

The plan reads files the operator names and never writes them.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from _codex_rollout import RolloutError, load_rollout, spawn_ceiling
from _context_reset import ContextResetError, observe_codex_rollout, observe_copilot_events
from _harness_capability import (
    Capability,
    CapabilityStatus,
    HarnessCapabilityError,
    HarnessCapabilityRecord,
    validate_record,
)
from _offline_capability import classify_context_reset, classify_spawn_ceiling

_RESET = "context_reset_observability"
_CEILING = "concurrency_limit"
REGENERATE_COMMAND = (
    "python3 scripts/eval/eval_recorded_capabilities.py "
    "--captures scripts/eval/examples/harness-capability-recorded-captures.json"
)
_SUPPORTED = {("codex", _CEILING), ("codex", _RESET), ("copilot", _RESET)}


class CapturePlanError(HarnessCapabilityError):
    """The capture plan is malformed or names a file it cannot read."""


@dataclass(frozen=True, slots=True)
class RecordedCapture:
    """One classified capture and where it came from."""

    harness: str
    capability: str
    cell: Capability
    sources: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return the report form."""
        return {
            "harness": self.harness,
            "capability": self.capability,
            "status": self.cell.status.value,
            "evidence": self.cell.evidence.value,
            "detail": self.cell.detail,
            "value": self.cell.value,
            "sources": list(self.sources),
        }


def load_plan(path: Path) -> list[Mapping[str, object]]:
    """Read the plan document, failing closed on anything unexpected."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CapturePlanError(f"could not read capture plan: {exc}") from exc
    entries = document.get("captures") if isinstance(document, dict) else None
    if not isinstance(entries, list) or not entries:
        raise CapturePlanError("captures must be a non-empty array")
    if not all(isinstance(entry, dict) for entry in entries):
        raise CapturePlanError("every capture must be an object")
    return entries


def _record_for(
    records: Sequence[HarnessCapabilityRecord], harness: str
) -> HarnessCapabilityRecord:
    for record in records:
        if record.harness == harness:
            return record
    raise CapturePlanError(f"matrix has no record for harness {harness!r}")


def _path(base: Path, value: object, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise CapturePlanError(f"{field} must be a non-empty path string")
    return (base / value).resolve()


def _configured(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CapturePlanError("configured_max_threads must be a positive integer")
    return value


def _ceiling_capture(
    entry: Mapping[str, object], record: HarnessCapabilityRecord, base: Path
) -> RecordedCapture:
    children = entry.get("children")
    if not isinstance(children, list) or not children:
        raise CapturePlanError("children must be a non-empty array of paths")
    configured = _configured(entry.get("configured_max_threads"))
    parent_path = _path(base, entry.get("parent"), "parent")
    child_paths = [_path(base, value, "children[]") for value in children]
    parent = load_rollout(parent_path)
    ceiling = spawn_ceiling(parent, [load_rollout(child) for child in child_paths])
    cell = classify_spawn_ceiling(ceiling, record, configured)
    return RecordedCapture(
        record.harness, _CEILING, cell, tuple(p.name for p in [parent_path, *child_paths])
    )


def _reset_capture(
    entry: Mapping[str, object], record: HarnessCapabilityRecord, base: Path
) -> RecordedCapture:
    if record.harness == "codex":
        source = _path(base, entry.get("rollout"), "rollout")
        observation = observe_codex_rollout(load_rollout(source))
    else:
        source = _path(base, entry.get("events"), "events")
        try:
            text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CapturePlanError(f"could not read {source.name}: {exc}") from exc
        observation = observe_copilot_events(text.splitlines())
    return RecordedCapture(
        record.harness, _RESET, classify_context_reset(observation, record), (source.name,)
    )


def derive_captures(
    records: Sequence[HarnessCapabilityRecord],
    entries: Sequence[Mapping[str, object]],
    base: Path,
) -> list[RecordedCapture]:
    """Classify every plan entry. Any unreadable or unsupported entry raises."""
    captures: list[RecordedCapture] = []
    for entry in entries:
        harness, capability = entry.get("harness"), entry.get("capability")
        if (harness, capability) not in _SUPPORTED:
            raise CapturePlanError(f"unsupported capture: {harness!r} {capability!r}")
        record = _record_for(records, str(harness))
        try:
            build = _ceiling_capture if capability == _CEILING else _reset_capture
            captures.append(build(entry, record, base))
        except (RolloutError, ContextResetError) as exc:
            raise CapturePlanError(f"{harness} {capability}: {exc}") from exc
    return captures


def _with_provenance(capture: RecordedCapture) -> Capability:
    """Give a verified cell the sources and regenerating command other cells carry."""
    sources = ", ".join(capture.sources)
    return replace(
        capture.cell,
        detail=f"{capture.cell.detail} Sources: {sources}.",
        probe_command=REGENERATE_COMMAND,
    )


def _without_owed(record: HarnessCapabilityRecord, capability: str) -> HarnessCapabilityRecord:
    """Drop the pending live probes a verified capability no longer owes."""
    prefix = f"{record.harness} {capability}"
    kept = tuple(p for p in record.pending_live_probes if not p.scope.startswith(prefix))
    return replace(record, pending_live_probes=kept)


def apply_verified(
    records: Sequence[HarnessCapabilityRecord], captures: Sequence[RecordedCapture]
) -> list[HarnessCapabilityRecord]:
    """Return records with each `VERIFIED` capture written into its cell.

    The written cell carries its sources, capture date, and regenerating
    command, and the capability's pending live probes are dropped.
    """
    updated = list(records)
    for capture in captures:
        if capture.cell.status is not CapabilityStatus.VERIFIED:
            continue
        for index, record in enumerate(updated):
            if record.harness == capture.harness:
                cells = {**record.capabilities, capture.capability: _with_provenance(capture)}
                revised = _without_owed(replace(record, capabilities=cells), capture.capability)
                validate_record(revised)
                updated[index] = revised
    return updated
