"""Shared builders for live durable-outcome tests (issue #5768). No real claude is started."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _claude_stream as stream_mod  # noqa: E402
import _durable_live as live_mod  # noqa: E402
import _durable_live_record as record_mod  # noqa: E402
import _routing_grader as grader_mod  # noqa: E402
import _routing_scenario as scenario_mod  # noqa: E402
import eval_durable_live as cli  # noqa: E402
from _durable_outcome import Verdict, classify, compare  # noqa: E402
from _outcome_record import parse_record  # noqa: E402

CORPUS = cli.DEFAULT_CORPUS
GOOD_TASK = "RB-01-bounded-implementation"
PLAUSIBLE_TASK = "RB-05-plausible-but-wrong"

__all__ = [
    "CORPUS",
    "EVAL_DIR",
    "Verdict",
    "classify",
    "compare",
    "parse_record",
    "GOOD_TASK",
    "PLAUSIBLE_TASK",
    "cli",
    "fake_runner",
    "grader_mod",
    "live_mod",
    "load",
    "record_mod",
    "stream_mod",
    "stream_text",
]


def load(task_id: str) -> Any:
    return next(s for s in scenario_mod.load_corpus(CORPUS) if s.scenario_id == task_id)


def stream_text(
    *,
    model: str = "claude-haiku-4-5-20251001",
    text: str = "Done.",
    tools: Sequence[str] = ("Edit",),
    tool_error: bool = False,
    subtype: str = "success",
    is_error: bool = False,
    denials: int = 0,
    cost: float = 0.02,
    with_result: bool = True,
) -> str:
    events: list[dict[str, Any]] = [
        {"type": "system", "subtype": "init", "claude_code_version": "2.1.285"},
        {
            "type": "assistant",
            "message": {
                "model": model,
                "content": [{"type": "tool_use", "name": name, "input": {}} for name in tools],
            },
        },
        {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "is_error": tool_error}]},
        },
    ]
    if with_result:
        events.append(
            {
                "type": "result",
                "subtype": subtype,
                "is_error": is_error,
                "total_cost_usd": cost,
                "num_turns": 3,
                "duration_ms": 1200,
                "permission_denials": [{}] * denials,
                "result": text,
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 30,
                    "cache_creation_input_tokens": 40,
                },
            }
        )
    return "".join(json.dumps(event) + "\n" for event in events)


def _copy_overlay(scenario: Any, overlay: str | None, workdir: Path) -> None:
    if overlay is None:
        return
    with tempfile.TemporaryDirectory(prefix="test-overlay-") as name:
        staged = Path(name) / "state"
        grader_mod.materialize(scenario, staged, overlay)
        shutil.copytree(staged, workdir, dirs_exist_ok=True)


def fake_runner(
    scenario: Any,
    overlays: Sequence[str | None],
    *,
    stdout: Callable[[int], str] | None = None,
    returncodes: Sequence[int] | None = None,
) -> Callable[..., subprocess.CompletedProcess[str]]:
    """A process runner whose i-th call leaves `overlays[i]` (last repeats) in the cwd."""
    calls: list[list[str]] = []

    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        index = len(calls)
        calls.append(list(argv))
        _copy_overlay(scenario, overlays[min(index, len(overlays) - 1)], Path(kwargs["cwd"]))
        code = 0 if returncodes is None else returncodes[min(index, len(returncodes) - 1)]
        out = stdout(index) if stdout else stream_text()
        return subprocess.CompletedProcess(argv, code, out, "")

    runner.calls = calls  # type: ignore[attr-defined]
    return runner
