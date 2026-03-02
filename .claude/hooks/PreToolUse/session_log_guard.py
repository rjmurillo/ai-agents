#!/usr/bin/env python3
"""PreToolUse hook that blocks git commit without session log evidence.

Prevents untracked work by requiring a session log for the current date.

Checks:
1. Command is git commit (or git ci alias)
2. Session log exists for today in .agents/sessions/
3. Session log contains work evidence (non-empty, valid structure)

Part of Tier 2 enforcement hooks (Issue #773, Session tracking).

Hook Type: PreToolUse
Exit Codes:
    0 = Allow (not a commit, or session log exists with evidence)
    2 = Block (commit without session log or with insufficient evidence)

See: .agents/SESSION-PROTOCOL.md
"""

import json
import os
import re
import sys
from datetime import date
from pathlib import Path


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


def is_git_commit_command(command: str) -> bool:
    """Test if a command string is a git commit command.

    Matches both 'git commit' and 'git ci' (common alias).
    """
    if not command or not command.strip():
        return False
    return bool(re.search(r"(?:^|\s)git\s+(commit|ci)", command))


def get_today_session_log(sessions_dir: str, today: str) -> str | None:
    """Find the most recent session log for a specific date.

    Args:
        sessions_dir: Path to the .agents/sessions directory.
        today: Date string in YYYY-MM-DD format.

    Returns:
        Full path to the most recent session log, or None if not found.
    """
    sessions_path = Path(sessions_dir)
    if not sessions_path.is_dir():
        return None

    pattern = f"{today}-session-*.json"
    logs = sorted(sessions_path.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not logs:
        return None
    return str(logs[0])


def check_session_log_evidence(session_log_path: str) -> dict:
    """Validate session log has substantial content.

    Returns:
        Dict with 'valid' bool and either 'content' preview or 'reason' for failure.
    """
    try:
        with open(session_log_path, encoding="utf-8") as f:
            content = f.read()
    except PermissionError:
        return {
            "valid": False,
            "reason": "Session log is locked or you lack permissions. Close editors and retry.",
        }
    except FileNotFoundError:
        return {
            "valid": False,
            "reason": "Session log was deleted after detection. Create a new session log.",
        }
    except (ValueError, OSError):
        return {
            "valid": False,
            "reason": "Error reading session log. Check file format or recreate.",
        }

    if len(content) < 100:
        return {"valid": False, "reason": "Session log exists but is empty"}

    # Optionally validate JSON structure
    try:
        data = json.loads(content)
        if isinstance(data, dict) and len(data) < 2:
            return {"valid": False, "reason": "Session log lacks required sections"}
    except (json.JSONDecodeError, ValueError):
        # Not JSON is acceptable (could be markdown log)
        pass

    preview_length = min(200, len(content))
    return {"valid": True, "content": content[:preview_length]}


def main() -> int:
    """Main hook execution."""
    try:
        # Compute date once to avoid midnight race condition
        today = date.today().isoformat()

        # Read JSON input from stdin
        if sys.stdin.isatty():
            return 0

        input_text = sys.stdin.read()
        if not input_text or not input_text.strip():
            return 0

        hook_input = json.loads(input_text)

        # Extract command from tool_input
        tool_input = hook_input.get("tool_input")
        if not tool_input or not isinstance(tool_input, dict):
            return 0

        command = tool_input.get("command")
        if not command:
            return 0

        # Test if this is a git commit command
        if not is_git_commit_command(command):
            return 0

        # Check for session log
        project_dir = get_project_directory()
        sessions_dir = os.path.join(project_dir, ".agents", "sessions")
        session_log = get_today_session_log(sessions_dir, today)

        if session_log is None:
            output = f"""
## BLOCKED: No Session Log Found

**YOU MUST create a session log before committing.**

### Why Session Logs Matter
- Evidence of work performed
- Compliance tracking (ADR-007, ADR-033)
- Context for future sessions
- Audit trail for peer review

### How to Create a Session Log

**Option 1: Use /session-init skill**
```
/session-init
```

**Option 2: Create manually**
```bash
python3 scripts/sessions/initialize_session_log.py
```

Session logs go in: `.agents/sessions/{today}-session-NN.json`

**Current Date**: {today}
**Sessions Directory**: {sessions_dir}

See: `.agents/SESSION-PROTOCOL.md` for full details.
"""
            print(output)
            print(
                "Session blocked: No session log found for today",
                file=sys.stderr,
            )
            return 2

        # Validate session log has content
        evidence = check_session_log_evidence(session_log)

        if not evidence["valid"]:
            log_name = os.path.basename(session_log)
            output = f"""
## BLOCKED: Session Log Empty or Invalid

**Reason**: {evidence['reason']}

### Fix

Edit the session log and add substantial work evidence:

```
{session_log}
```

Session log MUST contain:
- Timestamp of work
- Description of tasks performed
- Tool usage evidence
- Key decisions made

**Current Session Log**: {log_name}
"""
            print(output)
            print(
                "Session blocked: Session log has insufficient evidence",
                file=sys.stderr,
            )
            return 2

        # Session log valid, allow commit
        return 0

    except Exception as exc:
        # Fail-open on errors (don't block on infrastructure issues)
        print(f"Session log guard error: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
