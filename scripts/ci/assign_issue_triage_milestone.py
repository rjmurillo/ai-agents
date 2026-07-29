#!/usr/bin/env python3
"""Assign the AI issue triage milestone."""

from __future__ import annotations

import os
import re
import subprocess

MILESTONE_PATTERN = re.compile(r"^(?=.{1,50}$)[A-Za-z0-9](?:[A-Za-z0-9 _.-]*[A-Za-z0-9])?$")


def _run_gh(args: list[str], *, discard_stderr: bool = False) -> subprocess.CompletedProcess[str]:
    stderr = subprocess.DEVNULL if discard_stderr else subprocess.STDOUT
    return subprocess.run(
        ["gh", *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=stderr,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _milestone_titles(repository: str) -> list[str]:
    result = _run_gh(
        ["api", f"repos/{repository}/milestones", "--jq", ".[].title"],
        discard_stderr=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def assign_milestone(*, issue_number: str, milestone: str, repository: str) -> int:
    if not milestone or milestone == "null":
        print("No milestone to assign")
        return 0

    if not MILESTONE_PATTERN.fullmatch(milestone):
        print(f"WARNING: Invalid milestone format: {milestone}")
        return 0

    titles_lower = {title.lower() for title in _milestone_titles(repository)}
    if milestone.lower() not in titles_lower:
        print(f"::notice::Milestone not found: {milestone} (skipping assignment)")
        return 0

    print(f"Assigning milestone: {milestone}")
    result = _run_gh(["issue", "edit", issue_number, "--milestone", milestone])
    if result.returncode != 0:
        print(f"WARNING: Failed to assign milestone '{milestone}' to issue #{issue_number}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv:
        return 2
    return assign_milestone(
        issue_number=os.environ.get("ISSUE_NUMBER", ""),
        milestone=os.environ.get("MILESTONE", ""),
        repository=os.environ.get("GITHUB_REPOSITORY", ""),
    )


if __name__ == "__main__":
    raise SystemExit(main())
