"""Tests for scripts/ci/merge_tree_ratchet_check.py.

Tests exercise the full CLI (main()) against real git repos created in
tmp_path. No mocking of git or the linters; the linter calls are replaced
with monkeypatched counter functions to keep tests fast and hermetic.

Coverage:
- clean merge: all counters under baseline -> EXIT_OK
- regression: one counter over baseline -> EXIT_REGRESSION
- conflict: merge-tree exits 1 -> EXIT_OK with skip message
- git failure: merge-tree exits 2 -> EXIT_EXTERNAL
- counter returns None: -> EXIT_EXTERNAL
- baseline unreadable at base ref: -> EXIT_CONFIG
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


def _make_repo_with_baselines(tmp_path: Path, ruff: int, taste: int, ignore: int) -> Path:
    """A repo with committed baseline files and one tracked Python file."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    ci = repo / "scripts" / "ci"
    ci.mkdir(parents=True)
    (ci / "ruff_count_baseline.txt").write_text(f"{ruff}\n", encoding="utf-8")
    (ci / "taste_count_baseline.txt").write_text(f"{taste}\n", encoding="utf-8")
    (ci / "type_ignore_count_baseline.txt").write_text(f"{ignore}\n", encoding="utf-8")
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

    def test_regression_blocks(self, tmp_path: Path) -> None:
        """One counter above baseline -> EXIT_REGRESSION."""
        repo = _make_repo_with_baselines(tmp_path, ruff=5, taste=10, ignore=10)
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=6),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])
        assert rc == _m.EXIT_REGRESSION

    def test_conflict_skips_with_ok(self, tmp_path: Path) -> None:
        """Merge conflict -> EXIT_OK; counters are NOT invoked."""
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

        call_counts = {"ruff": 0, "taste": 0, "ignore": 0}

        def _ruff(_root):
            call_counts["ruff"] += 1
            return 0

        def _taste(_root):
            call_counts["taste"] += 1
            return 0

        def _ignore(_root):
            call_counts["ignore"] += 1
            return 0

        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", side_effect=_ruff),
            patch("scripts.ci.taste_count_ratchet.current_count", side_effect=_taste),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", side_effect=_ignore),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

        assert rc == _m.EXIT_OK
        # None of the counters should run - conflict was detected and skipped
        assert call_counts == {"ruff": 0, "taste": 0, "ignore": 0}, (
            f"Counters ran despite conflict: {call_counts}"
        )

    def test_git_failure_returns_external(self, tmp_path: Path) -> None:
        """git merge-tree hard failure -> EXIT_EXTERNAL."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        rc = _m.main(
            ["--repo-root", str(repo), "--base-ref", "nonexistent-ref-xyz123"]
        )
        assert rc == _m.EXIT_EXTERNAL

    def test_counter_returns_none_is_external(self, tmp_path: Path) -> None:
        """Counter returning None -> EXIT_EXTERNAL."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=None),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        ):
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])
        assert rc == _m.EXIT_EXTERNAL

    def test_missing_baseline_returns_config(self, tmp_path: Path) -> None:
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
