#!/usr/bin/env python3
"""Enforces ADR-007 memory-first protocol with hybrid education/escalation strategy.

Claude Code SessionStart hook that verifies memory retrieval evidence before
allowing work to proceed. Uses hybrid enforcement:

- First 3 invocations: Educational guidance (inject context)
- After threshold: Strong warning with escalated urgency (inject context)

Evidence verification checks session log protocolCompliance.sessionStart for:
1. serenaActivated.complete = true
2. handoffRead.complete = true
3. memoriesLoaded.Evidence contains memory names

Part of Tier 2 enforcement hooks (Issue #773, Protocol enforcement).

NOTE: SessionStart hooks cannot block (exit 2 only shows stderr as error,
does not block the session, and prevents stdout from being injected).
All enforcement is via context injection (exit 0 with stdout).

Hook Type: SessionStart
Exit Codes:
    0 = Success (guidance or warning injected into Claude's context)
"""

import datetime
import json
import os
import sys
from pathlib import Path

EDUCATION_THRESHOLD = 3


def _get_project_directory() -> str:
    """Resolve project root directory."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        return env_dir

    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return str(current)
        current = current.parent

    return str(Path.cwd())


def _get_today_session_logs(sessions_dir: str) -> list[str]:
    """Find all session logs for today's date."""
    if not os.path.isdir(sessions_dir):
        return []

    today = datetime.date.today().strftime("%Y-%m-%d")
    try:
        pattern_prefix = f"{today}-session-"
        logs = []
        for entry in os.listdir(sessions_dir):
            if entry.startswith(pattern_prefix) and entry.endswith(".json"):
                full_path = os.path.join(sessions_dir, entry)
                if os.path.isfile(full_path):
                    logs.append(full_path)
        return logs
    except OSError:
        return []


def _test_memory_evidence(session_log_path: str) -> dict:
    """Check session log for memory-first protocol evidence."""
    try:
        with open(session_log_path, "r", encoding="utf-8") as f:
            content = json.load(f)

        protocol = content.get("protocolCompliance", {})
        session_start = protocol.get("sessionStart", {})

        if not session_start:
            return {
                "complete": False,
                "reason": "Missing protocolCompliance.sessionStart section",
            }

        # Check Serena activation
        serena = session_start.get("serenaActivated", {})
        if not serena or not serena.get("complete"):
            return {
                "complete": False,
                "reason": "Serena not initialized",
            }

        # Check HANDOFF.md read
        handoff = session_start.get("handoffRead", {})
        if not handoff or not handoff.get("complete"):
            return {
                "complete": False,
                "reason": "HANDOFF.md not read",
            }

        # Check memories loaded with evidence
        memories = session_start.get("memoriesLoaded", {})
        if not memories or not memories.get("complete"):
            return {
                "complete": False,
                "reason": "Memories not loaded",
            }

        evidence = memories.get("Evidence", "")
        if not evidence or not str(evidence).strip():
            return {
                "complete": False,
                "reason": "Memory evidence is empty",
            }

        return {
            "complete": True,
            "evidence": evidence,
        }

    except PermissionError:
        return {
            "complete": False,
            "reason": (
                "Session log is locked or you lack permissions. "
                "Close editors and retry."
            ),
        }
    except FileNotFoundError:
        return {
            "complete": False,
            "reason": (
                "Session log was deleted after detection. "
                "Create a new session log."
            ),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "complete": False,
            "reason": (
                "Session log contains invalid JSON. "
                "Check file format or recreate."
            ),
        }
    except OSError as exc:
        return {
            "complete": False,
            "reason": f"Error parsing session log: {type(exc).__name__} - {exc}",
        }


def _get_invocation_count(state_dir: str, today: str) -> int:
    """Read the invocation counter for today."""
    state_file = os.path.join(state_dir, "memory-first-counter.txt")
    if not os.path.isfile(state_file):
        return 0

    try:
        with open(state_file, "r", encoding="utf-8") as f:
            content = f.read().strip()

        lines = content.split("\n")
        if len(lines) == 2:
            stored_count = int(lines[0])
            stored_date = lines[1].strip()
            if stored_date != today:
                return 0
            return stored_count

        # Legacy format (just a number)
        return int(content)
    except (OSError, ValueError):
        return 0


def _increment_invocation_count(state_dir: str, today: str) -> int:
    """Increment and return the invocation counter for today."""
    os.makedirs(state_dir, exist_ok=True)
    state_file = os.path.join(state_dir, "memory-first-counter.txt")
    count = _get_invocation_count(state_dir, today) + 1

    with open(state_file, "w", encoding="utf-8") as f:
        f.write(f"{count}\n{today}")

    return count


def main() -> int:
    """Main hook entry point. Returns exit code."""
    try:
        today = datetime.date.today().strftime("%Y-%m-%d")

        project_dir = _get_project_directory()
        sessions_dir = os.path.join(project_dir, ".agents", "sessions")
        state_dir = os.path.join(project_dir, ".agents", ".hook-state")

        today_logs = _get_today_session_logs(sessions_dir)

        if not today_logs:
            output = (
                f"\n## ADR-007 Memory-First Protocol\n\n"
                f"**No session log found for today.** Create one early in session:\n"
                f"- Use ``/session-init`` skill, OR\n"
                f"- Create ``.agents/sessions/{today}-session-NN.json``\n\n"
                f"**Required evidence in session log**:\n"
                f"- ``protocolCompliance.sessionStart.serenaActivated.Complete = true``\n"
                f"- ``protocolCompliance.sessionStart.handoffRead.Complete = true``\n"
                f"- ``protocolCompliance.sessionStart.memoriesLoaded.Evidence`` "
                f"contains memory names\n\n"
                f"See: ``.agents/SESSION-PROTOCOL.md`` Phase 1-2\n"
            )
            print(output)
            return 0

        # Check most recent session log for evidence
        # Sort by modification time descending
        today_logs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        latest_log = today_logs[0]
        evidence = _test_memory_evidence(latest_log)

        if evidence.get("complete"):
            print("\nADR-007 Memory-First: Evidence verified in session log.\n")
            return 0

        # Evidence missing, check invocation count for education vs escalation
        count = _increment_invocation_count(state_dir, today)

        reason = evidence.get("reason", "Unknown")

        if count <= EDUCATION_THRESHOLD:
            output = (
                f"\n## ADR-007 Memory-First: Evidence Missing "
                f"(Warning {count}/{EDUCATION_THRESHOLD})\n\n"
                f"**Reason**: {reason}\n\n"
                "Complete these steps NOW to build evidence:\n\n"
                "1. **Initialize Serena** (REQUIRED):\n"
                "   ```\n"
                "   mcp__serena__activate_project\n"
                "   mcp__serena__initial_instructions\n"
                "   ```\n\n"
                "2. **Load Project Context** (REQUIRED):\n"
                "   - Read ``.agents/HANDOFF.md``\n"
                "   - Read ``memory-index`` from Serena\n"
                "   - Read task-relevant memories listed in memory-index\n\n"
                "3. **Document Evidence** (REQUIRED):\n"
                "   - Session log MUST show tool outputs from steps 1-2\n"
                "   - ``protocolCompliance.sessionStart.memoriesLoaded`` "
                "MUST list specific memories\n\n"
                "**Why This Matters**: Without memory retrieval, you will repeat "
                "past mistakes, violate learned constraints, and ignore "
                "architectural decisions.\n\n"
                f"**After {EDUCATION_THRESHOLD} warnings, this becomes BLOCKING.**\n"
            )
        else:
            output = (
                f"\n## ADR-007: Memory-First Protocol Violation "
                f"(Warning {count}, past threshold)\n\n"
                f"**Reason**: {reason}\n\n"
                "Complete these steps NOW (in order):\n\n"
                "1. **Initialize Serena** (REQUIRED):\n"
                "   ```\n"
                "   mcp__serena__activate_project\n"
                "   mcp__serena__initial_instructions\n"
                "   ```\n\n"
                "2. **Load Project Context** (REQUIRED):\n"
                "   - Read ``.agents/HANDOFF.md``\n"
                "   - Read ``memory-index`` from Serena\n"
                "   - Read task-relevant memories listed in memory-index\n\n"
                "3. **Document Evidence** (REQUIRED):\n"
                "   - Session log MUST show tool outputs from steps 1-2\n"
                "   - ``protocolCompliance.sessionStart.memoriesLoaded`` "
                "MUST list specific memories\n\n"
                "**Why This Matters**: Without memory retrieval, you will repeat "
                "past mistakes, violate learned constraints, and ignore "
                "architectural decisions.\n\n"
                "See: ``.agents/SESSION-PROTOCOL.md`` Phase 1-2\n"
            )

        print(output)
        return 0

    except Exception as exc:
        # Fail-open on errors (don't block session startup)
        print(f"Memory-first enforcer error: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
