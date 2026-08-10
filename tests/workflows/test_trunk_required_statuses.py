"""Pin the Trunk Merge Queue required-status override.

`.trunk/trunk.yaml` tells Merge Queue which checks to wait on while testing a
queued pull request. Without it Trunk falls back to all 16 required contexts on
ruleset 11104075, six of which are paid AI agent reviews that re-review code
the source pull request already gated.

The load-bearing risk is drift. Trunk matches these entries against GitHub job
names as literal strings, so renaming a job silently makes the queue wait on a
check that no longer exists, and the queue hangs. That is the same class of
failure as the required-context rename that stalled `main` for five hours on
2026-08-09, and `.claude/rules/ci-scripts.md` MUST 22 is the rule it produced.
These tests fail the moment a listed name stops matching a real job.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_CONFIG = _ROOT / ".trunk" / "trunk.yaml"
_WORKFLOWS = _ROOT / ".github" / "workflows"

# Names Trunk cannot match, because GitHub expands them per run.
_TEMPLATED = re.compile(r"\$\{\{")


@pytest.fixture(scope="module")
def required_statuses() -> list[str]:
    data = yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))
    return data["merge"]["required_statuses"]


@pytest.fixture(scope="module")
def job_names() -> set[str]:
    names: set[str] = set()
    for path in _WORKFLOWS.glob("*.yml"):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:  # pragma: no cover - a broken workflow fails elsewhere
            continue
        if not isinstance(data, dict):
            continue
        for job_id, job in (data.get("jobs") or {}).items():
            if isinstance(job, dict):
                names.add(str(job.get("name", job_id)))
    return names


def test_config_declares_a_non_empty_override(required_statuses: list[str]) -> None:
    """An empty or missing list silently reverts to all 16 branch-protection
    contexts, which is the cost problem this file exists to fix."""
    assert required_statuses
    assert all(isinstance(name, str) and name for name in required_statuses)


def test_every_required_status_matches_a_real_job(
    required_statuses: list[str], job_names: set[str]
) -> None:
    """Positive: each entry resolves to a job that can actually report."""
    missing = [name for name in required_statuses if name not in job_names]
    assert not missing, f"required_statuses name no job produces: {missing}"


def test_no_required_status_is_templated(required_statuses: list[str]) -> None:
    """Negative: a name containing an expression never matches, because GitHub
    expands it per run and Trunk compares literals."""
    templated = [name for name in required_statuses if _TEMPLATED.search(name)]
    assert not templated, f"templated names can never match: {templated}"


def test_paid_ai_reviews_are_excluded(required_statuses: list[str]) -> None:
    """The reason this override exists. These gate the source pull request and
    cost AI credits; re-running them against the merge adds cost, not signal."""
    paid = {
        "Analyst Review",
        "Architect Review",
        "DevOps Review",
        "QA Review",
        "Roadmap Review",
        "Security Review",
        "Validate Spec Coverage",
    }
    overlap = paid.intersection(required_statuses)
    assert not overlap, f"paid AI reviews must not gate the queue: {sorted(overlap)}"


def test_checks_not_observed_reporting_on_a_draft_are_excluded(
    required_statuses: list[str],
) -> None:
    """Edge: requiring a check that does not report on a draft hangs the queue
    forever. These were not seen reporting on drafts 4796, 4803, or 4805, but
    every one of those runs was cancelled after another gate failed, so their
    absence is unproven rather than established. They stay excluded because
    the downside is a hung queue; re-evaluate after one clean queue run."""
    not_observed = {"Analyze (actions)", "Analyze (python)"}
    overlap = not_observed.intersection(required_statuses)
    assert not overlap, f"not observed reporting on a Trunk draft: {sorted(overlap)}"


def test_metadata_only_checks_are_excluded(required_statuses: list[str]) -> None:
    """`Validate PR` validates pull request metadata, not the merged tree, and
    Trunk's generated body can never satisfy it. Measured on draft 4805: job
    93324296243 failed at `Check QA Report Exists`, a real failure rather than
    a cancellation. The name-existence test above passed while this check was
    configured and broken, which is why this assertion is separate."""
    assert "Validate PR" not in required_statuses


def test_title_check_is_excluded(required_statuses: list[str]) -> None:
    """`Validate PR title` is exempt on trunk-merge branches by construction,
    so requiring it in the queue asserts nothing."""
    assert "Validate PR title" not in required_statuses
