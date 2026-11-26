"""Branch history rules of the ADR-127 evidence check: append-only results and the runner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.validation.skill_rewrite_helpers import (
    EVID,
    SCEN,
    SKILL,
    checker,
    commit,
    commit_evidence,
    driver_change,
    git,
    repo,
    results,
    run,
    run_gated,
    scenario_doc,
    skill_md,
    write,
)

__all__ = ["repo"]


class TestAppendOnly:
    def test_editing_a_results_file_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo, {"S1": ("PPP", "FFF")}, verdict="FAIL"))
        commit(repo, "failed run")
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "overwrite")
        code, out = run(repo, capsys)
        assert code == 1
        assert "run-1.json is edited or deleted in" in out

    def test_deleting_a_results_file_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo, {"S1": ("PPP", "FFF")}, verdict="FAIL"))
        commit(repo, "failed run")
        git(repo, "rm", "-q", f"{EVID}/run-1.json")
        write(repo, f"{EVID}/run-2.json", results(repo))
        commit(repo, "swap")
        code, out = run(repo, capsys)
        assert code == 1
        assert "run-1.json is edited or deleted in" in out

    def test_retired_file_may_change(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/retired.json", json.dumps({"retired": []}))
        commit(repo, "retired")
        write(repo, f"{EVID}/retired.json", json.dumps({"retired": [], "note": "x"}))
        commit_evidence(repo)
        code, out = run(repo, capsys)
        assert code == 0, out

    def test_merge_resolution_edit_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Only the merge commit edits run-1.json, so only merge handling can name it."""
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo, {"S1": ("PPP", "FFF")}, verdict="FAIL"))
        commit(repo, "failed run")
        git(repo, "checkout", "-q", "-b", "side")
        write(repo, "side.txt", "side\n")
        commit(repo, "side work")
        git(repo, "checkout", "-q", "feature")
        write(repo, "feature.txt", "feature\n")
        commit(repo, "feature work")
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "-c",
                "commit.gpgsign=false",
                "merge",
                "-q",
                "--no-commit",
                "side",
            ],
            capture_output=True,
            check=False,
            timeout=60,
        )
        write(repo, f"{EVID}/run-1.json", results(repo))
        merge = commit(repo, "merge side, rewriting the failed run")
        assert len(git(repo, "rev-list", "--parents", "-n1", "HEAD").split()) == 3
        code, out = run(repo, capsys)
        assert code == 1
        assert f"run-1.json is edited or deleted in {merge[:10]}" in out

    def test_results_added_by_a_merge_commit_counts_as_added(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        git(repo, "checkout", "-q", "-b", "side")
        write(repo, "side.txt", "side\n")
        commit(repo, "side")
        git(repo, "checkout", "-q", "feature")
        write(repo, "feature.txt", "feature\n")
        commit(repo, "feature")
        git(repo, "-c", "commit.gpgsign=false", "merge", "-q", "--no-commit", "side")
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "merge side with evidence")
        code, out = run(repo, capsys)
        assert code == 0, out

    def test_runner_edit_in_a_gated_branch_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, "scripts/eval/eval-prompt-change.py", "# lenient\n")
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence and runner")
        code, out = run(repo, capsys)
        assert code == 1
        assert "a gated change may not also change ['scripts/eval/eval-prompt-change.py']" in out

    def test_runner_edit_alone_is_not_gated(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, "scripts/eval/eval-prompt-change.py", "# change\n")
        commit(repo, "runner")
        assert run(repo, capsys)[0] == 0

    def test_label_flip_blocks(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        doc = json.loads(scenario_doc())
        doc["scenarios"][0]["expected_verdict"] = "STOP"
        write(repo, SCEN, json.dumps(doc))
        commit(repo, "scenario commit")
        code, out = run_gated(repo, capsys)
        assert code == 1
        assert "scenario S1 changes expected_verdict from 'GO' to 'STOP'" in out

    def test_label_case_only_edit_is_not_a_flip(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        doc = json.loads(scenario_doc())
        doc["scenarios"][0]["expected_verdict"] = "go "
        write(repo, SCEN, json.dumps(doc))
        commit(repo, "scenario commit")
        code, out = run_gated(repo, capsys)
        assert code == 0, out
        assert "changes expected_verdict" not in out

    def test_head_ref_reads_the_named_commit(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        tip = commit(repo, "evidence")
        write(repo, SKILL, skill_md("driver", body="after the run"))
        commit(repo, "late edit")
        code = checker.main(["--repo-root", str(repo), "--base-ref", "main", "--head-ref", tip])
        assert code == 0, capsys.readouterr().out
        assert run(repo, capsys)[0] == 1
