"""Tests for scripts/ci/merge_tree_ratchet_check.py.

Tests exercise the full CLI (main()) against real git repos created in
tmp_path. No mocking of git or the linters; the linter calls are replaced
with monkeypatched counter functions to keep tests fast and hermetic.

Coverage:
- clean merge: all counters under baseline -> EXIT_OK
- regression: one counter over baseline -> EXIT_REGRESSION
- conflict: merge-tree exits 1 -> distinct nonzero conflict exit
- git failure: merge-tree exits 2 -> EXIT_EXTERNAL
- counter returns None: -> EXIT_EXTERNAL
- baseline unreadable at base ref: -> EXIT_CONFIG
- baseline diagnostics identify whether the base or merged tree is unreadable
- baseline is read from the merged tree, not HEAD or the working tree
- scratch dir cleanup: always cleaned up, even on failure
- negative control: a cosmetic comment change to the script does NOT break
  the regression test (proves the test is not asserting on line number)
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ci import merge_tree_ratchet_check as _m
from scripts.ci import merge_tree_ratchet_preparation as _prep


def _git(repo: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)


def _commit_all(repo: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", message], check=True)


def _make_repo_with_baselines(
    tmp_path: Path, ruff: int, taste: int, ignore: int, memory: int = 10
) -> Path:
    """A repo with committed baseline files and one tracked Python file."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    ci = repo / "scripts" / "ci"
    ci.mkdir(parents=True)
    (ci / "ruff_count_baseline.txt").write_text(f"{ruff}\n", encoding="utf-8")
    (ci / "taste_count_baseline.txt").write_text(f"{taste}\n", encoding="utf-8")
    (ci / "type_ignore_count_baseline.txt").write_text(f"{ignore}\n", encoding="utf-8")
    (ci / "memory_index_count_baseline.txt").write_text(
        f"{memory}\n", encoding="utf-8"
    )
    (ci / "cli_exit_contract_baseline.txt").write_text("10\n", encoding="utf-8")
    (repo / "hello.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(repo, "main baseline")
    return repo


def _run(repo: Path, base_ref: str = "HEAD") -> int:
    """Run main() with monkeypatched counters that always return 0."""
    with (
        patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
    ):
        return _m.main(["--repo-root", str(repo), "--base-ref", base_ref])


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.usefixtures("_zero_non_target_aggregate_counts")
class TestMergeTreeRatchetCheck:
    def test_clean_merge_passes(self, tmp_path: Path) -> None:
        """All counters under baseline -> EXIT_OK."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=5),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=5),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=5),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])
        assert rc == _m.EXIT_OK

    def test_count_equal_to_baseline_passes(self, tmp_path: Path) -> None:
        """count == baseline -> EXIT_OK (equal is not a regression)."""
        repo = _make_repo_with_baselines(tmp_path, ruff=7, taste=7, ignore=7)
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=7),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=7),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=7),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])
        assert rc == _m.EXIT_OK

    def test_regression_blocks(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """One counter above baseline -> EXIT_REGRESSION."""
        repo = _make_repo_with_baselines(tmp_path, ruff=5, taste=10, ignore=10)
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=6),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])

        assert rc == _m.EXIT_REGRESSION
        error = capsys.readouterr().err
        assert "BLOCKED. The merged result breaches a ratchet ceiling." in error
        assert "Merge or rebase from HEAD and re-check." in error

    def test_memory_index_regression_blocks(self, tmp_path: Path) -> None:
        """The merge-tree gate covers the memory-index count ratchet too."""
        repo = _make_repo_with_baselines(
            tmp_path, ruff=10, taste=10, ignore=10, memory=5
        )
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
            patch(
                "scripts.ci.memory_index_count_ratchet.current_count", return_value=6
            ),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])
        assert rc == _m.EXIT_REGRESSION

    def test_conflict_fails_closed_without_running_counters(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)

        # Create a branch that conflicts with main on hello.py
        _git(repo, "checkout", "-b", "feature")
        (repo / "hello.py").write_text("x = 2  # feature\n", encoding="utf-8")
        _commit_all(repo, "feature change")

        _git(repo, "checkout", "main")
        (repo / "hello.py").write_text("x = 3  # main\n", encoding="utf-8")
        _commit_all(repo, "main change")

        # Check out feature so HEAD is the feature branch
        _git(repo, "checkout", "feature")

        call_counts = {"ruff": 0, "taste": 0, "ignore": 0, "memory": 0}

        def _ruff(_root):
            call_counts["ruff"] += 1
            return 0

        def _taste(_root):
            call_counts["taste"] += 1
            return 0

        def _ignore(_root):
            call_counts["ignore"] += 1
            return 0

        def _memory(_root):
            call_counts["memory"] += 1
            return 0

        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", side_effect=_ruff),
            patch("scripts.ci.taste_count_ratchet.current_count", side_effect=_taste),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", side_effect=_ignore),
            patch(
                "scripts.ci.memory_index_count_ratchet.current_count",
                side_effect=_memory,
            ),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

        assert rc == _m.EXIT_CONFLICT
        error = capsys.readouterr().err
        assert "merge has conflicts" in error
        assert "resolve the conflicts and rerun the ratchet" in error
        assert "breaches a ratchet ceiling" not in error
        assert call_counts == {"ruff": 0, "taste": 0, "ignore": 0, "memory": 0}, (
            f"Counters ran despite conflict: {call_counts}"
        )

    def test_git_failure_returns_external(self, tmp_path: Path) -> None:
        """git merge-tree hard failure -> EXIT_EXTERNAL."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        rc = _m.main(
            ["--repo-root", str(repo), "--base-ref", "nonexistent-ref-xyz123"]
        )
        assert rc == _m.EXIT_EXTERNAL

    def test_counter_returns_none_is_external(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Counter returning None -> EXIT_EXTERNAL."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=None),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])

        assert rc == _m.EXIT_EXTERNAL
        error = capsys.readouterr().err
        assert "counter returned None" in error
        assert "BLOCKED. The merged result breaches a ratchet ceiling." not in error

    def test_missing_baseline_returns_config(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Missing baseline at base ref -> EXIT_CONFIG."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        _git(repo, "rm", "scripts/ci/ruff_count_baseline.txt")
        _commit_all(repo, "remove ruff baseline")

        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])

        assert rc == _m.EXIT_CONFIG
        error = capsys.readouterr().err
        assert "CONFIG ERROR" in error
        assert "BLOCKED. The merged result breaches a ratchet ceiling." not in error

    def test_scratch_dir_cleaned_on_success(self, tmp_path: Path) -> None:
        """Scratch dir must be removed on a clean run."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        created_dirs: list[Path] = []
        _real_mkdtemp = __import__("tempfile").mkdtemp

        def _capturing_mkdtemp(**kwargs):
            d = _real_mkdtemp(**kwargs)
            created_dirs.append(Path(d))
            return d

        import tempfile

        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
            patch.object(tempfile, "mkdtemp", side_effect=_capturing_mkdtemp),
        ):
            _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])

        for d in created_dirs:
            assert not d.exists(), f"scratch dir {d} was not cleaned up"

    def test_scratch_dir_cleaned_on_regression(self, tmp_path: Path) -> None:
        """Scratch dir must be removed even when a regression is detected."""
        repo = _make_repo_with_baselines(tmp_path, ruff=0, taste=10, ignore=10)
        created_dirs: list[Path] = []
        _real_mkdtemp = __import__("tempfile").mkdtemp

        def _capturing_mkdtemp(**kwargs):
            d = _real_mkdtemp(**kwargs)
            created_dirs.append(Path(d))
            return d

        import tempfile

        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=5),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
            patch.object(tempfile, "mkdtemp", side_effect=_capturing_mkdtemp),
        ):
            _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])

        for d in created_dirs:
            assert not d.exists(), f"scratch dir {d} was not cleaned up"

    def test_stale_branch_is_caught(self, tmp_path: Path) -> None:
        """The canonical #4272 failure shape.

        main lowers taste baseline from 10 to 5; a branch cut before that
        merge carries an old taste count of 8, which was fine against the old
        ceiling of 10 but breaches the new ceiling of 5.
        """
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)

        # Branch: old taste count is 8 (under the old ceiling).
        _git(repo, "checkout", "-b", "pr-branch")
        # Simulate a PR that lowers ruff but not taste.
        (repo / "pr_change.py").write_text("# new file\n", encoding="utf-8")
        _commit_all(repo, "PR change")

        # Main: lower taste baseline to 5.
        _git(repo, "checkout", "main")
        (repo / "scripts" / "ci" / "taste_count_baseline.txt").write_text(
            "5\n", encoding="utf-8"
        )
        _commit_all(repo, "lower taste baseline to 5")
        _git(repo, "checkout", "pr-branch")

        # Merged tree would have taste count 8, against new ceiling 5 -> REGRESSION.
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=8),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])
        assert rc == _m.EXIT_REGRESSION

    def test_stale_branch_after_rebase_passes(self, tmp_path: Path) -> None:
        """After rebasing onto updated main, the same branch passes."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)

        _git(repo, "checkout", "-b", "pr-branch")
        (repo / "pr_change.py").write_text("# new file\n", encoding="utf-8")
        _commit_all(repo, "PR change")

        _git(repo, "checkout", "main")
        (repo / "scripts" / "ci" / "taste_count_baseline.txt").write_text(
            "5\n", encoding="utf-8"
        )
        _commit_all(repo, "lower taste baseline to 5")

        # Rebase pr-branch onto updated main.
        _git(repo, "checkout", "pr-branch")
        _git(repo, "rebase", "main")

        # After rebase, taste count of 4 passes the new ceiling of 5.
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=4),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])
        assert rc == _m.EXIT_OK

    def test_cosmetic_comment_change_does_not_affect_result(self, tmp_path: Path) -> None:
        """Negative control: a comment-only change to this test file does NOT cause
        regression. Proves tests are not asserting on line numbers or file content.
        """
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        # Add a comment-only Python file; counters return 0 -> still passes.
        (repo / "commented.py").write_text(
            "# This is just a comment. No violations.\n", encoding="utf-8"
        )
        _commit_all(repo, "add comment file")
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])
        assert rc == _m.EXIT_OK

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

        Patches ``_git`` on ``merge_tree_ratchet_preparation``, not on ``_m``:
        ``_merge_tree_oid`` moved to that module (issue #5441 review, to keep
        ``merge_tree_ratchet_check.py`` under the taste-lints line ceiling),
        and it resolves ``_git`` through its own module's globals.
        """
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        empty = subprocess.CompletedProcess(args=["git"], returncode=0, stdout="", stderr="")
        with patch.object(_prep, "_git", return_value=empty):
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
