#!/usr/bin/env python3
"""
PreCompact hook: Checkpoints work-in-progress state before context compaction.

Saves current session state, open TODO items, and branch info so agents
can resume seamlessly after compaction. Prints resume context to stdout
for injection into the compacted context.

Hook Type: PreCompact (non-blocking)
Exit Codes: Always 0 (fail-open — never blocks compaction)

Related:
- Issue #1703 (lifecycle hook infrastructure)
- Issue #1691 (anti-drift protocol)
- ADR-008 (protocol automation lifecycle hooks)
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


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


def get_current_branch() -> str:
    """Get current git branch name."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return "unknown"


def get_session_info(project_dir: Path) -> dict:
    """Get current session log info."""
    sessions_dir = project_dir / ".agents" / "sessions"
    if not sessions_dir.is_dir():
        return {}

    today = datetime.now().strftime("%Y-%m-%d")
    session_files = sorted(
        sessions_dir.glob(f"{today}-session-*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    if not session_files:
        return {}

    session_file = session_files[0]
    try:
        data = json.loads(session_file.read_text(encoding="utf-8"))
        work_items = data.get("work", [])
        return {
            "session_log": session_file.name,
            "last_modified": datetime.fromtimestamp(
                session_file.stat().st_mtime
            ).isoformat(),
            "open_items_count": len(work_items),
            "work_items": [
                (item if isinstance(item, str) else item.get("description", str(item)))
                for item in work_items[:5]
            ],
        }
    except (json.JSONDecodeError, OSError):
        return {"session_log": session_file.name}


def main() -> int:
    """Checkpoint state before compaction."""
    # Skip if stdin is TTY
    if sys.stdin.isatty():
        return 0

    # Consume stdin
    try:
        sys.stdin.read()
    except Exception:
        pass

    project_dir = get_project_directory()
    if not project_dir:
        return 0

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%H%M%S")
    branch = get_current_branch()
    session_info = get_session_info(project_dir)

    # Build checkpoint
    checkpoint = {
        "timestamp": now.isoformat(),
        "branch": branch,
        "session": session_info,
        "resume_context": (
            f"Compaction occurred at {now.strftime('%H:%M:%S')}. "
            f"Branch: {branch}. "
            f"Session: {session_info.get('session_log', 'none')}. "
            f"Open items: {session_info.get('open_items_count', 0)}"
        ),
    }

    # Write checkpoint file
    try:
        hook_state_dir = project_dir / ".agents" / ".hook-state"
        hook_state_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_file = hook_state_dir / f"pre-compact-{today}-{timestamp}.json"
        checkpoint_file.write_text(
            json.dumps(checkpoint, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass  # Fail-open

    # Print resume context to stdout (injected into compacted context)
    print(checkpoint["resume_context"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
