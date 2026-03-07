"""Tests for CWE-22 path traversal prevention in path_validation module.

Validates that:
- Absolute paths outside repo are rejected
- Symlinks outside repo are rejected
- Normal relative paths within repo are accepted
- Paths with .. components that resolve within repo are accepted
- Paths with .. that resolve outside repo are rejected
"""

from __future__ import annotations

import subprocess

# Add the scripts directory to the path so we can import path_validation
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS_DIR = str(
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / ".claude"
    / "skills"
    / "context-optimizer"
    / "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

from path_validation import get_repo_root, validate_path_within_repo  # noqa: E402


@pytest.fixture
def repo_root() -> Path:
    """Get the actual repo root for tests."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip()).resolve()


@pytest.fixture
def temp_dir_outside_repo(tmp_path: Path) -> Path:
    """Create a temp directory guaranteed to be outside the repo."""
    outside_dir = tmp_path / "outside_repo"
    outside_dir.mkdir()
    return outside_dir


class TestGetRepoRoot:
    """Tests for get_repo_root function."""

    def test_returns_path_in_git_repo(self, repo_root: Path) -> None:
        """get_repo_root returns a valid path when inside a git repo."""
        result = get_repo_root()
        assert result == repo_root
        assert result.is_dir()

    def test_raises_when_git_unavailable(self) -> None:
        """get_repo_root raises RuntimeError when git is not available."""
        with patch("path_validation.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("git not found")
            with pytest.raises(RuntimeError, match="Unable to determine repository root"):
                get_repo_root()

    def test_raises_when_not_in_repo(self) -> None:
        """get_repo_root raises RuntimeError when not in a git repo."""
        with patch("path_validation.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(128, "git")
            with pytest.raises(RuntimeError, match="Unable to determine repository root"):
                get_repo_root()


class TestValidatePathWithinRepo:
    """Tests for validate_path_within_repo function."""

    def test_accepts_relative_path_within_repo(self, repo_root: Path) -> None:
        """Relative paths that resolve within repo are accepted."""
        result = validate_path_within_repo(Path("CLAUDE.md"), repo_root=repo_root)
        assert result.is_relative_to(repo_root)
        assert result == repo_root / "CLAUDE.md"

    def test_accepts_nested_relative_path(self, repo_root: Path) -> None:
        """Nested relative paths within repo are accepted."""
        result = validate_path_within_repo(
            Path(".claude/skills/context-optimizer/scripts/path_validation.py"),
            repo_root=repo_root,
        )
        assert result.is_relative_to(repo_root)

    def test_accepts_dotdot_resolving_within_repo(self, repo_root: Path) -> None:
        """Paths with .. that still resolve within repo are accepted."""
        # .claude/../CLAUDE.md resolves to CLAUDE.md in repo root
        result = validate_path_within_repo(
            Path(".claude/../CLAUDE.md"), repo_root=repo_root
        )
        assert result.is_relative_to(repo_root)
        assert result == repo_root / "CLAUDE.md"

    def test_rejects_absolute_path_outside_repo(self, repo_root: Path) -> None:
        """Absolute paths outside repo are rejected."""
        with pytest.raises(PermissionError, match="Path traversal blocked"):
            validate_path_within_repo(Path("/etc/passwd"), repo_root=repo_root)

    def test_rejects_absolute_path_root(self, repo_root: Path) -> None:
        """Absolute path to filesystem root is rejected."""
        with pytest.raises(PermissionError, match="Path traversal blocked"):
            validate_path_within_repo(Path("/"), repo_root=repo_root)

    def test_rejects_dotdot_escaping_repo(self, repo_root: Path) -> None:
        """Paths with .. that escape the repo root are rejected."""
        # Build enough .. segments to escape any repo depth
        escape_path = Path("/".join([".."] * 20) + "/etc/passwd")
        with pytest.raises(PermissionError, match="Path traversal blocked"):
            validate_path_within_repo(escape_path, repo_root=repo_root)

    def test_rejects_symlink_outside_repo(
        self, repo_root: Path, temp_dir_outside_repo: Path
    ) -> None:
        """Symlinks pointing outside the repo are rejected."""
        # Create a target file outside repo
        target_file = temp_dir_outside_repo / "secret.txt"
        target_file.write_text("secret data")

        # Create a symlink inside the repo pointing to the external file
        symlink_path = repo_root / "test_symlink_for_cwe22"
        try:
            symlink_path.symlink_to(target_file)
            with pytest.raises(PermissionError, match="Path traversal blocked"):
                validate_path_within_repo(symlink_path, repo_root=repo_root)
        finally:
            # Clean up the symlink
            if symlink_path.is_symlink():
                symlink_path.unlink()

    def test_rejects_symlink_dir_outside_repo(
        self, repo_root: Path, temp_dir_outside_repo: Path
    ) -> None:
        """Symlink directories pointing outside repo are rejected."""
        symlink_dir = repo_root / "test_symlink_dir_for_cwe22"
        try:
            symlink_dir.symlink_to(temp_dir_outside_repo)
            # Try to access a file "through" the symlink directory
            traversal_path = symlink_dir / "some_file.txt"
            with pytest.raises(PermissionError, match="Path traversal blocked"):
                validate_path_within_repo(traversal_path, repo_root=repo_root)
        finally:
            if symlink_dir.is_symlink():
                symlink_dir.unlink()

    def test_accepts_absolute_path_within_repo(self, repo_root: Path) -> None:
        """Absolute paths within the repo are accepted."""
        abs_path = repo_root / "CLAUDE.md"
        result = validate_path_within_repo(abs_path, repo_root=repo_root)
        assert result == abs_path

    def test_auto_detects_repo_root(self) -> None:
        """When repo_root is None, it auto-detects via git."""
        # This test runs inside the repo, so it should work
        result = validate_path_within_repo(Path("CLAUDE.md"))
        assert result.name == "CLAUDE.md"

    def test_error_message_contains_paths(self, repo_root: Path) -> None:
        """Error message includes the attempted path and repo root for debugging."""
        with pytest.raises(PermissionError) as exc_info:
            validate_path_within_repo(Path("/etc/passwd"), repo_root=repo_root)

        error_msg = str(exc_info.value)
        assert "/etc/passwd" in error_msg
        assert str(repo_root) in error_msg


class TestEdgeCases:
    """Edge case tests for path validation."""

    def test_empty_relative_path(self, repo_root: Path) -> None:
        """Empty path (current directory equivalent) resolves within repo."""
        result = validate_path_within_repo(Path("."), repo_root=repo_root)
        assert result.is_relative_to(repo_root)

    def test_path_with_multiple_slashes(self, repo_root: Path) -> None:
        """Paths with redundant slashes are normalized and accepted."""
        result = validate_path_within_repo(
            Path(".claude///skills"), repo_root=repo_root
        )
        assert result.is_relative_to(repo_root)

    def test_path_with_dot_segments(self, repo_root: Path) -> None:
        """Paths with . segments are normalized and accepted."""
        result = validate_path_within_repo(
            Path("./.claude/./skills"), repo_root=repo_root
        )
        assert result.is_relative_to(repo_root)

    def test_deeply_nested_dotdot_within_repo(self, repo_root: Path) -> None:
        """Deep .. navigation that stays within repo is accepted."""
        # Go into .claude/skills then back to .claude
        result = validate_path_within_repo(
            Path(".claude/skills/../CLAUDE.md"), repo_root=repo_root
        )
        assert result.is_relative_to(repo_root)
