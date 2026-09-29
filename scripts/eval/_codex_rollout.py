"""Reader for Codex rollout files: child topology and the spawn ceiling.

Issue #5423 asks for a verified subagent concurrency limit per harness. A live
`codex exec --json` run cannot show it: the JSON stream omits `spawn_agent`,
and the run in `harness-capability-matrix.json` peaked at 2 of 3 requested
children because the backend reports `parallel_tool_calls=false`. Codex does
write one rollout file per thread under `CODEX_HOME/sessions`, and a child's
file names its parent. This module reads those files offline, so a recorded
session can bound the ceiling without a paid call.

Observed record shapes, read from Codex rollout files written by codex-cli
0.154.0 (trimmed copies live in
`tests/eval/fixtures/harness_capability/codex-0.154.0-rollouts/`):

    {"timestamp": <ISO>, "type": "session_meta", "payload": {"id": ...,
     "timestamp": <ISO>, "cli_version": "0.154.0", "parent_thread_id": ...,
     "source": {"subagent": {"thread_spawn": {"parent_thread_id": ...}}}}}
    {"type": "event_msg", "payload": {"type": "task_started" | "task_complete"}}
    {"type": "event_msg", "payload": {"type": "context_compacted"}}
    {"type": "compacted", "payload": {...}}
    {"type": "response_item", "payload": {"type": "function_call_output" |
     "custom_tool_call_output", "output": <str | [{"text": ...}]>}}

The refusal text is `collab spawn failed: agent thread limit reached`, the
string `codex-0.156.0/thread-limit-1.trace.log` also shows for
`-c agents.max_threads=1`.

What the ceiling bounds mean (both are sound, neither is an estimate):

* lower bound: the most children whose turns were provably running at once.
  Each was admitted, so the limit is at least that many.
* upper bound: at a refused spawn, the runtime held at least `limit` live
  threads. Live threads never exceed the children the parent had spawned by
  then, so `limit <= children spawned before the refusal`.

When the bounds meet, the limit is exact for that capture. A child that
finished its turn may still be a live thread, so "running" is only ever used
for the lower bound and "spawned" only for the upper bound.

Stricter/looser/different than canonical: the runtime owns the limit and no
in-tree source states it; this reader infers it from recorded behavior and
does not read `agents.max_threads` from any config.

Observation only. Nothing here runs a CLI or decides a `CapabilityStatus`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

#: Verbatim refusal text; see `codex-0.156.0/thread-limit-1.trace.log`.
SPAWN_LIMIT_REFUSAL = "collab spawn failed: agent thread limit reached"


class RolloutError(ValueError):
    """A rollout file is malformed. Raised, never papered over with a default."""


@dataclass(frozen=True, slots=True)
class Rollout:
    """The facts one rollout file states about one thread."""

    thread_id: str
    parent_thread_id: str | None
    cli_version: str
    started_at: datetime
    ended_at: datetime
    turns_balanced: bool
    compacted_records: int
    context_compacted_events: int
    spawn_refusals: tuple[datetime, ...]


@dataclass(frozen=True, slots=True)
class SpawnCeiling:
    """Sound bounds on the child-thread limit from one parent's capture."""

    cli_version: str
    lower_bound: int
    upper_bound: int
    refusals: int

    @property
    def exact(self) -> bool:
        """True when the bounds meet, so the capture pins the limit."""
        return self.lower_bound == self.upper_bound


def _parse_time(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise RolloutError(f"{field} must be an ISO timestamp string")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RolloutError(f"{field} is not an ISO timestamp: {value!r}") from exc


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RolloutError(f"{field} must be a non-empty string")
    return value


def _record(line: str, number: int) -> Mapping[str, object]:
    try:
        record = json.loads(line)
    except json.JSONDecodeError as exc:
        raise RolloutError(f"line {number} is not JSON: {exc}") from exc
    if not isinstance(record, dict):
        raise RolloutError(f"line {number} is not a JSON object")
    return record


def _payload(record: Mapping[str, object]) -> Mapping[str, object]:
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else {}


def _parent_id(payload: Mapping[str, object]) -> str | None:
    """Return the parent thread id, refusing two ids that disagree."""
    found: list[str] = []
    direct = payload.get("parent_thread_id")
    if isinstance(direct, str):
        found.append(direct)
    source = payload.get("source")
    if isinstance(source, dict):
        subagent = source.get("subagent")
        spawn = subagent.get("thread_spawn") if isinstance(subagent, dict) else None
        nested = spawn.get("parent_thread_id") if isinstance(spawn, dict) else None
        if isinstance(nested, str):
            found.append(nested)
    if len(set(found)) > 1:
        raise RolloutError(f"parent_thread_id disagrees between fields: {found}")
    return found[0] if found else None


def _output_text(payload: Mapping[str, object]) -> str:
    output = payload.get("output")
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        return "\n".join(
            item["text"] for item in output if isinstance(item, dict) and "text" in item
        )
    return ""


def _is_refusal(record: Mapping[str, object]) -> bool:
    payload = _payload(record)
    kind = payload.get("type")
    if record.get("type") != "response_item" or kind not in (
        "function_call_output",
        "custom_tool_call_output",
    ):
        return False
    return SPAWN_LIMIT_REFUSAL in _output_text(payload)


def parse_rollout(lines: Iterable[str]) -> Rollout:
    """Parse one rollout, failing closed on anything it cannot account for."""
    meta: Mapping[str, object] | None = None
    last: datetime | None = None
    open_turns = 0
    compacted = 0
    context_events = 0
    refusals: list[datetime] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        record = _record(line, number)
        stamp = _parse_time(record.get("timestamp"), f"line {number} timestamp")
        last = stamp if last is None else max(last, stamp)
        if meta is None:
            if record.get("type") != "session_meta":
                raise RolloutError("first record must be session_meta")
            meta = _payload(record)
            continue
        kind = _payload(record).get("type")
        if record.get("type") == "compacted":
            compacted += 1
        elif record.get("type") == "event_msg" and kind == "context_compacted":
            context_events += 1
        elif record.get("type") == "event_msg" and kind == "task_started":
            open_turns += 1
        elif record.get("type") == "event_msg" and kind == "task_complete":
            open_turns -= 1
        elif _is_refusal(record):
            refusals.append(stamp)
    if meta is None or last is None:
        raise RolloutError("rollout is empty")
    if open_turns < 0:
        raise RolloutError("task_complete without a matching task_started")
    return Rollout(
        thread_id=_text(meta.get("id"), "session_meta.id"),
        parent_thread_id=_parent_id(meta),
        cli_version=_text(meta.get("cli_version"), "session_meta.cli_version"),
        started_at=_parse_time(meta.get("timestamp"), "session_meta.timestamp"),
        ended_at=last,
        turns_balanced=open_turns == 0,
        compacted_records=compacted,
        context_compacted_events=context_events,
        spawn_refusals=tuple(refusals),
    )


def load_rollout(path: Path) -> Rollout:
    """Read and parse a rollout file."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RolloutError(f"could not read {path.name}: {exc}") from exc
    return parse_rollout(text.splitlines())


def peak_running_children(children: Sequence[Rollout]) -> int | None:
    """Return the most children running at once, or `None` if unmeasurable.

    A child whose turns never all closed has not shown when it stopped, so the
    peak among the rest could be a false low (the same rule
    `_capability_topology.max_concurrent_children` applies). At an equal
    instant an end sorts before a start: touching spans do not overlap.
    """
    if not children or not all(child.turns_balanced for child in children):
        return None
    edges = [(child.started_at, 1) for child in children]
    edges += [(child.ended_at, -1) for child in children]
    depth = peak = 0
    for _, step in sorted(edges, key=lambda edge: (edge[0], edge[1])):
        depth += step
        peak = max(peak, depth)
    return peak


def spawn_ceiling(parent: Rollout, children: Sequence[Rollout]) -> SpawnCeiling | None:
    """Bound the child-thread limit from a parent and its children.

    Returns `None` when there is no refusal (no upper bound exists), when the
    peak is unmeasurable, or when a child names a different parent. A capture
    spanning two CLI versions is refused: the ceiling belongs to one runtime.
    """
    if not parent.spawn_refusals:
        return None
    if any(child.parent_thread_id != parent.thread_id for child in children):
        return None
    if any(child.cli_version != parent.cli_version for child in children):
        return None
    lower = peak_running_children(children)
    if lower is None:
        return None
    upper = min(
        sum(1 for child in children if child.started_at <= refusal)
        for refusal in parent.spawn_refusals
    )
    if upper < lower:
        return None
    return SpawnCeiling(
        cli_version=parent.cli_version,
        lower_bound=lower,
        upper_bound=upper,
        refusals=len(parent.spawn_refusals),
    )
