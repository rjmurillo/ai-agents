"""Process launch and run settings for the live durable-outcome drivers (issue #5768).

Split out of `_durable_live.py` so that module stays under the taste line limit.
`_durable_live.py` re-exports every name here, so callers keep importing from it.
Holds the allowlisted `claude` argv and environment, the shell-free process
launcher, and `RunSettings`. No grading and no record assembly live here.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _cli_transport import BASE_ENV_ALLOWLIST, minimal_process_env
from _durable_review import ReviewerSpec

ALLOWED_TOOLS = ("Read", "Edit", "Write", "Glob", "Grep", "Bash(python:*)", "Bash(python3:*)")
DEFAULT_TIMEOUT_SECONDS = 600.0
DEFAULT_MAX_TURNS = 25
DEFAULT_MAX_BUDGET_USD = 0.75
_BLOCKED_BILLING_ENV = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_FOUNDRY",
        "CLAUDE_CODE_USE_VERTEX",
    }
)

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


HARNESSES = ("claude", "codex")


@dataclass(frozen=True, slots=True)
class RunSettings:
    """Run parameters. `max_turns` and `max_budget_usd` bind claude only.

    `cli_version` is the `codex --version` text, recorded for the codex harness.
    `reviewer` turns the independent reviewer arm on; `None` leaves it off and the
    record's `review_findings` is `None`.
    """

    model: str
    effort: str
    max_turns: int = DEFAULT_MAX_TURNS
    retry_budget: int = 1
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    max_budget_usd: float = DEFAULT_MAX_BUDGET_USD
    harness: str = "claude"
    cli_version: str = ""
    reviewer: ReviewerSpec | None = None


def claude_argv(
    settings: RunSettings,
    control_file: Path,
    prompt: str,
    tools: Sequence[str] = ALLOWED_TOOLS,
    *,
    restrict_tools: bool = False,
) -> list[str]:
    """Shell-free argv for one run. Tools are an explicit allowlist.

    `--allowedTools` only pre-approves permission prompts. It does not remove a
    tool, so with `--permission-mode acceptEdits` Edit and Write stay usable.
    `restrict_tools` adds `--tools`, which limits which built-in tools exist.
    The reviewer arm sets it so the reviewer has no edit or shell tool.
    """
    argv = [
        "claude",
        "-p",
        prompt,
        "--model",
        settings.model,
        "--effort",
        settings.effort,
        "--max-turns",
        str(settings.max_turns),
        "--max-budget-usd",
        str(settings.max_budget_usd),
        "--permission-mode",
        "acceptEdits",
        "--allowedTools",
        *tools,
        "--setting-sources",
        "",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--append-system-prompt-file",
        str(control_file),
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    if restrict_tools:
        argv += ["--tools", ",".join(tools)]
    return argv


def claude_env() -> dict[str, str]:
    """Allowlisted environment. Billing variables are removed so the stored login bills."""
    env: dict[str, str] = minimal_process_env(
        allow=BASE_ENV_ALLOWLIST,
        blocked=_BLOCKED_BILLING_ENV,
        overrides={"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1"},
    )
    return env


def run_process(
    argv: Sequence[str],
    workdir: Path,
    env: Mapping[str, str],
    *,
    runner: Runner = subprocess.run,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[int | None, str, str, str]:
    """Launch one process. Returns (exit code or None, stdout, stderr, failure detail)."""
    try:
        done: Any = runner(
            list(argv),
            cwd=workdir,
            env=dict(env),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return None, "", "", f"{argv[0]} is not on PATH"
    except subprocess.TimeoutExpired:
        return None, "", "", f"timed out after {timeout}s"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "", "", f"process did not complete: {type(exc).__name__}"
    code = int(done.returncode)
    detail = "" if code == 0 else f"exit code {code}"
    return code, str(done.stdout or ""), str(done.stderr or ""), detail


def run_claude(
    argv: Sequence[str],
    workdir: Path,
    *,
    runner: Runner = subprocess.run,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[int | None, str, str]:
    """Launch one claude process. Returns (exit code or None, stdout, failure detail)."""
    env = claude_env()
    code, stdout, _, detail = run_process(argv, workdir, env, runner=runner, timeout=timeout)
    return code, stdout, detail
