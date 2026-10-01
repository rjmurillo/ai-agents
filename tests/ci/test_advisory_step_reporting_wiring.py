"""Each advisory workflow step and lefthook job reports through the typed helper.

Issue #5636, decision D17 item 2. The inventory rows for these constructs read
``Visible: partial`` or ``no`` because the step swallowed its own failure. Each
now hands its result to ``scripts/ci/report_advisory_result.py``, and none of
them gained a way to fail the job. Every assertion parses the YAML object graph
(``.claude/rules/testing.md`` MUST 9), so a step renamed or deleted fails here.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
HELPER = "scripts/ci/report_advisory_result.py"
# One standalone comparison, optionally wrapped in ${{ }}. Anything with a
# conjunct or disjunct does not match, so it never counts as a complement.
_COMPARISON = re.compile(r"^\s*(?:\$\{\{\s*)?([\w.-]+)\s*(==|!=)\s*'([^']*)'\s*(?:\}\})?\s*$")

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
    assert f'--outcome "${{{{ steps.{step_id}.outcome }}}}"' in run


@pytest.mark.parametrize(("workflow", "job", "name", "step_id", "validator"), STEP_MODE_ROWS)
def test_a_report_step_has_no_condition_that_could_hide_a_failure(
    workflow: str, job: str, name: str, step_id: str, validator: str
) -> None:
    steps = _steps(workflow, job)
    report = steps[_index(steps, name) + 1]

    assert "if" not in report
    assert "continue-on-error" not in report


def _helper_steps() -> list[tuple[str, str, int, list[dict[str, Any]]]]:
    rows = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_name, job in (document.get("jobs") or {}).items():
            steps = list(job.get("steps") or [])
            for at, step in enumerate(steps):
                if HELPER in str(step.get("run", "")):
                    rows.append((path.name, job_name, at, steps))
    return rows


def _always_checked_out(conditions: list[Any]) -> bool:
    """True when one checkout is unconditional or two cover both branches.

    pr-validation.yml checks out under ``X != 'true'`` and again under
    ``X == 'true'``, so exactly one of the pair runs on every path. Only a
    pair of standalone comparisons counts: a shared extra conjunct could make
    both checkouts skip.
    """
    if None in conditions:
        return True
    parsed = {m.groups() for c in conditions if (m := _COMPARISON.match(str(c)))}
    return any((lhs, "==", value) in parsed for lhs, op, value in parsed if op == "!=")


@pytest.mark.parametrize(
    ("conditions", "expected"),
    [
        ([None], True),
        (["steps.s.outputs.skip != 'true'", "steps.s.outputs.skip == 'true'"], True),
        (["steps.s.outputs.skip != 'true'"], False),
        (["steps.s.outputs.skip == 'true'"], False),
        (["steps.a.outputs.x != 'true'", "steps.b.outputs.x == 'true'"], False),
        (["${{ steps.s.outputs.skip != 'true' }}", "steps.s.outputs.skip == 'true'"], True),
        (
            [
                "steps.s.outputs.skip != 'true' && github.event_name == 'pull_request'",
                "steps.s.outputs.skip == 'true' && github.event_name == 'pull_request'",
            ],
            False,
        ),
        (["steps.s.outputs.skip != 'true'", "steps.s.outputs.skip == 'false'"], False),
    ],
)
def test_the_checkout_coverage_rule(conditions: list[Any], expected: bool) -> None:
    assert _always_checked_out(conditions) is expected


def test_the_helper_scan_finds_every_wired_row() -> None:
    """Guards the scan below against silently matching nothing."""
    assert len(_helper_steps()) >= len(STEP_MODE_ROWS) + len(RUN_MODE_ROWS)


@pytest.mark.parametrize(
    ("workflow", "job", "at", "steps"),
    _helper_steps(),
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_a_reporter_step_runs_only_after_a_checkout_that_ran(
    workflow: str, job: str, at: int, steps: list[dict[str, Any]]
) -> None:
    """Regression: a bot-skip guard on checkout left the helper path missing.

    pr-validation.yml skips its checkout for Renovate and Dependabot. An
    unguarded reporter step then failed the required Validate PR check with
    "can't open file", which blocked every bot pull request from merging.
    """
    condition = steps[at].get("if")
    checkouts = [
        step.get("if") for step in steps[:at] if "actions/checkout" in str(step.get("uses", ""))
    ]

    assert checkouts, f"{workflow}:{job} runs {HELPER} before any checkout"
    assert _always_checked_out(checkouts) or condition in checkouts, (
        f"{workflow}:{job} step {steps[at].get('name')!r} runs under {condition!r}, "
        f"but every earlier checkout is conditional: {checkouts!r}"
    )


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
    # Ruff's own crash used to fail the hook even under --exit-zero, so the
    # ruff jobs keep failing on a crash; the gc reporter always swallowed.
    assert ("--propagate-errors" in run) is job.startswith("python-")


@pytest.mark.parametrize(
    ("name", "job_seconds"),
    [
        ("worktree-gc-report", 120),
        ("python-lint-advisory", 120),
        ("python-autofix", 300),
        ("python-check", 300),
    ],
)
def test_the_reporter_timeout_stays_under_the_lefthook_job_timeout(
    name: str, job_seconds: int
) -> None:
    """MUST 19: a lefthook timeout kill cannot be absorbed, so the inner cap must be lower."""
    job = _lefthook_jobs()[name]
    run = str(job["run"]).split()
    inner = int(run[run.index("--timeout") + 1])

    assert job["timeout"] == {120: "2m", 300: "5m"}[job_seconds]
    assert inner < job_seconds


def test_the_dev_extra_stays_on_the_blocking_python_tool_jobs() -> None:
    """Regression: the two jobs below need mypy and semgrep from the dev extra."""
    jobs = _lefthook_jobs()
    for name in ("python-type-check", "security-scan"):
        if name in jobs:
            assert "--extra dev" in str(jobs[name]["run"]), name


def test_no_lefthook_job_swallows_ruff_with_exit_zero() -> None:
    for name, job in _lefthook_jobs().items():
        assert "--exit-zero" not in str(job["run"]), name
