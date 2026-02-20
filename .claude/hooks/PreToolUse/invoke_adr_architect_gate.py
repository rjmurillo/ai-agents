#!/usr/bin/env python3
"""Block Edit/Write on ADR files unless architect review evidence exists.

Claude Code PreToolUse hook that enforces architect involvement before
modifying ADR files. This is a routing-level gate per ADR-033.

Blocks Edit/Write operations on:
- .agents/architecture/ADR-*.md
- docs/architecture/ADR-*.md
- **/ADR-*.md (any location)

Evidence sources (any satisfies the gate):
1. Debate log artifact in .agents/analysis/ or .agents/critique/
2. Session log contains architect agent routing evidence
3. adr-review skill was invoked

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (continue with tool use)
    2 = Block (deny tool use with message)
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
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import (  # noqa: E402
    get_project_directory,
    get_today_session_log,
)

_ADR_PATTERN = re.compile(r"ADR-\d+.*\.md$", re.IGNORECASE)

_ARCHITECT_EVIDENCE_PATTERNS = [
    re.compile(r"/adr-review"),
    re.compile(r"adr-review skill"),
    re.compile(r"ADR Review Protocol"),
    re.compile(r"subagent_type\s*=\s*['\"]?architect"),
    re.compile(r"Task\s*\(\s*.*architect.*\)", re.DOTALL),
    re.compile(r"\barchitect\s+agent\b", re.IGNORECASE),
    re.compile(r"multi-agent consensus.{0,200}\bADR\b", re.DOTALL),
]

_BLOCKED_MESSAGE_TEMPLATE = """\

## BLOCKED: ADR Edit Without Architect Review

**YOU MUST invoke the architect agent before modifying ADR files.**

### File Targeted

{file_path}

### Required Action

Invoke the architect agent to review ADR changes:

```
Task(subagent_type='architect', prompt='Review ADR changes for {adr_name}')
```

After architect review, the adr-review skill will automatically be invoked
for multi-agent debate (6 agents: architect, critic, independent-thinker,
security, analyst, high-level-advisor).

### Alternative

Invoke the adr-review skill directly:

```
/adr-review {file_path}
```

**Skill**: `.claude/skills/adr-review/SKILL.md`
"""


def write_audit_log(message: str) -> None:
    """Write to the hook audit log for infrastructure error visibility."""
    try:
        hook_dir = Path(__file__).resolve().parents[1]
        audit_log_path = hook_dir / "audit.log"
        timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [ADRArchitectGate] {message}\n"
        with open(audit_log_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError:
        print(
            f"[ADRArchitectGate] CRITICAL: Audit log write failed. Original error: {message}",
            file=sys.stderr,
        )


def is_adr_file(file_path: str) -> bool:
    """Check if file path matches ADR naming pattern."""
    return _ADR_PATTERN.search(file_path) is not None


def check_architect_evidence(project_dir: str) -> dict[str, object]:
    """Check for architect involvement evidence.

    Returns dict with 'complete' (bool) and 'reason' or 'evidence' key.
    """
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    # Check 1: Debate log artifacts in .agents/analysis/ or .agents/critique/
    for artifact_dir in [".agents/analysis", ".agents/critique"]:
        analysis_dir = Path(project_dir) / artifact_dir
        if analysis_dir.is_dir():
            debate_logs = list(analysis_dir.glob("*debate*.md"))
            for log in debate_logs:
                if log.stat().st_mtime > (datetime.now(tz=UTC).timestamp() - 86400):
                    return {
                        "complete": True,
                        "evidence": f"Debate log artifact found: {log.name}",
                    }

    # Check 2: Session log evidence
    sessions_dir = os.path.join(project_dir, ".agents", "sessions")
    session_log = get_today_session_log(sessions_dir, date=today)

    if session_log is not None:
        try:
            content = session_log.read_text(encoding="utf-8")
            for pattern in _ARCHITECT_EVIDENCE_PATTERNS:
                if pattern.search(content):
                    return {
                        "complete": True,
                        "evidence": f"Session log contains architect evidence: {pattern.pattern}",
                    }
        except OSError as exc:
            write_audit_log(f"Session log read failed: {exc}")

    return {
        "complete": False,
        "reason": "No architect involvement evidence found in session log or analysis artifacts",
    }


def main() -> int:
    """Main hook entry point. Returns exit code."""
    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)

        tool_name = hook_input.get("tool_name", "")
        if tool_name not in ("Edit", "Write"):
            return 0

        tool_input = hook_input.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0

        file_path = tool_input.get("file_path", "")
        if not file_path:
            return 0

        if not is_adr_file(file_path):
            return 0

        # ADR file edit/write detected, check for architect evidence
        project_dir = get_project_directory()
        evidence = check_architect_evidence(project_dir)

        if evidence["complete"]:
            return 0

        # Block the operation
        adr_name = Path(file_path).name
        print(
            _BLOCKED_MESSAGE_TEMPLATE.format(
                file_path=file_path,
                adr_name=adr_name,
            )
        )
        print(
            "Blocked: ADR edit without architect review",
            file=sys.stderr,
        )
        return 2

    except json.JSONDecodeError as exc:
        error_msg = f"JSON parse error: {exc}"
        print(error_msg, file=sys.stderr)
        write_audit_log(error_msg)
        return 0  # Fail-open on infrastructure errors

    except Exception as exc:
        # Fail-open on infrastructure errors
        error_msg = f"ADR architect gate error: {type(exc).__name__} - {exc}"
        print(error_msg, file=sys.stderr)
        write_audit_log(error_msg)
        return 0


if __name__ == "__main__":
    sys.exit(main())
