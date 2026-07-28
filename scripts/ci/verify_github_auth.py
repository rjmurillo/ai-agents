"""Verify GitHub CLI authentication for ai-review diagnostics."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2


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


def verify_github_auth(runner: Callable[[Sequence[str]], CommandResult] = run_command) -> int:
    print("Verifying GitHub authentication...")
    auth_result = runner(["gh", "auth", "status"])
    print(auth_result.stdout, end="")
    print(auth_result.stderr, end="", file=sys.stderr)
    if auth_result.returncode != 0:
        print("::error::GitHub CLI authentication failed")
        print("::error::Ensure bot-pat has valid token with required scopes")
        return EXIT_LOGIC

    print("Testing API access...")
    api_result = runner(["gh", "api", "user", "-q", ".login"])
    print(api_result.stdout, end="")
    print(api_result.stderr, end="", file=sys.stderr)
    if api_result.returncode != 0:
        print("::error::GitHub API access verification failed")
        print("::error::Ensure bot-pat has 'repo' scope for API access")
        return EXIT_LOGIC

    print("Authentication verified successfully")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        print("error: no arguments are supported", file=sys.stderr)
        return EXIT_CONFIG
    return verify_github_auth()


if __name__ == "__main__":
    raise SystemExit(main())
