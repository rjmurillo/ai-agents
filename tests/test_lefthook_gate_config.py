"""Tests that lefthook gate jobs include enforcement flags (issue #4313)."""
from __future__ import annotations

from pathlib import Path

import yaml

from scripts.ci.merge_tree_ratchet_registry import RATCHETS, trigger_globs

LEFTHOOK_PATH = Path(__file__).parent.parent / "lefthook.yml"


def _iter_all_jobs(data) -> list[dict]:
    """Recursively yield all named job dicts from any lefthook structure."""
    results = []
    if isinstance(data, dict):
        if "name" in data and "run" in data:
            results.append(data)
        for key in ("jobs", "commands"):
            child = data.get(key)
            if child is not None:
                results.extend(_iter_all_jobs(child))
        for key, val in data.items():
            if key not in ("name", "run", "jobs", "commands", "glob", "skip",
                           "timeout", "parallel", "piped"):
                results.extend(_iter_all_jobs(val))
    elif isinstance(data, list):
        for item in data:
            results.extend(_iter_all_jobs(item))
    return results


class TestMemoryTierGateEnforcement:
    """Memory gate lefthook jobs must enforce, each at the tier issue #4313 chose."""

    def _find_job(self, name: str) -> dict:
        data = yaml.safe_load(LEFTHOOK_PATH.read_text(encoding="utf-8"))
        for job in _iter_all_jobs(data):
            if job.get("name") == name:
                return job
        raise AssertionError(f"Job {name!r} not found in lefthook.yml")

    def test_memory_tier_job_does_not_use_bare_ci(self) -> None:
        """--ci promotes 425 pre-existing warnings to errors and blocks every commit.

        Issue #4313 rejected that shape by name: "A ratchet fits the repo's
        existing pattern and avoids a 400-file cleanup blocking unrelated work."
        The count is enforced by memory-index-count-ratchet instead, so this
        asserts the rejected shape stays gone.
        """
        job = self._find_job("memory-tier")
        run = job.get("run", "")
        assert "--ci" not in run, (
            f"memory-tier carries --ci, which blocks every commit touching "
            f".serena/memories/** until the whole backlog is cleared: {run!r}"
        )

    def test_memory_tier_count_is_enforced_by_a_ratchet(self) -> None:
        job = self._find_job("memory-index-count-ratchet")
        run = job.get("run", "")
        assert "scripts/ci/memory_index_count_ratchet.py" in run, (
            f"memory-index-count-ratchet does not run the ratchet: {run!r}"
        )
        assert "--base-ref" in run, (
            f"memory-index-count-ratchet cannot catch a PR that raises the "
            f"baseline without --base-ref: {run!r}"
        )

    def test_merge_tree_ratchet_watches_memory_index_baseline(self) -> None:
        job = self._find_job("merge-tree-ratchet")
        glob = job.get("glob", [])
        assert "scripts/ci/memory_index_count_baseline.txt" in glob, (
            "merge-tree-ratchet does not run when the memory-index baseline changes"
        )

    def test_merge_tree_ratchet_globs_equal_registry_union(self) -> None:
        job = self._find_job("merge-tree-ratchet")
        assert set(job.get("glob", [])) == trigger_globs()

    def test_cli_exit_contract_ratchet_watches_baseline_only_changes(self) -> None:
        job = self._find_job("cli-exit-contract-ratchet")
        assert "scripts/ci/cli_exit_contract_baseline.txt" in job.get("glob", [])

    def test_every_registered_baseline_triggers_the_merge_tree(self) -> None:
        merge_globs = trigger_globs()
        assert {ratchet.baseline_path for ratchet in RATCHETS} <= merge_globs

    def test_memory_index_job_has_ci_flag(self) -> None:
        job = self._find_job("memory-index")
        run = job.get("run", "")
        assert "--ci" in run, f"memory-index is missing --ci: {run!r}"
