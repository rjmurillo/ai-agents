"""Which results file decides: the first run, whatever the history traversal order."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.validation.skill_rewrite_helpers import (
    EVID,
    MOVED,
    SKILL,
    checker,
    commit,
    driver_change,
    git,
    on_main,
    repo,
    results,
    run,
    skill_md,
    write,
)

__all__ = ["repo"]

AMBIGUOUS = "so the first run is ambiguous; remove one or rerun"
FAILED = {"S1": ("PPP", "FFF")}


def _base_results(repo: Path, name: str, failed: bool = False) -> None:
    """Commit a results file for the head surface on main, then rebuild feature."""
    write(repo, SKILL, skill_md("driver", body="\n".join(MOVED)))
    text = results(repo, FAILED, verdict="FAIL") if failed else results(repo)
    git(repo, "checkout", "--", SKILL)
    on_main(repo, {f"{EVID}/{name}": text}, f"base {name}")


def _run_text(repo: Path, failed: bool) -> str:
    return results(repo, FAILED, verdict="FAIL") if failed else results(repo)


class TestInheritedRuns:
    def test_first_inherited_run_passes_and_a_later_failed_one_is_ignored(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _base_results(repo, "run-1.json")
        _base_results(repo, "run-2.json", failed=True)
        driver_change(repo)
        code, out = run(repo, capsys)
        assert code == 0, out

    def test_first_inherited_run_fails_and_a_later_pass_does_not_rescue_it(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _base_results(repo, "run-1.json", failed=True)
        _base_results(repo, "run-2.json")
        driver_change(repo)
        code, out = run(repo, capsys)
        assert code == 1
        assert "run-1.json: recomputed gate is FAIL" in out
        assert "run-2.json" not in out

    def test_a_branch_run_never_precedes_an_inherited_one(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _base_results(repo, "run-9.json", failed=True)
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "a passing run named to sort first")
        code, out = run(repo, capsys)
        assert code == 1
        assert "run-9.json: recomputed gate is FAIL" in out


class TestAmbiguousRuns:
    @pytest.mark.parametrize("order", ["ab", "ba"])
    @pytest.mark.parametrize("passing", ["a", "b"])
    def test_runs_added_on_parallel_branches_block_in_either_parent_order(
        self, repo: Path, capsys: pytest.CaptureFixture[str], order: str, passing: str
    ) -> None:
        driver_change(repo)
        for branch in "ab":
            git(repo, "checkout", "-q", "-b", branch, "feature")
            write(repo, f"{EVID}/run-{branch}.json", _run_text(repo, branch != passing))
            commit(repo, f"run {branch}")
        git(repo, "checkout", "-q", "feature")
        for branch in order:
            git(repo, "merge", "-q", "--no-ff", "-m", f"merge {branch}", branch)
        code, out = run(repo, capsys)
        assert code == 1
        assert "added on parallel branches" in out
        assert AMBIGUOUS in out
        assert "recomputed gate" not in out

    def test_runs_added_in_one_commit_block(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        write(repo, f"{EVID}/run-2.json", _run_text(repo, failed=True))
        commit(repo, "two runs together")
        code, out = run(repo, capsys)
        assert code == 1
        assert "added in the same commit" in out
        assert AMBIGUOUS in out

    def test_a_run_only_a_merge_commit_adds_still_orders_after_an_earlier_run(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "first run")
        git(repo, "checkout", "-q", "-b", "side", "main")
        write(repo, "side.txt", "side\n")
        commit(repo, "side")
        git(repo, "checkout", "-q", "feature")
        git(repo, "merge", "-q", "--no-ff", "--no-commit", "side")
        write(repo, f"{EVID}/run-2.json", _run_text(repo, failed=True))
        commit(repo, "merge side, adding a run")
        code, out = run(repo, capsys)
        assert code == 0, out


class _FakeGit:
    def __init__(self, adds: dict[str, str | None], ancestors: dict[tuple[str, str], Any]) -> None:
        self.adds, self.ancestors = adds, ancestors

    def adding_commit(self, ref: str, path: str) -> str | None:
        return self.adds[path]

    def is_ancestor(self, ancestor: str, descendant: str) -> bool | None:
        return self.ancestors.get((ancestor, descendant), False)


class TestDecidingRunUnit:
    def _ctx(self, git_stub: _FakeGit) -> SimpleNamespace:
        return SimpleNamespace(head="HEAD", commits=["c0"], git=git_stub)

    def test_a_file_with_no_adding_commit_fails_closed(self) -> None:
        ctx = self._ctx(_FakeGit({"a": "c1", "b": None}, {}))
        first, found = checker._deciding_run(ctx, ["a", "b"], {})
        assert first is None
        assert found == ["b has no adding commit in the history, so the first run is unknown"]

    def test_an_unknown_ancestor_is_not_an_ordering(self) -> None:
        ctx = self._ctx(_FakeGit({"a": "c1", "b": "c2"}, {("c1", "c2"): None}))
        first, found = checker._deciding_run(ctx, ["a", "b"], {})
        assert first is None
        assert "added on parallel branches" in found[0]

    def test_the_earlier_ancestor_decides(self) -> None:
        ctx = self._ctx(_FakeGit({"a": "c1", "b": "c2"}, {("c2", "c1"): True}))
        assert checker._deciding_run(ctx, ["a", "b"], {}) == ("b", [])

    def test_one_candidate_needs_no_history(self) -> None:
        assert checker._deciding_run(self._ctx(_FakeGit({}, {})), ["a"], {}) == ("a", [])
