"""Tests that lefthook gate jobs include enforcement flags (issue #4313)."""
from __future__ import annotations

from pathlib import Path

import yaml

from scripts.ci.merge_tree_ratchet_registry import RATCHETS, trigger_globs

LEFTHOOK_PATH = Path(__file__).parent.parent / "lefthook.yml"
MEMORY_WORKFLOW_PATH = (
    Path(__file__).parent.parent
    / ".github"
    / "workflows"
    / "memory-validation.yml"
)


# Each registered ratchet's own lefthook job. Registration is what lets
# count_ratchet.run waive the baseline-above-base comparison, so these are
# exactly the jobs whose trigger paths must stay inside the merge-tree job's.
# Keyed by baseline path so the registry, not a name, decides membership.
_BACKED_RATCHET_JOBS = {
    "scripts/ci/ruff_count_baseline.txt": "python-lint-count-ratchet",
    "scripts/ci/taste_count_baseline.txt": "taste-count-ratchet",
    "scripts/ci/type_ignore_count_baseline.txt": "type-ignore-count-ratchet",
    "scripts/ci/memory_index_count_baseline.txt": "memory-index-count-ratchet",
    "scripts/ci/cli_exit_contract_baseline.txt": "cli-exit-contract-ratchet",
}


def _expand_braces(globs) -> set[str]:
    """Lefthook globs with one ``{a,b}`` group expanded into separate patterns.

    ``taste-count-ratchet`` writes ``**/*.{py,md,yml,...}`` while the registry
    lists the same extensions one per entry, so a set comparison of the raw
    strings reports a difference that does not exist. Only a single group is
    handled because only a single group is used; a second one would leave the
    pattern unexpanded and fail the comparison rather than pass it quietly.
    """
    expanded: set[str] = set()
    for pattern in [globs] if isinstance(globs, str) else globs:
        head, sep, rest = pattern.partition("{")
        body, closed, tail = rest.partition("}")
        if not sep or not closed or "{" in tail:
            expanded.add(pattern)
            continue
        expanded.update(f"{head}{choice}{tail}" for choice in body.split(","))
    return expanded


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

    def test_backed_ratchet_job_names_cover_the_registry(self) -> None:
        """The map below must answer for every registered ratchet.

        Without this, adding a ratchet to the registry and forgetting its entry
        in ``_BACKED_RATCHET_JOBS`` would leave the coverage test below silently
        blind to it, which is the same shape of hole it exists to close.
        """
        assert set(_BACKED_RATCHET_JOBS) == {
            ratchet.baseline_path for ratchet in RATCHETS
        }

    def test_every_backed_ratchet_job_is_covered_by_the_merge_tree_job(self) -> None:
        """A ratchet may not fire on a path that does not also fire its backstop.

        ``count_ratchet.run`` waives the baseline-above-base comparison for a
        registered ratchet on the grounds that ``merge_tree_ratchet_check.py``
        measures the merged result instead. The merge-tree job selects on
        ``trigger_globs()``, so that trade only holds where the ratchet's own
        lefthook glob is a subset of it. Where it is not, a change matching only
        the uncovered paths runs the ratchet, takes the waiver, and skips the
        gate the waiver was traded for: the branch passes locally and fails in
        CI, which is the opposite of what a local backstop claim promises.

        Measured on this repository before the fix: ``python-lint-count-ratchet``
        fired for ``pyproject.toml``, ``ruff.toml``, ``.ruff.toml``, ``uv.lock``,
        ``**/*.pyi`` and ``**/*.ipynb``, and the registry gave ruff only
        ``**/*.py``, so a config-only branch took the waiver with the merge-tree
        job skipped for the same reason it was eligible.
        """
        merge_globs = trigger_globs()
        uncovered: dict[str, set[str]] = {}
        for _baseline_path, job_name in sorted(_BACKED_RATCHET_JOBS.items()):
            job_globs = _expand_braces(self._find_job(job_name).get("glob", []))
            missing = job_globs - merge_globs
            if missing:
                uncovered[job_name] = missing

        assert not uncovered, (
            f"these ratchet jobs fire on paths the merge-tree job does not, so "
            f"count_ratchet's merge_tree_backed waiver would be taken with no "
            f"backstop running: "
            f"{ {job: sorted(globs) for job, globs in uncovered.items()} }. "
            f"Add the paths to merge_tree_ratchet_registry.py::RATCHETS (and "
            f"the merge-tree job's glob, which must equal that union), or set "
            f"the ratchet module's MERGE_TREE_BACKED to False."
        )

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
