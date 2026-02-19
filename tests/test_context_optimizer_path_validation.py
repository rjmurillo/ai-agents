"""Tests for context-optimizer path validation (CWE-22 repo-root anchoring).

Verifies that the validate_path_within_repo function properly prevents
path traversal attacks by anchoring validation to the repository root.
"""

from __future__ import annotations

import subprocess

# Import from the context-optimizer scripts directory
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
        / ".claude"
        / "skills"
        / "context-optimizer"
        / "scripts"
    ),
)
from path_validation import get_repo_root, validate_path_within_repo


class TestGetRepoRoot:
    """Tests for get_repo_root function."""

    def test_returns_path_in_git_repo(self) -> None:
        """Returns a valid Path when inside a git repository."""
        result = get_repo_root()
        assert isinstance(result, Path)
        assert result.exists()
        assert (result / ".git").exists()

    def test_raises_when_git_unavailable(self) -> None:
        """Raises RuntimeError when git is not available."""
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            with pytest.raises(RuntimeError, match="Unable to determine repository root"):
                get_repo_root()

    def test_raises_when_not_in_repo(self) -> None:
        """Raises RuntimeError when not inside a git repository."""
        with patch(
            "subprocess.run", side_effect=subprocess.CalledProcessError(128, "git")
        ):
            with pytest.raises(RuntimeError, match="Unable to determine repository root"):
                get_repo_root()


class TestValidatePathWithinRepo:
    """Tests for validate_path_within_repo function."""

    @pytest.fixture()
    def repo_root(self) -> Path:
        """Get the actual repo root for testing."""
        return get_repo_root()

    def test_valid_relative_path(self, repo_root: Path) -> None:
        """Valid relative path within repo is accepted."""
        result = validate_path_within_repo(Path("README.md"), repo_root=repo_root)
        assert result.is_relative_to(repo_root)

    def test_valid_nested_path(self, repo_root: Path) -> None:
        """Nested relative path within repo is accepted."""
        result = validate_path_within_repo(
            Path(".claude/skills/context-optimizer/SKILL.md"), repo_root=repo_root
        )
        assert result.is_relative_to(repo_root)

    def test_absolute_path_outside_repo_rejected(self, repo_root: Path) -> None:
        """Absolute path outside repository root is rejected."""
        with pytest.raises(PermissionError, match="Path traversal blocked"):
            validate_path_within_repo(Path("/etc/passwd"), repo_root=repo_root)

    def test_traversal_outside_repo_rejected(self, repo_root: Path) -> None:
        """Path with .. components escaping repo root is rejected."""
        with pytest.raises(PermissionError, match="Path traversal blocked"):
            validate_path_within_repo(
                Path("../../../../../../etc/passwd"), repo_root=repo_root
            )

    def test_dot_dot_resolving_within_repo_accepted(self, repo_root: Path) -> None:
        """Path with .. that still resolves within repo is accepted."""
        result = validate_path_within_repo(
            Path("src/../README.md"), repo_root=repo_root
        )
        assert result.is_relative_to(repo_root)

    def test_symlink_outside_repo_rejected(self, repo_root: Path, tmp_path: Path) -> None:
        """Symlink pointing outside repo root is rejected."""
        external_dir = tmp_path / "external"
        external_dir.mkdir()
        external_file = external_dir / "secret.txt"
        external_file.write_text("secret")

        symlink = repo_root / "test_symlink_escape"
        try:
            symlink.symlink_to(external_dir)
            with pytest.raises(PermissionError, match="Path traversal blocked"):
                validate_path_within_repo(
                    Path("test_symlink_escape/secret.txt"), repo_root=repo_root
                )
        except OSError:
            pytest.skip("Cannot create symlinks on this system")
        finally:
            if symlink.exists() or symlink.is_symlink():
                symlink.unlink()

    def test_current_directory_accepted(self, repo_root: Path) -> None:
        """Current directory (.) resolves to repo root and is accepted."""
        result = validate_path_within_repo(Path("."), repo_root=repo_root)
        assert result == repo_root

    def test_auto_detects_repo_root(self) -> None:
        """When repo_root is None, auto-detects via git."""
        result = validate_path_within_repo(Path("README.md"))
        assert result.exists()
        assert result.name == "README.md"
