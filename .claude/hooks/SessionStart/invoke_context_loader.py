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

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if os.path.isdir(_lib_dir) and _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

try:
    from hook_utilities import get_project_directory as _get_project_directory
    from hook_utilities import lock_file as _lock_file
    from hook_utilities import unlock_file as _unlock_file

    def get_project_directory() -> Path | None:
        """Wrap shared utility returning Path for backward compat."""
        result = _get_project_directory()
        return Path(result) if result else None

except ImportError:
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

    _lock_file = None  # type: ignore[assignment]
    _unlock_file = None  # type: ignore[assignment]

# Maximum characters to inject per file to avoid context bloat
MAX_CHARS_PER_FILE = 4000

# Audit trail directory
AUDIT_DIR_NAME = ".agents/.hook-state"


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
            if _lock_file is not None:
                _lock_file(f)
            try:
                f.write(entry + "\n")
            finally:
                if _unlock_file is not None:
                    _unlock_file(f)
    except OSError as e:
        print(
            f"[hook-error] invoke_context_loader audit: {type(e).__name__}: {e}",
            file=sys.stderr,
        )


def main() -> int:
    """Load HANDOFF.md and latest retro, print to stdout for context injection."""
    # Skip if stdin is a TTY (interactive, not piped from Claude)
    if sys.stdin.isatty():
        return 0

    # Drain stdin so the harness pipe closes cleanly. Contents are unused;
    # the hook injects context based on filesystem state, not stdin.
    try:
        sys.stdin.read()
    except Exception as e:
        print(f"[hook-error] invoke_context_loader stdin: {type(e).__name__}: {e}", file=sys.stderr)

    project_dir = get_project_directory()
    if not project_dir:
        return 0  # Fail-open

    # Consumer-repo guard: if .agents/ does not exist, this is not an
    # ai-agents-bearing repo. Skip silently rather than create surprise files.
    if not (project_dir / ".agents").is_dir():
        return 0

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
        except OSError as e:
            print(
                f"[hook-error] invoke_context_loader handoff_read: {type(e).__name__}: {e}",
                file=sys.stderr,
            )

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
        except OSError as e:
            print(
                f"[hook-error] invoke_context_loader retro_read: {type(e).__name__}: {e}",
                file=sys.stderr,
            )

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
