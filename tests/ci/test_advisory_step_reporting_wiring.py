"""Each advisory workflow step and lefthook job reports through the typed helper.

Issue #5636, decision D17 item 2. The inventory rows for these constructs read
``Visible: partial`` or ``no`` because the step swallowed its own failure. Each
now hands its result to ``scripts/ci/report_advisory_result.py``, and none of
them gained a way to fail the job. Every assertion parses the YAML object graph
(``.claude/rules/testing.md`` MUST 9), so a step renamed or deleted fails here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
HELPER = "scripts/ci/report_advisory_result.py"

# (workflow, job, swallowed step name, step id, validator name)
STEP_MODE_ROWS = [
    (
        "ai-spec-validation.yml",
        "validate-spec",
        "\U0001f517 Requirements Traceability Check (Analyst Agent)",
        "trace",
        "spec-traceability-check",
    ),
    (
        "ai-spec-validation.yml",
        "validate-spec",
        "✅ Completeness Check (Critic Agent)",
        "completeness",
        "spec-completeness-check",
    ),
    (
        "ai-spec-validation.yml",
        "validate-spec",
        "External-signal gate (observe)",
        "external-gate",
        "spec-external-signal-gate",
    ),
    (
        "ai-spec-validation.yml",
        "validate-spec",
        "Post PR Comment",
        "post-comment",
        "spec-report-comment",
    ),
    (
        "drift-detection.yml",
        "detect-drift",
        "Emit K2 kill-criteria event",
        "emit-k2",
        "drift-k2-event",
    ),
    (
        "drift-detection.yml",
        "detect-drift",
        "Summarize kill-criteria drift telemetry",
        "summarize",
        "drift-telemetry-summary",
    ),
    (
        "drift-detection.yml",
        "detect-drift",
        "Upload kill-criteria events",
        "upload-events",
        "drift-events-upload",
    ),
    (
        "memory-health.yml",
        "health-check",
        "Run health check (Markdown)",
        "health-markdown",
        "memory-health-markdown",
    ),
    (
        "pr-validation.yml",
        "validate-pr",
        "Post PR Comment",
        "post-comment",
        "pr-validation-comment",
    ),
    (
        "post-pr-retrospective.yml",
        "retrospective",
        "Run retrospective via Claude Code",
        "retro-agent",
        "post-pr-retrospective",
    ),
]

# (workflow, job, step name, validator): the wrapper replaced a shell guard or
# sits around a command whose exit code the step used to swallow.
RUN_MODE_ROWS = [
    ("audit-hook-bypass.yml", "detect-bypass", "Report findings", "hook-bypass-report"),
    (
        "pr-maintenance.yml",
        "discover-prs",
        "Detect orphan commits on merged PR branches",
        "orphan-commit-report",
    ),
]

# (lefthook job name, validator)
LEFTHOOK_ROWS = [
    ("python-autofix", "python-autofix"),
    ("python-check", "python-check"),
    ("worktree-gc-report", "worktree-gc-report"),
    ("python-lint-advisory", "python-lint-advisory"),
]


def _steps(workflow: str, job: str) -> list[dict[str, Any]]:
    document = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    return list(document["jobs"][job]["steps"])


def _index(steps: list[dict[str, Any]], name: str) -> int:
    matches = [i for i, step in enumerate(steps) if step.get("name") == name]
    assert len(matches) == 1, f"expected one step named {name!r}, found {len(matches)}"
    return matches[0]


@pytest.mark.parametrize(("workflow", "job", "name", "step_id", "validator"), STEP_MODE_ROWS)
def test_a_swallowed_step_is_followed_by_a_report_of_its_outcome(
    workflow: str, job: str, name: str, step_id: str, validator: str
) -> None:
    steps = _steps(workflow, job)
    at = _index(steps, name)
    swallowed, report = steps[at], steps[at + 1]

    assert swallowed["id"] == step_id
    assert swallowed["continue-on-error"] is True
    run = " ".join(str(report["run"]).split())
    assert f"{HELPER} step" in run
    assert f"--validator {validator}" in run
    assert f"--outcome ${{{{ steps.{step_id}.outcome }}}}" in run


@pytest.mark.parametrize(("workflow", "job", "name", "step_id", "validator"), STEP_MODE_ROWS)
def test_a_report_step_has_no_condition_that_could_hide_a_failure(
    workflow: str, job: str, name: str, step_id: str, validator: str
) -> None:
    steps = _steps(workflow, job)
    report = steps[_index(steps, name) + 1]

    assert "if" not in report
    assert "continue-on-error" not in report


@pytest.mark.parametrize(("workflow", "job", "name", "validator"), RUN_MODE_ROWS)
def test_a_wrapped_command_runs_through_the_reporter_without_a_shell_swallow(
    workflow: str, job: str, name: str, validator: str
) -> None:
    steps = _steps(workflow, job)
    run = " ".join(str(steps[_index(steps, name)]["run"]).split())

    assert f"{HELPER} run" in run
    assert f"--validator {validator}" in run
    assert "--findings-exit 1" in run
    assert "|| true" not in run
    assert "|| :" not in run


def test_the_audit_workflow_no_longer_swallows_the_detector_exit_code() -> None:
    text = (WORKFLOWS / "audit-hook-bypass.yml").read_text(encoding="utf-8")

    assert "detect_hook_bypass.py --base-ref origin/main || true" not in text


def _lefthook_jobs() -> dict[str, dict[str, Any]]:
    document = yaml.safe_load((REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    jobs: dict[str, dict[str, Any]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "name" in node and "run" in node:
                jobs.setdefault(str(node["name"]), node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(document)
    return jobs


@pytest.mark.parametrize(("job", "validator"), LEFTHOOK_ROWS)
def test_a_lefthook_advisory_job_reports_through_the_helper(job: str, validator: str) -> None:
    run = " ".join(str(_lefthook_jobs()[job]["run"]).split())

    assert f"{HELPER} run" in run
    assert f"--validator {validator}" in run
    assert "--findings-exit 1" in run
    assert "--exit-zero" not in run
    assert "|| echo" not in run


def test_the_worktree_gc_reporter_budget_stays_under_the_job_timeout() -> None:
    """MUST 19: a lefthook timeout kill cannot be absorbed, so the inner cap must be lower."""
    job = _lefthook_jobs()["worktree-gc-report"]
    run = str(job["run"]).split()
    inner = int(run[run.index("--timeout") + 1])

    assert job["timeout"] == "2m"
    assert inner < 120


def test_no_lefthook_job_swallows_ruff_with_exit_zero() -> None:
    for name, job in _lefthook_jobs().items():
        assert "--exit-zero" not in str(job["run"]), name
