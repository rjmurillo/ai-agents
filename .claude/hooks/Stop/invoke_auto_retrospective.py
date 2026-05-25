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

import fcntl
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
    from hook_utilities import get_project_directory, get_recent_session_log, get_today_session_log
    from hook_utilities.guards import skip_if_consumer_repo
except ImportError:
    from datetime import timedelta

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

    def get_recent_session_log(sessions_dir: str) -> Path | None:
        """Return newest today or yesterday session log for cross-midnight support."""
        sessions_path = Path(sessions_dir)
        if not sessions_path.is_dir():
            return None
        now = datetime.now(tz=UTC)
        for offset in (0, 1):
            date = (now - timedelta(days=offset)).strftime("%Y-%m-%d")
            try:
                candidates = list(sessions_path.glob(f"{date}-session-*.json"))
                if candidates:
                    return max(candidates, key=lambda p: p.stat().st_mtime)
            except OSError:
                continue
        return None

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


def _find_today_retro_filename(retro_dir: Path, today: str) -> str | None:
    """Return the basename of today's retro markdown, or None.

    Used by main() to repair a missing INDEX.md row when the per-day
    retro file already exists. Returns the lexically-first match so the
    result is deterministic when multiple files exist for the same day.
    """
    if not retro_dir.is_dir():
        return None
    try:
        matches = sorted(retro_dir.glob(f"{today}*.md"))
    except OSError:
        return None
    if not matches:
        return None
    return matches[0].name


def _is_trivial_session(session_log: Path | None) -> bool:
    """Check if session was trivial (too short to warrant retrospective).

    Streams only the bytes needed instead of loading the whole file, so
    large session logs do not balloon hook memory.
    """
    if session_log is None:
        return True
    try:
        with session_log.open(encoding="utf-8", errors="replace") as handle:
            content = handle.read(TRIVIAL_SESSION_THRESHOLD)
        return len(content) < TRIVIAL_SESSION_THRESHOLD
    except OSError:
        return True


def _extract_text_items(value: object) -> list[str]:
    """Pull human-readable strings from a JSON value of any supported shape.

    Supports the legacy ``outcomes: [str, ...]`` shape, the current
    ``outcomes: { ... }`` shape, and the observed ``work: { tasks: [...] }``
    shape (see ``.agents/sessions/2026-02-08-session-1194.json``). Returns
    an ordered list with empty strings filtered out.
    """
    items: list[str] = []
    if isinstance(value, str):
        if value.strip():
            items.append(value)
    elif isinstance(value, list):
        for entry in value:
            items.extend(_extract_text_items(entry))
    elif isinstance(value, dict):
        # ``status`` is a state token ("done", "in_progress"), not a
        # description; including it would produce bullets like ``- done``
        # when an entry has only ``status`` set. Outcome/result keys carry
        # narrative content and stay.
        preferred_keys = (
            "description",
            "task",
            "summary",
            "result",
            "outcome",
            "title",
            "name",
            "detail",
            "details",
        )
        for key in preferred_keys:
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                items.append(text)
                break
    return items


def _extract_session_summary(session_log: Path) -> dict[str, str]:
    """Extract summary info from session log JSON.

    Tolerates non-dict roots, the legacy list shapes for ``outcomes`` and
    ``work``, and the current schema where ``outcomes`` is an object and
    work is recorded under ``workLog`` or ``work.tasks``/``work.filesChanged``.
    """
    result = {"objective": "", "outcomes": "", "work_items": ""}
    try:
        content = session_log.read_text(encoding="utf-8", errors="replace")
        data = json.loads(content)
    except (json.JSONDecodeError, OSError):
        return result

    if not isinstance(data, dict):
        return result

    objective = data.get("objective", "")
    result["objective"] = objective if isinstance(objective, str) else ""

    def _as_bullets(values: list[str]) -> str:
        return "\n".join(
            f"- {value}" for value in values if isinstance(value, str) and value.strip()
        )

    # Outcomes: support legacy list shape and current object shape.
    outcomes = data.get("outcomes", [])
    outcome_items: list[str] = []
    if isinstance(outcomes, list):
        outcome_items.extend(_extract_text_items(outcomes))
    elif isinstance(outcomes, dict):
        for key in ("completed", "achieved", "results", "items", "summary"):
            if key in outcomes:
                outcome_items.extend(_extract_text_items(outcomes[key]))
        if not outcome_items:
            for value in outcomes.values():
                outcome_items.extend(_extract_text_items(value))
    elif isinstance(outcomes, str):
        outcome_items.extend(_extract_text_items(outcomes))
    result["outcomes"] = _as_bullets(outcome_items)

    # Work: legacy list, current ``workLog``, and observed object-shaped
    # ``work`` with ``tasks``/``filesChanged`` keys.
    work_items: list[str] = []
    work_log = data.get("workLog", [])
    work = data.get("work", [])

    if isinstance(work_log, (str, list, dict)):
        work_items.extend(_extract_text_items(work_log))

    if isinstance(work, list):
        work_items.extend(_extract_text_items(work))
    elif isinstance(work, dict):
        if "tasks" in work:
            work_items.extend(_extract_text_items(work.get("tasks")))
        if "filesChanged" in work:
            files_changed = work.get("filesChanged")
            if isinstance(files_changed, list):
                for file_path in files_changed:
                    if isinstance(file_path, str) and file_path.strip():
                        work_items.append(f"Changed {file_path}")
            else:
                work_items.extend(_extract_text_items(files_changed))
        remaining_work = {
            key: value
            for key, value in work.items()
            if key not in {"tasks", "filesChanged"}
        }
        if remaining_work:
            work_items.extend(_extract_text_items(remaining_work))
    elif isinstance(work, str):
        work_items.extend(_extract_text_items(work))

    result["work_items"] = _as_bullets(work_items)

    return result


def _generate_retrospective(today: str, session_summary: dict[str, str]) -> str:
    """Generate a structured retrospective template."""
    objective = session_summary.get("objective") or "(no objective recorded)"
    outcomes = session_summary.get("outcomes") or "(no outcomes recorded)"
    work_items = session_summary.get("work_items") or "(no work items recorded)"

    return f"""# Auto-Retrospective: {today}

> Generated automatically by the auto-retrospective Stop hook.
> Review and refine this template with actual observations.
> Per `.claude/rules/retros.md`: fill in Failure Mode Classification,
> Evidence, and Remediation before this entry can be considered complete.

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

## Failure Mode Classification

<!-- Required by .claude/rules/retros.md MUST #2.
     Map each failure to a class in .agents/governance/FAILURE-MODES.md.
     If no existing class matches, propose a new class in a linked ADR. -->
- (classify against FAILURE-MODES.md)

## Failure Patterns

<!-- Recurring patterns that led to issues -->
- (review session log and add observations)

## Evidence

<!-- Required by .claude/rules/retros.md MUST #3.
     Links to offending commits, PRs, issues, or CI runs. No hand-waving. -->
- (link commits, PRs, issues, CI runs)

## Remediation

<!-- Required by .claude/rules/retros.md MUST #4.
     Concrete follow-up actions (governance change, ADR, instruction
     update, skill change) with owners or issues. -->
- (list concrete remediations with owners)

## Work Completed

{work_items}

## Outcomes

{outcomes}

---

*Auto-generated by invoke_auto_retrospective.py (Issue #1703)*
"""


def _index_has_entry_for(index_path: Path, filename: str) -> bool:
    """Return True when INDEX.md already references `filename`.

    Used to make _update_retro_index idempotent so a previous index-write
    failure can be retried on the next Stop hook invocation even after
    the per-day retro markdown exists. The check is a plain substring
    match because every row this hook writes embeds the exact filename.
    """
    try:
        return filename in index_path.read_text(encoding="utf-8")
    except OSError:
        return False


def _update_retro_index(project_dir: str, today: str, filename: str) -> None:
    """Append entry to docs/retros/INDEX.md, creating it if needed.

    Idempotent: a second call with the same (today, filename) is a
    no-op once the row is present. This lets the caller re-run on
    later sessions if a prior index-write failed after the retro
    markdown was already written.

    Uses advisory file locking to prevent concurrent Stop hooks from
    racing on the check-then-append operation.
    """
    index_path = Path(project_dir) / "docs" / "retros" / "INDEX.md"

    try:
        index_path.parent.mkdir(parents=True, exist_ok=True)

        header = (
            "# Retrospective Index\n\n"
            "> Auto-maintained by the auto-retrospective Stop hook (Issue #1703).\n"
            "> Manual entries are welcome; the hook only appends new rows.\n\n"
            "| Date | File | Summary |\n"
            "|------|------|---------|\n"
        )

        if not index_path.exists():
            index_path.write_text(header, encoding="utf-8")

        with index_path.open("r+", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                content = f.read()
                if filename in content:
                    return
                f.seek(0, 2)
                f.write(f"| {today} | [{filename}](../../.agents/retrospective/{filename}) "
                        f"| Auto-generated session retrospective |\n")
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        print(f"[WARNING] {HOOK_NAME}: Failed to update INDEX.md: {exc}", file=sys.stderr)


def _resolve_safe_project_path() -> Path | None:
    """Resolve the project directory and require it to look like a repo root.

    Defends against a misconfigured ``CLAUDE_PROJECT_DIR`` pointing outside
    the repository, which would otherwise let this hook write retro files
    anywhere on disk. Validates via repo signals (``.agents/`` or ``.git/``)
    instead of comparing against ``__file__.parents[3]``: when this hook
    runs from an installed plugin location, the script's parent chain has
    nothing to do with the user's repo, so a path-prefix check would
    spuriously reject valid project directories.
    """
    candidate = Path(get_project_directory()).resolve()
    if (candidate / ".agents").is_dir() or (candidate / ".git").is_dir():
        return candidate
    print(
        f"[WARNING] {HOOK_NAME}: project_dir lacks .agents/ or .git/ "
        f"signal, refusing to write under: {candidate}",
        file=sys.stderr,
    )
    return None


def main() -> None:
    """Generate retrospective if one doesn't exist for today."""
    if skip_if_consumer_repo(HOOK_NAME):
        sys.exit(0)

    if os.environ.get("SKIP_AUTO_RETRO", "").lower() == "true":
        sys.exit(0)

    project_path = _resolve_safe_project_path()
    if project_path is None:
        sys.exit(0)
    project_dir = str(project_path)
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    retro_dir = project_path / ".agents" / "retrospective"

    # Idempotent: skip retro generation if one already exists today, but
    # still retry the INDEX.md update so a previous index-write failure
    # is recoverable on the next Stop hook invocation. _update_retro_index
    # short-circuits when the row is already present.
    if _retro_exists_today(retro_dir, today):
        existing = _find_today_retro_filename(retro_dir, today)
        if existing is not None:
            _update_retro_index(project_dir, today, existing)
        print(f"[INFO] {HOOK_NAME}: Retrospective already exists for {today}", file=sys.stderr)
        sys.exit(0)

    # Check for trivial session using get_recent_session_log to support
    # sessions spanning midnight (falls back to yesterday's log if today's
    # is missing or trivial).
    sessions_dir = str(project_path / ".agents" / "sessions")
    session_log = get_recent_session_log(sessions_dir)

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
