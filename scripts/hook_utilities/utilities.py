"""Shared utilities for Claude Code hook scripts.

Migrated from .claude/hooks/Common/HookUtilities.psm1 per issue #1053.
"""

from __future__ import annotations

import os
import re
import warnings
from pathlib import Path
from datetime import UTC, datetime

_GIT_COMMIT_PATTERN = re.compile(r"(?:^|\s)git\s+(commit|ci)")


def resolve_plugin_lib_dir(hook_file: str | Path | None = None) -> str | None:
    """Resolve the plugin lib directory for hook imports.

    Checks CLAUDE_PLUGIN_ROOT environment variable first, then walks up
    from the hook file location looking for .claude-plugin/plugin.json
    (the plugin manifest marker). The sibling lib/ is the plugin's lib dir.

    Args:
        hook_file: Path to the hook file (__file__). If None, uses the
            calling module's __file__ via stack inspection.

    Returns:
        Absolute path to the lib directory as a string, or None if not found.
        Caller should handle None appropriately (e.g., sys.exit with hook-
        specific exit code).

    Example:
        _lib_dir = resolve_plugin_lib_dir(__file__)
        if _lib_dir is None or not os.path.isdir(_lib_dir):
            print("Plugin lib directory not found", file=sys.stderr)
            sys.exit(2)  # or 0 for non-blocking hooks
        if _lib_dir not in sys.path:
            sys.path.insert(0, _lib_dir)
    """
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        return str(Path(plugin_root).resolve() / "lib")

    if hook_file is None:
        import inspect
        frame = inspect.currentframe()
        if frame is not None and frame.f_back is not None:
            hook_file = frame.f_back.f_globals.get("__file__")
        if hook_file is None:
            return None

    cur = Path(hook_file).resolve().parent
    while True:
        if (cur / ".claude-plugin" / "plugin.json").is_file():
            return str(cur / "lib")
        if cur.parent == cur:
            break
        cur = cur.parent

    return None
_GIT_PUSH_PATTERN = re.compile(r"(?:^|\s)git\s+push(?:\s|$)")
# M7-T3: `gh pr create` dispatches to session_log_guard alongside `git commit`.
# Hooks registered for both commands need to recognize both.
_GH_PR_CREATE_PATTERN = re.compile(r"(?:^|\s)gh\s+pr\s+create\b")
_DATE_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}")


def get_project_directory() -> str:
    """Resolve the project root directory. Never returns None."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        return str(Path(env_dir).resolve())

    # Walk up from cwd looking for .git
    try:
        current = Path.cwd().resolve()
        while True:
            if (current / ".git").exists():
                return str(current)
            parent = current.parent
            if parent == current:
                break
            current = parent
    except OSError as exc:
        warnings.warn(
            f"Failed to locate project directory: {exc}. Using current directory as fallback.",
            stacklevel=2,
        )
        return str(Path.cwd())

    warnings.warn(
        "Project root (.git directory) not found. Using current directory as fallback.",
        stacklevel=2,
    )
    return str(Path.cwd())


def is_git_commit_command(command: str | None) -> bool:
    """Check if a command string is a git commit or git ci command."""
    if not command:
        return False
    return _GIT_COMMIT_PATTERN.search(command) is not None


def is_git_push_command(command: str | None) -> bool:
    """Check if a command string is a git push command."""
    if not command:
        return False
    return _GIT_PUSH_PATTERN.search(command) is not None


def is_git_commit_or_push_command(command: str | None) -> bool:
    """Check if a command string is a git commit, ci, or push command."""
    return is_git_commit_command(command) or is_git_push_command(command)


def is_pr_create_command(command: str | None) -> bool:
    """Check if a command string creates a GitHub pull request via the gh CLI.

    M7-T3: hooks registered for both `Bash(git commit*)` and the
    pr-creation matcher need to recognize both. Without this, the
    pr-creation copy of session_log_guard fires its shim correctly but
    the body returns immediately because it only checked git commit.
    """
    if not command:
        return False
    return _GH_PR_CREATE_PATTERN.search(command) is not None


def is_session_logged_command(command: str | None) -> bool:
    """True for any command that requires a session log to exist (git commit or pr create).

    Aggregates :func:`is_git_commit_command` and :func:`is_pr_create_command`
    so multi-matcher hooks have a single predicate to call regardless of
    which matcher fired the shim.
    """
    return is_git_commit_command(command) or is_pr_create_command(command)


def get_today_session_log(sessions_dir: str, date: str | None = None) -> Path | None:
    """Find the most recent session log for the given date.

    Returns the path with the latest modification time, or None if no logs found.
    """
    if date is None:
        date = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    elif not _DATE_FORMAT.fullmatch(date):
        msg = f"Invalid date format: {date!r}. Expected YYYY-MM-DD."
        raise ValueError(msg)

    sessions_path = Path(sessions_dir)
    if not sessions_path.is_dir():
        warnings.warn(f"Session directory not found: {sessions_dir}", stacklevel=2)
        return None

    try:
        logs = sorted(
            sessions_path.glob(f"{date}-session-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError as exc:
        warnings.warn(
            f"Failed to read session logs from {sessions_dir}: {exc}",
            stacklevel=2,
        )
        return None

    if not logs:
        return None
    return logs[0]


def get_today_session_logs(sessions_dir: str) -> list[Path]:
    """Find all session logs for today's date."""
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    sessions_path = Path(sessions_dir)
    if not sessions_path.is_dir():
        warnings.warn(f"Session directory not found: {sessions_dir}", stacklevel=2)
        return []

    try:
        return list(sessions_path.glob(f"{today}-session-*.json"))
    except OSError as exc:
        warnings.warn(
            f"Failed to read session logs from {sessions_dir}: {exc}",
            stacklevel=2,
        )
        return []
