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
from datetime import UTC, datetime
from pathlib import Path

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

try:
    from hook_utilities import coerce_to_list as _coerce_to_list
    from hook_utilities import get_project_directory as _get_project_directory
    from hook_utilities import get_recent_session_log as _get_recent_session_log

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

    _get_recent_session_log = None  # type: ignore[assignment]
    _coerce_to_list = None  # type: ignore[assignment]


def get_current_branch(project_dir: Path | None = None) -> str:
    """Get current git branch name."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(project_dir) if project_dir else None,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        print(
            f"[hook-error] invoke_compact_checkpoint get_current_branch: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
    return "unknown"


def _coerce_to_list_fallback(value) -> list:
    """Fallback normalizer when hook_utilities is unavailable."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("tasks", "items", "log", "entries"):
            inner = value.get(key)
            if isinstance(inner, list):
                return inner
        for v in value.values():
            if isinstance(v, list):
                return v
        return [value]
    if isinstance(value, str):
        return [value] if value.strip() else []
    return []


def coerce_to_list(value) -> list:
    """Normalize work to a list across legacy and current session schema shapes."""
    if _coerce_to_list is not None:
        return _coerce_to_list(value)
    return _coerce_to_list_fallback(value)


def _format_work_item(item: dict) -> str:
    """Format a work item dict into a human-readable string.

    Supports multiple session schemas:
    - Current: {'step': N, 'action': '...', 'outcome': '...'}
    - Legacy: {'description': '...'} or {'task': '...'}
    """
    # Try current schema (step/action/outcome)
    if "action" in item:
        parts = []
        if "step" in item:
            parts.append(f"Step {item['step']}:")
        parts.append(item["action"])
        if "outcome" in item:
            parts.append(f"→ {item['outcome']}")
        return " ".join(parts)
    # Try legacy schemas
    if "description" in item:
        return item["description"]
    if "task" in item:
        return item["task"]
    # Fallback to repr
    return str(item)


def _find_recent_session_fallback(sessions_dir: Path) -> Path | None:
    """Fallback session lookup when hook_utilities is unavailable."""
    from datetime import timedelta

    now = datetime.now(tz=UTC)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    candidates = []
    for date_prefix in (today, yesterday):
        candidates.extend(sessions_dir.glob(f"{date_prefix}-session-*.json"))

    if not candidates:
        return None

    return max(candidates, key=lambda f: f.stat().st_mtime)


def get_session_info(project_dir: Path) -> dict:
    """Get current session log info.

    Checks both today's and yesterday's session files (UTC) to handle sessions
    that span midnight.
    """
    sessions_dir = project_dir / ".agents" / "sessions"
    if not sessions_dir.is_dir():
        return {}

    # Use shared utility if available (handles cross-midnight)
    if _get_recent_session_log is not None:
        session_file = _get_recent_session_log(str(sessions_dir))
    else:
        session_file = _find_recent_session_fallback(sessions_dir)

    if not session_file:
        return {}
    try:
        data = json.loads(session_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"session_log": session_file.name}
        # Modern schema is workLog; legacy is work (sometimes a dict wrapper).
        work_raw = data.get("workLog")
        if not work_raw:
            work_raw = data.get("work", [])
        work_items = coerce_to_list(work_raw)
        return {
            "session_log": session_file.name,
            "last_modified": datetime.fromtimestamp(
                session_file.stat().st_mtime, tz=UTC
            ).isoformat(),
            "open_items_count": len(work_items),
            "work_items": [
                (
                    item if isinstance(item, str)
                    else _format_work_item(item) if isinstance(item, dict)
                    else str(item)
                )
                for item in work_items[:5]
            ],
        }
    except (json.JSONDecodeError, OSError) as e:
        print(
            f"[hook-error] invoke_compact_checkpoint get_session_info: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return {"session_log": session_file.name}


def main() -> int:
    """Checkpoint state before compaction."""
    # Skip if stdin is TTY
    if sys.stdin.isatty():
        return 0

    # Consume stdin
    try:
        sys.stdin.read()
    except Exception as e:
        print(f"[hook-error] invoke_compact_checkpoint stdin: {type(e).__name__}: {e}", file=sys.stderr)

    project_dir = get_project_directory()
    if not project_dir:
        return 0

    now = datetime.now(tz=UTC)
    today = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%H%M%S")
    branch = get_current_branch(project_dir)
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

    # Write checkpoint file (skip silently in consumer repos that lack .agents/)
    try:
        agents_dir = project_dir / ".agents"
        if not agents_dir.is_dir():
            return 0
        hook_state_dir = agents_dir / ".hook-state"
        hook_state_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_file = hook_state_dir / f"pre-compact-{today}-{timestamp}.json"
        checkpoint_file.write_text(
            json.dumps(checkpoint, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as e:
        print(
            f"[hook-error] invoke_compact_checkpoint checkpoint write: {type(e).__name__}: {e}",
            file=sys.stderr,
        )

    # Print resume context to stdout (injected into compacted context)
    print(checkpoint["resume_context"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
