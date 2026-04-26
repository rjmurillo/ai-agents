#!/usr/bin/env python3
"""
SessionStart hook: Auto-loads HANDOFF.md and latest retrospective into context.

Addresses issue #1703 acceptance criteria: SessionStart hook implemented and tested.
Fixes 95.8% context reading failure rate by injecting critical context automatically.

Hook Type: SessionStart (non-blocking)
Exit Codes: Always 0 (fail-open — never blocks session start)

Related:
- Issue #1672 (session-start gate)
- ADR-008 (protocol automation lifecycle hooks)
- .agents/SESSION-PROTOCOL.md
"""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Cross-platform file locking
if sys.platform == "win32":
    import msvcrt

    def _lock_file(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock_file(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock_file(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)

    def _unlock_file(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

# Maximum characters to inject per file to avoid context bloat
MAX_CHARS_PER_FILE = 4000

# Audit trail directory
AUDIT_DIR_NAME = ".agents/.hook-state"


def get_project_directory() -> Path | None:
    """Resolve project root from env or git."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        return Path(env_dir)

    # Walk up from CWD to find .git
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None


def get_latest_retrospective(retro_dir: Path) -> Path | None:
    """Find the most recent retrospective file by modification time."""
    if not retro_dir.is_dir():
        return None

    retro_files = sorted(
        retro_dir.glob("*.md"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return retro_files[0] if retro_files else None


def write_audit_log(project_dir: Path, event: str, details: str) -> None:
    """Write hook execution to audit trail (best-effort)."""
    try:
        audit_dir = project_dir / AUDIT_DIR_NAME
        audit_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        audit_file = audit_dir / f"audit-{today}.jsonl"
        entry = json.dumps({
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "hook": "invoke_context_loader",
            "event": event,
            "details": details,
        })
        with open(audit_file, "a", encoding="utf-8") as f:
            _lock_file(f)
            try:
                f.write(entry + "\n")
            finally:
                _unlock_file(f)
    except OSError:
        pass  # Fail-open


def main() -> int:
    """Load HANDOFF.md and latest retro, print to stdout for context injection."""
    # Skip if stdin is a TTY (interactive, not piped from Claude)
    if sys.stdin.isatty():
        return 0

    # Read stdin (Claude provides JSON context)
    try:
        stdin_data = sys.stdin.read()
    except Exception as e:
        print(f"[hook-error] invoke_context_loader stdin: {type(e).__name__}: {e}", file=sys.stderr)
        stdin_data = ""

    project_dir = get_project_directory()
    if not project_dir:
        return 0  # Fail-open

    loaded_files = []
    output_parts = []

    # Load HANDOFF.md
    handoff_path = project_dir / ".agents" / "HANDOFF.md"
    if handoff_path.is_file():
        try:
            content = handoff_path.read_text(encoding="utf-8")[:MAX_CHARS_PER_FILE]
            output_parts.append(
                f"--- HANDOFF.md (auto-loaded by context_loader hook) ---\n{content}\n"
            )
            loaded_files.append("HANDOFF.md")
        except OSError:
            pass  # Fail-open

    # Load latest retrospective
    retro_dir = project_dir / ".agents" / "retrospective"
    latest_retro = get_latest_retrospective(retro_dir)
    if latest_retro:
        try:
            content = latest_retro.read_text(encoding="utf-8")[:MAX_CHARS_PER_FILE]
            output_parts.append(
                f"--- Latest Retro: {latest_retro.name} (auto-loaded) ---\n{content}\n"
            )
            loaded_files.append(latest_retro.name)
        except OSError:
            pass  # Fail-open

    # Print to stdout (injected into Claude's context)
    if output_parts:
        print("\n".join(output_parts))

    # Audit log
    write_audit_log(
        project_dir,
        "context_loaded",
        f"Loaded: {', '.join(loaded_files) if loaded_files else 'none'}",
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
