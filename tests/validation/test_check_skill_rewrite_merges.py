"""A merge cannot hide a results file: ADR-127 append-only rule at merge commits."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.validation.skill_rewrite_helpers import (
    EVID,
    checker,
    commit,
    commit_evidence,
    driver_change,
    git,
    repo,
    results,
    run,
    write,
)

__all__ = ["repo"]

FAILED = {"S1": ("PPP", "FFF")}


def _failed_run(repo: Path) -> str:
    return results(repo, FAILED, verdict="FAIL")


class TestMergeCannotHideAResult:
    def test_merge_that_drops_a_first_parent_results_file_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``--cc`` omits a path the merge takes from the other parent, here by absence."""
        driver_change(repo)
        git(repo, "checkout", "-q", "-b", "side")
        write(repo, "side.txt", "side\n")
        commit(repo, "side")
        git(repo, "checkout", "-q", "feature")
        write(repo, f"{EVID}/run-1.json", _failed_run(repo))
        commit(repo, "failed run")
        git(repo, "merge", "-q", "--no-commit", "side")
        git(repo, "rm", "-q", f"{EVID}/run-1.json")
        commit(repo, "merge side, dropping the failed run")
        write(repo, f"{EVID}/run-2.json", results(repo))
        commit(repo, "clean run")
        code, out = run(repo, capsys)
        assert code == 1
        assert "run-1.json is missing at HEAD" in out

    def test_merge_that_drops_a_second_parent_results_file_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The failed run lands on the merged-in side, so the first parent never held it."""
        driver_change(repo)
        git(repo, "checkout", "-q", "-b", "side")
        write(repo, f"{EVID}/run-1.json", _failed_run(repo))
        commit(repo, "failed run on the side")
        git(repo, "checkout", "-q", "feature")
        write(repo, "feature.txt", "feature\n")
        commit(repo, "feature")
        git(repo, "merge", "-q", "--no-commit", "side")
        git(repo, "rm", "-q", "-f", f"{EVID}/run-1.json")
        commit(repo, "merge side, dropping its failed run")
        write(repo, f"{EVID}/run-2.json", results(repo))
        commit(repo, "clean run")
        code, out = run(repo, capsys)
        assert code == 1
        assert "run-1.json is missing at HEAD" in out

    def test_merge_carrying_the_other_parents_edit_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", _failed_run(repo))
        commit(repo, "failed run")
        git(repo, "checkout", "-q", "-b", "side")
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "side overwrites the run")
        git(repo, "checkout", "-q", "feature")
        write(repo, "feature.txt", "feature\n")
        commit(repo, "feature")
        git(repo, "merge", "-q", "--no-ff", "-m", "merge side", "side")
        code, out = run(repo, capsys)
        assert code == 1
        assert "run-1.json is edited or deleted in" in out

    def test_results_inherited_from_the_other_parent_are_not_a_second_add(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        git(repo, "checkout", "-q", "-b", "side")
        commit_evidence(repo, "side evidence")
        git(repo, "checkout", "-q", "feature")
        write(repo, "feature.txt", "feature\n")
        commit(repo, "feature")
        git(repo, "merge", "-q", "--no-ff", "-m", "merge side", "side")
        code, out = run(repo, capsys)
        assert code == 0, out

    def test_merge_may_drop_the_retired_file(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        git(repo, "checkout", "-q", "-b", "side")
        write(repo, "side.txt", "side\n")
        commit(repo, "side")
        git(repo, "checkout", "-q", "feature")
        write(repo, f"{EVID}/retired.json", json.dumps({"retired": []}))
        commit(repo, "retired")
        git(repo, "merge", "-q", "--no-commit", "side")
        git(repo, "rm", "-q", f"{EVID}/retired.json")
        commit(repo, "merge side, dropping retired.json")
        commit_evidence(repo)
        code, out = run(repo, capsys)
        assert code == 0, out


class _FakeGit:
    """Maps (ref, prefix) to the blobs ``tree_blobs`` would list."""

    def __init__(self, blobs: dict[tuple[str, str], dict[str, str]]) -> None:
        self.blobs = blobs

    def tree_blobs(self, ref: str, prefix: str) -> dict[str, str]:
        return self.blobs[(ref, prefix)]


class TestHeadBlobFindings:
    """The comparison alone: a path that reaches head with another blob, or none."""

    PATH = f"{EVID}/run-1.json"

    def _ctx(self, at_head: dict[str, str]) -> SimpleNamespace:
        blobs = {("HEAD", f"{EVID}/"): at_head, ("c1", self.PATH): {self.PATH: "aaa"}}
        return SimpleNamespace(head="HEAD", commits=["c0", "c1"], git=_FakeGit(blobs))

    def _findings(self, at_head: dict[str, str], flagged: set[str] | None = None) -> list[str]:
        ctx = self._ctx(at_head)
        return checker._head_blob_findings(ctx, f"{EVID}/", {self.PATH: 1}, flagged or set())

    def test_same_blob_is_clean(self) -> None:
        assert self._findings({self.PATH: "aaa"}) == []

    def test_other_blob_at_head_is_a_finding(self) -> None:
        (found,) = self._findings({self.PATH: "bbb"})
        assert f"{self.PATH} differs at HEAD from its first-added version" in found

    def test_missing_at_head_is_a_finding(self) -> None:
        (found,) = self._findings({})
        assert f"{self.PATH} is missing at HEAD" in found

    def test_a_path_already_flagged_is_not_repeated(self) -> None:
        assert self._findings({}, flagged={self.PATH}) == []
