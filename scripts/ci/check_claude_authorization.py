#!/usr/bin/env python3
"""Run the Claude authorization check and validate its answer.

Extracted from ``.github/workflows/claude.yml`` under ADR-006 (no logic in
workflow YAML). Issue #3536.

The shell this replaces separated two failure modes that look identical from
the outside, and that separation is the point of the step:

* The checker exited non-zero. That is a script fault, not a denial, and it
  must fail the job loudly rather than read as "not authorized".
* The checker exited zero but printed something other than ``true`` or
  ``false``. That is a silent failure (an early return, a truncated write)
  and must also fail the job rather than be coerced to a decision.

The shell ran the answer through ``tr -d '[:space:]'``, which also deleted
whitespace inside the value, so a garbled ``tr ue`` was accepted as ``true``.
The checker only ever prints ``true`` or ``false``, so trimming the ends is
enough and rejecting a garbled value is the safer reading.

The checker path is passed in from the workflow rather than hardcoded, so this
script carries no knowledge of the repository layout.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_VALID = ("true", "false")

_ARGUMENTS = (
    "event-name",
    "actor",
    "author-association",
    "comment-body",
    "review-body",
    "issue-body",
    "issue-title",
    "pr-body",
    "pr-title",
)


def _fail(*lines: str) -> int:
    for line in lines:
        print(f"::error::{line}")
    return 1


def run_check(checker: Path, values: dict[str, str]) -> tuple[int, str]:
    """Return the checker's exit code and its stdout."""
    argv: list[str] = [sys.executable, str(checker)]
    for name in _ARGUMENTS:
        argv.extend([f"--{name}", values[name]])
    sys.stdout.flush()
    completed = subprocess.run(
        argv,
        check=False,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.returncode, completed.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checker", required=True, help="Authorization check script.")
    for name in _ARGUMENTS:
        parser.add_argument(f"--{name}", default="")
    args = parser.parse_args(argv)

    checker = Path(args.checker)
    if not checker.is_file():
        return _fail(f"Authorization check script not found: {checker}")

    values = {name: getattr(args, name.replace("-", "_")) for name in _ARGUMENTS}
    exit_code, stdout = run_check(checker, values)

    if exit_code != 0:
        return _fail(
            f"Authorization check script failed with exit code {exit_code}.",
            "This indicates a script error, not an authorization denial.",
            "Review the step output above for specific error messages.",
            "Check the Actions summary 'Claude Authorization Check' section if available.",
        )

    authorized = stdout.strip()
    if authorized not in _VALID:
        return _fail(
            f"Authorization check returned unexpected value: '{authorized}'. "
            "Expected 'true' or 'false'.",
            "This may indicate the script exited without producing valid output.",
        )

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as handle:
            handle.write(f"authorized={authorized}\n")
    else:
        print(f"authorized={authorized}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
