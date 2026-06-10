#!/usr/bin/env python3
"""Block git commit when staged files match security-sensitive patterns without review.

Claude Code PreToolUse hook that enforces the "Do Router" gate per ADR-033
Phase 4. Complements invoke_security_gate.py (Edit/Write) by also checking
at commit time whether staged files touch auth/security paths.

Hook Type: PreToolUse
Matcher: Bash(git commit*)
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = allow: no security-sensitive files staged, or review evidence present.
    2 = block: security-sensitive files staged without review, or an
        infrastructure error reading the index. Paired with a top-level
        {"decision": "block"} payload, the recognized Claude Code PreToolUse
        contract (see invoke_branch_protection_guard.py). A previous version
        emitted {"decision": "deny"} with exit 0, which the harness ignored, so
        the gate never actually blocked (Issue #2521).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# Bootstrap: find lib directory via env var or manifest walk-up.
# CLAUDE_PLUGIN_ROOT honored when set; otherwise walk up from __file__
# looking for .claude-plugin/plugin.json (the plugin marker). Sibling
# lib/ is the plugin's lib dir. Layout-independent: works in source
# tree (.claude/) and in the deeper src/<provider>/hooks/<event>/ copy.
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
_lib_dir: str | None = None
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _cur = Path(__file__).resolve().parent
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
if _lib_dir is None or not os.path.isdir(_lib_dir):
    print(
        f"Plugin lib directory not found: {_lib_dir} "
        f"(CLAUDE_PLUGIN_ROOT={_plugin_root!r})",
        file=sys.stderr,
    )
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import get_project_directory, is_git_commit_command  # noqa: E402
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


def write_block_response(reason: str) -> None:
    """Emit a PreToolUse block decision (matches invoke_branch_protection_guard.py).

    Claude Code recognizes a top-level ``{"decision": "block"}`` payload, paired
    with exit code 2, to deny a tool call. The previous ``{"decision": "deny"}``
    with exit 0 was not a recognized top-level value, so the gate's output was
    ignored and the security-sensitive commit proceeded (Issue #2521). The value
    ``deny`` is only valid under ``hookSpecificOutput.permissionDecision``.
    """
    print(json.dumps({"decision": "block", "reason": reason}, separators=(",", ":")))


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
        if not is_git_commit_command(command):
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

        # Security files staged without review evidence: block the commit.
        file_list = "\n".join(f"  - {f}" for f in security_files)
        write_block_response(
            "SECURITY COMMIT GATE: Security review required before committing "
            "security-sensitive files.\n\n"
            f"Matched files:\n{file_list}\n\n"
            "Invoke the security agent:\n"
            "  Task(subagent_type='security', prompt='Review security-sensitive "
            "changes')\n\n"
            "Or create a security report in .agents/security/\n\n"
            "Bypass: Set SKIP_SECURITY_GATE=true (requires justification)"
        )
        return 2

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # Infrastructure error enumerating staged files (not a git repo, index
        # lock, git timeout). Fail closed with a diagnostic so the failure is
        # distinguishable from a genuine security signal (Issue #2521).
        detail = ""
        stderr = getattr(exc, "stderr", None)
        if stderr:
            detail = (
                stderr.decode("utf-8", errors="replace").strip()
                if isinstance(stderr, bytes)
                else str(stderr).strip()
            )
        print(
            f"Security commit gate could not read staged files: "
            f"{type(exc).__name__}. {detail}".strip(),
            file=sys.stderr,
        )
        write_block_response(
            "SECURITY COMMIT GATE: could not enumerate staged files "
            f"({type(exc).__name__}). Commit blocked as a precaution. "
            "Verify the repository state: git status."
        )
        return 2

    except Exception as exc:
        # Fail-closed on any other infrastructure error.
        print(f"Security commit gate error: {type(exc).__name__} - {exc}", file=sys.stderr)
        write_block_response(
            f"SECURITY COMMIT GATE FAILED due to an internal error: "
            f"{type(exc).__name__}. Commit blocked as a security precaution."
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
