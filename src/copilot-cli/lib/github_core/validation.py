"""Canonical: scripts/github_core/validation.py. Sync via scripts/sync_plugin_lib.py."""

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
        name_type: Either "owner" or "repo" (case-insensitive).

    Returns:
        True if the name conforms to GitHub's rules.
    """
    if not name or not name.strip():
        return False

    normalized = name_type.lower()
    if normalized == "owner":
        return bool(_OWNER_PATTERN.match(name))
    if normalized == "repo":
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
            from .repo import get_repo_root

            repo_root = get_repo_root()
            allowed_base = str(repo_root) if repo_root is not None else os.getcwd()
        resolved_path = str(Path(path).resolve())
        resolved_base = str(Path(allowed_base).resolve())
        return resolved_path == resolved_base or resolved_path.startswith(
            resolved_base + os.sep
        )
    except (OSError, ValueError):
        return False


def _candidate_temp_roots() -> list[str]:
    """Return all temp-directory roots a mktemp-style command may use.

    macOS resolves TMPDIR to a per-user /var/folders/.../T/ path. mktemp -t
    may place files under /tmp or /private/tmp depending on PATH and shell.
    Linux GNU mktemp obeys TMPDIR consistently. Collect every plausible
    base so reply staging works under all shells.
    """
    import tempfile

    roots: list[str] = []
    seen: set[str] = set()
    for candidate in (
        os.environ.get("TMPDIR"),
        tempfile.gettempdir(),
        "/tmp",
        "/private/tmp",
    ):
        if not candidate:
            continue
        try:
            resolved = str(Path(candidate).resolve())
        except (OSError, ValueError):
            continue
        if resolved not in seen and Path(resolved).exists():
            seen.add(resolved)
            roots.append(resolved)
    return roots


def assert_valid_body_file(body_file: str, allowed_base: str | None = None) -> None:
    """Validate a body file parameter for safe file access.

    Raises SystemExit if the file does not exist or escapes the allowed base.

    When allowed_base is None, accepts paths within either the repo root or
    any plausible system temp directory (TMPDIR, tempfile.gettempdir(), /tmp,
    or /private/tmp). This supports temp-file-based reply staging on every
    shell.

    Args:
        body_file: The file path to validate.
        allowed_base: Optional base directory restriction.
    """
    from .api import error_and_exit  # lazy import to avoid cycle

    if not Path(body_file).exists():
        error_and_exit(f"Body file not found: {body_file}", 2)

    if allowed_base is not None:
        if not is_safe_file_path(body_file, allowed_base):
            error_and_exit(f"Body file path traversal not allowed: {body_file}", 2)
        return

    if is_safe_file_path(body_file, None):
        return

    for temp_root in _candidate_temp_roots():
        if is_safe_file_path(body_file, temp_root):
            return

    error_and_exit(f"Body file path traversal not allowed: {body_file}", 2)
