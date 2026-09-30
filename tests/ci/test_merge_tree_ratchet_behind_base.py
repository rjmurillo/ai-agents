"""Behind-base and shallow-fetch controls for the merge-tree ratchet (issue #4518)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ci import merge_tree_ratchet_check as _m
from tests.ci.test_merge_tree_ratchet_check import (
    _commit_all,
    _git,
    _make_repo_with_baselines,
    _run,
)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.usefixtures("_zero_non_target_aggregate_counts")
class TestMergeTreeRatchetBehindBase:
    def _behind_base_clone(self, tmp_path: Path, *, shallow: bool) -> Path:
        """A clone whose branch is behind base, with base fetched shallow or full.

        Reproduces issue #4518: the gate exists to judge branches that are behind
        their base, and a shallow base fetch made exactly that case error out.
        """
        origin = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        behind_point = _git(origin, "rev-parse", "HEAD").stdout.strip()
        (origin / "later.py").write_text("y = 2\n", encoding="utf-8")
        _commit_all(origin, "main moves ahead")

        work = tmp_path / "work"
        subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
        subprocess.run(["git", "-C", str(work), "config", "user.email", "t@e.com"], check=True)
        subprocess.run(["git", "-C", str(work), "config", "user.name", "t"], check=True)
        _git(work, "checkout", "-q", "-b", "feature", behind_point)
        (work / "feature.py").write_text("z = 3\n", encoding="utf-8")
        _commit_all(work, "feature work")

        depth = ["--depth=1"] if shallow else []
        subprocess.run(
            ["git", "-C", str(work), "fetch", "-q", *depth, "origin", "main"], check=True
        )
        return work

    def test_branch_behind_base_renders_a_verdict(self, tmp_path: Path) -> None:
        """Issue #4518: a branch behind its base must get a real verdict.

        This is the gate's target case. With the base fetched at full depth a
        merge base is reachable, so the check evaluates the merged tree instead
        of erroring out.
        """
        work = self._behind_base_clone(tmp_path, shallow=False)
        rc = _run(work, "FETCH_HEAD")
        assert rc == _m.EXIT_OK, "behind-base branch must be judged, not errored"

    def test_shallow_base_fetch_reports_the_fetch_not_a_ratchet_breach(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Issue #4518: if the shallow fetch ever returns, say so by name.

        Negative control for the test above: same repository shape, only the
        fetch depth differs. Without this pair a regression to `--depth=1` is
        indistinguishable from a real ratchet breach.
        """
        work = self._behind_base_clone(tmp_path, shallow=True)
        rc = _run(work, "FETCH_HEAD")
        assert rc == _m.EXIT_EXTERNAL
        err = capsys.readouterr().err
        assert "shallow-fetch" in err, err
        assert "#4518" in err, err

    def test_shallow_diagnostic_is_not_followed_by_a_generic_oid_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """PR #4567 review: one failure must produce exactly one explanation.

        The caller used to append "git merge-tree did not produce a tree OID"
        after the shallow-fetch diagnosis. Two messages for one failure make the
        specific one read like a guess and send the reader back to the ratchet.
        """
        work = self._behind_base_clone(tmp_path, shallow=True)
        _run(work, "FETCH_HEAD")
        err = capsys.readouterr().err
        assert "shallow-fetch" in err, err
        assert "did not produce a tree OID" not in err, err

    def test_empty_merge_tree_output_still_explains_itself(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Edge case: git succeeds but prints no OID, so nothing else explains it.

        Moving the message out of the caller must not turn this path silent.
        A bare EXIT_EXTERNAL with no stderr is the failure mode to avoid.
        """
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        empty = subprocess.CompletedProcess(args=["git"], returncode=0, stdout="", stderr="")
        with patch.object(_m, "_git", return_value=empty):
            oid, conflicts = _m._merge_tree_oid(repo, "HEAD")
        assert oid is None
        assert conflicts is False
        err = capsys.readouterr().err
        assert "no tree OID" in err, err

    def test_successful_run_prints_no_failure_diagnostic(self, tmp_path: Path) -> None:
        """Negative control: the diagnostics must not fire on a clean evaluation.

        Without this the two assertions above would pass against a build that
        never writes to stderr at all.
        """
        work = self._behind_base_clone(tmp_path, shallow=False)
        with patch.object(_m.sys.stderr, "write") as writes:
            rc = _run(work, "FETCH_HEAD")
        assert rc == _m.EXIT_OK
        assert writes.call_args_list == []
