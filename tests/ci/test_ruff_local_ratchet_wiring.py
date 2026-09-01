"""Pre-push wiring tests for the ruff ratchets."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from scripts.ci.merge_tree_ratchet_registry import RATCHETS as SHARED_RATCHETS

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
    """Issue #5441: --skip-merge-tree hands the backstop to its own job."""
    job = _aggregate_job()
    assert job["run"] == (
        "uv run --frozen python scripts/validation/checks_ratchet.py --skip-merge-tree"
    )
    assert job.get("glob") is None


def test_registry_contains_both_ruff_ratchets() -> None:
    """The two ruff ratchets live in different registries (issue #5441).

    ``python-lint-ratchet`` (warnings, not baselined) stays in
    ``checks_ratchet.RATCHETS``. ``python-lint-count-ratchet`` moved to
    ``merge_tree_ratchet_registry.py`` alongside the other four
    merge-tree-backed counters, so ``validate_count_ratchets`` measures it
    exactly once instead of once per registry.
    """
    by_name = {ratchet.job_name: ratchet for ratchet in checks_ratchet.RATCHETS}
    assert by_name["python-lint-ratchet"].script == "scripts/ci/ruff_ratchet.py"

    shared_labels = {ratchet.label for ratchet in SHARED_RATCHETS}
    assert "ruff count ratchet" in shared_labels


def test_ruff_local_ratchet_keeps_the_dev_extra() -> None:
    by_name = {ratchet.job_name: ratchet for ratchet in checks_ratchet.RATCHETS}
    assert by_name["python-lint-ratchet"].extra_dev is True


def test_whole_tree_ruff_count_ratchet_module_matches_the_registry() -> None:
    """``ruff_count_ratchet`` is the counter module the backstop registers.

    ``uses_base_ref`` no longer applies to it: ``validate_count_ratchets``'s
    merge-tree backstop always resolves a base ref for every entry in
    ``merge_tree_ratchet_registry.py``, so there is nothing per-ratchet left
    to pin here.
    """
    ruff_entry = next(r for r in SHARED_RATCHETS if r.label == "ruff count ratchet")
    assert ruff_entry.counter_module.__name__ == "scripts.ci.ruff_count_ratchet"
