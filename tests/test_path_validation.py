"""Tests for path validation utilities.

These tests verify the security controls for CWE-22 (Path Traversal) protection.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.utils.path_validation import (
    is_safe_filename,
    sanitize_path_component,
    validate_filename,
    validate_safe_path,
)


class TestValidateSafePath:
    """Tests for validate_safe_path function."""

    def test_valid_relative_path(self, tmp_path: Path) -> None:
        """Valid relative path within base directory is accepted."""
        subdir = tmp_path / "data"
        subdir.mkdir()
        test_file = subdir / "config.json"
        test_file.touch()

        result = validate_safe_path("data/config.json", tmp_path)

        assert result == test_file.resolve()

    def test_valid_nested_path(self, tmp_path: Path) -> None:
        """Deeply nested path within base directory is accepted."""
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        test_file = nested / "file.txt"
        test_file.touch()

        result = validate_safe_path("a/b/c/file.txt", tmp_path)

        assert result == test_file.resolve()

    def test_path_traversal_attack_rejected(self, tmp_path: Path) -> None:
        """Path with .. traversal outside base directory is rejected."""
        with pytest.raises(ValueError, match="outside base directory"):
            validate_safe_path("../etc/passwd", tmp_path)

    def test_double_dot_in_middle_rejected(self, tmp_path: Path) -> None:
        """Path with .. in middle escaping base directory is rejected."""
        subdir = tmp_path / "data"
        subdir.mkdir()

        with pytest.raises(ValueError, match="outside base directory"):
            validate_safe_path("data/../../etc/passwd", tmp_path)

    def test_absolute_path_outside_base_rejected(self, tmp_path: Path) -> None:
        """Absolute path outside base directory is rejected."""
        with pytest.raises(ValueError, match="outside base directory"):
            validate_safe_path("/etc/passwd", tmp_path)

    def test_base_directory_not_exist(self, tmp_path: Path) -> None:
        """Non-existent base directory raises FileNotFoundError."""
        fake_base = tmp_path / "nonexistent"

        with pytest.raises(FileNotFoundError, match="does not exist"):
            validate_safe_path("file.txt", fake_base)

    def test_base_is_file_not_directory(self, tmp_path: Path) -> None:
        """Base path that is a file raises ValueError."""
        base_file = tmp_path / "basefile.txt"
        base_file.touch()

        with pytest.raises(ValueError, match="not a directory"):
            validate_safe_path("file.txt", base_file)

    def test_symlink_escape_rejected(self, tmp_path: Path) -> None:
        """Symlink pointing outside base directory is rejected."""
        # Create a symlink pointing outside the base
        symlink = tmp_path / "escape"
        try:
            symlink.symlink_to("/etc")
        except OSError:
            pytest.skip("Cannot create symlinks on this system")

        with pytest.raises(ValueError, match="outside base directory"):
            validate_safe_path("escape/passwd", tmp_path)

    def test_path_with_null_byte_rejected(self, tmp_path: Path) -> None:
        """Path containing null byte raises appropriate error."""
        # Null bytes in paths are often used in attacks
        with pytest.raises((ValueError, OSError)):
            validate_safe_path("file\x00.txt", tmp_path)

    def test_empty_path_returns_base(self, tmp_path: Path) -> None:
        """Empty path returns the base directory itself."""
        result = validate_safe_path("", tmp_path)

        assert result == tmp_path.resolve()

    def test_dot_path_returns_base(self, tmp_path: Path) -> None:
        """Single dot path returns the base directory."""
        result = validate_safe_path(".", tmp_path)

        assert result == tmp_path.resolve()

    def test_accepts_path_object(self, tmp_path: Path) -> None:
        """Function accepts Path objects as well as strings."""
        subdir = tmp_path / "data"
        subdir.mkdir()

        result = validate_safe_path(Path("data"), tmp_path)

        assert result == subdir.resolve()


class TestIsSafeFilename:
    """Tests for is_safe_filename function."""

    @pytest.mark.parametrize(
        "filename",
        [
            "config.json",
            "file.txt",
            "data_2024.csv",
            "my-file.md",
            "file123.py",
            "a",
            "123",
            "test.tar.gz",
        ],
    )
    def test_safe_filenames_accepted(self, filename: str) -> None:
        """Valid safe filenames return True."""
        assert is_safe_filename(filename) is True

    @pytest.mark.parametrize(
        "filename",
        [
            "../secret.txt",
            "..\\secret.txt",
            "path/to/file.txt",
            "path\\to\\file.txt",
            "file with spaces.txt",
            "file\ttab.txt",
            "",
            "..",
            "../../etc/passwd",
        ],
    )
    def test_unsafe_filenames_rejected(self, filename: str) -> None:
        """Unsafe filenames return False."""
        assert is_safe_filename(filename) is False

    def test_hidden_files_accepted(self) -> None:
        """Files starting with dot are accepted if otherwise safe."""
        # Single dot at start is fine for hidden files
        assert is_safe_filename(".gitignore") is True
        assert is_safe_filename(".env") is True

    def test_unicode_rejected(self) -> None:
        """Unicode characters outside safe set are rejected."""
        # Non-ASCII characters can cause issues
        assert is_safe_filename("file\u200b.txt") is False  # Zero-width space
        assert is_safe_filename("file\u0000.txt") is False  # Null byte


class TestValidateFilename:
    """Tests for validate_filename function."""

    def test_valid_filename_returned(self) -> None:
        """Valid filename is returned unchanged."""
        result = validate_filename("config.json")

        assert result == "config.json"

    def test_unsafe_filename_raises(self) -> None:
        """Unsafe filename raises ValueError."""
        with pytest.raises(ValueError, match="Unsafe filename"):
            validate_filename("../etc/passwd")

    def test_path_separator_raises(self) -> None:
        """Filename with path separator raises ValueError."""
        with pytest.raises(ValueError, match="Unsafe filename"):
            validate_filename("path/file.txt")


class TestSanitizePathComponent:
    """Tests for sanitize_path_component function."""

    def test_removes_forward_slash(self) -> None:
        """Forward slashes are removed."""
        assert sanitize_path_component("path/file") == "pathfile"

    def test_removes_backslash(self) -> None:
        """Backslashes are removed."""
        assert sanitize_path_component("path\\file") == "pathfile"

    def test_removes_double_dots(self) -> None:
        """Double dot sequences are removed."""
        assert sanitize_path_component("..file") == "file"
        assert sanitize_path_component("my..file") == "myfile"

    def test_removes_leading_trailing_dots(self) -> None:
        """Leading and trailing dots are stripped."""
        assert sanitize_path_component(".hidden.") == "hidden"
        assert sanitize_path_component("...test...") == "test"

    def test_removes_leading_trailing_spaces(self) -> None:
        """Leading and trailing spaces are stripped."""
        assert sanitize_path_component("  file  ") == "file"

    def test_complex_attack_string(self) -> None:
        """Complex attack strings are sanitized."""
        attack = "../../../etc/passwd"
        result = sanitize_path_component(attack)

        assert ".." not in result
        assert "/" not in result

    def test_empty_string_unchanged(self) -> None:
        """Empty string returns empty string."""
        assert sanitize_path_component("") == ""

    def test_safe_string_unchanged(self) -> None:
        """Already safe strings are returned unchanged."""
        assert sanitize_path_component("config") == "config"
        assert sanitize_path_component("my-file") == "my-file"
