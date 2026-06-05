"""Tests for detect_scope_explosion module.

Verifies scope explosion detection used in pre-commit hook.
Related: Issue #944, PR #908 (95 files)
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from scripts.detect_scope_explosion import (
    BLOCK_THRESHOLD,
    STRONG_WARN_THRESHOLD,
    TRUNK_BRANCHES,
    WARN_THRESHOLD,
    ScopeResult,
    detect_scope,
    format_bar,
    get_changed_files,
    get_current_branch,
    get_index_files_against_ref,
    get_merge_head_commit,
    get_merge_base,
    get_ref_commit,
    get_staged_new_files,
    main,
    report,
    resolve_base_ref,
)

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture


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
            setattr(result, "file_count", 10)


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


class TestGetMergeBase:
    """Tests for get_merge_base function."""

    def test_returns_none_when_base_ref_unresolvable(self) -> None:
        with patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value=None
        ):
            result = get_merge_base("main")
            assert result is None

    def test_returns_none_on_failure(self) -> None:
        # resolve_base_ref succeeds, but merge-base itself fails.
        with patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
            result = get_merge_base("main")
            assert result is None

    def test_uses_resolved_ref_for_merge_base(self) -> None:
        # Regression for Issue #2207: must hand origin/main (not bare main) to git merge-base
        # so stale local main in worktrees doesn't poison the diff.
        with patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="deadbeef1234\n", stderr=""
            )
            result = get_merge_base("main")
            assert result == "deadbeef1234"
            cmd = mock_run.call_args.args[0]
            assert cmd[:3] == ["git", "merge-base", "HEAD"]
            assert cmd[3] == "origin/main"


class TestGetChangedFiles:
    """Tests for get_changed_files function."""

    def test_returns_empty_on_failure(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
            result = get_changed_files("abc123")
            assert result == []

    def test_parses_file_list(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="a.py\nb.py\nc.md\n", stderr=""
            )
            result = get_changed_files("abc123")
            assert result == ["a.py", "b.py", "c.md"]

    def test_strips_empty_lines(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="a.py\n\nb.py\n", stderr=""
            )
            result = get_changed_files("abc123")
            assert result == ["a.py", "b.py"]


class TestGetStagedNewFiles:
    """Tests for get_staged_new_files function."""

    def test_returns_empty_on_failure(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
            result = get_staged_new_files("abc123")
            assert result == []


class TestGetIndexFilesAgainstRef:
    """Tests for staged result diffing against a base ref."""

    def test_parses_file_list(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="a.py\nb.py\n", stderr=""
            )
            assert get_index_files_against_ref("origin/main") == ["a.py", "b.py"]

    def test_returns_empty_on_failure(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
            assert get_index_files_against_ref("origin/main") == []


class TestDetectScope:
    """Tests for detect_scope function."""

    def test_returns_none_on_trunk_branch(self) -> None:
        with patch(
            "scripts.detect_scope_explosion.get_current_branch", return_value="main"
        ):
            result = detect_scope()
            assert result is None

    def test_returns_none_on_no_branch(self) -> None:
        with patch(
            "scripts.detect_scope_explosion.get_current_branch", return_value=None
        ):
            result = detect_scope()
            assert result is None

    def test_returns_none_on_no_merge_base(self) -> None:
        with patch(
            "scripts.detect_scope_explosion.get_current_branch",
            return_value="feat/test",
        ), patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch(
            "scripts.detect_scope_explosion.get_merge_head_commit", return_value=None
        ), patch(
            "scripts.detect_scope_explosion.get_merge_base", return_value=None
        ):
            result = detect_scope()
            assert result is None

    def test_returns_scope_result(self) -> None:
        with patch(
            "scripts.detect_scope_explosion.get_current_branch",
            return_value="feat/test",
        ), patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch(
            "scripts.detect_scope_explosion.get_merge_head_commit", return_value=None
        ), patch(
            "scripts.detect_scope_explosion.get_merge_base",
            return_value="abc123456789",
        ), patch(
            "scripts.detect_scope_explosion.get_changed_files",
            return_value=["a.py", "b.py"],
        ), patch(
            "scripts.detect_scope_explosion.get_staged_new_files",
            return_value=["c.py"],
        ):
            result = detect_scope()
            assert result is not None
            assert result.file_count == 3
            assert result.current_branch == "feat/test"
            assert "a.py" in result.files
            assert "b.py" in result.files
            assert "c.py" in result.files

    def test_deduplicates_files(self) -> None:
        with patch(
            "scripts.detect_scope_explosion.get_current_branch",
            return_value="feat/test",
        ), patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch(
            "scripts.detect_scope_explosion.get_merge_head_commit", return_value=None
        ), patch(
            "scripts.detect_scope_explosion.get_merge_base",
            return_value="abc123456789",
        ), patch(
            "scripts.detect_scope_explosion.get_changed_files",
            return_value=["a.py", "b.py"],
        ), patch(
            "scripts.detect_scope_explosion.get_staged_new_files",
            return_value=["a.py", "c.py"],
        ):
            result = detect_scope()
            assert result is not None
            assert result.file_count == 3

    def test_in_progress_base_merge_counts_index_against_base(self) -> None:
        with patch(
            "scripts.detect_scope_explosion.get_current_branch",
            return_value="feat/test",
        ), patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch(
            "scripts.detect_scope_explosion.get_merge_head_commit",
            return_value="base123456789",
        ), patch(
            "scripts.detect_scope_explosion.get_ref_commit",
            return_value="base123456789",
        ), patch(
            "scripts.detect_scope_explosion.get_index_files_against_ref",
            return_value=["pr.py", "tests/test_pr.py"],
        ), patch(
            "scripts.detect_scope_explosion.get_merge_base"
        ) as mock_get_merge_base:
            result = detect_scope()
            assert result is not None
            assert result.file_count == 2
            assert result.files == ("pr.py", "tests/test_pr.py")
            mock_get_merge_base.assert_not_called()

    def test_in_progress_merge_counts_against_merge_head_not_base_ref(self) -> None:
        # Regression for Issue #2376: in a linked-worktree merge where local
        # origin/main has advanced past MERGE_HEAD, counting the staged index
        # against base_ref includes every upstream merge file and surfaces a
        # false scope explosion (observed: 86/50 reported for a 13-file PR).
        # The detector must compare staged result against MERGE_HEAD itself so
        # only the PR's real diff is counted.
        captured_args: list[str] = []

        def fake_index_files(ref: str) -> list[str]:
            captured_args.append(ref)
            # Simulate: against MERGE_HEAD only PR files differ (13 files);
            # against base_ref the upstream merge files leak in (86 files).
            if ref == "merge_head_sha":
                return [f"pr_file_{i}.py" for i in range(13)]
            return [f"upstream_{i}.py" for i in range(86)]

        with patch(
            "scripts.detect_scope_explosion.get_current_branch",
            return_value="fix/spec-pipeline-hardening",
        ), patch(
            "scripts.detect_scope_explosion.resolve_base_ref", return_value="origin/main"
        ), patch(
            "scripts.detect_scope_explosion.get_merge_head_commit",
            return_value="merge_head_sha",
        ), patch(
            "scripts.detect_scope_explosion.get_ref_commit",
            return_value="stale_local_main_sha",
        ), patch(
            "scripts.detect_scope_explosion.get_index_files_against_ref",
            side_effect=fake_index_files,
        ), patch(
            "scripts.detect_scope_explosion.get_merge_base"
        ) as mock_get_merge_base:
            result = detect_scope()
            assert result is not None
            # Must reflect the real PR diff against MERGE_HEAD (13), not the
            # staged upstream merge (86).
            assert result.file_count == 13
            assert "merge_head_sha" in captured_args
            mock_get_merge_base.assert_not_called()


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

    def test_at_block_threshold(self, capsys: CaptureFixture[str]) -> None:
        result = ScopeResult(
            file_count=50,
            merge_base="abc123",
            current_branch="feat/test",
            files=tuple(f"file{i}.py" for i in range(50)),
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
        with patch.dict(os.environ, {"SKIP_SCOPE_CHECK": "1"}), patch(
            "sys.argv", ["detect_scope_explosion.py"]
        ):
            exit_code = main()
            assert exit_code == 0
            captured = capsys.readouterr()
            assert "bypassed" in captured.out.lower()

    def test_returns_zero_when_no_result(self) -> None:
        with patch.dict(os.environ, {}, clear=False), patch(
            "scripts.detect_scope_explosion.detect_scope", return_value=None
        ), patch(
            "sys.argv", ["detect_scope_explosion.py"]
        ):
            # Remove SKIP_SCOPE_CHECK if set
            env = os.environ.copy()
            env.pop("SKIP_SCOPE_CHECK", None)
            with patch.dict(os.environ, env, clear=True):
                exit_code = main()
                assert exit_code == 0

    def test_returns_one_when_blocked(self) -> None:
        blocked_result = ScopeResult(
            file_count=55,
            merge_base="abc123",
            current_branch="feat/big",
            files=tuple(f"file{i}.py" for i in range(55)),
        )
        env = os.environ.copy()
        env.pop("SKIP_SCOPE_CHECK", None)
        with patch.dict(os.environ, env, clear=True), patch(
            "scripts.detect_scope_explosion.detect_scope",
            return_value=blocked_result,
        ), patch("sys.argv", ["detect_scope_explosion.py"]):
            exit_code = main()
            assert exit_code == 1
