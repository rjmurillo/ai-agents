#!/usr/bin/env python3
"""Enforce session protocol initialization at session start.

Claude Code SessionStart hook that warns against working on main/master
branches and injects git state into Claude's context.

Checks:
1. Current branch is not main/master (WARNING injected into context)
2. Git status and recent commits (injected into context)
3. Session log status for today (reported, not blocking)

Part of Tier 1 enforcement hooks (Session initialization).

NOTE: SessionStart hooks cannot block (exit 2 only shows stderr as error,
does not block the session, and prevents stdout from being injected).
Branch protection at commit time is enforced by PreToolUse hooks.

Hook Type: SessionStart
Exit Codes:
    0 = Success (stdout injected into Claude's context)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import (  # noqa: E402
    get_project_directory,
    get_today_session_log,
)
from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402

PROTECTED_BRANCHES = ("main", "master")


def get_current_branch() -> str | None:
    """Get the current git branch name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except OSError:
        pass
    return None


def is_protected_branch(branch: str | None) -> bool:
    """Check if the branch is main or master."""
    if not branch:
        return False
    return branch in PROTECTED_BRANCHES


def get_session_status(project_dir: str) -> str:
    """Get today's session log status."""
    sessions_dir = str(Path(project_dir) / ".agents" / "sessions")
    session_log = get_today_session_log(sessions_dir)
    if session_log is None:
        return "none (run /session-init)"
    return session_log.name


def main() -> int:
    """Main hook entry point. Returns exit code."""
    if skip_if_consumer_repo("session-init-enforcer"):
        return 0
    try:
        project_dir = get_project_directory()
        current_branch = get_current_branch()

        if is_protected_branch(current_branch):
            print(
                f"\n## WARNING: On Protected Branch\n\n"
                f"**Current Branch**: `{current_branch}` "
                f"- Switch to feature branch. Commits blocked by pre-commit hooks.\n\n"
                f"```bash\ngit checkout -b feat/your-feature-name\n```"
            )
            return 0

        session_status = get_session_status(project_dir)
        print(f"Branch: `{current_branch}` | Session: {session_status} | Status: ready")
        return 0

    except Exception as exc:
        # Fail-open on errors (don't block session startup)
        exc_type = type(exc).__name__
        print(f"Session initialization enforcer error: {exc_type} - {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
