"""Input validation utilities for GitHub operations.

Prevents CWE-78 (command injection) and CWE-22 (path traversal).
"""

import os
import re


def test_github_name_valid(name: str, name_type: str) -> bool:
    """Validate GitHub owner or repository names.

    Args:
        name: The name to validate.
        name_type: Either "owner" or "repo".

    Returns:
        True if the name is valid per GitHub naming rules.
    """
    if not name or not name.strip():
        return False

    patterns = {
        "owner": r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$",
        "repo": r"^[a-zA-Z0-9._-]{1,100}$",
    }

    pattern = patterns.get(name_type.lower())
    if not pattern:
        return False

    return bool(re.match(pattern, name))


def test_safe_file_path(path: str, allowed_base: str | None = None) -> bool:
    """Validate that a file path does not traverse outside allowed boundaries.

    Prevents path traversal attacks (CWE-22).

    Args:
        path: The file path to validate.
        allowed_base: The base directory. Defaults to CWD.

    Returns:
        True if the path stays within the allowed base.
    """
    if ".." in path.replace("\\", "/").split("/"):
        return False

    if allowed_base is None:
        allowed_base = os.getcwd()

    resolved_path = os.path.realpath(path)
    resolved_base = os.path.realpath(allowed_base)

    return resolved_path.startswith(resolved_base + os.sep) or resolved_path == resolved_base
