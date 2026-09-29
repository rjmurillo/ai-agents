"""Shared fixtures for the required-context lint tests.

Two test modules exercise the same workflow-building helpers. They live here so
the duplicate-test-helper gate has one definition to point at.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

CONTEXT = "Run Python Tests"

# One step whose `if:` reads the actor, the smallest input that yields a finding.
FLAGGED_STEP = "      - name: g\n        if: github.actor == 'a'\n        run: echo 1\n"


def write_workflow(directory: Path, name: str, body: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(textwrap.dedent(body), encoding="utf-8")


def job_body(condition: str = "", steps: str = "      - run: echo ok\n") -> str:
    header = f"    if: {condition}\n" if condition else ""
    return (
        "on: pull_request\njobs:\n  gate:\n    name: Run Python Tests\n"
        f"{header}    runs-on: ubuntu-latest\n    steps:\n{steps}"
    )
