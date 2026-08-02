#!/usr/bin/env python3
"""Assert that upstream job results match their expected values.

Replaces the inline shell chain in a workflow's summary job, which read each
`needs.<job>.result` (or an output) from the environment, compared it to an
expected string, emitted a `::error::` annotation, and exited 1 on the first
mismatch. Keeping the comparison here (ADR-006: no logic in YAML) makes the
gate testable.

Every check is evaluated so a single run reports all failures, not just the
first. The exit code is 1 if any check failed.

A check is `NAME EXPECTED MESSAGE`, where NAME is an environment variable the
workflow populated from a `needs.*` expression. MESSAGE is emitted verbatim
unless it contains `{value}`, which is replaced with the observed value.

An unset variable reads as the empty string and therefore fails its check.
That is deliberate: a summary job that cannot see an upstream result must not
report success.

EXIT CODES (ADR-035):
  0  - Success: every check matched
  1  - Error: at least one check did not match
  2  - Error: usage/configuration (no checks supplied)
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping

EXIT_SUCCESS = 0
EXIT_MISMATCH = 1
EXIT_USAGE = 2


def _format(message: str, value: str) -> str:
    """Return MESSAGE with `{value}` replaced, or unchanged when absent."""
    if "{value}" not in message:
        return message
    return message.replace("{value}", value)


def failures(
    checks: list[tuple[str, str, str]], environ: Mapping[str, str]
) -> list[str]:
    """Return one formatted message per check whose value did not match."""
    return [
        _format(message, environ.get(name, ""))
        for name, expected, message in checks
        if environ.get(name, "") != expected
    ]


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the job-result gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        nargs=3,
        action="append",
        metavar=("NAME", "EXPECTED", "MESSAGE"),
        help="Environment variable, its required value, and the failure message.",
    )
    parser.add_argument(
        "--success-message",
        default="",
        help="Message to print when every check matched.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Evaluate every check. Returns an ADR-035 exit code."""
    args = build_parser().parse_args(argv)

    if not args.check:
        print("ERROR: at least one --check is required", file=sys.stderr)
        return EXIT_USAGE

    checks = [(name, expected, message) for name, expected, message in args.check]
    bad = failures(checks, os.environ)
    for message in bad:
        print(f"::error::{message}")
    if bad:
        return EXIT_MISMATCH

    if args.success_message:
        print(args.success_message)
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
