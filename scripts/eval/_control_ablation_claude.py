"""Claude Code invocation for the reduced-control ablation runner (REQ-046 AC-8).

Builds the shell-free argv, places an isolated profile beside the workspace
(or keeps the operator's real HOME under `--real-home`), and reads the
stream-json result. Raises `HarnessFailureError` for a timeout-free run whose
stream is unparsable, carries no `total_cost_usd`, or resolved a different
model than requested. `eval_control_ablation.py` owns the run loop.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path

import _control_ablation_tasks as ablation_tasks
from _durable_review import REVIEW_TOOLS
from _runtime_harness import real_home_enabled, runtime_env
from _runtime_output import RuntimeOutputError, claude_result, parse_events, same_model

CLAUDE_EXECUTABLE = "claude"

Runner = Callable[..., subprocess.CompletedProcess[str]]

#: `--tools` value for the reviewer arm: the read-only names, comma-joined.
REVIEWER_TOOLS = ",".join(REVIEW_TOOLS)


class HarnessFailureError(RuntimeError):
    """A live run's Claude invocation could not produce a usable record (AC-8).

    `cost_usd` and `wall_seconds` are what the failed launch still spent: the
    elapsed time always, the cost when the stream reported one. The reviewer arm
    adds them to the run's economics, because a launch that ran and failed was
    still paid for.
    """

    def __init__(self, message: str, *, cost_usd: float = 0.0, wall_seconds: float = 0.0) -> None:
        super().__init__(message)
        self.cost_usd = cost_usd
        self.wall_seconds = wall_seconds


# ---------------------------------------------------------------------------
# Claude invocation (DESIGN-044 "Run sequence (live)", step 2)
# ---------------------------------------------------------------------------


#: Tool set and Bash allowlist of the producer run (DESIGN-044 step 2).
PRODUCER_TOOLS = "Read,Edit,Write,Glob,Grep,Bash"
PRODUCER_ALLOWED = "Bash(python3:*),Bash(git:*),Bash(ls:*),Bash(cat:*)"


def claude_argv(
    model: str,
    prompt: str,
    *,
    tools: str = PRODUCER_TOOLS,
    allowed_tools: str | None = PRODUCER_ALLOWED,
) -> list[str]:
    """Build the fixed argv DESIGN-044's run sequence specifies for step 2.

    The defaults are the producer run. The reviewer arm passes read-only
    `tools` and `allowed_tools=None`, which drops the Bash allowlist.
    """
    argv = [
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
        tools,
    ]
    if allowed_tools is not None:
        argv += ["--allowedTools", allowed_tools]
    return argv


def total_cost_usd(events: Sequence[Mapping[str, object]]) -> float | None:
    for event in events:
        if event.get("type") != "result":
            continue
        value = event.get("total_cost_usd")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)
    return None


def _reported_cost(stdout: str) -> float:
    """The cost a failed launch's stream reported, or 0.0 when it reported none."""
    try:
        cost = total_cost_usd(parse_events(stdout))
    except RuntimeOutputError:
        return 0.0
    return cost if cost is not None else 0.0


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
    return _run_claude(workspace, claude_argv(model, task.prompt), model, timeout, runner)


def invoke_reviewer(
    workspace: Path,
    prompt: str,
    model: str,
    timeout: float,
    runner: Runner,
) -> tuple[str, float, float]:
    """Run the independent reviewer: read-only tools, no Bash. Returns (reply, cost, wall).

    Raises `HarnessFailureError` on the same conditions as `invoke_claude`. The
    caller treats that as a missing review (`review_findings` is `None`), not as
    a failed producer run.
    """
    argv = claude_argv(model, prompt, tools=REVIEWER_TOOLS, allowed_tools=None)
    _, reply, cost, wall_seconds, _ = _run_claude(workspace, argv, model, timeout, runner)
    return reply, cost, wall_seconds


def _run_claude(
    workspace: Path,
    argv: list[str],
    model: str,
    timeout: float,
    runner: Runner,
) -> tuple[list[dict[str, object]], str, float, float, list[str]]:
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
        raise HarnessFailureError(
            f"claude timed out after {timeout:.0f}s", wall_seconds=time.monotonic() - started
        ) from None
    wall_seconds = time.monotonic() - started
    spent = _reported_cost(result.stdout)
    if result.returncode != 0:
        raise HarnessFailureError(
            f"claude exited {result.returncode}", cost_usd=spent, wall_seconds=wall_seconds
        )
    try:
        events = parse_events(result.stdout)
    except RuntimeOutputError as exc:
        raise HarnessFailureError(str(exc), wall_seconds=wall_seconds) from exc
    reply, resolved_model = claude_result(events)
    try:
        _require_success_result(events, reply)
    except HarnessFailureError as exc:
        raise HarnessFailureError(str(exc), cost_usd=spent, wall_seconds=wall_seconds) from exc
    if not same_model(resolved_model, model):
        raise HarnessFailureError(
            f"resolved model {resolved_model!r} does not match requested {model!r}",
            cost_usd=spent,
            wall_seconds=wall_seconds,
        )
    cost = total_cost_usd(events)
    if cost is None:
        raise HarnessFailureError(
            "claude stream result event carries no total_cost_usd", wall_seconds=wall_seconds
        )
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


#: A shell segment that invokes a test runner: `pytest ...`, or `python -m pytest|unittest`
#: (any `python`, `python3`, or interpreter path), optionally after `uv run` or `cd x &&`.
_TEST_INVOCATION = re.compile(
    r"(?:^|[;&|(]\s*)(?:uv\s+run\s+(?:--\S+\s+)*)?"
    r"(?:pytest\b|\S*python[\d.]*\s+(?:-\S+\s+)*-m\s+(?:pytest|unittest)\b)",
    re.MULTILINE,
)
#: A heredoc opener (`<<'E'`, `<<-EOF`, `<< "X"`): its body is data, not commands.
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")


def _without_heredoc_bodies(command: str) -> str:
    """Drop each heredoc body, so code a heredoc writes is never read as a command."""
    kept: list[str] = []
    terminator: str | None = None
    for line in command.split("\n"):
        if terminator is not None:
            if line.strip() == terminator:
                terminator = None
            continue
        kept.append(line)
        opener = _HEREDOC.search(line)
        if opener:
            terminator = opener.group(2)
    return "\n".join(kept)


def is_test_invocation(command: str) -> bool:
    """True when a Bash command runs a test suite, not merely mentions one."""
    return _TEST_INVOCATION.search(_without_heredoc_bodies(command)) is not None


def _strings(value: object) -> Iterator[str]:
    """Every raw string inside a tool input, so a marker is matched before any escaping."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def _tool_uses(events: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
    uses: list[Mapping[str, object]] = []
    for event in events:
        message = event.get("message")
        content = message.get("content") if isinstance(message, Mapping) else None
        if isinstance(content, list):
            uses += [b for b in content if isinstance(b, Mapping) and b.get("type") == "tool_use"]
    return uses


#: Longest string kept per tool-input field: enough to audit which path a
#: Read, Grep, or Glob touched, without copying whole edited files into the report.
_INPUT_CLIP = 200


def _clip(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(k): _clip(v) for k, v in value.items()}
    if isinstance(value, str) and len(value) > _INPUT_CLIP:
        return value[:_INPUT_CLIP] + "..."
    return value


def _denied_ids(denials: object) -> set[str]:
    if not isinstance(denials, list):
        return set()
    return {
        str(item["tool_use_id"])
        for item in denials
        if isinstance(item, Mapping) and item.get("tool_use_id")
    }


def trajectory(
    events: Sequence[Mapping[str, object]], withheld_markers: Sequence[str] = ()
) -> dict[str, object]:
    """Trajectory evidence of one run, kept apart from its output correctness (issue #6814).

    `bash_commands` lists every Bash command the agent issued and
    `other_tool_inputs` every other tool call's input, clipped, so a leak audit
    can see which paths a Read, Grep, or Glob touched. `test_commands` lists the
    Bash commands that ran a test suite, and `denied_test_commands` the ones the
    harness refused (matched on the denial's `tool_use_id`), so an attempted check
    is never read as an executed one. `permission_denials` counts every refused
    call (`None` when the stream reports none), and `withheld_marker_hits` lists
    each tool call whose input names a withheld marker (a hidden check path, the
    fix commit, the fix PR, the runner's checkout): a non-empty list means the
    agent may have seen withheld evidence.
    """
    uses = _tool_uses(events)
    denials: object = None
    for event in events:
        if event.get("type") == "result":
            denials = event.get("permission_denials")
    denied = _denied_ids(denials)
    bash = [
        (str(tool_input.get("command", "")), str(use.get("id", "")) in denied)
        for use in uses
        if use.get("name") == "Bash" and isinstance(tool_input := use.get("input"), Mapping)
    ]
    tests = [(c, was_denied) for c, was_denied in bash if is_test_invocation(c)]
    hits = sorted(
        {
            f"{use.get('name')}: {marker}"
            for use in uses
            for marker in withheld_markers
            if marker and any(marker in text for text in _strings(use.get("input")))
        }
    )
    return {
        "tool_calls": len(uses),
        "other_tool_inputs": [
            {"name": str(use.get("name")), "input": _clip(use.get("input"))}
            for use in uses
            if use.get("name") != "Bash"
        ],
        "bash_commands": [c for c, _ in bash],
        "test_commands": [c for c, was_denied in tests if not was_denied],
        "denied_test_commands": [c for c, was_denied in tests if was_denied],
        "permission_denials": len(denials) if isinstance(denials, list) else None,
        "withheld_marker_hits": hits,
    }
