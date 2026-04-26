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
from datetime import UTC, datetime
from pathlib import Path

# Cross-platform file locking
# On Windows, msvcrt.locking operates on bytes at the current file position,
# so we must save/restore position around lock/unlock operations.
_win_lock_positions: dict[int, int] = {}

if sys.platform == "win32":
    import msvcrt

    def _lock_file(f):
        fd = f.fileno()
        _win_lock_positions[fd] = f.tell()
        f.seek(_win_lock_positions[fd])
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)

    def _unlock_file(f):
        fd = f.fileno()
        pos = _win_lock_positions.pop(fd, 0)
        f.seek(pos)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock_file(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)

    def _unlock_file(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

try:
    from hook_utilities import get_project_directory as _get_project_directory
    from hook_utilities import get_today_session_log

    def get_project_directory() -> Path | None:
        """Wrap shared utility returning Path for backward compat."""
        result = _get_project_directory()
        return Path(result) if result else None

except ImportError:
    # Fallback if hook_utilities not available
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

    get_today_session_log = None  # type: ignore[assignment]

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


def find_session_log(project_dir: Path) -> Path | None:
    """Find today's session log using UTC date."""
    sessions_dir = project_dir / ".agents" / "sessions"
    if not sessions_dir.is_dir():
        return None

    # Use shared utility if available (uses UTC)
    if get_today_session_log is not None:
        return get_today_session_log(str(sessions_dir))

    # Fallback: use UTC explicitly
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    candidates = sorted(
        sessions_dir.glob(f"{today}-session-*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def has_verification_evidence(project_dir: Path) -> bool:
    """Check session log for evidence of test/build runs."""
    # Check session log
    session_log = find_session_log(project_dir)
    if session_log:
        try:
            content = session_log.read_text(encoding="utf-8")
            if VERIFICATION_PATTERNS.search(content):
                return True
        except OSError:
            pass

    return False


def write_audit_log(
    project_dir: Path,
    command: str,
    decision: str,
    reason: str,
    session_id: str = "",
    tool_use_id: str = "",
) -> None:
    """Log every terminal decision to audit trail.

    Logs include:
    - decision: 'block', 'allow_verified', 'allow_no_project', 'bypass_env',
                'error_parse', 'allow_no_command', 'allow_not_completion'
    - session_id, tool_use_id: correlation IDs from hook stdin
    - schema: 1 for forward-compat
    """
    try:
        audit_dir = project_dir / ".agents" / ".hook-state"
        audit_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        audit_file = audit_dir / f"audit-{today}.jsonl"
        entry = json.dumps({
            "schema": 1,
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "hook": "invoke_false_completion_gate",
            "command": command[:200],
            "decision": decision,
            "reason": reason,
            "session_id": session_id,
            "tool_use_id": tool_use_id,
        })
        with open(audit_file, "a", encoding="utf-8") as f:
            _lock_file(f)
            try:
                f.write(entry + "\n")
            finally:
                _unlock_file(f)
    except OSError as e:
        print(f"[hook-error] invoke_false_completion_gate audit: {type(e).__name__}: {e}", file=sys.stderr)


def main() -> int:
    """Check for false completion claims without verification.

    Audits every terminal decision so SRE can prove the gate ran.
    """
    project_dir = get_project_directory()
    session_id = ""
    tool_use_id = ""

    # Bypass env var (audited so operators see when gate was disabled)
    if os.environ.get("SKIP_COMPLETION_GATE", "").lower() == "true":
        if project_dir:
            write_audit_log(project_dir, "", "bypass_env", "SKIP_COMPLETION_GATE=true", session_id, tool_use_id)
        return 0

    # Skip if stdin is TTY (interactive shell, not a hook invocation)
    if sys.stdin.isatty():
        return 0

    # Read stdin JSON; extract correlation IDs even on parse-failure path
    try:
        stdin_data = sys.stdin.read()
        if not stdin_data.strip():
            return 0
        hook_input = json.loads(stdin_data)
    except (json.JSONDecodeError, ValueError) as e:
        if project_dir:
            write_audit_log(project_dir, "", "error_parse", f"{type(e).__name__}: {e}", session_id, tool_use_id)
        return 0  # Fail-open

    # Correlation IDs from harness
    session_id = str(hook_input.get("session_id", ""))
    tool_use_id = str(hook_input.get("tool_use_id", ""))

    # Extract command from tool input
    tool_input = hook_input.get("tool_input", {})
    command = tool_input.get("command", "")

    if not command:
        return 0  # Not a Bash invocation we care about; do not flood audit

    # Only check completion-relevant commands (commits, PRs)
    if not COMPLETION_COMMANDS.search(command):
        return 0  # Out of scope; do not flood audit

    # Check for completion signals in the command
    if not COMPLETION_SIGNALS.search(command):
        if project_dir:
            write_audit_log(project_dir, command, "allow_not_completion", "no completion keyword", session_id, tool_use_id)
        return 0

    # Completion signal detected — check for verification evidence
    if not project_dir:
        # Fail-open without project dir; cannot audit either
        return 0

    if has_verification_evidence(project_dir):
        write_audit_log(project_dir, command, "allow_verified", "verification evidence found", session_id, tool_use_id)
        return 0

    # BLOCK: False completion without verification
    reason = (
        "Completion claim detected without prior test/build verification. "
        "Run tests (pytest, npm test, etc.) before claiming completion."
    )
    # Output deny decision (Claude hook protocol)
    print(json.dumps({"decision": "block", "reason": reason}))

    write_audit_log(project_dir, command, "block", reason, session_id, tool_use_id)

    return 2  # Exit code 2 = BLOCK


if __name__ == "__main__":
    sys.exit(main())
