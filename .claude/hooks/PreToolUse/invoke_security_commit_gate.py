#!/usr/bin/env python3
"""Block git commit when staged files match security-sensitive patterns without review.

Claude Code PreToolUse hook that enforces the "Do Router" gate per ADR-033
Phase 4. Complements invoke_security_gate.py (Edit/Write) by also checking
at commit time whether staged files touch auth/security paths.

Hook Type: PreToolUse
Matcher: Bash(git commit*)
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Always (uses JSON decision payload for deny/allow semantics)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
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
from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402

# Security-sensitive file path patterns
_SECURITY_PATH_PATTERNS = [
    re.compile(r"(^|[/\\])[Aa]uth[/\\]"),
    re.compile(r"(^|[/\\])[Ss]ecurity[/\\]"),
    re.compile(r"\.env($|\.)"),
    re.compile(r"(^|[/\\])\.githooks[/\\]"),
    re.compile(r"(^|[/\\])secrets[/\\]"),
    re.compile(r"(?i)password"),
    re.compile(r"(^|[/\\])token"),
    re.compile(r"(^|[/\\])[Oo]auth[/\\]"),
    re.compile(r"(^|[/\\])[Jj]wt[/\\]"),
]

# Session log patterns indicating security review
_SECURITY_REVIEW_PATTERNS = [
    re.compile(r"security.*review", re.IGNORECASE),
    re.compile(r"security.*agent", re.IGNORECASE),
    re.compile(r"threat.*model", re.IGNORECASE),
    re.compile(r"OWASP", re.IGNORECASE),
    re.compile(r"/security-scan"),
    re.compile(r"subagent_type.*security", re.IGNORECASE),
]


def get_staged_files() -> list[str]:
    """Get list of staged file paths.

    Raises:
        OSError: If git is not found or cannot be executed.
        subprocess.TimeoutExpired: If the command times out.
        subprocess.CalledProcessError: If git returns a non-zero exit code.
    """
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    if result.stdout.strip():
        return result.stdout.strip().splitlines()
    return []


def match_security_paths(files: list[str]) -> list[str]:
    """Return files matching security-sensitive patterns."""
    matched = []
    for f in files:
        for pattern in _SECURITY_PATH_PATTERNS:
            if pattern.search(f):
                matched.append(f)
                break
    return matched


def find_security_evidence(project_dir: str) -> bool:
    """Check for security review evidence in the current session."""
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
    """Main hook entry point."""
    if skip_if_consumer_repo("security-commit-gate"):
        return 0

    # Bypass: environment variable
    if os.environ.get("SKIP_SECURITY_GATE") == "true":
        return 0

    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        input_data = json.loads(input_json)
        tool_input = input_data.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0

        command = tool_input.get("command", "")
        if "git commit" not in command:
            return 0

        staged = get_staged_files()
        if not staged:
            return 0

        security_files = match_security_paths(staged)
        if not security_files:
            return 0

        project_dir = get_project_directory()
        if find_security_evidence(project_dir):
            return 0

        # Security files staged without review evidence: deny
        file_list = "\n".join(f"  - {f}" for f in security_files)
        output = {
            "decision": "deny",
            "reason": (
                "SECURITY COMMIT GATE: Security review required before committing "
                "security-sensitive files.\n\n"
                f"Matched files:\n{file_list}\n\n"
                "Invoke the security agent:\n"
                "  Task(subagent_type='security', prompt='Review security-sensitive "
                "changes')\n\n"
                "Or create a security report in .agents/security/\n\n"
                "Bypass: Set SKIP_SECURITY_GATE=true (requires justification)"
            ),
        }
        print(json.dumps(output, separators=(",", ":")))
        return 0

    except Exception as exc:
        # Fail-closed on infrastructure errors
        print(f"Security commit gate error: {type(exc).__name__} - {exc}", file=sys.stderr)
        output = {
            "decision": "deny",
            "reason": (
                f"SECURITY COMMIT GATE FAILED due to an internal error: "
                f"{type(exc).__name__}. Commit blocked as a security precaution."
            ),
        }
        print(json.dumps(output, separators=(",", ":")))
        return 0


if __name__ == "__main__":
    sys.exit(main())
