"""Input validation functions for GitHub operations (CWE-22/CWE-78 prevention)."""

from __future__ import annotations

import os
import re
from pathlib import Path

# Owner: alphanumeric + hyphens, 1-39 chars, cannot start/end with hyphen
_OWNER_PATTERN = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$")

# Repo: alphanumeric, hyphens, underscores, periods, 1-100 chars
_REPO_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{1,100}$")

_TRAVERSAL_PATTERN = re.compile(r"\.\.[/\\]")


def is_github_name_valid(name: str, name_type: str) -> bool:
    """Validate a GitHub owner or repository name.

    Prevents command injection (CWE-78) by enforcing GitHub naming rules.

    Args:
        name: The name to validate.
        name_type: Either "Owner" or "Repo".

    Returns:
        True if the name conforms to GitHub's rules.
    """
    if not name or not name.strip():
        return False

    if name_type == "Owner":
        return bool(_OWNER_PATTERN.match(name))
    if name_type == "Repo":
        return bool(_REPO_PATTERN.match(name))

    return False


def is_safe_file_path(path: str, allowed_base: str | None = None) -> bool:
    """Validate that a file path does not traverse outside allowed boundaries.

    Prevents path traversal attacks (CWE-22).

    Args:
        path: The file path to validate.
        allowed_base: Base directory paths must stay within. Defaults to cwd.

    Returns:
        True if the resolved path stays within the allowed base.
    """
    if _TRAVERSAL_PATTERN.search(path):
        return False

    try:
        if allowed_base is None:
            allowed_base = os.getcwd()
        resolved_path = str(Path(path).resolve())
        resolved_base = str(Path(allowed_base).resolve())
        return resolved_path.startswith(resolved_base)
    except (OSError, ValueError):
        return False


def assert_valid_body_file(body_file: str, allowed_base: str | None = None) -> None:
    """Validate a body file parameter for safe file access.

    Raises SystemExit if the file does not exist or escapes the allowed base.

    Args:
        body_file: The file path to validate.
        allowed_base: Optional base directory restriction.
    """
    from scripts.github_core.api import error_and_exit  # lazy import to avoid cycle

    if not Path(body_file).exists():
        error_and_exit(f"Body file not found: {body_file}", 2)

    if allowed_base and not is_safe_file_path(body_file, allowed_base):
        error_and_exit(f"Body file path traversal not allowed: {body_file}", 1)
