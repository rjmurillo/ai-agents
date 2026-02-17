#!/usr/bin/env python3
"""Enforce ADR-007 memory-first protocol with hybrid education/escalation strategy.

Claude Code SessionStart hook that verifies memory retrieval evidence before
allowing work to proceed. Uses hybrid enforcement:

- First 3 invocations: Educational guidance (inject context)
- After threshold: Strong warning with escalated urgency (inject context)

Evidence verification checks session log protocolCompliance.sessionStart for:
1. serenaActivated.Complete = true
2. handoffRead.Complete = true
3. memoriesLoaded.Evidence (or .evidence) is non-empty

Part of Tier 2 enforcement hooks (Issue #773, Protocol enforcement).

NOTE: SessionStart hooks cannot block (exit 2 only shows stderr as error,
does not block the session, and prevents stdout from being injected).
All enforcement is via context injection (exit 0 with stdout).

Hook Type: SessionStart
Exit Codes:
    0 = Success (guidance or warning injected into Claude's context)
"""

from __future__ import annotations

import json
import os
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
    get_today_session_logs,
)

EDUCATION_THRESHOLD = 3


def test_memory_evidence(session_log_path: str) -> dict[str, object]:
    """Check session log for memory-first protocol compliance evidence.

    Returns a dict with 'complete' (bool) and either 'evidence' or 'reason'.
    """
    try:
        content = json.loads(Path(session_log_path).read_text(encoding="utf-8"))

        protocol = content.get("protocolCompliance", {})
        session_start = protocol.get("sessionStart", {})
        if not session_start:
            return {"complete": False, "reason": "Missing protocolCompliance.sessionStart section"}

        serena = session_start.get("serenaActivated", {})
        if not serena or not serena.get("Complete", serena.get("complete")):
            return {"complete": False, "reason": "Serena not initialized"}

        handoff = session_start.get("handoffRead", {})
        if not handoff or not handoff.get("Complete", handoff.get("complete")):
            return {"complete": False, "reason": "HANDOFF.md not read"}

        memories = session_start.get("memoriesLoaded", {})
        if not memories or not memories.get("Complete", memories.get("complete")):
            return {"complete": False, "reason": "Memories not loaded"}

        evidence = memories.get("Evidence", memories.get("evidence", ""))
        if not evidence or not str(evidence).strip():
            return {"complete": False, "reason": "Memory evidence is empty"}

        return {"complete": True, "evidence": evidence}

    except PermissionError:
        return {
            "complete": False,
            "reason": "Session log is locked or you lack permissions. Close editors and retry.",
        }
    except FileNotFoundError:
        return {
            "complete": False,
            "reason": "Session log was deleted after detection. Create a new session log.",
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "complete": False,
            "reason": "Session log contains invalid JSON. Check file format or recreate.",
        }
    except Exception as exc:
        return {
            "complete": False,
            "reason": f"Error parsing session log: {type(exc).__name__} - {exc}",
        }


def get_invocation_count(state_dir: str, today: str) -> int:
    """Read the invocation counter for today."""
    state_file = Path(state_dir) / "memory-first-counter.txt"
    if not state_file.exists():
        return 0
    try:
        content = state_file.read_text(encoding="utf-8").strip()
        lines = content.splitlines()
        if len(lines) == 2:
            stored_count = int(lines[0])
            stored_date = lines[1]
            if stored_date != today:
                return 0
            return stored_count
        # Legacy format (just a number)
        return int(content)
    except (ValueError, OSError):
        return 0


def increment_invocation_count(state_dir: str, today: str) -> int:
    """Increment and store the invocation counter for today."""
    state_path = Path(state_dir)
    state_path.mkdir(parents=True, exist_ok=True)

    count = get_invocation_count(state_dir, today) + 1
    state_file = state_path / "memory-first-counter.txt"
    state_file.write_text(f"{count}\n{today}", encoding="utf-8")
    return count


def main() -> int:
    """Main hook entry point. Returns exit code."""
    try:
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        project_dir = get_project_directory()
        sessions_dir = str(Path(project_dir) / ".agents" / "sessions")
        state_dir = str(Path(project_dir) / ".agents" / ".hook-state")

        today_logs = get_today_session_logs(sessions_dir)

        if not today_logs:
            print(
                "\nADR-007: No session log for today. Run `/session-init`. "
                "Protocol details in AGENTS.md.\n"
            )
            return 0

        # Check most recent session log for evidence
        latest_log = sorted(today_logs, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        evidence = test_memory_evidence(str(latest_log))

        if evidence["complete"]:
            print("\nADR-007 Memory-First: Evidence verified in session log.\n")
            return 0

        # Evidence missing - check invocation count for education vs escalation
        count = increment_invocation_count(state_dir, today)

        if count <= EDUCATION_THRESHOLD:
            severity = f"Warning {count}/{EDUCATION_THRESHOLD}"
        else:
            severity = f"VIOLATION (warning {count})"

        reason = evidence.get("reason", "Unknown")
        print(
            f"\nADR-007 {severity}: {reason}. "
            f"Complete: Serena init, HANDOFF.md read, memory retrieval. "
            f"See AGENTS.md Session Protocol Gates.\n"
        )
        return 0

    except Exception as exc:
        # Fail-open on errors (don't block session startup)
        print(f"Memory-first enforcer error: {type(exc).__name__} - {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
