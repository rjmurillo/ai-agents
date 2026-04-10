#!/usr/bin/env python3
"""Run a command with ADR-035 exit code handling.

Wraps any command with retry logic for transient failures and
fail-fast behavior for configuration and authentication errors.

Exit codes (ADR-035):
    0 - Success
    1 - Logic/validation error (passthrough)
    2 - Configuration error (fail-fast, passthrough)
    3 - External service error (retried, then exits 1)
    4 - Authentication error (fail-fast, exits 1)

Usage:
    python3 run_with_retry.py [--max-retries N] [--retry-delay N] -- COMMAND [ARGS...]

Examples:
    python3 .github/scripts/run_with_retry.py -- \\
        python3 .github/scripts/post_issue_comment.py --issue 42 --body "hello"

    python3 .github/scripts/run_with_retry.py --max-retries 3 --retry-delay 10 -- \\
        python3 .github/scripts/set_item_milestone.py --item-type pr --item-number 1
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

_EXIT_SUCCESS = 0
_EXIT_LOGIC = 1
_EXIT_CONFIG = 2
_EXIT_TRANSIENT = 3
_EXIT_AUTH = 4


def parse_args(argv: list[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    """Parse wrapper options and extract the command to run."""
    parser = argparse.ArgumentParser(
        description="Run a command with ADR-035 exit code retry handling.",
        usage="%(prog)s [--max-retries N] [--retry-delay N] -- COMMAND [ARGS...]",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Max retry attempts for transient failures (default: 2)",
    )
    parser.add_argument(
        "--retry-delay",
        type=int,
        default=5,
        help="Base delay seconds between retries, scaled by attempt (default: 5)",
    )

    if argv is None:
        argv = sys.argv[1:]

    try:
        sep = argv.index("--")
        wrapper_args = argv[:sep]
        command = argv[sep + 1 :]
    except ValueError:
        wrapper_args = []
        command = argv

    if not command:
        parser.error(
            "No command specified. "
            "Usage: run_with_retry.py [options] -- COMMAND [ARGS...]"
        )

    args = parser.parse_args(wrapper_args)
    return args, command


def run_with_retry(
    command: list[str],
    *,
    max_retries: int = 2,
    retry_delay: int = 5,
) -> int:
    """Execute command with ADR-035 exit code semantics.

    Returns the exit code for this process.
    """
    for attempt in range(max_retries + 1):
        result = subprocess.run(command)
        code = result.returncode

        if code == _EXIT_SUCCESS:
            return 0

        if code == _EXIT_CONFIG:
            print(
                "::error::Configuration error (ADR-035 exit 2). "
                "Check script arguments.",
                flush=True,
            )
            return _EXIT_CONFIG

        if code == _EXIT_AUTH:
            print(
                "::error::Authentication error (ADR-035 exit 4). "
                "Check token permissions.",
                flush=True,
            )
            return _EXIT_AUTH

        if code == _EXIT_TRANSIENT:
            if attempt < max_retries:
                delay = (attempt + 1) * retry_delay
                print(
                    f"::warning::Transient failure (ADR-035 exit 3). "
                    f"Retry {attempt + 1}/{max_retries} in {delay}s...",
                    flush=True,
                )
                time.sleep(delay)
                continue

            print(
                f"::error::External service error (ADR-035 exit 3) "
                f"after {max_retries + 1} attempts.",
                flush=True,
            )
            return _EXIT_TRANSIENT

        return code

    return _EXIT_TRANSIENT


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args, command = parse_args(argv)
    return run_with_retry(
        command,
        max_retries=args.max_retries,
        retry_delay=args.retry_delay,
    )


if __name__ == "__main__":
    sys.exit(main())
