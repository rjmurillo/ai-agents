"""Regression guard for #5097: superseded runs must not publish red aggregates.

Every workflow here uses `cancel-in-progress`, so pushing to a branch while a
run is live cancels that run and leaves its jobs reporting `cancelled`. A
result-aggregator job gated on `always()` runs anyway, reads those `cancelled`
values, and exits non-zero, so GitHub records a red check run against the PR
head for a run nobody is waiting on. The next push repeats it. Contributors
then triage CI failures that describe nothing but their own typing speed.

The fix is `!cancelled()` in place of `always()`. The vendor documents the
substitution directly (docs.github.com, expressions reference): `always()`
"Causes the step to always execute, and returns true, even when canceled",
and "If you want to run a job or step regardless of its success or failure,
use the recommended alternative: `if: ${{ !cancelled() }}`". So the guarded
job still runs when a dependency FAILED or was SKIPPED, which is what the
aggregators exist for, and skips only when the run itself is being cancelled.
A skipped job publishes no check run, so the superseded run goes quiet and the
superseding run becomes the authoritative one.

`!cancelled()` is also not a false-green risk for a required check: a skipped
job is not a success, so branch protection keeps waiting rather than merging.

Sibling: `test_quality_gate_aggregate_cancel_skip.py` pins the same guard on
`ai-pr-quality-gate.yml` and `ai-session-protocol.yml`, which were fixed for
#2347 with the equivalent `always() && !cancelled()` spelling. Those two keep
their spelling; the `always()` term there is redundant, not wrong, so only the
semantic sweep in this module covers them.

Assertions run against `yaml.safe_load` output, never against workflow text
(`.claude/rules/testing.md` MUST 9).
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

# A job that reads a dependency's outcome. `needs.<job>.result` covers the
# per-job spelling; `toJSON(needs)` covers the whole-context spelling used by
# `pytest.yml::main-failure-alert` and `installed-plugin-hook-guard.yml`.
CONSUMES_NEEDS_RESULT = re.compile(r"needs\.[A-Za-z0-9_-]+\.result|toJSON\(\s*needs\s*\)")

# Events that put a check run on a pull request head. A schedule-only or
# dispatch-only aggregate cannot produce the #5097 noise, so it is out of scope.
PR_HEAD_EVENTS = frozenset({"pull_request", "push"})

# The five jobs this change converted. Keyed workflow file to job id.
FIXED_AGGREGATORS: tuple[tuple[str, str], ...] = (
    ("pytest.yml", "test-result"),
    ("pytest.yml", "main-failure-alert"),
    ("cli-smoke.yml", "smoke-result"),
    ("installed-plugin-hook-guard.yml", "guard-result"),
    ("test-codeql-integration.yml", "aggregate-results"),
)

# The `if` each fixed job carried before this change, read verbatim from
# `git show origin/main:<workflow>` and parsed with the same loader the tests
# use, so the folded block scalars appear here exactly as GitHub would see
# them. These drive the negative controls: the checkers below must reject
# every one of them.
PRE_FIX_CONDITIONS: dict[tuple[str, str], str] = {
    ("pytest.yml", "test-result"): (
        "always() && (needs.check-paths.result != 'success' || "
        "needs.check-paths.outputs.python-changed == 'true')"
    ),
    ("pytest.yml", "main-failure-alert"): (
        "always() && github.event_name == 'push' && "
        "github.ref_name == github.event.repository.default_branch"
    ),
    ("cli-smoke.yml", "smoke-result"): "always()",
    ("installed-plugin-hook-guard.yml", "guard-result"): "always()",
    ("test-codeql-integration.yml", "aggregate-results"): "always()",
}

# Lower bound on what the repository-wide sweep must examine. Without it a
# broken classifier that matches nothing reports a clean sweep
# (`.claude/rules/testing.md` MUST 10: report the scope size, not only the
# finding count). Measured at 7 on this branch: the five above plus the two
# already guarded for #2347.
MINIMUM_AGGREGATORS_EXAMINED = 7


def _load_workflow(name: str) -> Mapping[Any, Any]:
    path = WORKFLOW_DIR / name
    assert path.is_file(), f"missing workflow file: {path}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _job(workflow_name: str, job_id: str) -> dict[str, Any]:
    jobs = _load_workflow(workflow_name).get("jobs") or {}
    assert job_id in jobs, f"{workflow_name} has no job {job_id!r}"
    return jobs[job_id]


def _strings(node: Any):
    """Yield every string reachable in a parsed YAML node."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def _triggers(workflow: Mapping[Any, Any]) -> set[str]:
    """Event names for a workflow.

    PyYAML resolves an unquoted `on:` key to the boolean True, so read both.
    """
    on = workflow.get(True, workflow.get("on")) or {}
    if isinstance(on, (dict, list)):
        return set(on)
    return {on}


# Control-only keys: `needs` lists job ids (never `.result` text, so scanning
# it cannot produce a false match) and `if` decides whether the job runs at
# all rather than consuming a result as part of its own execution. Excluding
# them keeps "does this job operationally consume a dependency result" a
# distinct question from "does its guard condition mention one", which
# `cancellation_guard_violations` already answers by reading `if` directly.
_CONTROL_ONLY_KEYS = frozenset({"if", "needs"})


def _consumes_dependency_results(job: Mapping[str, Any]) -> bool:
    """True if the job's own execution payload reads a dependency result.

    Scans every field except `if` and `needs`. A normal job carries the
    reference inside `steps` (an `env:` value or a `run:` line); a
    reusable-workflow call job (`uses: ./.github/workflows/x.yml`) has no
    `steps` at all and instead passes dependency-derived values through
    `with:`. Scanning only `steps` misses that second shape entirely, so an
    unguarded reusable-workflow aggregator would pass through the sweep
    unexamined instead of failing it.
    """
    payload = {key: value for key, value in job.items() if key not in _CONTROL_ONLY_KEYS}
    return any(CONSUMES_NEEDS_RESULT.search(text) for text in _strings(payload))


def cancellation_guard_violations(job: Mapping[str, Any]) -> list[str]:
    """Reasons this job would publish a red check for a superseded run.

    Empty list means the job is safe. Shared by the real-workflow assertions
    and by the negative controls, so a control that passes proves the same
    code path the real assertion runs.
    """
    violations: list[str] = []
    if not job.get("needs"):
        violations.append("job declares no needs, so it is not an aggregator")
    condition = job.get("if")
    if condition is None:
        violations.append("job has no `if`, so a cancelled run cannot be excluded")
        return violations
    condition = str(condition)
    if "!cancelled()" not in condition and "cancelled() == false" not in condition:
        violations.append(f"`if` does not guard on cancellation: {condition!r}")
    return violations


def bare_always_violations(job: Mapping[str, Any]) -> list[str]:
    """Reject a leftover `always()` term in a job this change converted."""
    condition = str(job.get("if") or "")
    if "always()" in condition:
        return [f"`if` still carries always(): {condition!r}"]
    return []


def unguarded_pr_head_aggregators(workflow: Mapping[Any, Any]) -> tuple[list[str], int]:
    """Return (violating job ids, number of aggregator jobs examined)."""
    if not (_triggers(workflow) & PR_HEAD_EVENTS):
        return [], 0
    violations: list[str] = []
    examined = 0
    for job_id, job in (workflow.get("jobs") or {}).items():
        if not isinstance(job, dict) or not job.get("needs"):
            continue
        if not _consumes_dependency_results(job):
            continue
        examined += 1
        if cancellation_guard_violations(job):
            violations.append(job_id)
    return violations, examined


@pytest.fixture(params=FIXED_AGGREGATORS, ids=lambda t: f"{t[0]}::{t[1]}")
def fixed_aggregator(request: pytest.FixtureRequest) -> tuple[tuple[str, str], dict[str, Any]]:
    workflow_name, job_id = request.param
    return request.param, _job(workflow_name, job_id)


class TestFixedAggregators:
    def test_aggregator_skips_a_cancelled_run(
        self, fixed_aggregator: tuple[tuple[str, str], dict[str, Any]]
    ) -> None:
        key, job = fixed_aggregator
        assert cancellation_guard_violations(job) == [], f"{key[0]}::{key[1]} is unguarded"

    def test_aggregator_drops_bare_always(
        self, fixed_aggregator: tuple[tuple[str, str], dict[str, Any]]
    ) -> None:
        key, job = fixed_aggregator
        assert bare_always_violations(job) == [], f"{key[0]}::{key[1]} kept always()"

    def test_aggregator_still_reads_dependency_results(
        self, fixed_aggregator: tuple[tuple[str, str], dict[str, Any]]
    ) -> None:
        """Guards the premise, not the fix.

        If a job stops reading `needs.<job>.result` it is no longer the
        aggregator these assertions describe, and the sweep below would stop
        examining it. Failing here is a signal to re-derive the list, not to
        delete the case.
        """
        key, job = fixed_aggregator
        assert _consumes_dependency_results(job), f"{key[0]}::{key[1]} reads no dependency result"

    def test_pre_fix_condition_is_rejected(
        self, fixed_aggregator: tuple[tuple[str, str], dict[str, Any]]
    ) -> None:
        """Negative control: the condition that shipped #5097 must fail.

        Rebuilds each job as it stood on origin/main, then runs the same
        checker the assertions above use. Without this, a checker that
        accepted everything would report a clean pass.
        """
        key, job = fixed_aggregator
        pre_fix = copy.deepcopy(job)
        pre_fix["if"] = PRE_FIX_CONDITIONS[key]

        violations = cancellation_guard_violations(pre_fix)

        assert violations, f"checker accepted the pre-fix condition for {key[0]}::{key[1]}"
        assert any("guard on cancellation" in reason for reason in violations)
        assert bare_always_violations(pre_fix)


class TestCheckerEdges:
    """Inputs the real workflows do not currently produce."""

    def test_missing_if_is_a_violation(self) -> None:
        violations = cancellation_guard_violations({"needs": ["build"], "steps": []})
        assert any("no `if`" in reason for reason in violations)

    def test_missing_needs_is_a_violation(self) -> None:
        violations = cancellation_guard_violations({"if": "${{ !cancelled() }}"})
        assert any("no needs" in reason for reason in violations)

    def test_equality_spelling_of_the_guard_is_accepted(self) -> None:
        """A cosmetic rewrite must not read as a dropped guard."""
        job = {"needs": ["build"], "if": "cancelled() == false && github.event_name == 'push'"}
        assert cancellation_guard_violations(job) == []

    def test_success_only_condition_is_a_violation(self) -> None:
        job = {"needs": ["build"], "if": "needs.build.result == 'success'"}
        violations = cancellation_guard_violations(job)
        assert any("guard on cancellation" in reason for reason in violations)

    def test_guard_combined_with_always_passes_the_semantic_check(self) -> None:
        """The #2347 spelling is redundant, not unsafe.

        `always() && !cancelled()` evaluates false during cancellation, so the
        semantic sweep must accept it while the spelling check rejects it.
        """
        job = {"needs": ["build"], "if": "always() && !cancelled()"}
        assert cancellation_guard_violations(job) == []
        assert bare_always_violations(job)


class TestRepositoryWideSweep:
    """No PR-head aggregator anywhere may convert a cancellation into red."""

    def test_every_pr_head_aggregator_is_guarded(self) -> None:
        offenders: list[str] = []
        examined = 0
        for path in sorted(WORKFLOW_DIR.glob("*.yml")):
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                continue
            violations, count = unguarded_pr_head_aggregators(document)
            examined += count
            offenders.extend(f"{path.name}::{job_id}" for job_id in violations)

        assert examined >= MINIMUM_AGGREGATORS_EXAMINED, (
            f"sweep examined only {examined} aggregator jobs, expected at least "
            f"{MINIMUM_AGGREGATORS_EXAMINED}; the classifier stopped matching rather "
            "than the repository getting cleaner"
        )
        assert offenders == [], f"unguarded PR-head aggregators: {offenders}"

    def test_sweep_reports_an_unguarded_aggregator(self) -> None:
        """Negative control for the sweep itself."""
        document = {
            "on": {"pull_request": None},
            "jobs": {
                "build": {"runs-on": "ubuntu-latest", "steps": []},
                "result": {
                    "needs": ["build"],
                    "if": "always()",
                    "steps": [{"env": {"BUILD": "${{ needs.build.result }}"}, "run": "true"}],
                },
            },
        }

        violations, examined = unguarded_pr_head_aggregators(document)

        assert examined == 1
        assert violations == ["result"]

    def test_sweep_ignores_a_workflow_off_the_pr_head(self) -> None:
        """A schedule-only aggregate publishes no check run on a PR."""
        document = {
            "on": {"schedule": [{"cron": "0 3 * * *"}]},
            "jobs": {
                "result": {
                    "needs": ["build"],
                    "if": "always()",
                    "steps": [{"env": {"BUILD": "${{ needs.build.result }}"}, "run": "true"}],
                },
            },
        }

        assert unguarded_pr_head_aggregators(document) == ([], 0)

    def test_sweep_catches_a_reusable_workflow_call_aggregator(self) -> None:
        """A `uses:` job has no `steps`; the payload scan must still see `with`.

        Regression for a Copilot review finding on PR #5103: the classifier
        originally scanned only `job.get("steps")`, so a reusable-workflow
        call job that passes a dependency result through `with:` (its only
        execution payload) was invisible to `_consumes_dependency_results`
        and never counted as examined, let alone flagged when unguarded.
        """
        document = {
            "on": {"pull_request": None},
            "jobs": {
                "build": {"runs-on": "ubuntu-latest", "steps": []},
                "result": {
                    "needs": ["build"],
                    "if": "always()",
                    "uses": "./.github/workflows/report-status.yml",
                    "with": {"build_status": "${{ needs.build.result }}"},
                },
            },
        }

        violations, examined = unguarded_pr_head_aggregators(document)

        assert examined == 1
        assert violations == ["result"]

    def test_sweep_reads_the_boolean_on_key(self) -> None:
        """PyYAML resolves an unquoted `on:` to True; the sweep must still see it."""
        document = {
            True: {"push": None},
            "jobs": {
                "result": {
                    "needs": ["build"],
                    "if": "always()",
                    "steps": [{"env": {"BUILD": "${{ needs.build.result }}"}, "run": "true"}],
                },
            },
        }

        assert unguarded_pr_head_aggregators(document) == (["result"], 1)


class TestConcurrencyStaysOn:
    """The fix belongs in the gate, not in disabling cancellation.

    Reverting `cancel-in-progress` would also silence #5097, at the cost of
    every superseded run burning a full runner. Pin it so that repair is not
    mistaken for this one.
    """

    @pytest.mark.parametrize(
        "workflow_name",
        sorted({workflow for workflow, _ in FIXED_AGGREGATORS}),
    )
    def test_cancel_in_progress_remains_enabled(self, workflow_name: str) -> None:
        concurrency = _load_workflow(workflow_name).get("concurrency") or {}
        setting = concurrency.get("cancel-in-progress")
        assert setting not in (None, False, "false"), (
            f"{workflow_name} no longer cancels superseded runs; the #5097 fix is "
            "in the aggregate gate, not in disabling concurrency cancellation"
        )
