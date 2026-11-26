"""Which results file decides: the first run, whatever the history traversal order."""

from __future__ import annotations

import os
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

AMBIGUOUS = "so the first run is ambiguous; results files are append-only, so fix the skill"
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

    def test_a_branch_run_on_a_path_the_base_once_held_keeps_its_branch_order(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        on_main(repo, {f"{EVID}/run-1.json": "{}"}, "an old run")
        git(repo, "checkout", "-q", "main")
        git(repo, "rm", "-q", f"{EVID}/run-1.json")
        commit(repo, "drop the old run")
        git(repo, "checkout", "-q", "-B", "feature")
        driver_change(repo)
        write(repo, f"{EVID}/run-2.json", _run_text(repo, failed=True))
        commit(repo, "first run fails")
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "a passing run on the reused path")
        code, out = run(repo, capsys)
        assert code == 1
        assert "run-2.json: recomputed gate is FAIL" in out

    @pytest.mark.parametrize("main_first", [False, True])
    def test_a_branch_copy_of_a_base_run_keeps_the_base_add(
        self, repo: Path, capsys: pytest.CaptureFixture[str], main_first: bool
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-2.json", results(repo))
        commit(repo, "a passing run")
        failed = _run_text(repo, failed=True)
        git(repo, "checkout", "-q", "main")
        write(repo, f"{EVID}/run-1.json", failed)
        commit(repo, "a failed run on main")
        git(repo, "checkout", "-q", "feature")
        write(repo, f"{EVID}/run-1.json", failed)
        commit(repo, "a byte-identical copy of the base run")
        if main_first:
            git(repo, "checkout", "-q", "-b", "joined", "main")
            git(repo, "merge", "-q", "--no-ff", "-m", "merge feature", "feature")
            git(repo, "checkout", "-q", "-B", "feature", "joined")
        else:
            git(repo, "merge", "-q", "--no-ff", "-m", "merge main", "main")
        code, out = run(repo, capsys)
        assert code == 1, out
        assert "run-1.json" in out

    def test_two_later_runs_in_one_commit_do_not_hide_the_first(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "the first run passes")
        failed = _run_text(repo, failed=True)
        write(repo, f"{EVID}/run-2.json", failed)
        write(repo, f"{EVID}/run-3.json", failed)
        commit(repo, "two diagnostic runs together")
        code, out = run(repo, capsys)
        assert code == 0, out


class TestAddingCommit:
    @pytest.mark.skipif(os.name == "nt", reason="NTFS rejects * in a file name")
    def test_a_file_named_as_a_glob_does_not_borrow_a_neighbour_s_commit(self, repo: Path) -> None:
        write(repo, f"{EVID}/run-1.json", "{}")
        commit(repo, "a neighbour")
        write(repo, f"{EVID}/*.json", "{}")
        own = commit(repo, "a file named as a glob")
        assert checker.Git(repo).adding_commit("HEAD", f"{EVID}/*.json") == own

    def test_a_reused_path_reports_its_newest_add(self, repo: Path) -> None:
        write(repo, f"{EVID}/run-1.json", "{}")
        commit(repo, "old add")
        git(repo, "rm", "-q", f"{EVID}/run-1.json")
        commit(repo, "delete")
        write(repo, f"{EVID}/run-1.json", "{}")
        newest = commit(repo, "new add")
        assert checker.Git(repo).adding_commit("HEAD", f"{EVID}/run-1.json") == newest

    def test_a_path_no_commit_added_is_none(self, repo: Path) -> None:
        assert checker.Git(repo).adding_commit("HEAD", f"{EVID}/never.json") is None


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

    def tree_blobs(self, ref: str, prefix: str) -> dict[str, str]:
        return {}

    def is_ancestor(self, ancestor: str, descendant: str) -> bool | None:
        return self.ancestors.get((ancestor, descendant), False)


class TestDecidingRunUnit:
    def _ctx(self, git_stub: _FakeGit) -> SimpleNamespace:
        return SimpleNamespace(head="HEAD", base_ref="main", commits=["c0"], git=git_stub)

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
