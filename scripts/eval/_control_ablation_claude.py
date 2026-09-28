"""Claude Code invocation for the reduced-control ablation runner (REQ-043 AC-8).

Builds the shell-free argv, places an isolated profile beside the workspace,
optionally installs an operator-supplied login for the call, and reads the
stream-json result. Raises `HarnessFailureError` for a timeout-free run whose
stream is unparsable, carries no `total_cost_usd`, or resolved a different
model than requested. `eval_control_ablation.py` owns the run loop.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import stat
import subprocess
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path

import _control_ablation_tasks as ablation_tasks
from _runtime_harness import runtime_env
from _runtime_output import RuntimeOutputError, claude_result, parse_events, same_model

CLAUDE_EXECUTABLE = "claude"

Runner = Callable[..., subprocess.CompletedProcess[str]]


class HarnessFailureError(RuntimeError):
    """A live run's Claude invocation could not produce a usable record (AC-8)."""


class AuthExpiryError(HarnessFailureError):
    """The operator's login would expire during the call; the batch must stop.

    A copied login whose access token expires mid-call makes the isolated CLI
    refresh it. The refresh rotates the refresh token inside a copy that is
    then deleted, so every later copy fails with "OAuth session expired"
    (observed 2026-09-28: 20 of 30 runs). Stopping before the call keeps the
    operator's own login out of that rotation.
    """


#: Margin beyond the call timeout, so the CLI never sees a near-expiry token.
AUTH_EXPIRY_MARGIN_SECONDS = 300.0


# ---------------------------------------------------------------------------
# Claude invocation (DESIGN-041 "Run sequence (live)", step 2)
# ---------------------------------------------------------------------------


def claude_argv(model: str, prompt: str) -> list[str]:
    """Build the fixed argv DESIGN-041's run sequence specifies for step 2."""
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


@contextlib.contextmanager
def claude_auth(source: Path | None, config_dir: Path) -> Iterator[None]:
    """Copy an operator-supplied `.credentials.json` into one run's isolated profile.

    `runtime_env` points CLAUDE_CONFIG_DIR at a profile with no login, and the
    agent shim unsets ANTHROPIC_API_KEY, so a subscription CLI needs this copy
    (probed 2026-09-28, Claude Code 2.1.283: a copied `.credentials.json`
    authenticated with `apiKeySource: none`). `config_dir` is outside the
    agent's workspace (`claude_config_dir`). Same shape as
    `eval_harness_capability._install_codex_auth`: exclusive, no-follow create
    at mode 0o600, contents never logged. The copy is deleted as soon as the
    Claude call returns, before grading, so it never outlives that call.
    """
    if source is None:
        yield
        return
    config_dir.mkdir(parents=True, exist_ok=True, mode=stat.S_IRWXU)
    os.chmod(config_dir, stat.S_IRWXU)
    target = config_dir / ".credentials.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, stat.S_IRUSR | stat.S_IWUSR)
    try:
        with os.fdopen(fd, "wb") as dest, source.open("rb") as src:
            shutil.copyfileobj(src, dest)
        yield
    finally:
        target.unlink(missing_ok=True)


def require_unexpired_auth(
    source: Path, timeout: float, now: Callable[[], float] = time.time
) -> None:
    """Raise `AuthExpiryError` unless `source` stays valid past this call.

    Reads only `claudeAiOauth.expiresAt` (epoch milliseconds); never logs a
    token. An unreadable or missing expiry fails closed.
    """
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        expires_at = float(payload["claudeAiOauth"]["expiresAt"]) / 1000.0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AuthExpiryError(f"cannot read claudeAiOauth.expiresAt from {source}") from exc
    remaining = expires_at - now()
    if remaining < timeout + AUTH_EXPIRY_MARGIN_SECONDS:
        raise AuthExpiryError(
            f"login in {source} expires in {remaining:.0f}s, under the {timeout:.0f}s call "
            f"timeout plus {AUTH_EXPIRY_MARGIN_SECONDS:.0f}s; run `claude` once to refresh it"
        )


_REDACTED = "[REDACTED]"
_MIN_SECRET_LENGTH = 16


def redact_credentials(text: str, source: Path) -> str:
    """Replace every string value of `source`'s `claudeAiOauth` object in `text`.

    The agent under test can read the copied login by absolute path, so a reply
    may carry a token. Replies reach `report.json` and stdout; this is the last
    point before either. Values shorter than 16 characters (scopes, plan names)
    are not secrets and are left alone.
    """
    try:
        oauth = json.loads(source.read_text(encoding="utf-8")).get("claudeAiOauth", {})
    except (OSError, ValueError, AttributeError):
        return text
    secrets = (
        value
        for value in (oauth.values() if isinstance(oauth, dict) else ())
        if isinstance(value, str) and len(value) >= _MIN_SECRET_LENGTH
    )
    for secret in secrets:
        text = text.replace(secret, _REDACTED)
    return text


def _require_success_result(events: Sequence[Mapping[str, object]], reply: str) -> None:
    """A result event marked `is_error` is a harness failure, not a task attempt."""
    for event in events:
        if event.get("type") != "result":
            continue
        if event.get("is_error") is True or event.get("subtype") not in (None, "success"):
            raise HarnessFailureError(f"claude result is an error: {reply[:200]!r}")
        return


def claude_config_dir(workspace: Path) -> Path:
    """Place the Claude profile beside the workspace, not inside it.

    `runtime_env` roots CLAUDE_CONFIG_DIR at `<workspace>/.parity-profile`,
    which is the agent's working tree: a `git add -A` or a `cat` from the
    agent would reach the copied credential there. A sibling directory keeps
    it out of the workspace's git and outside the agent's working directory.
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
    auth_file: Path | None = None,
) -> tuple[list[dict[str, object]], str, float, float, list[str]]:
    """Run one Claude CLI turn; raise `HarnessFailureError` for an AC-8 condition."""
    if auth_file is not None:
        require_unexpired_auth(auth_file, timeout)
    argv = claude_argv(model, task.prompt)
    env = runtime_env(workspace, "claude")
    env["CLAUDE_CONFIG_DIR"] = str(claude_config_dir(workspace))
    started = time.monotonic()
    with claude_auth(auth_file, Path(env["CLAUDE_CONFIG_DIR"])):
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
    wall_seconds = time.monotonic() - started
    if result.returncode != 0:
        raise HarnessFailureError(f"claude exited {result.returncode}")
    try:
        events = parse_events(result.stdout)
    except RuntimeOutputError as exc:
        raise HarnessFailureError(str(exc)) from exc
    reply, resolved_model = claude_result(events)
    if auth_file is not None:
        reply = redact_credentials(reply, auth_file)
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
