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


def _aggregate_job() -> dict | None:
    config = yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        return None
    pre_push = config.get("pre-push")
    if not isinstance(pre_push, dict):
        return None
    return next(
        (job for job in _walk_jobs(pre_push.get("jobs")) if job.get("name") == "count-ratchets"),
        None,
    )


class TestAggregateRatchetWiring:
    def test_job_invokes_the_authoritative_registry(self) -> None:
        job = _aggregate_job()
        assert job is not None
        assert str(job.get("run")) == (
            "uv run --frozen python scripts/validation/checks_ratchet.py"
        )

    def test_job_runs_for_every_push(self) -> None:
        job = _aggregate_job()
        assert job is not None
        assert job.get("glob") is None

    def test_registry_retains_taste_and_type_ignore_ratchets(self) -> None:
        by_name = {ratchet.job_name: ratchet for ratchet in checks_ratchet.RATCHETS}
        assert by_name["taste-count-ratchet"].script == (
            "scripts/ci/taste_count_ratchet.py"
        )
        assert by_name["type-ignore-count-ratchet"].script == (
            "scripts/ci/type_ignore_count_ratchet.py"
        )

    def test_registry_retains_every_consolidated_ratchet(self) -> None:
        """Floor against silent deletion, by name rather than by count.

        This was `len(RATCHETS) == 8`. A bare count also fails on an addition,
        which is not the loss it exists to catch, and it names nothing when it
        does fail. The exact registry contents, additions included, are pinned
        by `_EXPECTED_RATCHETS` in test_pre_pr_runs_lefthook_ratchets.py, so
        this one only has to hold the floor.
        """
        consolidated = {
            "python-lint-ratchet",
            "python-lint-count-ratchet",
            "taste-count-ratchet",
            "type-ignore-count-ratchet",
            "memory-index-count-ratchet",
            "cli-exit-contract-ratchet",
            "memory-index-token-ratchet",
            "merge-tree-ratchet",
        }
        registered = {ratchet.job_name for ratchet in checks_ratchet.RATCHETS}

        assert consolidated <= registered, consolidated - registered

    def test_base_ref_contracts_stay_explicit(self) -> None:
        by_name = {ratchet.job_name: ratchet for ratchet in checks_ratchet.RATCHETS}
        assert by_name["taste-count-ratchet"].uses_base_ref is True
        assert by_name["type-ignore-count-ratchet"].uses_base_ref is True


class TestAggregateBudgetIsConsistentWithLefthook:
    """The gate's own deadline must fire before lefthook kills the job (#5482).

    If lefthook's timeout were the smaller of the two, it would kill the gate
    mid-run with no attribution: the operator sees the job fail and not which
    ratchet was responsible. The gate's deadline fires first precisely so the
    failure names the offending entry.
    """

    def _count_ratchets_timeout_seconds(self) -> int:
        config = yaml.safe_load((REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
        found: list[str] = []

        def walk(node: object) -> None:
            if isinstance(node, dict):
                if node.get("name") == "count-ratchets":
                    found.append(str(node.get("timeout", "")))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(config)
        assert len(found) == 1, f"expected one count-ratchets job, found {found}"
        return int(found[0].removesuffix("s"))

    def test_lefthook_allows_more_time_than_the_aggregate_deadline(self) -> None:
        assert (
            self._count_ratchets_timeout_seconds()
            > checks_ratchet._AGGREGATE_TIMEOUT_SECONDS
        )

    def test_the_module_declares_the_lefthook_budget_it_assumes(self) -> None:
        """Keep the two numbers from drifting apart silently."""
        assert (
            checks_ratchet._LEFTHOOK_TIMEOUT_SECONDS
            == self._count_ratchets_timeout_seconds()
        )
