#!/usr/bin/env python3
"""
PostToolUse hook: Persists plan/TODO state after Write/Edit operations.

Saves lightweight checkpoints when session logs or plan files are modified,
enabling resume context after compaction.

Hook Type: PostToolUse (matcher: ^(Write|Edit)$)
Exit Codes: Always 0 (fail-open)

Related:
- Issue #1703 (lifecycle hook infrastructure)
- Issue #1691 (anti-drift protocol)
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

# Files that trigger checkpointing
PLAN_PATTERNS = [
    re.compile(r"(^|/)\.agents/sessions/.*\.json$"),
    re.compile(r"(^|/)TODO\.md$", re.IGNORECASE),
    re.compile(r"(^|/)PLAN\.md$", re.IGNORECASE),
    re.compile(r"(^|/)\.agents/plan.*\.md$", re.IGNORECASE),
    re.compile(r"(^|/)PROJECT-PLAN\.md$", re.IGNORECASE),
]


def is_plan_file(file_path: str) -> bool:
    """Check if the modified file is a plan/session/TODO file."""
    # Normalize to forward slashes for pattern matching
    normalized = file_path.replace("\\", "/")
    return any(p.search(normalized) for p in PLAN_PATTERNS)


def write_checkpoint(project_dir: Path, file_path: str, content: str) -> None:
    """Write a lightweight checkpoint for the modified plan file."""
    hook_state_dir = project_dir / ".agents" / ".hook-state"
    hook_state_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    checkpoint_file = hook_state_dir / f"plan-checkpoint-{today}.json"

    # Create file if it doesn't exist
    if not checkpoint_file.exists():
        checkpoint_file.write_text("[]", encoding="utf-8")

    # Locked read-modify-write to prevent race conditions
    with open(checkpoint_file, "r+", encoding="utf-8") as f:
        _lock_file(f)
        try:
            # Read existing checkpoint data
            f.seek(0)
            existing = []
            try:
                existing = json.load(f)
                if not isinstance(existing, list):
                    existing = [existing]
            except (json.JSONDecodeError, OSError):
                existing = []

            # Append new checkpoint entry
            entry = {
                "file": file_path,
                "timestamp": datetime.now(tz=UTC).isoformat(),
                "summary": content[:500],
            }
            existing.append(entry)

            # Keep only last 20 entries to avoid unbounded growth
            if len(existing) > 20:
                existing = existing[-20:]

            # Write back
            f.seek(0)
            f.truncate()
            json.dump(existing, f, indent=2, ensure_ascii=False)
        finally:
            _unlock_file(f)


def main() -> int:
    """Check if modified file is a plan file and checkpoint if so."""
    # Skip if stdin is TTY
    if sys.stdin.isatty():
        return 0

    # Read stdin JSON
    try:
        stdin_data = sys.stdin.read()
        if not stdin_data.strip():
            return 0
        hook_input = json.loads(stdin_data)
    except Exception as e:
        print(f"[hook-error] invoke_plan_state_sync stdin: {type(e).__name__}: {e}", file=sys.stderr)
        return 0  # Fail-open

    # Extract file path from tool input
    tool_input = hook_input.get("tool_input", {})
    file_path = tool_input.get("file_path", "") or tool_input.get("path", "")

    if not file_path:
        return 0

    if not is_plan_file(file_path):
        return 0

    project_dir = get_project_directory()
    if not project_dir:
        return 0

    # Read the file content for summary
    try:
        full_path = Path(file_path)
        if not full_path.is_absolute():
            full_path = project_dir / file_path
        if full_path.is_file():
            content = full_path.read_text(encoding="utf-8")
        else:
            content = ""
    except OSError:
        content = ""

    try:
        write_checkpoint(project_dir, file_path, content)
    except OSError:
        pass  # Fail-open

    return 0


if __name__ == "__main__":
    sys.exit(main())
