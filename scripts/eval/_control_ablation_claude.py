"""Claude Code invocation for the reduced-control ablation runner (REQ-046 AC-8).

Builds the shell-free argv, places an isolated profile beside the workspace
(or keeps the operator's real HOME under `--real-home`), and reads the
stream-json result. Raises `HarnessFailureError` for a timeout-free run whose
stream is unparsable, carries no `total_cost_usd`, or resolved a different
model than requested. `eval_control_ablation.py` owns the run loop.
"""

from __future__ import annotations

import os
import stat
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import _control_ablation_tasks as ablation_tasks
from _runtime_harness import real_home_enabled, runtime_env
from _runtime_output import RuntimeOutputError, claude_result, parse_events, same_model

CLAUDE_EXECUTABLE = "claude"

Runner = Callable[..., subprocess.CompletedProcess[str]]


class HarnessFailureError(RuntimeError):
    """A live run's Claude invocation could not produce a usable record (AC-8)."""



# ---------------------------------------------------------------------------
# Claude invocation (DESIGN-044 "Run sequence (live)", step 2)
# ---------------------------------------------------------------------------


def claude_argv(model: str, prompt: str) -> list[str]:
    """Build the fixed argv DESIGN-044's run sequence specifies for step 2."""
    return [
        CLAUDE_EXECUTABLE,
        "--print",
        prompt,
        "--setting-sources",
        "project",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--permission-mode",
        "acceptEdits",
        "--output-format",
        "stream-json",
        "--verbose",
        "--no-session-persistence",
        "--model",
        model,
        "--tools",
        "Read,Edit,Write,Glob,Grep,Bash",
        "--allowedTools",
        "Bash(python3:*),Bash(git:*),Bash(ls:*),Bash(cat:*)",
    ]


def total_cost_usd(events: Sequence[Mapping[str, object]]) -> float | None:
    for event in events:
        if event.get("type") != "result":
            continue
        value = event.get("total_cost_usd")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)
    return None


def _require_success_result(events: Sequence[Mapping[str, object]], reply: str) -> None:
    """A result event marked `is_error` is a harness failure, not a task attempt."""
    for event in events:
        if event.get("type") != "result":
            continue
        if event.get("is_error") is True or event.get("subtype") not in (None, "success"):
            raise HarnessFailureError(f"claude result is an error: {reply[:200]!r}")
        return


def claude_config_dir(workspace: Path) -> Path:
    """Place the isolated Claude profile beside the workspace, not inside it.

    `runtime_env` roots CLAUDE_CONFIG_DIR at `<workspace>/.parity-profile`,
    which is the agent's working tree. A sibling directory keeps the profile
    out of the workspace's git and outside the agent's working directory.
    """
    config_dir = workspace.parent / f"{workspace.name}.claude-config"
    config_dir.mkdir(parents=True, exist_ok=True, mode=stat.S_IRWXU)
    os.chmod(config_dir, stat.S_IRWXU)
    return config_dir


def invoke_claude(
    workspace: Path,
    task: ablation_tasks.Task,
    model: str,
    timeout: float,
    runner: Runner,
) -> tuple[list[dict[str, object]], str, float, float, list[str]]:
    """Run one Claude CLI turn; raise `HarnessFailureError` for an AC-8 condition.

    Under `--real-home` (`EVAL_RUNTIME_REAL_HOME=1`) the child keeps the
    operator's own HOME and finds its stored login itself. Nothing is copied,
    linked, or read. Without it the profile is isolated and carries no login.
    """
    argv = claude_argv(model, task.prompt)
    env = runtime_env(workspace, "claude")
    if not real_home_enabled():
        env["CLAUDE_CONFIG_DIR"] = str(claude_config_dir(workspace))
    started = time.monotonic()
    try:
        result = runner(
            argv,
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        # str(TimeoutExpired) carries the full argv, including the prompt.
        raise HarnessFailureError(f"claude timed out after {timeout:.0f}s") from None
    wall_seconds = time.monotonic() - started
    if result.returncode != 0:
        raise HarnessFailureError(f"claude exited {result.returncode}")
    try:
        events = parse_events(result.stdout)
    except RuntimeOutputError as exc:
        raise HarnessFailureError(str(exc)) from exc
    reply, resolved_model = claude_result(events)
    _require_success_result(events, reply)
    if not same_model(resolved_model, model):
        raise HarnessFailureError(
            f"resolved model {resolved_model!r} does not match requested {model!r}"
        )
    cost = total_cost_usd(events)
    if cost is None:
        raise HarnessFailureError("claude stream result event carries no total_cost_usd")
    return events, reply, cost, wall_seconds, argv


def tool_results(events: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
    """Return `tool_result` content blocks from Claude's user-role turns.

    Claude Code's stream-json reports a completed tool call as a `user`-role
    event whose `message.content` list carries a block with
    `type: "tool_result"` and `is_error`. `_runtime_output.traces` extracts
    `tool_use` call blocks (the request), not this result block, so this
    stays local rather than widening that shared helper's contract.
    """
    results: list[Mapping[str, object]] = []
    for event in events:
        message = event.get("message")
        if not isinstance(message, Mapping):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, Mapping) and block.get("type") == "tool_result":
                results.append(block)
    return results


def tool_failures(events: Sequence[Mapping[str, object]]) -> int:
    return sum(1 for block in tool_results(events) if block.get("is_error"))
