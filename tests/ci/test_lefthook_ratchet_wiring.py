"""Ratchet registry and aggregate pre-push wiring tests (issues #4041, #5317)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = REPO_ROOT / "lefthook.yml"
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import checks_ratchet  # noqa: E402

from scripts.ci.merge_tree_ratchet_registry import RATCHETS as SHARED_RATCHETS  # noqa: E402


def _walk_jobs(jobs: object) -> list[dict]:
    if not isinstance(jobs, list):
        return []
    found: list[dict] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        found.append(job)
        group = job.get("group")
        if isinstance(group, dict):
            found.extend(_walk_jobs(group.get("jobs")))
    return found


def _job(name: str) -> dict | None:
    config = yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        return None
    pre_push = config.get("pre-push")
    if not isinstance(pre_push, dict):
        return None
    return next(
        (job for job in _walk_jobs(pre_push.get("jobs")) if job.get("name") == name),
        None,
    )


def _aggregate_job() -> dict | None:
    return _job("count-ratchets")


class TestAggregateRatchetWiring:
    def test_job_invokes_the_authoritative_registry(self) -> None:
        """Issue #5441: the job skips the backstop, which runs as its own job."""
        job = _aggregate_job()
        assert job is not None
        assert str(job.get("run")) == (
            "uv run --frozen python scripts/validation/checks_ratchet.py --skip-merge-tree"
        )

    def test_job_runs_for_every_push(self) -> None:
        job = _aggregate_job()
        assert job is not None
        assert job.get("glob") is None

    def test_merge_tree_ratchet_job_is_wired_as_its_own_job(self) -> None:
        """Issue #5441: split from count-ratchets so both run in parallel."""
        job = _job("merge-tree-ratchet")
        assert job is not None
        run = str(job.get("run"))
        assert "scripts/ci/merge_tree_ratchet_check.py" in run
        assert "--base-ref origin/main" in run
        assert "--extra dev" in run

    def test_registry_retains_taste_and_type_ignore_ratchets(self) -> None:
        """Issue #5441: these two moved to the merge-tree-backed registry.

        ``checks_ratchet.RATCHETS`` used to run them a second time in the same
        aggregate that also fed them to the merge-tree check; they now live
        only in ``merge_tree_ratchet_registry.py``, so
        ``validate_shared_ratchets`` measures each exactly once.
        """
        labels = {ratchet.label for ratchet in SHARED_RATCHETS}
        assert "taste count ratchet" in labels
        assert "type-ignore count ratchet" in labels

    def test_registry_retains_seven_ratchets_across_both_tables(self) -> None:
        """The two standalone entries plus the five merge-tree-backed ones."""
        assert len(checks_ratchet.RATCHETS) == 2
        assert len(SHARED_RATCHETS) == 5

    def test_no_ratchet_is_registered_in_both_tables(self) -> None:
        """Issue #5441: the bug was exactly this overlap running twice."""
        local_scripts = {ratchet.script for ratchet in checks_ratchet.RATCHETS}
        shared_modules = {ratchet.counter_module.__name__ for ratchet in SHARED_RATCHETS}
        shared_scripts = {
            name.replace("scripts.ci.", "scripts/ci/") + ".py" for name in shared_modules
        }
        assert local_scripts.isdisjoint(shared_scripts)
