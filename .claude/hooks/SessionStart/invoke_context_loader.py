#!/usr/bin/env python3
"""Auto-load HANDOFF.md and latest retrospective at session start.

Claude Code SessionStart hook that injects critical context files into
the session to eliminate the 95.8% context reading failure rate documented
in retrospective analysis.

Loads:
1. .agents/HANDOFF.md (read-only dashboard of project state)
2. Latest retrospective from .agents/retrospective/ (learnings from prior sessions)

Both are truncated to prevent context bloat. Output is printed to stdout
so Claude Code injects it into the session context.

Hook Type: SessionStart (non-blocking, fail-open)
Exit Codes:
    0 = Success (always, fail-open)

References:
    - Issue #1703 (lifecycle hook infrastructure)
    - Issue #1672 (session-start gate)
    - ADR-008 (protocol automation via lifecycle hooks)
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# --- Standard hook boilerplate: resolve lib directory ---
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if os.path.isdir(_lib_dir) and _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

try:
    from hook_utilities import get_project_directory
    from hook_utilities.guards import skip_if_consumer_repo
except ImportError:

    def get_project_directory() -> str:
        env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
        if env_dir:
            return str(Path(env_dir).resolve())
        return str(Path.cwd())

    def skip_if_consumer_repo(hook_name: str) -> bool:
        agents_path = Path(get_project_directory()) / ".agents"
        if not agents_path.is_dir():
            print(f"[SKIP] {hook_name}: .agents/ not found (consumer repo)", file=sys.stderr)
            return True
        return False


# Maximum characters to inject per file to prevent context bloat
MAX_HANDOFF_CHARS = 4000
MAX_RETRO_CHARS = 4000

HOOK_NAME = "context-loader"


def _read_file_truncated(path: Path, max_chars: int) -> str | None:
    """Read a file, truncating to max_chars if necessary."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    if len(content) > max_chars:
        return content[:max_chars] + f"\n\n[... truncated at {max_chars} chars ...]"
    return content


def _find_latest_retrospective(retro_dir: Path) -> Path | None:
    """Find the most recent retrospective file by modification time."""
    if not retro_dir.is_dir():
        return None

    try:
        retro_files = sorted(
            retro_dir.glob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None

    return retro_files[0] if retro_files else None


def _write_audit_log(project_dir: str, loaded_files: list[str]) -> None:
    """Write a brief audit entry for session start context loading."""
    try:
        audit_dir = Path(project_dir) / ".agents" / ".hook-state"
        audit_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        timestamp = datetime.now(tz=UTC).isoformat()
        audit_file = audit_dir / f"context-loader-{today}.log"

        with audit_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] Loaded: {', '.join(loaded_files)}\n")
    except OSError:
        pass  # Fail-open: audit is best-effort


def main() -> None:
    """Load HANDOFF.md and latest retrospective into session context."""
    if skip_if_consumer_repo(HOOK_NAME):
        sys.exit(0)

    project_dir = get_project_directory()
    project_path = Path(project_dir)
    loaded_files: list[str] = []
    output_parts: list[str] = []

    # 1. Load HANDOFF.md
    handoff_path = project_path / ".agents" / "HANDOFF.md"
    handoff_content = _read_file_truncated(handoff_path, MAX_HANDOFF_CHARS)
    if handoff_content:
        output_parts.append(
            "## 📋 Auto-loaded: HANDOFF.md (read-only dashboard)\n\n"
            f"{handoff_content}"
        )
        loaded_files.append("HANDOFF.md")

    # 2. Load latest retrospective
    retro_dir = project_path / ".agents" / "retrospective"
    latest_retro = _find_latest_retrospective(retro_dir)
    if latest_retro:
        retro_content = _read_file_truncated(latest_retro, MAX_RETRO_CHARS)
        if retro_content:
            output_parts.append(
                f"## 📝 Auto-loaded: Latest Retrospective ({latest_retro.name})\n\n"
                f"{retro_content}"
            )
            loaded_files.append(f"retrospective/{latest_retro.name}")

    # Output to stdout (injected into Claude's context)
    if output_parts:
        header = "## 🔄 Context Loader: Session Start Auto-Injection\n\n"
        summary = f"**Loaded {len(loaded_files)} file(s)**: {', '.join(loaded_files)}\n\n---\n\n"
        print(header + summary + "\n\n---\n\n".join(output_parts))
    else:
        print("## 🔄 Context Loader: No context files found to auto-load")

    # Audit trail (best-effort)
    _write_audit_log(project_dir, loaded_files if loaded_files else ["(none)"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Fail-open: never block session start
        print(f"[WARNING] context-loader error: {exc}", file=sys.stderr)
        sys.exit(0)
