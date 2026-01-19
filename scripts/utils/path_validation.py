"""Path validation utilities for CWE-22 protection.

This module provides secure path validation to prevent path traversal attacks.
All user-provided paths should be validated using these utilities before use.

Reference: ADR-042 Phase 2 Security Controls
"""

from __future__ import annotations

import re
from pathlib import Path

# Pattern for safe filenames: alphanumeric, underscore, hyphen, dot
SAFE_FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")


def validate_safe_path(path: str | Path, base_dir: str | Path) -> Path:
    """Validate that a path is safe and within the base directory.

    This function resolves both the input path and base directory to their
    canonical forms, then verifies the resolved path is a child of the base
    directory. This prevents path traversal attacks using "..", symlinks,
    or other techniques.

    Args:
        path: The path to validate. Can be relative or absolute.
        base_dir: The base directory that path must be within.

    Returns:
        Resolved Path object that is guaranteed to be within base_dir.

    Raises:
        ValueError: If path is outside base_dir or contains invalid characters.
        FileNotFoundError: If base_dir does not exist.

    Example:
        >>> project_root = Path("/home/user/project")
        >>> safe = validate_safe_path("data/config.json", project_root)
        >>> str(safe)
        '/home/user/project/data/config.json'

        >>> validate_safe_path("../etc/passwd", project_root)
        ValueError: Path ../etc/passwd is outside base directory
    """
    resolved_base = Path(base_dir).resolve()

    if not resolved_base.exists():
        raise FileNotFoundError(f"Base directory does not exist: {base_dir}")

    if not resolved_base.is_dir():
        raise ValueError(f"Base path is not a directory: {base_dir}")

    # Resolve the path relative to base_dir
    resolved_path = (resolved_base / path).resolve()

    # Check if resolved path is within base directory
    # Use string comparison after resolving to handle edge cases
    try:
        resolved_path.relative_to(resolved_base)
    except ValueError:
        raise ValueError(
            f"Path {path} is outside base directory {base_dir}"
        ) from None

    return resolved_path


def is_safe_filename(filename: str) -> bool:
    """Check if a filename is safe (no path traversal characters).

    A safe filename:
    - Contains only alphanumeric characters, underscore, hyphen, or dot
    - Does not contain path separators (/ or \\)
    - Does not contain ".." sequences

    Args:
        filename: The filename to check.

    Returns:
        True if safe, False otherwise.

    Example:
        >>> is_safe_filename("config.json")
        True
        >>> is_safe_filename("../secret.txt")
        False
        >>> is_safe_filename("file with spaces.txt")
        False
    """
    if not filename:
        return False

    if ".." in filename:
        return False

    if "/" in filename or "\\" in filename:
        return False

    return bool(SAFE_FILENAME_PATTERN.match(filename))


def validate_filename(filename: str) -> str:
    """Validate and return a safe filename.

    Args:
        filename: The filename to validate.

    Returns:
        The validated filename.

    Raises:
        ValueError: If the filename is unsafe.

    Example:
        >>> validate_filename("config.json")
        'config.json'
        >>> validate_filename("../etc/passwd")
        ValueError: Unsafe filename: ../etc/passwd
    """
    if not is_safe_filename(filename):
        raise ValueError(f"Unsafe filename: {filename}")
    return filename


def sanitize_path_component(component: str) -> str:
    """Sanitize a single path component by removing unsafe characters.

    This function removes characters that could be used for path traversal
    or that are invalid in filenames on common filesystems.

    Args:
        component: A single path component (not a full path).

    Returns:
        Sanitized string with unsafe characters removed.

    Example:
        >>> sanitize_path_component("my..file")
        'myfile'
        >>> sanitize_path_component("config/secret")
        'configsecret'
    """
    # Remove path separators
    result = component.replace("/", "").replace("\\", "")

    # Remove .. sequences
    while ".." in result:
        result = result.replace("..", "")

    # Remove leading/trailing dots and spaces
    result = result.strip(". ")

    return result
