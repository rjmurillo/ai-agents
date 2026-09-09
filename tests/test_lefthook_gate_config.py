"""Tests that lefthook gate jobs include enforcement flags (issue #4313)."""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.validation.checks_ratchet import RATCHETS as PRE_PUSH_RATCHETS

LEFTHOOK_PATH = Path(__file__).parent.parent / "lefthook.yml"
# Issue #5626 deleted memory-validation.yml as fully redundant. The server-side
# leg of the memory count ratchet it used to carry now lives only here, in the
# required `Validate PR` check, so these assertions follow it rather than
# retiring with the workflow.
PR_VALIDATION_WORKFLOW_PATH = (
    Path(__file__).parent.parent / ".github" / "workflows" / "pr-validation.yml"
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
            if key not in (
                "name",
                "run",
                "jobs",
                "commands",
                "glob",
                "skip",
                "timeout",
                "parallel",
                "piped",
            ):
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
        ratchets = {ratchet.job_name: ratchet for ratchet in PRE_PUSH_RATCHETS}
        entry = ratchets["memory-index-count-ratchet"]
        assert entry.script == "scripts/ci/memory_index_count_ratchet.py"
        assert entry.uses_base_ref is True

    def test_count_ratchets_job_has_no_glob_filter(self) -> None:
        job = self._find_job("count-ratchets")
        assert "glob" not in job

    def test_cli_exit_contract_ratchet_watches_baseline_only_changes(self) -> None:
        ratchets = {ratchet.job_name: ratchet for ratchet in PRE_PUSH_RATCHETS}
        assert ratchets["cli-exit-contract-ratchet"].uses_base_ref is True

    def test_memory_index_job_has_ci_flag(self) -> None:
        job = self._find_job("memory-index")
        run = job.get("run", "")
        assert "--ci" in run, f"memory-index is missing --ci: {run!r}"

    def test_memory_index_job_uses_ratchet_orphan_policy(self) -> None:
        job = self._find_job("memory-index")
        run = job.get("run", "")
        assert "--orphan-policy ratchet" in run, (
            f"memory-index must leave the legacy backlog to the count ratchet: {run!r}"
        )

    def _count_ratchet_step(self) -> dict:
        """The one server-side step that still runs the unindexed-memory ratchet."""
        data = yaml.safe_load(PR_VALIDATION_WORKFLOW_PATH.read_text(encoding="utf-8"))
        steps = data["jobs"]["validate-pr"]["steps"]
        return next(
            step
            for step in steps
            if isinstance(step, dict)
            and "memory_index_count_ratchet.py" in str(step.get("run", ""))
        )

    def test_count_ratchet_survives_in_the_required_check(self) -> None:
        """Deleting memory-validation.yml must not take the remote leg with it.

        Pre-push stops the count rising locally, but `--no-verify`, a clone with
        no hooks installed, a bot push, and a cloud agent all reach the remote
        unchecked. `Validate PR` is a required context; this step is what makes
        the ratchet reachable from it.
        """
        run = self._count_ratchet_step()["run"]
        assert "--base-ref" in run

    def test_count_ratchet_fetches_base_history_at_full_depth(self) -> None:
        """A shallow fetch grafts .git/shallow and breaks the later merge-tree pass."""
        run = self._count_ratchet_step()["run"]
        assert "git fetch origin" in run
        assert "--depth" not in run

    def test_count_ratchet_has_a_default_branch_base_fallback(self) -> None:
        """`github.base_ref` is empty off pull_request, so the fallback carries it."""
        step = self._count_ratchet_step()
        assert step["env"]["BASE_REF"] == (
            "${{ github.base_ref || github.event.repository.default_branch }}"
        )

    def test_count_ratchet_uses_the_locked_environment(self) -> None:
        """Bare python3 resolves the runner's interpreter, which has installed nothing."""
        assert "uv run --frozen python3" in self._count_ratchet_step()["run"]

    def test_tier_validation_stays_blocking_at_the_hook(self) -> None:
        """Tier structure was the workflow's only unduplicated-looking step.

        It was not: lefthook's `memory-tier` job runs the same validator on
        pre-commit with no `continue-on-error` escape, so the check the deleted
        workflow performed is still performed.
        """
        job = self._find_job("memory-tier")
        assert "scripts/validate_memory_tier.py" in job["run"]
        assert "continue-on-error" not in job
