#!/usr/bin/env python3
"""Run PR description validation and map its exit code for workflow outputs."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

CONFIG_ERROR = 2
FINDING_LIMIT = 300
_CRITICAL_HEADER = re.compile(r"^\[CRITICAL\]\s+(.+)")
_UNSAFE_CHARS = re.compile(r"[\x00-\x1f\x7f`]+")


def _append_output(name: str, value: str) -> int:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        print("::error::GITHUB_OUTPUT is required", file=sys.stderr)
        return CONFIG_ERROR
    with Path(output_path).open("a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")
    return 0


def _status_for_exit_code(exit_code: int) -> str:
    if exit_code == 0:
        return "PASS"
    if exit_code == 1:
        return "FAIL"
    return "ERROR"


def _clean(text: str) -> str:
    """Return one line with no control characters or backticks, capped in length.

    The value lands in GITHUB_OUTPUT (one ``name=value`` line), a markdown
    comment, and a workflow command, so a newline or backtick from a
    PR-controlled file name must not survive.
    """
    flat = " ".join(_UNSAFE_CHARS.sub(" ", text).split())
    if len(flat) <= FINDING_LIMIT:
        return flat
    return flat[: FINDING_LIMIT - 3] + "..."


def extract_first_finding(output: str) -> str:
    """Return the first CRITICAL finding of the validator output, else its first error."""
    lines = output.splitlines()
    for index, line in enumerate(lines):
        match = _CRITICAL_HEADER.match(line.strip())
        if match:
            return _clean(" ".join([match.group(1), *lines[index + 1 : index + 3]]))
    errors = [line for line in lines if line.startswith("Error:")]
    return _clean(errors[0]) if errors else ""


def main(argv: list[str] | None = None) -> int:
    if argv:
        print("::error::unexpected command line arguments", file=sys.stderr)
        return CONFIG_ERROR
    pr_number = os.environ.get("PR_NUMBER", "")
    print("Validating PR description...")
    sys.stdout.flush()
    result = subprocess.run(
        [
            "python3",
            "scripts/validation/pr_description.py",
            "--pr-number",
            pr_number,
            "--ci",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    sys.stdout.write(result.stdout)
    sys.stdout.flush()
    finding = extract_first_finding(result.stdout) if result.returncode else ""
    status = _append_output("validation_result", _status_for_exit_code(result.returncode))
    if status:
        return status
    return _append_output("validation_finding", finding)


if __name__ == "__main__":
    raise SystemExit(main())
