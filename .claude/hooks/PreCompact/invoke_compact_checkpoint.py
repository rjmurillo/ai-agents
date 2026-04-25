#!/usr/bin/env python3
"""Checkpoint work-in-progress state before context compaction.

Claude Code PreCompact hook that snapshots the current work state before
context is compacted, providing a resume context for the post-compaction
session.

Captures:
1. Current session log path and last-modified timestamp
2. Open TODO items from session log work field
3. Current git branch
4. Resume context string (printed to stdout for injection)

Hook Type: PreCompact (non-blocking, fail-open)
Exit Codes:
    0 = Always (never blocks compaction)

References:
    - Issue #1703 (lifecycle hook infrastructure)
    - Issue #1691 (anti-drift protocol)
    - ADR-008 (protocol automation)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# --- Standard hook boilerplate ---
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if os.path.isdir(_lib_dir) and _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

try:
    from hook_utilities import get_project_directory, get_today_session_log
    from hook_utilities.guards import skip_if_consumer_repo
except ImportError:

    def get_project_directory() -> str:
        env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
        if env_dir:
            return str(Path(env_dir).resolve())
        return str(Path.cwd())

    def get_today_session_log(sessions_dir: str, date: str | None = None) -> Path | None:
        if date is None:
            date = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        sessions_path = Path(sessions_dir)
        if not sessions_path.is_dir():
            return None
        try:
            logs = sorted(
                sessions_path.glob(f"{date}-session-*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return None
        return logs[0] if logs else None

    def skip_if_consumer_repo(hook_name: str) -> bool:
        agents_path = Path(get_project_directory()) / ".agents"
        if not agents_path.is_dir():
            print(f"[SKIP] {hook_name}: .agents/ not found (consumer repo)", file=sys.stderr)
            return True
        return False


HOOK_NAME = "compact-checkpoint"


def _get_current_branch() -> str:
    """Get the current git branch name."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except OSError:
        pass
    return "(unknown)"


def _extract_open_items(session_log: Path) -> list[str]:
    """Extract open/incomplete work items from session log."""
    items: list[str] = []
    try:
        content = session_log.read_text(encoding="utf-8", errors="replace")
        data = json.loads(content)

        work = data.get("work", [])
        if isinstance(work, list):
            for w in work:
                if isinstance(w, dict):
                    status = w.get("status", "").lower()
                    if status not in ("done", "complete", "completed"):
                        desc = w.get("description", w.get("task", str(w)))
                        items.append(str(desc))
                elif isinstance(w, str):
                    items.append(w)
    except (json.JSONDecodeError, OSError):
        pass
    return items


def _write_checkpoint(
    project_dir: str,
    session_log_name: str,
    session_mtime: str,
    branch: str,
    open_items: list[str],
    resume_context: str,
) -> None:
    """Write checkpoint file for compaction recovery."""
    checkpoint_dir = Path(project_dir) / ".agents" / ".hook-state"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    timestamp = datetime.now(tz=UTC).strftime("%H%M%S")

    checkpoint_file = checkpoint_dir / f"pre-compact-{today}-{timestamp}.json"
    checkpoint_data = {
        "session_log": session_log_name,
        "session_mtime": session_mtime,
        "branch": branch,
        "open_items": open_items,
        "resume_context": resume_context,
        "created_at": datetime.now(tz=UTC).isoformat(),
    }

    checkpoint_file.write_text(
        json.dumps(checkpoint_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    """Snapshot state before context compaction."""
    if skip_if_consumer_repo(HOOK_NAME):
        sys.exit(0)

    project_dir = get_project_directory()
    project_path = Path(project_dir)

    # Get session log
    sessions_dir = str(project_path / ".agents" / "sessions")
    session_log = get_today_session_log(sessions_dir)

    session_log_name = session_log.name if session_log else "(none)"
    session_mtime = ""
    if session_log and session_log.exists():
        try:
            mtime = session_log.stat().st_mtime
            session_mtime = datetime.fromtimestamp(mtime, tz=UTC).isoformat()
        except OSError:
            session_mtime = "(unknown)"

    # Get open items
    open_items = _extract_open_items(session_log) if session_log else []

    # Get branch
    branch = _get_current_branch()

    # Build resume context
    timestamp = datetime.now(tz=UTC).isoformat()
    item_count = len(open_items)
    resume_context = (
        f"Compaction occurred at {timestamp}. "
        f"Resume from: {session_log_name}. "
        f"Branch: {branch}. "
        f"Open items: {item_count}."
    )

    if open_items:
        items_preview = "; ".join(open_items[:5])
        if len(open_items) > 5:
            items_preview += f" ... (+{len(open_items) - 5} more)"
        resume_context += f" Items: {items_preview}"

    # Write checkpoint
    _write_checkpoint(
        project_dir,
        session_log_name,
        session_mtime,
        branch,
        open_items,
        resume_context,
    )

    # Print resume context to stdout (injected into compacted context)
    print(f"## ⚠️ Pre-Compaction Checkpoint\n\n{resume_context}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[WARNING] {HOOK_NAME} error: {exc}", file=sys.stderr)
        sys.exit(0)
