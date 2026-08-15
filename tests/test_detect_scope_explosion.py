"""Tests for detect_scope_explosion module.

Verifies scope explosion detection used in pre-commit hook.
Related: Issue #944, PR #908 (95 files)
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from scripts.detect_scope_explosion import (
    BLOCK_THRESHOLD,
    STRONG_WARN_THRESHOLD,
    TRUNK_BRANCHES,
    WARN_THRESHOLD,
    ScopeDetectionError,
    ScopeResult,
    detect_scope,
    format_bar,
    get_current_branch,
    get_head_files_against_ref,
    get_index_files_against_ref,
    get_merge_base,
    get_merge_head_commit,
    get_ref_commit,
    is_ancestor,
    main,
    report,
    rescope_against_pr_base,
    resolve_base_ref,
)

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture


def _git(repo: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    return subprocess.run(
        ["git", "-C", str(repo), *argv],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _check_git(repo: Path, *argv: str) -> str:
    result = _git(repo, *argv)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _commit_all(repo: Path, message: str) -> str:
    _check_git(repo, "add", "-A")
    _check_git(repo, "commit", "-qm", message)
    return _check_git(repo, "rev-parse", "HEAD")


def _write_file(repo: Path, relative_path: str, content: str) -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _init_scope_repo(repo: Path) -> tuple[str, str]:
    repo.mkdir(parents=True)
    _check_git(repo, "init", "-q", "-b", "main")
    _check_git(repo, "config", "user.email", "tests@example.com")
    _check_git(repo, "config", "user.name", "Tests")
    _write_file(repo, "base.txt", "base\n")
    base = _commit_all(repo, "base")
    _check_git(repo, "update-ref", "refs/remotes/origin/main", base)
    return base, base


def _make_merge_scope_repo(repo: Path) -> tuple[str, str]:
    _init_scope_repo(repo)
    _check_git(repo, "checkout", "-qb", "feature")
    for index in range(11):
        _write_file(repo, f"feature/file_{index}.py", f"value = {index}\n")
    feature_tip = _commit_all(repo, "feature files")

    _check_git(repo, "checkout", "main")
    for index in range(97):
        _write_file(repo, f"main/file_{index}.py", f"value = {index}\n")
    main_tip = _commit_all(repo, "main files")
    _check_git(repo, "update-ref", "refs/remotes/origin/main", main_tip)
    return feature_tip, main_tip


def _run_main(repo: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "SKIP_SCOPE_CHECK" and not key.startswith("GIT_")
    }
    monkeypatch.chdir(repo)
    with patch.dict(os.environ, env, clear=True), patch("sys.argv", ["detect_scope_explosion.py"]):
        return main()


class TestConstants:
    """Tests for module constants."""

    def test_warn_threshold_is_10(self) -> None:
        assert WARN_THRESHOLD == 10

    def test_strong_warn_threshold_is_20(self) -> None:
        assert STRONG_WARN_THRESHOLD == 20

    def test_block_threshold_is_50(self) -> None:
        assert BLOCK_THRESHOLD == 50

    def test_trunk_branches_contains_main(self) -> None:
        assert "main" in TRUNK_BRANCHES
        assert "master" in TRUNK_BRANCHES


class TestScopeResult:
    """Tests for ScopeResult dataclass."""

    def test_is_frozen(self) -> None:
        result = ScopeResult(
            file_count=5,
            merge_base="abc123",
            current_branch="feat/test",
            files=("a.py", "b.py"),
        )
        with pytest.raises(AttributeError):
            # ruff B010 wants `result.file_count = 10` here, but ScopeResult is a
            # frozen dataclass, so file_count is a read-only field. mypy reports
            # the direct assignment as "Property ... is read-only" and rejects it
            # statically, which defeats a test that must reach runtime to assert
            # the AttributeError. setattr is the intended form: it exercises the
            # runtime frozen-instance enforcement without tripping the static
            # check.
            setattr(result, "file_count", 10)  # noqa: B010


class TestFormatBar:
    """Tests for format_bar function."""

    def test_zero_files(self) -> None:
        bar = format_bar(0, WARN_THRESHOLD)
        assert "0/50" in bar

    def test_at_warn_threshold(self) -> None:
        bar = format_bar(10, WARN_THRESHOLD)
        assert "10/50" in bar

    def test_at_block_threshold(self) -> None:
        bar = format_bar(50, BLOCK_THRESHOLD)
        assert "50/50" in bar

    def test_over_block_threshold(self) -> None:
        bar = format_bar(60, BLOCK_THRESHOLD)
        assert "60/50" in bar


class TestGetCurrentBranch:
    """Tests for get_current_branch function."""

    def test_returns_branch_name(self) -> None:
        branch = get_current_branch()
        # In a git repo, should return a string
        assert branch is None or isinstance(branch, str)

    def test_returns_none_on_failure(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            result = get_current_branch()
            assert result is None


class TestResolveBaseRef:
    """Tests for resolve_base_ref function (Issue #2207)."""

    def test_prefers_origin_when_available(self) -> None:
        # origin/main resolves -> use it (worktrees may have stale local main).
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="abc123\n", stderr=""
            )
            assert resolve_base_ref("main") == "origin/main"
            # First (and only) probe should target origin/<base>.
            first_call_args = mock_run.call_args_list[0].args[0]
            assert "origin/main^{commit}" in first_call_args

    def test_falls_back_to_local_when_origin_missing(self) -> None:
        # origin/main missing, local main present.
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.side_effect = [
                subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="abc123\n", stderr=""),
            ]
            assert resolve_base_ref("main") == "main"

    def test_returns_none_when_neither_exists(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=128, stdout="", stderr=""
            )
            assert resolve_base_ref("main") is None


class TestGetRefCommit:
    """Tests for ref commit resolution helpers."""

    def test_get_ref_commit_returns_sha(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="deadbeef\n", stderr=""
            )
            assert get_ref_commit("origin/main") == "deadbeef"

    def test_get_ref_commit_returns_none_on_failure(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=128, stdout="", stderr=""
            )
            assert get_ref_commit("missing") is None

    def test_get_merge_head_uses_merge_head_ref(self) -> None:
        with patch(
            "scripts.detect_scope_explosion.get_ref_commit",
            return_value="deadbeef",
        ) as mock_get_ref_commit:
            assert get_merge_head_commit() == "deadbeef"
            mock_get_ref_commit.assert_called_once_with("MERGE_HEAD")


class TestIsAncestor:
    """Tests for ancestry checks used by stacked PR rescoping."""

    def test_returns_true_when_git_reports_ancestor(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            assert is_ancestor("old", "new") is True

    def test_returns_false_when_git_reports_not_ancestor(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess(args=[], returncode=1)
            assert is_ancestor("new", "old") is False

    @pytest.mark.parametrize(
        "error",
        [OSError("git missing"), subprocess.TimeoutExpired("git", 10)],
    )
    def test_returns_false_when_git_cannot_answer(self, error: Exception) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run", side_effect=error):
            assert is_ancestor("old", "new") is False


class TestGetMergeBase:
    """Tests for get_merge_base function."""

    def test_returns_none_when_base_ref_unresolvable(self) -> None:
        with patch("scripts.detect_scope_explosion.resolve_base_ref", return_value=None):
            result = get_merge_base("main")
            assert result is None

    def test_returns_none_on_failure(self) -> None:
        # resolve_base_ref succeeds, but merge-base itself fails.
        with (
            patch("scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"),
            patch("scripts.detect_scope_explosion.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
            result = get_merge_base("main")
            assert result is None

    def test_uses_resolved_ref_for_merge_base(self) -> None:
        # Regression for Issue #2207: must hand origin/main (not bare main) to git merge-base
        # so stale local main in worktrees doesn't poison the diff.
        with (
            patch("scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"),
            patch("scripts.detect_scope_explosion.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="deadbeef1234\n", stderr=""
            )
            result = get_merge_base("main")
            assert result == "deadbeef1234"
            cmd = mock_run.call_args.args[0]
            assert cmd[:3] == ["git", "merge-base", "HEAD"]
            assert cmd[3] == "origin/main"


class TestGetIndexFilesAgainstRef:
    """Tests for staged result diffing against a base ref."""

    def test_parses_file_list(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="a.py\nb.py\n", stderr=""
            )
            assert get_index_files_against_ref("origin/main") == ["a.py", "b.py"]

    def test_raises_on_failure(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="fatal: bad ref"
            )
            with pytest.raises(
                ScopeDetectionError, match="git diff --cached against origin/main failed"
            ):
                get_index_files_against_ref("origin/main")

    def test_diffs_cached_index_against_base_ref(self) -> None:
        # The --cached diff against the base ref reflects the final staged tree.
        # A staged deletion of a branch-only file therefore drops out of the
        # count (Issue #3171). Lock in the exact command shape that yields this.
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="kept.py\n", stderr=""
            )
            assert get_index_files_against_ref("origin/main") == ["kept.py"]
            cmd = mock_run.call_args.args[0]
            assert cmd[:5] == [
                "git",
                "diff",
                "--cached",
                "--name-only",
                "--diff-filter=ACMR",
            ]
            assert cmd[5] == "origin/main"


class TestGetHeadFilesAgainstRef:
    """Tests for committed branch diffing against a base ref."""

    def test_diffs_head_against_base_ref(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="a.py\nb.py\n", stderr=""
            )
            assert get_head_files_against_ref("abc123") == ["a.py", "b.py"]
            assert mock_run.call_args.args[0] == [
                "git",
                "diff",
                "--name-only",
                "--diff-filter=ACMR",
                "abc123...HEAD",
            ]

    def test_raises_on_failure(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="fatal"
            )
            with pytest.raises(ScopeDetectionError, match="git diff against abc123...HEAD failed"):
                get_head_files_against_ref("abc123")


class TestDetectScope:
    """Tests for detect_scope function."""

    def test_returns_none_on_trunk_branch(self) -> None:
        with patch("scripts.detect_scope_explosion.get_current_branch", return_value="main"):
            result = detect_scope()
            assert result is None

    def test_raises_on_no_branch(self) -> None:
        with patch("scripts.detect_scope_explosion.get_current_branch", return_value=None):
            with pytest.raises(ScopeDetectionError):
                detect_scope()

    def test_raises_on_unresolved_base_ref(self) -> None:
        with (
            patch(
                "scripts.detect_scope_explosion.get_current_branch",
                return_value="feat/test",
            ),
            patch("scripts.detect_scope_explosion.resolve_base_ref", return_value=None),
        ):
            with pytest.raises(ScopeDetectionError):
                detect_scope()

    def test_raises_on_no_merge_base(self) -> None:
        with (
            patch(
                "scripts.detect_scope_explosion.get_current_branch",
                return_value="feat/test",
            ),
            patch("scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"),
            patch("scripts.detect_scope_explosion.get_merge_head_commit", return_value=None),
            patch("scripts.detect_scope_explosion.get_merge_base", return_value=None),
        ):
            with pytest.raises(ScopeDetectionError):
                detect_scope()

    def test_returns_scope_result(self) -> None:
        with (
            patch(
                "scripts.detect_scope_explosion.get_current_branch",
                return_value="feat/test",
            ),
            patch("scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"),
            patch("scripts.detect_scope_explosion.get_merge_head_commit", return_value=None),
            patch(
                "scripts.detect_scope_explosion.get_merge_base",
                return_value="abc123456789",
            ),
            patch(
                "scripts.detect_scope_explosion.get_index_files_against_ref",
                return_value=["a.py", "b.py", "c.py"],
            ),
        ):
            result = detect_scope()
            assert result is not None
            assert result.file_count == 3
            assert result.current_branch == "feat/test"
            assert "a.py" in result.files
            assert "b.py" in result.files
            assert "c.py" in result.files

    def test_deduplicates_files(self) -> None:
        with (
            patch(
                "scripts.detect_scope_explosion.get_current_branch",
                return_value="feat/test",
            ),
            patch("scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"),
            patch("scripts.detect_scope_explosion.get_merge_head_commit", return_value=None),
            patch(
                "scripts.detect_scope_explosion.get_merge_base",
                return_value="abc123456789",
            ),
            patch(
                "scripts.detect_scope_explosion.get_index_files_against_ref",
                return_value=["a.py", "b.py", "a.py", "c.py"],
            ),
        ):
            result = detect_scope()
            assert result is not None
            assert result.file_count == 3

    def test_staged_deletion_of_branch_only_file_subtracts(self) -> None:
        # Regression for Issue #3171 Bug 2: staging the deletion of a
        # branch-only file must lower the count. The non-merge path counts the
        # final staged tree against the merge base via get_index_files_against_ref,
        # so a deleted file simply never appears in that set.
        captured_ref: list[str] = []

        def fake_index_files(ref: str) -> list[str]:
            captured_ref.append(ref)
            # The staged deletion of "removed.py" leaves only these two.
            return ["kept_a.py", "kept_b.py"]

        with (
            patch(
                "scripts.detect_scope_explosion.get_current_branch",
                return_value="feat/test",
            ),
            patch("scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"),
            patch("scripts.detect_scope_explosion.get_merge_head_commit", return_value=None),
            patch(
                "scripts.detect_scope_explosion.get_merge_base",
                return_value="base987654321",
            ),
            patch(
                "scripts.detect_scope_explosion.get_index_files_against_ref",
                side_effect=fake_index_files,
            ),
        ):
            result = detect_scope()
            assert result is not None
            assert result.file_count == 2
            assert "removed.py" not in result.files
            # Counted against the merge base, not HEAD or the working tree.
            assert captured_ref == ["base987654321"]

    def test_in_progress_non_base_merge_counts_final_index_against_base_ref(self) -> None:
        captured_args: list[str] = []

        def fake_index_files(ref: str) -> list[str]:
            captured_args.append(ref)
            return ["pr.py", "tests/test_pr.py"]

        with (
            patch(
                "scripts.detect_scope_explosion.get_current_branch",
                return_value="feat/test",
            ),
            patch("scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"),
            patch(
                "scripts.detect_scope_explosion.get_merge_head_commit",
                return_value="base123456789",
            ),
            patch(
                "scripts.detect_scope_explosion.get_merge_base",
                return_value="base987654321",
            ),
            patch(
                "scripts.detect_scope_explosion.get_index_files_against_ref",
                side_effect=fake_index_files,
            ),
            patch(
                "scripts.detect_scope_explosion.get_head_files_against_ref"
            ) as mock_get_head_files,
        ):
            result = detect_scope()
            assert result is not None
            assert result.file_count == 2
            assert result.files == ("pr.py", "tests/test_pr.py")
            assert captured_args == ["origin/main"]
            mock_get_head_files.assert_not_called()

    def test_in_progress_merge_without_merge_base_still_uses_base_ref_index(self) -> None:
        captured_args: list[str] = []

        def fake_index_files(ref: str) -> list[str]:
            captured_args.append(ref)
            return ["feature_only.py"]

        with (
            patch(
                "scripts.detect_scope_explosion.get_current_branch",
                return_value="feat/test",
            ),
            patch("scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"),
            patch(
                "scripts.detect_scope_explosion.get_merge_head_commit",
                return_value="merge_head_sha",
            ),
            patch(
                "scripts.detect_scope_explosion.get_merge_base",
                return_value=None,
            ),
            patch(
                "scripts.detect_scope_explosion.get_index_files_against_ref",
                side_effect=fake_index_files,
            ),
            patch(
                "scripts.detect_scope_explosion.get_head_files_against_ref"
            ) as mock_get_head_files,
        ):
            result = detect_scope()
            assert result is not None
            assert result.file_count == 1
            assert result.merge_base == "origin/main"
            assert result.files == ("feature_only.py",)
            assert captured_args == ["origin/main"]
            mock_get_head_files.assert_not_called()

    def test_in_progress_base_lineage_merge_counts_final_index(self) -> None:
        # When MERGE_HEAD is the base branch being merged, count the final
        # staged tree against the resolved base ref. That keeps upstream merge
        # files out of scope while still counting branch-local files staged
        # after `git merge --no-commit`.
        captured_args: list[str] = []

        def fake_index_files(ref: str) -> list[str]:
            captured_args.append(ref)
            return [f"pr_file_{i}.py" for i in range(13)]

        with (
            patch(
                "scripts.detect_scope_explosion.get_current_branch",
                return_value="fix/spec-pipeline-hardening",
            ),
            patch("scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"),
            patch(
                "scripts.detect_scope_explosion.get_merge_head_commit",
                return_value="merge_head_sha",
            ),
            patch(
                "scripts.detect_scope_explosion.get_merge_base",
                return_value="real_merge_base_sha",
            ),
            patch(
                "scripts.detect_scope_explosion.get_index_files_against_ref"
            ) as mock_get_index_files,
            patch(
                "scripts.detect_scope_explosion.get_head_files_against_ref"
            ) as mock_get_head_files,
        ):
            mock_get_index_files.side_effect = fake_index_files
            result = detect_scope()
            assert result is not None
            assert result.file_count == 13
            assert captured_args == ["origin/main"]
            mock_get_head_files.assert_not_called()

    def test_sibling_merge_head_counts_final_index_against_base_ref(self) -> None:
        # Regression for Issue #4418: when MERGE_HEAD is the branch's own
        # remote tip (behind main), counting staged files against MERGE_HEAD
        # inflates the count by every file main gained since that tip.
        # Observed: 635 reported when 17 were real.
        captured_index_args: list[str] = []

        def fake_index_files(ref: str) -> list[str]:
            captured_index_args.append(ref)
            return [f"real_pr_{i}.py" for i in range(17)]

        with (
            patch(
                "scripts.detect_scope_explosion.get_current_branch",
                return_value="fix/4034-pr-comment-responder",
            ),
            patch("scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"),
            patch(
                "scripts.detect_scope_explosion.get_merge_head_commit",
                return_value="remote_tip_sha",
            ),
            patch(
                "scripts.detect_scope_explosion.get_index_files_against_ref",
                side_effect=fake_index_files,
            ),
            patch(
                "scripts.detect_scope_explosion.get_merge_base",
                return_value="real_merge_base_sha",
            ),
            patch(
                "scripts.detect_scope_explosion.get_head_files_against_ref"
            ) as mock_get_head_files,
        ):
            result = detect_scope()
            assert result is not None
            assert result.file_count == 17
            assert captured_index_args == ["origin/main"]
            mock_get_head_files.assert_not_called()

    def test_equal_merge_head_counts_against_base_ref_index(self) -> None:
        # A base-side merge should count the final staged tree against the
        # resolved base ref.
        captured_index_args: list[str] = []

        def fake_index_files(ref: str) -> list[str]:
            captured_index_args.append(ref)
            return ["real.py"]

        with (
            patch(
                "scripts.detect_scope_explosion.get_current_branch",
                return_value="fix/some-feature",
            ),
            patch("scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"),
            patch(
                "scripts.detect_scope_explosion.get_merge_head_commit",
                return_value="base_sha",
            ),
            patch(
                "scripts.detect_scope_explosion.get_merge_base",
                return_value="real_merge_base_sha",
            ),
            patch(
                "scripts.detect_scope_explosion.get_index_files_against_ref"
            ) as mock_get_index_files,
            patch(
                "scripts.detect_scope_explosion.get_head_files_against_ref"
            ) as mock_get_head_files,
        ):
            mock_get_index_files.side_effect = fake_index_files
            result = detect_scope()
            assert result is not None
            assert result.file_count == 1
            assert captured_index_args == ["origin/main"]
            mock_get_head_files.assert_not_called()

    def test_sibling_merge_head_uses_base_ref_index_not_merge_head(self) -> None:
        # Isolating control: the sibling path must count the final staged tree
        # against the resolved base ref, not against MERGE_HEAD.
        captured_index_args: list[str] = []

        def fake_index_files(ref: str) -> list[str]:
            captured_index_args.append(ref)
            return ["real.py"]

        with (
            patch(
                "scripts.detect_scope_explosion.get_current_branch",
                return_value="fix/some-feature",
            ),
            patch("scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"),
            patch(
                "scripts.detect_scope_explosion.get_merge_head_commit",
                return_value="remote_tip_sha",
            ),
            patch(
                "scripts.detect_scope_explosion.get_index_files_against_ref",
                side_effect=fake_index_files,
            ),
            patch(
                "scripts.detect_scope_explosion.get_head_files_against_ref"
            ) as mock_get_head_files,
        ):
            detect_scope()
            assert captured_index_args == ["origin/main"]
            mock_get_head_files.assert_not_called()

    def test_sibling_merged_into_local_main_does_not_trigger_index_path(self) -> None:
        with (
            patch(
                "scripts.detect_scope_explosion.get_current_branch",
                return_value="fix/some-feature",
            ),
            patch("scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"),
            patch(
                "scripts.detect_scope_explosion.get_merge_head_commit",
                return_value="sibling_commit_sha",
            ),
            patch(
                "scripts.detect_scope_explosion.get_index_files_against_ref",
                return_value=["real.py"],
            ),
            patch(
                "scripts.detect_scope_explosion.get_head_files_against_ref"
            ) as mock_get_head_files,
        ):
            result = detect_scope()
            assert result is not None
            assert result.file_count == 1
            mock_get_head_files.assert_not_called()

    def test_stale_remote_base_merge_still_counts_final_index(self) -> None:
        captured_index_args: list[str] = []

        def fake_index_files(ref: str) -> list[str]:
            captured_index_args.append(ref)
            return [f"pr_file_{i}.py" for i in range(56)]

        with (
            patch(
                "scripts.detect_scope_explosion.get_current_branch",
                return_value="fix/some-feature",
            ),
            patch("scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"),
            patch(
                "scripts.detect_scope_explosion.get_merge_head_commit",
                return_value="stale_base_sha",
            ),
            patch(
                "scripts.detect_scope_explosion.get_merge_base",
                return_value="real_merge_base_sha",
            ),
            patch(
                "scripts.detect_scope_explosion.get_index_files_against_ref"
            ) as mock_get_index_files,
            patch(
                "scripts.detect_scope_explosion.get_head_files_against_ref"
            ) as mock_get_head_files,
        ):
            mock_get_index_files.side_effect = fake_index_files
            result = detect_scope()
            assert result is not None
            assert result.file_count == 56
            assert captured_index_args == ["origin/main"]
            mock_get_head_files.assert_not_called()


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
class TestMergeHeadRealGit:
    """Real-git coverage for merge scope counting."""

    def test_attached_merge_counts_branch_local_staged_files_when_local_main_is_ahead(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = tmp_path / "repo"
        _feature_tip, _main_tip = _make_merge_scope_repo(repo)
        _check_git(repo, "checkout", "main")
        _write_file(repo, "main/local_only.py", "value = 'local'\n")
        local_main_tip = _commit_all(repo, "local main only")
        _check_git(repo, "checkout", "feature")
        _check_git(repo, "merge", "--no-commit", "--no-ff", local_main_tip)
        staged_feature_files = [f"feature/staged_{index}.py" for index in range(45)]
        for index, relative_path in enumerate(staged_feature_files):
            _write_file(repo, relative_path, f"staged = {index}\n")
        _check_git(repo, "add", *staged_feature_files)

        authored = _git(repo, "diff", "--name-only", "origin/main...HEAD")
        staged = _git(repo, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "origin/main")
        assert authored.returncode == 0
        assert staged.returncode == 0
        authored_paths = {line for line in authored.stdout.splitlines() if line}
        staged_paths = {line for line in staged.stdout.splitlines() if line}
        expected_paths = (
            {f"feature/file_{index}.py" for index in range(11)}
            | set(staged_feature_files)
            | {"main/local_only.py"}
        )
        assert len(authored_paths) == 11
        assert staged_paths.issuperset(set(staged_feature_files))
        assert len(staged_paths) == 57

        monkeypatch.chdir(repo)
        result = detect_scope()
        assert result is not None
        assert result.file_count == 57
        assert set(result.files) == expected_paths
        assert _run_main(repo, monkeypatch) == 1

    def test_attached_and_detached_merge_have_distinct_exit_codes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = tmp_path / "repo"
        feature_tip, main_tip = _make_merge_scope_repo(repo)

        _check_git(repo, "checkout", "feature")
        _check_git(repo, "merge", "--no-commit", "--no-ff", main_tip)
        assert _run_main(repo, monkeypatch) == 0

        _check_git(repo, "merge", "--abort")
        _check_git(repo, "checkout", "--detach", feature_tip)
        _check_git(repo, "merge", "--no-commit", "--no-ff", main_tip)
        assert _run_main(repo, monkeypatch) == 2

    def test_sibling_merge_counts_final_index_against_merge_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = tmp_path / "repo"
        _init_scope_repo(repo)
        _check_git(repo, "checkout", "-qb", "feature")
        for index in range(45):
            _write_file(repo, f"feature/file_{index}.py", f"value = {index}\n")
        _commit_all(repo, "feature files")

        _check_git(repo, "checkout", "main")
        _check_git(repo, "checkout", "-qb", "sibling")
        for index in range(10):
            _write_file(repo, f"sibling/file_{index}.py", f"value = {index}\n")
        sibling_tip = _commit_all(repo, "sibling files")

        _check_git(repo, "checkout", "feature")
        _check_git(repo, "merge", "--no-commit", "--no-ff", sibling_tip)

        staged = _git(repo, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "origin/main")
        assert staged.returncode == 0
        staged_paths = {line for line in staged.stdout.splitlines() if line}
        assert len(staged_paths) == 55

        monkeypatch.chdir(repo)
        result = detect_scope()
        assert result is not None
        assert result.file_count == 55
        assert _run_main(repo, monkeypatch) == 1

    def test_unrelated_history_merge_uses_base_ref_index_without_merge_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = tmp_path / "repo"
        _init_scope_repo(repo)
        _check_git(repo, "checkout", "--orphan", "feature")
        _write_file(repo, "feature/orphan_only.py", "value = 1\n")
        _commit_all(repo, "orphan feature")

        _check_git(
            repo,
            "merge",
            "--allow-unrelated-histories",
            "--no-commit",
            "--no-ff",
            "main",
        )

        staged = _git(repo, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "origin/main")
        assert staged.returncode == 0
        staged_paths = {line for line in staged.stdout.splitlines() if line}
        assert staged_paths == {"feature/orphan_only.py"}

        monkeypatch.chdir(repo)
        result = detect_scope()
        assert result is not None
        assert result.file_count == 1
        assert result.files == ("feature/orphan_only.py",)
        assert _run_main(repo, monkeypatch) == 0


class TestReport:
    """Tests for report function."""

    def test_below_warn_returns_zero(self, capsys: CaptureFixture[str]) -> None:
        result = ScopeResult(
            file_count=5,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(5)),
        )
        exit_code = report(result)
        assert exit_code == 0

    def test_at_warn_threshold(self, capsys: CaptureFixture[str]) -> None:
        result = ScopeResult(
            file_count=10,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(10)),
        )
        exit_code = report(result)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    def test_at_strong_warn_threshold(self, capsys: CaptureFixture[str]) -> None:
        result = ScopeResult(
            file_count=20,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(20)),
        )
        exit_code = report(result)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "splitting" in captured.out.lower()

    def test_at_block_threshold_still_allowed(self, capsys: CaptureFixture[str]) -> None:
        # Issue #3171 Bug 1: 50 is the inclusive hard limit. It must pass with a
        # strong warning, not block. Blocking begins at 51.
        result = ScopeResult(
            file_count=BLOCK_THRESHOLD,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(BLOCK_THRESHOLD)),
        )
        exit_code = report(result)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "BLOCKED" not in captured.out

    def test_just_below_block_threshold_allowed(self, capsys: CaptureFixture[str]) -> None:
        result = ScopeResult(
            file_count=BLOCK_THRESHOLD - 1,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(BLOCK_THRESHOLD - 1)),
        )
        exit_code = report(result)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "BLOCKED" not in captured.out

    def test_just_over_block_threshold_blocks(self, capsys: CaptureFixture[str]) -> None:
        # 51 is the first blocking count.
        result = ScopeResult(
            file_count=BLOCK_THRESHOLD + 1,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(BLOCK_THRESHOLD + 1)),
        )
        exit_code = report(result)
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out

    def test_over_block_threshold(self, capsys: CaptureFixture[str]) -> None:
        result = ScopeResult(
            file_count=60,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(60)),
        )
        exit_code = report(result)
        assert exit_code == 1

    def test_quiet_suppresses_below_warn(self, capsys: CaptureFixture[str]) -> None:
        result = ScopeResult(
            file_count=5,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(5)),
        )
        exit_code = report(result, quiet=True)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out == ""


class TestMain:
    """Tests for main entry point."""

    def test_bypass_with_env_var(self, capsys: CaptureFixture[str]) -> None:
        with (
            patch.dict(os.environ, {"SKIP_SCOPE_CHECK": "1"}),
            patch("sys.argv", ["detect_scope_explosion.py"]),
        ):
            exit_code = main()
            assert exit_code == 0
            captured = capsys.readouterr()
            assert "bypassed" in captured.out.lower()

    def test_returns_zero_when_no_result(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=False),
            patch("scripts.detect_scope_explosion.detect_scope", return_value=None),
            patch("sys.argv", ["detect_scope_explosion.py"]),
        ):
            # Remove SKIP_SCOPE_CHECK if set
            env = os.environ.copy()
            env.pop("SKIP_SCOPE_CHECK", None)
            with patch.dict(os.environ, env, clear=True):
                exit_code = main()
                assert exit_code == 0

    def test_returns_two_when_scope_cannot_be_determined(self, capsys: CaptureFixture[str]) -> None:
        with (
            patch.dict(os.environ, {}, clear=False),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                side_effect=ScopeDetectionError("detached HEAD"),
            ),
            patch("sys.argv", ["detect_scope_explosion.py"]),
        ):
            env = os.environ.copy()
            env.pop("SKIP_SCOPE_CHECK", None)
            with patch.dict(os.environ, env, clear=True):
                exit_code = main()
                assert exit_code == 2
        captured = capsys.readouterr()
        assert "detached HEAD" in captured.err

    def test_returns_one_when_blocked(self) -> None:
        blocked_result = ScopeResult(
            file_count=55,
            merge_base="abc123",
            current_branch="feat/big",
            files=tuple(f"file{i}.py" for i in range(55)),
        )
        env = os.environ.copy()
        env.pop("SKIP_SCOPE_CHECK", None)
        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=blocked_result,
            ),
            patch("sys.argv", ["detect_scope_explosion.py"]),
        ):
            exit_code = main()
            assert exit_code == 1


class TestBypassHintContext:
    """The bypass hint must match the hook stage where it will be used."""

    def _blocked_result(self) -> ScopeResult:
        return ScopeResult(
            file_count=BLOCK_THRESHOLD + 5,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(BLOCK_THRESHOLD + 5)),
        )

    def test_pre_commit_hint_says_git_commit(self, capsys: CaptureFixture[str]) -> None:
        """Pre-commit invocation (no --base-branch) prints 'git commit' bypass."""
        report(self._blocked_result(), from_prepush=False)
        out = capsys.readouterr().out
        assert "SKIP_SCOPE_CHECK=1 git commit" in out
        assert "git push" not in out

    def test_pre_push_hint_says_git_push(self, capsys: CaptureFixture[str]) -> None:
        """Pre-push invocation (--base-branch set) prints 'git push' bypass."""
        report(self._blocked_result(), from_prepush=True)
        out = capsys.readouterr().out
        assert "SKIP_SCOPE_CHECK=1 git push" in out
        assert "git commit" not in out.split("Bypass")[1]

    def test_main_without_base_branch_arg_is_pre_commit(self, capsys: CaptureFixture[str]) -> None:
        """main() with no --base-branch passes from_prepush=False to report."""
        blocked = self._blocked_result()
        env = {k: v for k, v in os.environ.items() if k != "SKIP_SCOPE_CHECK"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("scripts.detect_scope_explosion.detect_scope", return_value=blocked),
            patch("sys.argv", ["detect_scope_explosion.py"]),
        ):
            main()
        out = capsys.readouterr().out
        assert "SKIP_SCOPE_CHECK=1 git commit" in out

    def test_main_with_base_branch_arg_is_pre_push(self, capsys: CaptureFixture[str]) -> None:
        """main() with --base-branch origin/main passes from_prepush=True to report."""
        blocked = self._blocked_result()
        env = {k: v for k, v in os.environ.items() if k != "SKIP_SCOPE_CHECK"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("scripts.detect_scope_explosion.detect_scope", return_value=blocked),
            patch(
                "sys.argv",
                ["detect_scope_explosion.py", "--base-branch", "origin/main"],
            ),
        ):
            main()
        out = capsys.readouterr().out
        assert "SKIP_SCOPE_CHECK=1 git push" in out

    def test_pre_commit_remediation_mentions_stash(self, capsys: CaptureFixture[str]) -> None:
        """Pre-commit block message includes stash-based remediation steps."""
        report(self._blocked_result(), from_prepush=False)
        out = capsys.readouterr().out
        assert "git stash" in out

    def test_pre_push_remediation_omits_stash(self, capsys: CaptureFixture[str]) -> None:
        """Pre-push block message does not suggest stash; work is already committed."""
        report(self._blocked_result(), from_prepush=True)
        out = capsys.readouterr().out
        assert "git stash" not in out


class TestRescopeAgainstPrBase:
    """Tests for rescope_against_pr_base.

    Credibility is a graph property. The blocked result forks from main at
    MAIN_FORK; a genuine stack base forks later at STACK_FORK. Tests that want
    the rescope accepted must supply both, because identical fork points mean
    the base is not a stack and are refused without consulting git.
    """

    MAIN_FORK = "aaaa111"
    STACK_FORK = "bbbb222"

    @classmethod
    def _result(
        cls,
        count: int,
        branch: str = "feat/stacked",
        merge_base: str | None = None,
    ) -> ScopeResult:
        return ScopeResult(
            file_count=count,
            merge_base=cls.MAIN_FORK if merge_base is None else merge_base,
            current_branch=branch,
            files=tuple(f"file{i}.py" for i in range(count)),
        )

    @classmethod
    def _stacked(cls, count: int) -> ScopeResult:
        """A re-measurement whose fork point is downstream of main's."""
        return cls._result(count, merge_base=cls.STACK_FORK)

    @staticmethod
    def _no_merge():
        """Patch the merge check off so a test exercises the normal path."""
        return patch(
            "scripts.detect_scope_explosion.get_merge_head_commit", return_value=None
        )

    @staticmethod
    def _downstream(result: bool = True):
        """Patch the ancestry test the credibility check delegates to."""
        return patch("scripts.detect_scope_explosion.is_ancestor", return_value=result)

    def test_rescopes_to_the_pr_base(self) -> None:
        """A stacked PR is re-measured against its real base."""
        blocked = self._result(52)
        narrowed = self._stacked(13)
        with (
            self._no_merge(),
            self._downstream(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ),
            patch("scripts.detect_scope_explosion.detect_scope", return_value=narrowed),
        ):
            assert rescope_against_pr_base(None, blocked) is narrowed

    def test_passes_the_pr_base_to_detect_scope(self) -> None:
        """The re-measurement uses the resolved base, not the original one."""
        with (
            self._no_merge(),
            self._downstream(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=self._stacked(13),
            ) as detect,
        ):
            rescope_against_pr_base(None, self._result(52))
        detect.assert_called_once_with("fix/parent")

    def test_looks_up_the_pr_for_the_branch_that_was_measured(self) -> None:
        """The branch comes from the blocked result, not a fresh git read.

        Re-reading would let a branch switch between the two measurements
        resolve a PR belonging to a branch nobody measured.
        """
        blocked = self._result(52, branch="feat/measured")
        with (
            self._no_merge(),
            self._downstream(),
            patch(
                "scripts.detect_scope_explosion.get_current_branch",
                return_value="feat/switched-underneath-us",
            ),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ) as resolve,
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=self._stacked(13),
            ),
        ):
            rescope_against_pr_base(None, blocked)
        resolve.assert_called_once_with("feat/measured")

    def test_skips_rescoping_during_a_merge(self) -> None:
        """detect_scope compares differently mid-merge, so the numbers differ in kind."""
        with (
            patch(
                "scripts.detect_scope_explosion.get_merge_head_commit",
                return_value="deadbeef",
            ),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch"
            ) as resolve,
        ):
            assert rescope_against_pr_base(None, self._result(52)) is None
        resolve.assert_not_called()

    def test_returns_none_on_detached_head(self) -> None:
        """With no branch name on the measured result there is no PR to look up."""
        detached = self._result(52, branch="")
        with (
            self._no_merge(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch"
            ) as resolve,
        ):
            assert rescope_against_pr_base(None, detached) is None
        resolve.assert_not_called()

    def test_returns_none_when_no_pr_base(self) -> None:
        """With no PR resolved the caller keeps the original measurement."""
        with (
            self._no_merge(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value=None,
            ),
            patch("scripts.detect_scope_explosion.detect_scope") as detect,
        ):
            assert rescope_against_pr_base(None, self._result(52)) is None
        detect.assert_not_called()

    def test_returns_none_when_pr_base_is_already_the_measured_base(self) -> None:
        """Re-measuring against the same base would repeat the same work."""
        with (
            self._no_merge(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="main",
            ),
            patch("scripts.detect_scope_explosion.detect_scope") as detect,
        ):
            assert rescope_against_pr_base("main", self._result(52)) is None
        detect.assert_not_called()

    def test_normalizes_the_remote_prefix_before_comparing(self) -> None:
        """origin/main and main name the same branch; pre-push passes the former."""
        with (
            self._no_merge(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="main",
            ),
            patch("scripts.detect_scope_explosion.detect_scope") as detect,
        ):
            assert rescope_against_pr_base("origin/main", self._result(52)) is None
        detect.assert_not_called()

    def test_compares_against_the_requested_base_not_a_hardcoded_main(self) -> None:
        """A caller measuring against something other than main is honored.

        Every other test here passes None or a form of main, so hardcoding
        "main" in the comparison behaves identically in all of them and the
        parameter can be ignored without a single failure.
        """
        with (
            self._no_merge(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="release/next",
            ),
            patch("scripts.detect_scope_explosion.detect_scope") as detect,
        ):
            assert (
                rescope_against_pr_base("origin/release/next", self._result(52)) is None
            )
        detect.assert_not_called()

    def test_still_rescopes_when_the_requested_base_is_not_the_pr_base(self) -> None:
        """The negative control for the test above.

        Same non-main requested base, different PR base. This must re-measure,
        which proves the previous test refused for the reason it claims rather
        than because any non-main base is refused outright.
        """
        narrowed = self._stacked(13)
        with (
            self._no_merge(),
            self._downstream(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ),
            patch("scripts.detect_scope_explosion.detect_scope", return_value=narrowed),
        ):
            assert (
                rescope_against_pr_base("origin/release/next", self._result(52))
                is narrowed
            )

    def test_returns_none_when_remeasurement_fails(self) -> None:
        """An unresolvable second measurement keeps the original block."""
        with (
            self._no_merge(),
            self._downstream(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ),
            patch("scripts.detect_scope_explosion.detect_scope", return_value=None),
        ):
            assert rescope_against_pr_base(None, self._result(52)) is None

    def test_returns_none_when_remeasurement_raises(self) -> None:
        """A failed re-measurement must preserve the original blocking result."""
        with (
            self._no_merge(),
            self._downstream(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                side_effect=ScopeDetectionError("bad base"),
            ),
        ):
            assert rescope_against_pr_base(None, self._result(52)) is None

    def test_refuses_a_zero_file_remeasurement(self) -> None:
        """A zero-file remeasurement still must not clear the block.

        Diff failures now raise ScopeDetectionError and are caught before
        this point. A zero count here therefore means a genuine empty diff,
        which the gate still refuses to unblock.
        """
        with (
            self._no_merge(),
            self._downstream(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=self._stacked(0),
            ),
        ):
            assert rescope_against_pr_base(None, self._result(52)) is None

    def test_refuses_a_base_that_forks_where_main_forks(self) -> None:
        """An unrelated branch shares main's fork point, so it is not a stack."""
        not_stacked = self._result(13, merge_base=self.MAIN_FORK)
        with (
            self._no_merge(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/unrelated",
            ),
            patch(
                "scripts.detect_scope_explosion.detect_scope", return_value=not_stacked
            ),
        ):
            assert rescope_against_pr_base(None, self._result(52)) is None

    def test_refuses_a_base_whose_fork_point_is_not_downstream(self) -> None:
        """When git says the fork points are unordered the numbers are incomparable."""
        with (
            self._no_merge(),
            self._downstream(result=False),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=self._stacked(13),
            ),
        ):
            assert rescope_against_pr_base(None, self._result(52)) is None

    def test_accepts_a_stacked_base_naming_a_file_main_never_saw(self) -> None:
        """The regression path-set containment caused.

        A child that reverts a file its parent changed differs from its parent
        on exactly that file, and agrees with main about it, so the file is
        absent from the main-relative set. Containment rejected this honest
        stacked PR; ancestry accepts it.
        """
        blocked = ScopeResult(
            file_count=51,
            merge_base=self.MAIN_FORK,
            current_branch="feat/stacked",
            files=tuple(f"f{i:02d}.txt" for i in range(1, 52)),
        )
        reverted = ScopeResult(
            file_count=1,
            merge_base=self.STACK_FORK,
            current_branch="feat/stacked",
            files=("f00.txt",),
        )
        with (
            self._no_merge(),
            self._downstream(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ),
            patch("scripts.detect_scope_explosion.detect_scope", return_value=reverted),
        ):
            assert rescope_against_pr_base(None, blocked) is reverted

    def test_reports_both_counts(self, capsys: CaptureFixture[str]) -> None:
        """The operator sees which base produced which number."""
        with (
            self._no_merge(),
            self._downstream(),
            patch(
                "scripts.detect_scope_explosion.resolve_pr_base_branch",
                return_value="fix/parent",
            ),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=self._stacked(13),
            ),
        ):
            rescope_against_pr_base(None, self._result(52))
        err = capsys.readouterr().err
        assert "origin/fix/parent" in err
        assert "13 files" in err
        assert "52" in err


class TestMainConsultsPrBaseOnlyWhenBlocking:
    """Tests for the main() gate around rescope_against_pr_base."""

    @staticmethod
    def _result(count: int) -> ScopeResult:
        return ScopeResult(
            file_count=count,
            merge_base="abc123def456",
            current_branch="feat/stacked",
            files=tuple(f"file{i}.py" for i in range(count)),
        )

    def test_under_the_limit_skips_the_lookup(self) -> None:
        """The common path pays no gh call."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.argv", ["detect_scope_explosion.py"]),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=self._result(BLOCK_THRESHOLD),
            ),
            patch("scripts.detect_scope_explosion.rescope_against_pr_base") as rescope,
        ):
            assert main() == 0
        rescope.assert_not_called()

    def test_over_the_limit_consults_the_pr_base(self) -> None:
        """A blocking count triggers exactly one re-measurement attempt."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.argv", ["detect_scope_explosion.py"]),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=self._result(BLOCK_THRESHOLD + 2),
            ),
            patch(
                "scripts.detect_scope_explosion.rescope_against_pr_base",
                return_value=self._result(13),
            ) as rescope,
        ):
            assert main() == 0
        assert rescope.call_count == 1

    def test_still_blocks_a_genuinely_large_pr(self) -> None:
        """Re-measuring does not rescue a PR that is large against its own base."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.argv", ["detect_scope_explosion.py"]),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=self._result(BLOCK_THRESHOLD + 40),
            ),
            patch(
                "scripts.detect_scope_explosion.rescope_against_pr_base",
                return_value=self._result(BLOCK_THRESHOLD + 30),
            ),
        ):
            assert main() == 1

    def test_blocks_when_no_pr_base_resolves(self) -> None:
        """Unchanged behavior when gh cannot answer: the main count stands."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.argv", ["detect_scope_explosion.py"]),
            patch(
                "scripts.detect_scope_explosion.detect_scope",
                return_value=self._result(BLOCK_THRESHOLD + 2),
            ),
            patch(
                "scripts.detect_scope_explosion.rescope_against_pr_base",
                return_value=None,
            ),
        ):
            assert main() == 1


class TestGeneratedFileExclusion:
    """Tests for generated file exclusion from scope count (Issue #4920).

    Generated files (matching GENERATED_GLOBS/GENERATED_PATHS) must not count
    toward the scope explosion threshold.
    """

    def test_generated_files_excluded_from_count(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A branch with 60 generated files and 3 authored files passes."""
        repo = tmp_path / "repo"
        _init_scope_repo(repo)
        _check_git(repo, "checkout", "-qb", "feature")

        # 60 generated agent files
        for i in range(60):
            _write_file(repo, f"src/copilot-cli/agents/agent_{i}.agent.md", f"agent {i}\n")
        # 3 authored files
        for i in range(3):
            _write_file(repo, f"scripts/file_{i}.py", f"x = {i}\n")

        _commit_all(repo, "template regen + authored")

        monkeypatch.chdir(repo)
        result = detect_scope(base_branch="main")
        assert result is not None
        assert result.file_count == 3
        assert result.generated_count == 60

    def test_authored_files_still_block(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A branch with 55 authored files blocks even with generated files."""
        repo = tmp_path / "repo"
        _init_scope_repo(repo)
        _check_git(repo, "checkout", "-qb", "feature")

        # 10 generated
        for i in range(10):
            _write_file(repo, f"src/copilot-cli/agents/a_{i}.agent.md", f"a {i}\n")
        # 55 authored (over threshold)
        for i in range(55):
            _write_file(repo, f"lib/mod_{i}.py", f"v = {i}\n")

        _commit_all(repo, "large PR")

        monkeypatch.chdir(repo)
        result = detect_scope(base_branch="main")
        assert result is not None
        assert result.file_count == 55
        assert result.generated_count == 10

    def test_only_generated_files_yields_zero_count(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A branch with only generated files has file_count == 0."""
        repo = tmp_path / "repo"
        _init_scope_repo(repo)
        _check_git(repo, "checkout", "-qb", "feature")

        for i in range(30):
            _write_file(repo, f"src/vs-code-agents/agent_{i}.agent.md", f"vs {i}\n")

        _commit_all(repo, "regen only")

        monkeypatch.chdir(repo)
        result = detect_scope(base_branch="main")
        assert result is not None
        assert result.file_count == 0
        assert result.generated_count == 30

    def test_report_includes_generated_note(self, capsys: CaptureFixture[str]) -> None:
        """Report output mentions generated exclusion when count > 0."""
        result = ScopeResult(
            file_count=5,
            merge_base="abc123",
            current_branch="feature",
            files=tuple(f"f{i}.py" for i in range(5)),
            generated_count=61,
        )
        exit_code = report(result)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "61 generated excluded" in captured.out

    def test_report_omits_note_when_no_generated(self, capsys: CaptureFixture[str]) -> None:
        """Report output has no generated note when count is 0."""
        result = ScopeResult(
            file_count=5,
            merge_base="abc123",
            current_branch="feature",
            files=tuple(f"f{i}.py" for i in range(5)),
            generated_count=0,
        )
        report(result)
        captured = capsys.readouterr()
        assert "generated" not in captured.out

    def test_episode_files_excluded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Episode JSON files are recognized as generated."""
        repo = tmp_path / "repo"
        _init_scope_repo(repo)
        _check_git(repo, "checkout", "-qb", "feature")

        _write_file(repo, ".agents/memory/episodes/episode-2026-01-01-session-1.json", "{}")
        _write_file(repo, "scripts/real.py", "x = 1\n")
        _commit_all(repo, "episode + authored")

        monkeypatch.chdir(repo)
        result = detect_scope(base_branch="main")
        assert result is not None
        assert result.file_count == 1
        assert result.generated_count == 1

    def test_merge_in_progress_also_excludes_generated(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Generated files excluded even during an in-progress merge."""
        repo = tmp_path / "repo"
        _init_scope_repo(repo)

        # Create a side branch with generated files
        _check_git(repo, "checkout", "-qb", "side")
        for i in range(20):
            _write_file(repo, f"src/copilot-cli/agents/s_{i}.agent.md", f"s {i}\n")
        _write_file(repo, "authored.py", "y = 1\n")
        _commit_all(repo, "side work")

        # Back to feature, start merge
        _check_git(repo, "checkout", "main")
        _check_git(repo, "checkout", "-qb", "feature")
        _write_file(repo, "feature.py", "z = 1\n")
        _commit_all(repo, "feature file")
        _check_git(repo, "merge", "--no-commit", "side")

        monkeypatch.chdir(repo)
        result = detect_scope(base_branch="main")
        assert result is not None
        assert result.generated_count == 20
        # authored: feature.py + authored.py = 2
        assert result.file_count == 2
