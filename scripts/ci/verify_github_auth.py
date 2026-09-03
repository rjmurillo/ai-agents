"""Verify GitHub CLI authentication for ai-review diagnostics."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

_workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
if _workspace not in sys.path:
    sys.path.insert(0, _workspace)

# The workflow step runs this file with bare `python3`, so the ambient
# interpreter has nothing installed. `scripts.github_core.api` and everything it
# imports are stdlib-only; keep it that way or this step dies at module load.
from scripts.github_core.api import (  # noqa: E402
    GhAuthStatus,
    classify_gh_failure_text,
)

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_command(argv: Sequence[str]) -> CommandResult:
    try:
        completed = subprocess.run(
            list(argv), check=False, capture_output=True, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError:
        return CommandResult(
            returncode=127,
            stdout="",
            stderr=f"{argv[0]}: command not found",
        )
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _report_failure(stage: str, result: CommandResult, scope_hint: str) -> int:
    """Name the condition gh actually hit, not the token.

    A nonzero `gh` exit is a quota refusal or a 5xx as often as it is a bad
    token, and "Ensure bot-pat has valid token with required scopes" sends the
    operator to rotate a working secret during a GitHub outage (issue #3139).
    Rate limits and transport failures are external (exit 3) and clear on their
    own; only a credential problem earns the scope advice.
    """
    status = classify_gh_failure_text(f"{result.stdout}\n{result.stderr}")
    if status is GhAuthStatus.INVALID_CREDENTIALS:
        print(f"::error::{stage} failed")
        print(f"::error::{scope_hint}")
        return EXIT_LOGIC

    print(f"::warning::{stage} could not complete: {status.value}")
    if status is GhAuthStatus.TRANSPORT_BLOCKED:
        # A refused session never clears on its own, so "retry shortly" would
        # send the operator to wait out a condition that has no reset. Exit 2
        # (config) rather than 3: exit 3 is the retry signal, and an earlier
        # version printed the right words while still returning it, so callers
        # kept retrying a permanent refusal (Copilot review on PR #5509).
        print(
            "::warning::This environment refuses GitHub for gh; the token is "
            "not the fault and retrying will not clear it."
        )
        return EXIT_CONFIG
    print("::warning::This is not an authentication failure. Retry shortly.")
    return EXIT_EXTERNAL


def verify_github_auth(runner: Callable[[Sequence[str]], CommandResult] = run_command) -> int:
    print("Verifying GitHub authentication...")
    auth_result = runner(["gh", "auth", "status"])
    print(auth_result.stdout, end="")
    print(auth_result.stderr, end="", file=sys.stderr)
    if auth_result.returncode != 0:
        return _report_failure(
            "GitHub CLI authentication",
            auth_result,
            "Ensure bot-pat has valid token with required scopes",
        )

    print("Testing API access...")
    api_result = runner(["gh", "api", "user", "-q", ".login"])
    print(api_result.stdout, end="")
    print(api_result.stderr, end="", file=sys.stderr)
    if api_result.returncode != 0:
        return _report_failure(
            "GitHub API access verification",
            api_result,
            "Ensure bot-pat has 'repo' scope for API access",
        )

    print("Authentication verified successfully")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        print("error: no arguments are supported", file=sys.stderr)
        return EXIT_CONFIG
    return verify_github_auth()


if __name__ == "__main__":
    raise SystemExit(main())
