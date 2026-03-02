#!/usr/bin/env python3
"""Block Edit/Write on auth-related files without security review evidence.

Claude Code PreToolUse hook that enforces the "Do Router" gate per ADR-033
Phase 4. Blocks modifications to authentication and authorization files
unless security review evidence exists in the current session.

Hook Type: PreToolUse
Matcher: Edit, Write
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (not an auth file, or security review exists)
    2 = Block (auth file modification without security review)
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import get_project_directory  # noqa: E402

# File path patterns that indicate auth-related code
_AUTH_PATH_PATTERNS = [
    re.compile(r"(^|[/\\])[Aa]uth[/\\]"),
    re.compile(r"(^|[/\\])[Aa]uthentication[/\\]"),
    re.compile(r"(^|[/\\])[Aa]uthorization[/\\]"),
    re.compile(r"\.auth\.(ts|js|py|cs|java|go|rb)$"),
    re.compile(r"(^|[/\\])middleware[/\\]auth", re.IGNORECASE),
]

# Session log patterns indicating security review was performed
_SECURITY_REVIEW_PATTERNS = [
    re.compile(r"security.*review", re.IGNORECASE),
    re.compile(r"security.*agent", re.IGNORECASE),
    re.compile(r"threat.*model", re.IGNORECASE),
    re.compile(r"OWASP", re.IGNORECASE),
    re.compile(r"/security-scan"),
    re.compile(r"security-scan skill"),
    re.compile(r"subagent_type.*security", re.IGNORECASE),
]

_BLOCK_TEMPLATE = """\

## BLOCKED: Security Review Required for Auth Files

**DO ROUTER GATE: Security review required before modifying authentication/authorization files.**

### File

```
{file_path}
```

### Required Action

Run the security agent before editing auth-related files:

```
Task(subagent_type='security', prompt='Review auth-related changes for {file_path}')
```

The security agent will assess:
- Authentication flow security
- Authorization model correctness
- OWASP Top 10 considerations
- Threat model updates

### Alternative: Create Security Report

Place a security review report in `.agents/security/` with today's date:

```
.agents/security/YYYY-MM-DD-security-review.md
```

**Reference**: ADR-033 Phase 4 "Do Router" Integration
"""


def is_auth_path(file_path: str) -> bool:
    """Check if a file path matches auth-related patterns."""
    if not file_path:
        return False
    for pattern in _AUTH_PATH_PATTERNS:
        if pattern.search(file_path):
            return True
    return False


def find_security_evidence(project_dir: str) -> bool:
    """Check for security review evidence in the current session.

    Looks for:
    1. Security report files in .agents/security/ dated today
    2. Security review markers in today's session log
    """
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    # Check 1: Security report exists for today
    security_dir = Path(project_dir) / ".agents" / "security"
    if security_dir.is_dir():
        try:
            reports = list(security_dir.glob(f"*{today}*"))
            if reports:
                return True
        except OSError:
            pass

    # Check 2: Session log contains security review evidence
    sessions_dir = Path(project_dir) / ".agents" / "sessions"
    if sessions_dir.is_dir():
        try:
            session_logs = sorted(
                sessions_dir.glob(f"{today}-session-*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for log_path in session_logs:
                content = log_path.read_text(encoding="utf-8")
                for pattern in _SECURITY_REVIEW_PATTERNS:
                    if pattern.search(content):
                        return True
        except OSError:
            pass

    return False


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

        file_path = tool_input.get("file_path", "")
        if not file_path:
            return 0

        if not is_auth_path(file_path):
            return 0

        project_dir = get_project_directory()

        if find_security_evidence(project_dir):
            return 0

        # Auth file edit without security review: block
        print(_BLOCK_TEMPLATE.format(file_path=file_path))
        print(
            f"Blocked: Auth file edit without security review: {file_path}",
            file=sys.stderr,
        )
        return 2

    except Exception as exc:
        # Fail-open on infrastructure errors
        print(f"Security gate error: {type(exc).__name__} - {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
