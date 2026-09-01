"""Tests that lefthook gate jobs include enforcement flags (issue #4313)."""
from __future__ import annotations

from pathlib import Path

import yaml

from scripts.ci.merge_tree_ratchet_registry import RATCHETS as MERGE_TREE_RATCHETS

LEFTHOOK_PATH = Path(__file__).parent.parent / "lefthook.yml"
MEMORY_WORKFLOW_PATH = (
    Path(__file__).parent.parent
    / ".github"
    / "workflows"
    / "memory-validation.yml"
)


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
        """Issue #5441 moved this ratchet out of checks_ratchet.RATCHETS.

        It now lives in merge_tree_ratchet_registry.py, evaluated by
        scripts/ci/merge_tree_ratchet_check.py. Every entry there gets
        base-ref enforcement through the one-directional guard in
        merge_tree_ratchet_baseline_direction.raised_baseline, unconditionally
        (issue #5441 review), so the guarantee this test protects still
        holds: it is just no longer expressed as a per-entry boolean flag.
        """
        ratchets = {ratchet.label: ratchet for ratchet in MERGE_TREE_RATCHETS}
        entry = ratchets["memory-index count ratchet"]
        assert entry.counter_module.__name__ == "scripts.ci.memory_index_count_ratchet"

    def test_count_ratchets_job_has_no_glob_filter(self) -> None:
        job = self._find_job("count-ratchets")
        assert "glob" not in job

    def test_cli_exit_contract_ratchet_watches_baseline_only_changes(self) -> None:
        """Same repoint as above: moved to the merge-tree-backed registry."""
        ratchets = {ratchet.label: ratchet for ratchet in MERGE_TREE_RATCHETS}
        entry = ratchets["cli exit contract ratchet"]
        assert entry.counter_module.__name__ == "scripts.ci.cli_exit_contract_ratchet"

    def test_memory_index_job_has_ci_flag(self) -> None:
        job = self._find_job("memory-index")
        run = job.get("run", "")
        assert "--ci" in run, f"memory-index is missing --ci: {run!r}"

    def test_memory_index_job_uses_ratchet_orphan_policy(self) -> None:
        job = self._find_job("memory-index")
        run = job.get("run", "")
        assert "--orphan-policy ratchet" in run, (
            "memory-index must leave the legacy backlog to the count ratchet: "
            f"{run!r}"
        )

    def test_memory_workflow_uses_ratchet_orphan_policy(self) -> None:
        data = yaml.safe_load(MEMORY_WORKFLOW_PATH.read_text(encoding="utf-8"))
        steps = data["jobs"]["validate-memories"]["steps"]
        run_blocks = [
            step["run"]
            for step in steps
            if isinstance(step, dict) and isinstance(step.get("run"), str)
        ]
        command = next(
            run
            for run in run_blocks
            if "scripts/validation/memory_index.py" in run
        )
        assert "--orphan-policy ratchet" in command

    def test_memory_workflow_runs_count_ratchet(self) -> None:
        data = yaml.safe_load(MEMORY_WORKFLOW_PATH.read_text(encoding="utf-8"))
        steps = data["jobs"]["validate-memories"]["steps"]
        commands = [
            step["run"]
            for step in steps
            if isinstance(step, dict) and isinstance(step.get("run"), str)
        ]

        assert any(
            "scripts/ci/memory_index_count_ratchet.py" in command
            and "--base-ref" in command
            for command in commands
        )

    def test_memory_workflow_fetches_base_history(self) -> None:
        data = yaml.safe_load(MEMORY_WORKFLOW_PATH.read_text(encoding="utf-8"))
        steps = data["jobs"]["validate-memories"]["steps"]
        checkout = next(
            step
            for step in steps
            if step.get("uses", "").startswith("actions/checkout@")
        )

        assert checkout.get("with", {}).get("fetch-depth") == 0

    def test_memory_workflow_has_manual_dispatch_base_fallback(self) -> None:
        data = yaml.safe_load(MEMORY_WORKFLOW_PATH.read_text(encoding="utf-8"))
        steps = data["jobs"]["validate-memories"]["steps"]
        ratchet = next(
            step
            for step in steps
            if "memory_index_count_ratchet.py" in step.get("run", "")
        )

        assert ratchet["env"]["BASE_BRANCH"] == (
            "${{ github.base_ref || github.event.repository.default_branch }}"
        )
        assert '--base-ref "origin/$BASE_BRANCH"' in ratchet["run"]

    def test_memory_workflow_uses_locked_markdown_parser_environment(
        self,
    ) -> None:
        data = yaml.safe_load(MEMORY_WORKFLOW_PATH.read_text(encoding="utf-8"))
        steps = data["jobs"]["validate-memories"]["steps"]
        validator_commands = [
            step["run"]
            for step in steps
            if isinstance(step, dict)
            and isinstance(step.get("run"), str)
            and step.get("id") in {"tier-validation", "index-validation"}
        ]

        assert len(validator_commands) == 2
        assert all(
            command.startswith("uv run --frozen python ")
            for command in validator_commands
        )

    def test_memory_workflow_blocks_tier_structure_errors(self) -> None:
        data = yaml.safe_load(MEMORY_WORKFLOW_PATH.read_text(encoding="utf-8"))
        steps = data["jobs"]["validate-memories"]["steps"]
        tier_validation = next(
            step for step in steps if step.get("id") == "tier-validation"
        )

        assert "continue-on-error" not in tier_validation
        assert "--ci" not in tier_validation["run"]
