"""Pre-push wiring tests for the ruff ratchets."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import checks_ratchet  # noqa: E402


def _aggregate_job() -> dict:
    config = yaml.safe_load((_REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    jobs: list[dict] = []

    def collect(items: object) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            jobs.append(item)
            group = item.get("group")
            if isinstance(group, dict):
                collect(group.get("jobs"))

    collect(config["pre-push"]["jobs"])
    matches = [job for job in jobs if job.get("name") == "count-ratchets"]
    assert len(matches) == 1
    return matches[0]


def test_ruff_ratchets_block_through_the_aggregate_job() -> None:
    job = _aggregate_job()
    assert job["run"] == "uv run --frozen python scripts/validation/checks_ratchet.py"
    assert job.get("glob") is None


def test_registry_contains_both_ruff_ratchets() -> None:
    by_name = {ratchet.job_name: ratchet for ratchet in checks_ratchet.RATCHETS}
    assert by_name["python-lint-ratchet"].script == "scripts/ci/ruff_ratchet.py"
    assert by_name["python-lint-count-ratchet"].script == (
        "scripts/ci/ruff_count_ratchet.py"
    )


def test_ruff_ratchets_keep_the_dev_extra() -> None:
    by_name = {ratchet.job_name: ratchet for ratchet in checks_ratchet.RATCHETS}
    assert by_name["python-lint-ratchet"].extra_dev is True
    assert by_name["python-lint-count-ratchet"].extra_dev is True


def test_whole_tree_ruff_count_ratchet_keeps_base_ref() -> None:
    by_name = {ratchet.job_name: ratchet for ratchet in checks_ratchet.RATCHETS}
    assert by_name["python-lint-count-ratchet"].uses_base_ref is True
