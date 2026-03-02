#!/usr/bin/env python3
"""SessionStart hook that enforces session protocol initialization.

Warns against working on main/master branches and injects git state into
Claude's context at session start.

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

See: .agents/SESSION-PROTOCOL.md
"""

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path


PROTECTED_BRANCHES = ("main", "master")


def get_project_directory() -> str:
    """Resolve the project root directory.

    Checks CLAUDE_PROJECT_DIR env var first, then walks up from cwd to find .git.
    Falls back to cwd if project root cannot be determined.
    """
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        return env_dir

    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return str(current)
        current = current.parent

    return str(Path.cwd())


def get_current_branch() -> str | None:
    """Get the current git branch name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def is_protected_branch(branch: str | None) -> bool:
    """Check if branch is main or master."""
    if not branch or not branch.strip():
        return False
    return branch.strip() in PROTECTED_BRANCHES


def get_git_status() -> str:
    """Get short git status output."""
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip() if result.stdout.strip() else "(clean)"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return "(unable to get git status)"


def get_recent_commits(count: int = 3) -> str:
    """Get recent git commits in oneline format."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-n", str(count)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return "(unable to get recent commits)"


def get_today_session_log(sessions_dir: str) -> str | None:
    """Find the most recent session log for today.

    Returns the filename of the session log, or None.
    """
    sessions_path = Path(sessions_dir)
    if not sessions_path.is_dir():
        return None

    today = date.today().isoformat()
    logs = sorted(
        sessions_path.glob(f"{today}-session-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not logs:
        return None
    return logs[0].name


def format_protected_branch_warning(branch: str) -> str:
    """Format warning for protected branch."""
    return f"""
## WARNING: On Protected Branch

**Switch to a feature branch before making changes.**

**Current Branch**: `{branch}`

Direct commits to main/master are blocked by pre-commit hooks.
Create or switch to a feature branch:

```bash
git checkout -b feat/your-feature-name
```

### REMINDER: Skill-First Pattern + Retrieval-Led Reasoning

**Before using raw git/gh commands, check if a skill exists:**
- Git operations: Check `.claude/skills/git-*/`
- GitHub operations: Check `.claude/skills/github/` (mandatory per usage-mandatory memory)
- Prefer retrieval-led reasoning: Read skill documentation, don't rely on pre-training

**Process:**
1. Identify operation type (PR creation, merge, etc.)
2. Check SKILL-QUICK-REF.md for corresponding skill
3. Read skill's SKILL.md for current, tested patterns
4. Use skill instead of raw commands
"""


def format_session_status(
    branch: str, session_log_name: str | None, git_status: str, recent_commits: str
) -> str:
    """Format the session initialization status output."""
    if session_log_name:
        log_status = f"Session log exists: {session_log_name}"
    else:
        log_status = "No session log found for today"

    next_step = (
        "Continue with work"
        if session_log_name
        else "Create session log with /session-init or initialize_session_log.py"
    )

    return f"""
## Session Initialization Status

**Current Branch**: `{branch}`
**Session Log**: {log_status}

### Git Status
```
{git_status}
```

### Recent Commits
```
{recent_commits}
```

---

**Session Start Hook**: Completed successfully
**Branch Protection**: Passed (not on main/master)
**Next Step**: {next_step}
"""


def main() -> int:
    """Main hook execution. Always returns 0."""
    try:
        project_dir = get_project_directory()
        current_branch = get_current_branch()

        # Check if on protected branch
        if is_protected_branch(current_branch):
            print(format_protected_branch_warning(current_branch))
            return 0

        # Inject git state into context
        git_status = get_git_status()
        recent_commits = get_recent_commits()

        # Check for session log
        sessions_dir = os.path.join(project_dir, ".agents", "sessions")
        session_log_name = get_today_session_log(sessions_dir)

        branch_display = current_branch if current_branch else "(unknown)"
        print(
            format_session_status(
                branch_display, session_log_name, git_status, recent_commits
            )
        )
        return 0

    except Exception as exc:
        # Fail-open on errors (don't block session startup)
        print(f"Session initialization enforcer error: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
