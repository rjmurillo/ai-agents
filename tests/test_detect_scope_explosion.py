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
    get_merge_base,
    get_staged_new_files,
    main,
    report,
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
            result.file_count = 10  # type: ignore[misc]


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


class TestGetMergeBase:
    """Tests for get_merge_base function."""

    def test_returns_none_on_failure(self) -> None:
        with patch("scripts.detect_scope_explosion.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
            result = get_merge_base("main")
            assert result is None


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
            "scripts.detect_scope_explosion.get_merge_base", return_value=None
        ):
            result = detect_scope()
            assert result is None

    def test_returns_scope_result(self) -> None:
        with patch(
            "scripts.detect_scope_explosion.get_current_branch",
            return_value="feat/test",
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
