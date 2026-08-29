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
        names = {ratchet.job_name for ratchet in checks_ratchet.RATCHETS}
        assert {"taste-count-ratchet", "type-ignore-count-ratchet"} <= names

    def test_registry_retains_all_eight_ratchets(self) -> None:
        assert len(checks_ratchet.RATCHETS) == 8

    def test_base_ref_contracts_stay_explicit(self) -> None:
        by_name = {ratchet.job_name: ratchet for ratchet in checks_ratchet.RATCHETS}
        assert by_name["taste-count-ratchet"].uses_base_ref is True
        assert by_name["type-ignore-count-ratchet"].uses_base_ref is True
