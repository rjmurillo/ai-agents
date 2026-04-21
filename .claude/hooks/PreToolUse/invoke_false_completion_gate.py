#!/usr/bin/env python3
"""
PreToolUse hook: Blocks false completion claims without prior verification.

Detects when agents claim "done/fixed/complete" in commit messages or PR
descriptions without evidence of running tests/builds in the session.

Hook Type: PreToolUse (matcher: Bash)
Exit Codes:
    0 = Allow (no false completion detected, or verification evidence found)
    2 = Block (false completion detected without verification)

Bypass: SKIP_COMPLETION_GATE=true environment variable

Related:
- Issue #1703 (lifecycle hook infrastructure)
- Issue #1673 (false completion mentions)
- ADR-008 (protocol automation lifecycle hooks)
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Regex for false-completion signals in commands
COMPLETION_SIGNALS = re.compile(
    r"\b(done|fixed|complete[d]?|finished|resolved|merged|shipped|closes?\s+#\d+)\b",
    re.IGNORECASE,
)

# Evidence patterns indicating verification was performed
VERIFICATION_PATTERNS = re.compile(
    r"(pytest|python\s+-m\s+pytest|tsc\s+--noEmit|npm\s+test|npm\s+run\s+test|"
    r"pnpm\s+test|yarn\s+test|dotnet\s+test|go\s+test|"
    r"gh\s+pr\s+checks|Invoke-Pester|uv\s+run\s+pytest|make\s+test)",
    re.IGNORECASE,
)

# Commands that trigger completion detection
COMPLETION_COMMANDS = re.compile(
    r"(git\s+commit|gh\s+pr\s+create|gh\s+pr\s+merge)",
    re.IGNORECASE,
)


def get_project_directory() -> Path | None:
    """Resolve project root from env or git."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        return Path(env_dir)
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None


def find_session_log(project_dir: Path) -> Path | None:
    """Find today's session log."""
    sessions_dir = project_dir / ".agents" / "sessions"
    if not sessions_dir.is_dir():
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    candidates = sorted(
        sessions_dir.glob(f"{today}-session-*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def has_verification_evidence(project_dir: Path) -> bool:
    """Check session log and hook state for evidence of test/build runs."""
    # Check session log
    session_log = find_session_log(project_dir)
    if session_log:
        try:
            content = session_log.read_text(encoding="utf-8")
            if VERIFICATION_PATTERNS.search(content):
                return True
        except OSError:
            pass

    # Check hook state for plan checkpoints (indicates active work)
    # Exclude audit files to prevent self-poisoning (audit log reasons contain
    # verification pattern keywords like "pytest" that would falsely match)
    hook_state_dir = project_dir / ".agents" / ".hook-state"
    if hook_state_dir.is_dir():
        today = datetime.now().strftime("%Y-%m-%d")
        checkpoints = list(hook_state_dir.glob(f"*{today}*"))
        if checkpoints:
            for cp in checkpoints:
                if cp.name.startswith("audit-"):
                    continue
                try:
                    content = cp.read_text(encoding="utf-8")
                    if VERIFICATION_PATTERNS.search(content):
                        return True
                except OSError:
                    pass

    return False


def write_audit_log(project_dir: Path, command: str, decision: str, reason: str) -> None:
    """Log blocked events to audit trail."""
    try:
        audit_dir = project_dir / ".agents" / ".hook-state"
        audit_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        audit_file = audit_dir / f"audit-{today}.jsonl"
        entry = json.dumps({
            "timestamp": datetime.now().isoformat(),
            "hook": "invoke_false_completion_gate",
            "command": command[:200],
            "decision": decision,
            "reason": reason,
        })
        with open(audit_file, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError:
        pass


def main() -> int:
    """Check for false completion claims without verification."""
    # Bypass env var
    if os.environ.get("SKIP_COMPLETION_GATE", "").lower() == "true":
        return 0

    # Skip if stdin is TTY
    if sys.stdin.isatty():
        return 0

    # Read stdin JSON
    try:
        stdin_data = sys.stdin.read()
        if not stdin_data.strip():
            return 0
        hook_input = json.loads(stdin_data)
    except (json.JSONDecodeError, Exception):
        return 0  # Fail-open

    # Extract command from tool input
    tool_input = hook_input.get("tool_input", {})
    command = tool_input.get("command", "")

    if not command:
        return 0

    # Only check completion-relevant commands (commits, PRs)
    if not COMPLETION_COMMANDS.search(command):
        return 0

    # Check for completion signals in the command
    if not COMPLETION_SIGNALS.search(command):
        return 0

    # Completion signal detected — check for verification evidence
    project_dir = get_project_directory()
    if not project_dir:
        return 0  # Fail-open: can't verify

    if has_verification_evidence(project_dir):
        return 0  # Verification found — allow

    # BLOCK: False completion without verification
    reason = (
        "Completion claim detected without prior test/build verification. "
        "Run tests (pytest, npm test, etc.) before claiming completion."
    )
    # Output deny decision (Claude hook protocol)
    print(json.dumps({"decision": "block", "reason": reason}))

    write_audit_log(project_dir, command, "block", reason)

    return 2  # Exit code 2 = BLOCK


if __name__ == "__main__":
    sys.exit(main())
