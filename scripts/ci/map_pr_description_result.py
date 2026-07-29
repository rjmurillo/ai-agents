#!/usr/bin/env python3
"""Run PR description validation and map its exit code for workflow outputs."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

CONFIG_ERROR = 2


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


def main(argv: list[str] | None = None) -> int:
    if argv:
        print("::error::unexpected command line arguments", file=sys.stderr)
        return CONFIG_ERROR
    pr_number = os.environ.get("PR_NUMBER", "")
    print("Validating PR description...")
    result = subprocess.run(
        [
            "python3",
            "scripts/validation/pr_description.py",
            "--pr-number",
            pr_number,
            "--ci",
        ],
        check=False,
    )
    return _append_output("validation_result", _status_for_exit_code(result.returncode))


if __name__ == "__main__":
    raise SystemExit(main())
