#!/usr/bin/env python3
"""Auto-generate retrospective on session stop.

Claude Code Stop hook that creates a structured retrospective template
when one doesn't already exist for today. Updates docs/retros/INDEX.md
for tracking.

Addresses inconsistent retrospective generation where the manual process
is often skipped.

Behavior:
1. Check if retrospective exists for today (idempotent)
2. If none: create structured template from session log data
3. Update docs/retros/INDEX.md with new entry

Bypass conditions:
- SKIP_AUTO_RETRO=true environment variable
- Retrospective already exists for today
- Trivial session (session log < 500 chars or missing)

Hook Type: Stop (non-blocking, always exit 0)
Exit Codes:
    0 = Always (never blocks session stop)

References:
    - Issue #1703 (lifecycle hook infrastructure)
    - ADR-008 (protocol automation)
"""

from __future__ import annotations

import json
import os
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


HOOK_NAME = "auto-retrospective"
TRIVIAL_SESSION_THRESHOLD = 500  # chars


def _retro_exists_today(retro_dir: Path, today: str) -> bool:
    """Check if any retrospective exists for today."""
    if not retro_dir.is_dir():
        return False
    try:
        return any(retro_dir.glob(f"{today}*.md"))
    except OSError:
        return False


def _is_trivial_session(session_log: Path | None) -> bool:
    """Check if session was trivial (too short to warrant retrospective)."""
    if session_log is None:
        return True
    try:
        content = session_log.read_text(encoding="utf-8", errors="replace")
        return len(content) < TRIVIAL_SESSION_THRESHOLD
    except OSError:
        return True


def _extract_session_summary(session_log: Path) -> dict[str, str]:
    """Extract summary info from session log JSON."""
    result = {"objective": "", "outcomes": "", "work_items": ""}
    try:
        content = session_log.read_text(encoding="utf-8", errors="replace")
        data = json.loads(content)

        result["objective"] = data.get("objective", "")

        # Extract outcomes
        outcomes = data.get("outcomes", [])
        if isinstance(outcomes, list):
            result["outcomes"] = "\n".join(f"- {o}" for o in outcomes if isinstance(o, str))

        # Extract work items
        work = data.get("work", [])
        if isinstance(work, list):
            items = []
            for w in work:
                if isinstance(w, dict):
                    items.append(f"- {w.get('description', w.get('task', str(w)))}")
                elif isinstance(w, str):
                    items.append(f"- {w}")
            result["work_items"] = "\n".join(items)
    except (json.JSONDecodeError, OSError):
        pass

    return result


def _generate_retrospective(today: str, session_summary: dict[str, str]) -> str:
    """Generate a structured retrospective template."""
    objective = session_summary.get("objective") or "(no objective recorded)"
    outcomes = session_summary.get("outcomes") or "(no outcomes recorded)"
    work_items = session_summary.get("work_items") or "(no work items recorded)"

    return f"""# Auto-Retrospective: {today}

> Generated automatically by the auto-retrospective Stop hook.
> Review and refine this template with actual observations.

## Session Objective

{objective}

## What Went Well

<!-- List things that worked effectively this session -->
- (review session log and add observations)

## What Could Improve

<!-- List things that could be done better -->
- (review session log and add observations)

## Key Learnings

<!-- Specific learnings that should persist across sessions -->
- (review session log and add observations)

## Failure Patterns

<!-- Recurring patterns that led to issues -->
- (review session log and add observations)

## Work Completed

{work_items}

## Outcomes

{outcomes}

---

*Auto-generated by invoke_auto_retrospective.py (Issue #1703)*
"""


def _update_retro_index(project_dir: str, today: str, filename: str) -> None:
    """Append entry to docs/retros/INDEX.md, creating it if needed."""
    index_path = Path(project_dir) / "docs" / "retros" / "INDEX.md"

    try:
        index_path.parent.mkdir(parents=True, exist_ok=True)

        if not index_path.exists():
            header = (
                "# Retrospective Index\n\n"
                "> Auto-maintained by the auto-retrospective Stop hook.\n\n"
                "| Date | File | Summary |\n"
                "|------|------|---------|\n"
            )
            index_path.write_text(header, encoding="utf-8")

        # Append new row
        with index_path.open("a", encoding="utf-8") as f:
            f.write(f"| {today} | [{filename}](../../.agents/retrospective/{filename}) "
                    f"| Auto-generated session retrospective |\n")
    except OSError as exc:
        print(f"[WARNING] {HOOK_NAME}: Failed to update INDEX.md: {exc}", file=sys.stderr)


def main() -> None:
    """Generate retrospective if one doesn't exist for today."""
    if skip_if_consumer_repo(HOOK_NAME):
        sys.exit(0)

    if os.environ.get("SKIP_AUTO_RETRO", "").lower() == "true":
        sys.exit(0)

    project_dir = get_project_directory()
    project_path = Path(project_dir)
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    retro_dir = project_path / ".agents" / "retrospective"

    # Idempotent: skip if retro already exists today
    if _retro_exists_today(retro_dir, today):
        print(f"[INFO] {HOOK_NAME}: Retrospective already exists for {today}", file=sys.stderr)
        sys.exit(0)

    # Check for trivial session
    sessions_dir = str(project_path / ".agents" / "sessions")
    session_log = get_today_session_log(sessions_dir)

    if _is_trivial_session(session_log):
        print(f"[INFO] {HOOK_NAME}: Trivial session, skipping retro generation", file=sys.stderr)
        sys.exit(0)

    # Extract session data and generate retrospective
    session_summary = _extract_session_summary(session_log) if session_log else {}
    retro_content = _generate_retrospective(today, session_summary)

    # Write retrospective file
    retro_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{today}-auto-retro.md"
    retro_path = retro_dir / filename

    try:
        retro_path.write_text(retro_content, encoding="utf-8")
        print(f"📝 Auto-retrospective generated: .agents/retrospective/{filename}")
    except OSError as exc:
        print(f"[WARNING] {HOOK_NAME}: Failed to write retro: {exc}", file=sys.stderr)
        sys.exit(0)

    # Update index
    _update_retro_index(project_dir, today, filename)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[WARNING] {HOOK_NAME} error: {exc}", file=sys.stderr)
        sys.exit(0)
