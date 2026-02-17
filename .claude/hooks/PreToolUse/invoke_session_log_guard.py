#!/usr/bin/env python3
"""Block git commit without session log evidence.

Claude Code PreToolUse hook that enforces session logging before commits.
Prevents untracked work by requiring a session log for the current date.

Checks:
1. Command is git commit
2. Session log exists for today in .agents/sessions/
3. Session log has >= 100 characters and, if JSON, has >= 2 properties

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (not commit, or log exists with evidence)
    2 = Block (commit without session log or with empty log)
"""

from __future__ import annotations

import os
import sys

# Plugin mode: skip project-specific enforcement in consumer repos
if os.environ.get("CLAUDE_PLUGIN_ROOT"):
    sys.exit(0)

import json  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

_lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import (  # noqa: E402
    get_project_directory,
    get_today_session_log,
    is_git_commit_command,
)

MIN_SESSION_LOG_LENGTH = 100
MIN_JSON_PROPERTIES = 2


def check_session_log_evidence(session_log_path: Path) -> dict[str, object]:
    """Validate that the session log has substantial content.

    Returns a dict with 'valid' key (bool) and either 'reason' or 'content'.
    """
    try:
        content = session_log_path.read_text(encoding="utf-8")

        if len(content) < MIN_SESSION_LOG_LENGTH:
            return {"valid": False, "reason": "Session log exists but is empty"}

        try:
            data = json.loads(content)
            if isinstance(data, dict) and len(data) < MIN_JSON_PROPERTIES:
                return {"valid": False, "reason": "Session log lacks required sections"}
        except (json.JSONDecodeError, ValueError):
            pass  # Not JSON is acceptable (could be markdown log)

        preview_length = min(200, len(content))
        return {"valid": True, "content": content[:preview_length]}

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
    except (ValueError, OSError) as exc:
        return {
            "valid": False,
            "reason": f"Error reading session log: {type(exc).__name__} - {exc}",
        }


def main() -> int:
    """Main hook entry point. Returns exit code."""
    try:
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

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

        if not is_git_commit_command(command):
            return 0

        project_dir = get_project_directory()
        sessions_dir = os.path.join(project_dir, ".agents", "sessions")
        session_log = get_today_session_log(sessions_dir, date=today)

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
```
python3 scripts/sessions/initialize_session_log.py
```

Session logs go in: `.agents/sessions/{today}-session-NN.json`

**Current Date**: {today}
**Sessions Directory**: {sessions_dir}

See: `.agents/SESSION-PROTOCOL.md` for full details.
"""
            print(output)
            print("Session blocked: No session log found for today", file=sys.stderr)
            return 2

        evidence = check_session_log_evidence(session_log)

        if not evidence["valid"]:
            reason = evidence["reason"]
            output = f"""
## BLOCKED: Session Log Empty or Invalid

**Reason**: {reason}

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

**Current Session Log**: {session_log.name}
"""
            print(output)
            print("Session blocked: Session log has insufficient evidence", file=sys.stderr)
            return 2

        return 0

    except Exception as exc:
        # Fail-open on errors (don't block on infrastructure issues)
        print(f"Session log guard error: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
