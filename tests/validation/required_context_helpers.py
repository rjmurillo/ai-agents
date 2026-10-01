"""Shared fixtures for the required-context lint tests.

Two test modules exercise the same workflow-building helpers. They live here so
the duplicate-test-helper gate has one definition to point at.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from check_required_context_conditions import Finding, lint, load_workflows

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


def lint_one(tmp_path: Path, body: str, contexts: tuple[str, ...] = (CONTEXT,)):
    """Write one workflow, load it, and lint it against ``contexts``."""
    workflows = tmp_path / "workflows"
    write_workflow(workflows, "wf.yml", body)
    return lint(load_workflows(workflows), contexts)


def kinds(findings: list[Finding]) -> list[str]:
    return [finding.kind for finding in findings]
