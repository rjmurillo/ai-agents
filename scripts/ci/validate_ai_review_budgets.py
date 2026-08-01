#!/usr/bin/env python3
"""Validate workflow wall budgets for direct ai-review action steps."""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_CONFIG = 2

DEFAULT_OVERHEAD_MINUTES = 5
ATTEMPTS_PER_STEP = 3
RETRY_DELAY_MINUTES = 1.5


@dataclass(frozen=True, slots=True)
class BudgetFinding:
    workflow: Path
    job: str
    job_timeout: int
    step_timeouts: tuple[int, ...]
    required_timeout: int

    def message(self) -> str:
        steps = ", ".join(str(timeout) for timeout in self.step_timeouts)
        return (
            f"{self.workflow}:{self.job} timeout-minutes={self.job_timeout}, "
            f"required={self.required_timeout}, ai-review steps=[{steps}]"
        )


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return None


def _uses_ai_review(step: Mapping[str, object]) -> bool:
    return step.get("uses") == "./.github/actions/ai-review"


def _step_timeout(step: Mapping[str, object]) -> int | None:
    with_block = step.get("with")
    if not isinstance(with_block, Mapping):
        return None
    return _as_int(with_block.get("timeout-minutes"))


def required_job_timeout(step_timeouts: Sequence[int]) -> int:
    worst_case = sum(ATTEMPTS_PER_STEP * timeout + RETRY_DELAY_MINUTES for timeout in step_timeouts)
    return math.ceil(worst_case + DEFAULT_OVERHEAD_MINUTES)


def ai_review_step_timeouts(job: Mapping[object, object]) -> tuple[int, ...]:
    steps = job.get("steps")
    if not isinstance(steps, list):
        return ()
    return tuple(
        timeout
        for step in steps
        if isinstance(step, Mapping) and _uses_ai_review(step)
        for timeout in [_step_timeout(step)]
        if timeout is not None
    )


def budget_finding(
    path: Path, job_name: object, job: Mapping[object, object]
) -> BudgetFinding | None:
    step_timeouts = ai_review_step_timeouts(job)
    if not step_timeouts:
        return None
    required_timeout = required_job_timeout(step_timeouts)
    job_timeout = _as_int(job.get("timeout-minutes"))
    if job_timeout is None:
        return BudgetFinding(path, str(job_name), 0, step_timeouts, required_timeout)
    if job_timeout < required_timeout:
        return BudgetFinding(path, str(job_name), job_timeout, step_timeouts, required_timeout)
    return None


def inspect_workflow(path: Path) -> list[BudgetFinding]:
    try:
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"{path}: could not parse workflow YAML: {exc}") from exc
    if not isinstance(workflow, Mapping):
        return []
    jobs = workflow.get("jobs")
    if not isinstance(jobs, Mapping):
        return []

    findings: list[BudgetFinding] = []
    for job_name, job in jobs.items():
        if not isinstance(job, Mapping):
            continue
        finding = budget_finding(path, job_name, job)
        if finding is not None:
            findings.append(finding)
    return findings


def iter_workflows(root: Path) -> list[Path]:
    workflows = root / ".github" / "workflows"
    return sorted(path for path in workflows.glob("*.yml") if path.is_file())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        findings = [
            finding
            for workflow in iter_workflows(args.repo_root)
            for finding in inspect_workflow(workflow)
        ]
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    if findings:
        for finding in findings:
            print(f"::error::{finding.message()}", file=sys.stderr)
        return EXIT_REGRESSION
    print("AI review workflow budgets OK.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
