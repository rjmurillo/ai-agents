#!/usr/bin/env python3
"""Check whether code changes in a PR have a matching QA report."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

CONFIG_ERROR = 2
EXTERNAL_ERROR = 3
CODE_EXTENSIONS = {".ps1", ".cs", ".ts", ".js", ".py", ".yml", ".yaml", ".json"}


def _append_output(name: str, value: str) -> int:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        print("::error::GITHUB_OUTPUT is required", file=sys.stderr)
        return CONFIG_ERROR
    with Path(output_path).open("a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")
    return 0


def _changed_files(repository: str, pr_number: str) -> list[str] | None:
    """PR filenames from the GitHub API, or None when the call failed.

    Issue #4068: this ran with ``check=False`` and never read the return code,
    so a `gh` failure produced empty stdout, ``_has_code_changes([])`` was
    False, and the step wrote ``has_code_changes=False`` and exited 0. A PR full
    of code then graded as "no code changes, QA report not required". Returning
    None rather than an empty list keeps "the API broke" distinguishable from
    "the PR genuinely touches nothing", which is the distinction the caller
    needs to fail loudly.
    """
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repository}/pulls/{pr_number}/files",
            "--paginate",
            "--jq",
            ".[].filename",
        ],
        check=False,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _has_code_changes(changed_files: list[str]) -> bool:
    for filename in changed_files:
        if filename.startswith(".agents/"):
            continue
        if Path(filename).suffix in CODE_EXTENSIONS:
            return True
    return False


def _find_qa_report(pr_number: str) -> Path | None:
    reports = sorted(Path(".agents/qa").glob(f"*pr-{pr_number}*.md"))
    return reports[0] if reports else None


def main(argv: list[str] | None = None) -> int:
    if argv:
        print("::error::unexpected command line arguments", file=sys.stderr)
        return CONFIG_ERROR
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    pr_number = os.environ.get("PR_NUMBER", "")
    print("Checking for QA report...")
    changed_files = _changed_files(repository, pr_number)
    if changed_files is None:
        print(
            f"::error::gh api failed for repos/{repository}/pulls/{pr_number}/files",
            file=sys.stderr,
        )
        return EXTERNAL_ERROR
    has_code_changes = _has_code_changes(changed_files)
    output_result = _append_output("has_code_changes", str(has_code_changes))
    if output_result != 0:
        return output_result
    if not has_code_changes:
        output_result = _append_output("qa_report_exists", "N/A")
        if output_result == 0:
            print("No code changes, QA report not required")
        return output_result
    qa_report = _find_qa_report(pr_number)
    if qa_report:
        output_result = _append_output("qa_report_exists", "true")
        if output_result != 0:
            return output_result
        output_result = _append_output("qa_report", qa_report.name)
        if output_result == 0:
            print(f"✓ QA report found: {qa_report.name}")
        return output_result
    output_result = _append_output("qa_report_exists", "false")
    if output_result == 0:
        print("::warning::No QA report found for code changes")
    return output_result


if __name__ == "__main__":
    raise SystemExit(main())
