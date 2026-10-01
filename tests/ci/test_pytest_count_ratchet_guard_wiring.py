"""Whole-tree count ratchets run in an unconditional pytest.yml job (issue #5636, D13).

Dual-name rollout, step 2 (``.claude/rules/ci-scripts.md`` MUST 22): the
``count-ratchet-guard`` job name is pinned as a required context, the ratchet
steps are gone from the ``test`` job, and ``test-result`` still needs the job.

Every assertion parses the YAML object graph, never the file text, so a step
deleted but still named in a comment fails (``.claude/rules/testing.md`` MUST 9).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/pytest.yml"
GUARD = "count-ratchet-guard"
GUARD_NAME = "Check whole-tree count ratchets (blocking)"
RATCHETS = (
    "scripts/ci/ruff_count_ratchet.py",
    "scripts/ci/subprocess_encoding_count_ratchet.py",
)
SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def _jobs() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _run_lines(job: dict[str, Any]) -> list[str]:
    return [step["run"] for step in job["steps"] if "run" in step]


def test_guard_job_has_no_path_gate() -> None:
    job = _jobs()[GUARD]
    assert "needs" not in job
    assert "if" not in job


def test_guard_job_name_is_new_and_unique() -> None:
    jobs = _jobs()
    names = [j.get("name", key) for key, j in jobs.items()]
    assert names.count(GUARD_NAME) == 1
    assert jobs[GUARD]["name"] == GUARD_NAME


@pytest.mark.parametrize("script", RATCHETS)
def test_guard_runs_each_ratchet_against_the_fetched_base(script: str) -> None:
    lines = [line for line in _run_lines(_jobs()[GUARD]) if script in line]
    assert len(lines) == 1
    assert "--base-ref FETCH_HEAD" in lines[0]


def test_guard_fetches_full_history_before_the_ratchets() -> None:
    job = _jobs()[GUARD]
    checkout = next(
        s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout["with"]["fetch-depth"] == 0
    runs = _run_lines(job)
    fetch = next(i for i, line in enumerate(runs) if line.startswith("git fetch origin"))
    first_ratchet = next(i for i, line in enumerate(runs) if RATCHETS[0] in line)
    assert fetch < first_ratchet
    assert "--depth" not in runs[fetch]


def test_guard_base_ref_falls_back_to_the_default_branch() -> None:
    base_ref = _jobs()[GUARD]["env"]["BASE_REF"]
    assert "github.base_ref" in base_ref
    assert "default_branch" in base_ref


def test_guard_has_no_continue_on_error() -> None:
    job = _jobs()[GUARD]
    assert "continue-on-error" not in job
    assert all("continue-on-error" not in step for step in job["steps"])


def test_guard_actions_are_pinned_to_40_hex_shas() -> None:
    uses = [
        s["uses"] for s in _jobs()[GUARD]["steps"] if "uses" in s and not s["uses"].startswith("./")
    ]
    assert uses
    assert [u for u in uses if not SHA_PIN.match(u.split()[0])] == []


def test_test_result_requires_the_guard_result() -> None:
    job = _jobs()["test-result"]
    assert GUARD in job["needs"]
    step = next(s for s in job["steps"] if "require_job_results.py" in s.get("run", ""))
    assert f"needs.{GUARD}.result" in step["env"]["COUNT_RATCHET_RESULT"]
    assert "--check COUNT_RATCHET_RESULT success" in step["run"]


def test_main_failure_alert_watches_the_guard() -> None:
    assert GUARD in _jobs()["main-failure-alert"]["needs"]


@pytest.mark.parametrize("script", RATCHETS)
def test_ratchet_steps_are_gone_from_the_test_job(script: str) -> None:
    """The guard job fully covers the ratchets, so the duplicate copy is deleted."""
    steps = [s for s in _jobs()["test"]["steps"] if script in s.get("run", "")]
    assert steps == []


@pytest.mark.parametrize("script", RATCHETS)
def test_each_ratchet_runs_in_exactly_one_job(script: str) -> None:
    owners = [
        key
        for key, job in _jobs().items()
        if any(script in run for run in _run_lines(job))
    ]
    assert owners == [GUARD]


def test_guard_name_is_a_pinned_required_context() -> None:
    assert GUARD_NAME in REQUIRED_CONTEXTS
    assert "Run Python Tests" in REQUIRED_CONTEXTS
