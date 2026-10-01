"""Parse `claude -p --output-format stream-json` output into typed facts (issue #5768).

Observed on claude 2.1.285, 2026-09-30: the `system/init` event carries
`claude_code_version`; each `assistant` event carries `message.model` (the model
the API response names) and `tool_use` blocks; `user` events carry
`tool_result` blocks with `is_error`; the final `result` event carries
`subtype`, `is_error`, `total_cost_usd`, `usage`, `num_turns`, `duration_ms`,
`permission_denials`, and `result`. The stream names no reasoning effort.

A stream with no `result` event is an incomplete run, never a success.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

#: Result subtypes where the agent ran out of turns or budget. The working tree
#: holds whatever it finished, so this is a task outcome to grade, not a harness
#: failure. Observed on claude 2.1.285: `error_max_turns` at `--max-turns 12`.
TASK_LIMIT_SUBTYPES = frozenset({"error_max_turns", "error_max_budget_usd"})


@dataclass(frozen=True, slots=True)
class StreamFacts:
    """What one `claude -p --output-format stream-json` run reported."""

    models: tuple[str, ...] = ()
    cli_version: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    turns: int = 0
    duration_ms: int = 0
    tool_calls: tuple[str, ...] = ()
    tool_errors: int = 0
    permission_denials: int = 0
    final_text: str = ""
    completed: bool = False
    failure: str = ""
    limit_hit: str = ""


@dataclass(frozen=True, slots=True)
class Invocation:
    """One process run: what was asked, what came back, how long it took."""

    control: str
    task_id: str
    round_index: int
    exit_code: int | None
    wall_seconds: float
    facts: StreamFacts

    def summary(self) -> dict[str, object]:
        facts = self.facts
        return {
            "control": self.control,
            "task_id": self.task_id,
            "round": self.round_index,
            "exit_code": self.exit_code,
            "wall_seconds": round(self.wall_seconds, 3),
            "observed_models": list(facts.models),
            "cli_version": facts.cli_version,
            "completed": facts.completed,
            "failure": facts.failure,
            "limit_hit": facts.limit_hit,
            "turns": facts.turns,
            "input_tokens": facts.input_tokens,
            "output_tokens": facts.output_tokens,
            "cache_read_tokens": facts.cache_read_tokens,
            "cache_write_tokens": facts.cache_write_tokens,
            "cost_usd": facts.cost_usd,
            "tool_calls": list(facts.tool_calls),
            "tool_errors": facts.tool_errors,
            "permission_denials": facts.permission_denials,
        }


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _blocks(event: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return [block for block in content or [] if isinstance(block, dict)]


class _Collector:
    """Accumulates `StreamFacts` fields from decoded stream events."""

    def __init__(self) -> None:
        self.models: list[str] = []
        self.tools: list[str] = []
        self.version = ""
        self.tool_errors = 0
        self.result: Mapping[str, Any] | None = None
        self.malformed = 0

    def add(self, event: Mapping[str, Any]) -> None:
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            self.version = str(event.get("claude_code_version", ""))
        elif kind == "assistant":
            self._assistant(event)
        elif kind == "user":
            self.tool_errors += sum(1 for b in _blocks(event) if b.get("is_error") is True)
        elif kind == "result":
            self.result = event

    def _assistant(self, event: Mapping[str, Any]) -> None:
        message = event.get("message")
        model = message.get("model") if isinstance(message, dict) else None
        if isinstance(model, str) and model not in self.models:
            self.models.append(model)
        self.tools.extend(
            str(b.get("name", "")) for b in _blocks(event) if b.get("type") == "tool_use"
        )


def parse_stream(text: str) -> StreamFacts:
    """Parse stream-json output. A missing `result` event is an incomplete run, not a pass."""
    collector = _Collector()
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            collector.malformed += 1
            continue
        if isinstance(event, dict):
            collector.add(event)
    return _facts(collector)


def _facts(collector: _Collector) -> StreamFacts:
    result = collector.result
    if result is None:
        return StreamFacts(
            models=tuple(collector.models),
            cli_version=collector.version,
            tool_calls=tuple(collector.tools),
            tool_errors=collector.tool_errors,
            failure="no result event in stream",
        )
    raw_usage = result.get("usage")
    usage: Mapping[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
    denials = result.get("permission_denials")
    subtype = str(result.get("subtype", ""))
    limit = subtype if subtype in TASK_LIMIT_SUBTYPES else ""
    failed = (not limit) and (result.get("is_error") is True or subtype != "success")
    cost = result.get("total_cost_usd")
    return StreamFacts(
        models=tuple(collector.models),
        cli_version=collector.version,
        input_tokens=_int(usage.get("input_tokens")),
        output_tokens=_int(usage.get("output_tokens")),
        cache_read_tokens=_int(usage.get("cache_read_input_tokens")),
        cache_write_tokens=_int(usage.get("cache_creation_input_tokens")),
        cost_usd=float(cost) if isinstance(cost, (int, float)) else 0.0,
        turns=_int(result.get("num_turns")),
        duration_ms=_int(result.get("duration_ms")),
        tool_calls=tuple(collector.tools),
        tool_errors=collector.tool_errors,
        permission_denials=len(denials) if isinstance(denials, list) else 0,
        final_text=str(result.get("result", "")),
        completed=not failed,
        failure=subtype if failed else "",
        limit_hit=limit,
    )
