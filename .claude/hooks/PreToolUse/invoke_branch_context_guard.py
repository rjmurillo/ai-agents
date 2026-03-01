#!/usr/bin/env python3
"""Verify git branch matches session context before commit/push.

Claude Code PreToolUse hook that intercepts git commit/push commands and
verifies the current branch matches the expected branch from the session log.
Prevents cross-PR contamination by catching branch mismatches.

Root cause addressed: PR co-mingling from PR #669 retrospective.

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (branch matches or no session context)
    2 = Block (branch mismatch detected)
"""

from __future__ import annotations

import json
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
    sys.exit(0)  # Fail open on config issues
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import (  # noqa: E402
    get_project_directory,
    get_today_session_log,
    is_git_commit_or_push_command,
)


def get_current_branch(cwd: str) -> str | None:
    """Get the current git branch name."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def get_session_branch(session_log_path: Path) -> str | None:
    """Extract the expected branch from session log JSON."""
    try:
        content = session_log_path.read_text(encoding="utf-8")
        data = json.loads(content)
        # Session logs store branch at top level
        if isinstance(data, dict):
            return data.get("branch")
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(
            f"branch_context_guard: Error reading session log '{session_log_path}': {exc}",
            file=sys.stderr,
        )
    return None


def write_block_response(reason: str) -> None:
    """Write a JSON block response to stdout."""
    response = json.dumps({"decision": "block", "reason": reason})
    print(response)


def main() -> int:
    """Main hook entry point. Returns exit code."""
    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)

        tool_input = hook_input.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0
        command = tool_input.get("command")
        if not command:
            return 0

        # Only check for git commit/push commands
        if not is_git_commit_or_push_command(command):
            return 0

        project_dir = get_project_directory()
        sessions_dir = os.path.join(project_dir, ".agents", "sessions")

        # Skip if no sessions directory (consumer repo)
        if not os.path.isdir(sessions_dir):
            return 0

        # Get current branch
        current_branch = get_current_branch(project_dir)
        if not current_branch:
            # Cannot determine branch, fail open
            print(
                "branch_context_guard: Cannot determine current branch, skipping check",
                file=sys.stderr,
            )
            return 0

        # Get session log
        session_log = get_today_session_log(sessions_dir)
        if session_log is None:
            # No session log, let session_log_guard handle this
            return 0

        # Get expected branch from session
        session_branch = get_session_branch(session_log)
        if not session_branch:
            # No branch in session log, skip check
            return 0

        # Compare branches
        if current_branch != session_branch:
            output = f"""
## BLOCKED: Branch Mismatch Detected

**Current branch**: `{current_branch}`
**Session expects**: `{session_branch}`

### Why This Matters
Branch mismatch can cause cross-PR contamination. This happens when:
- You switched branches mid-session without updating the session log
- The session was created for a different PR
- A previous operation left the repo on the wrong branch

### How to Fix

**Option 1: Switch to the expected branch**
```bash
git checkout {session_branch}
```

**Option 2: Update session log to current branch**
Edit `{session_log.name}` and set `"branch": "{current_branch}"`

**Option 3: Start a new session**
Run `/session-init` to create a session for the current branch.

### Evidence
- Session log: `{session_log.name}`
- Current time: now
- Command blocked: `{command[:50] + "..." if len(command) > 50 else command}`

### Related
- PR #669: Root cause analysis of branch co-mingling
- Issue #682: This verification hook
"""
            print(output)
            write_block_response(
                f"Branch mismatch: current='{current_branch}', session='{session_branch}'"
            )
            return 2

        return 0

    except Exception as exc:
        # Fail open on errors
        print(
            f"branch_context_guard error: {type(exc).__name__} - {exc}",
            file=sys.stderr,
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
