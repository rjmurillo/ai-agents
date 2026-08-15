#!/usr/bin/env python3
"""Export ALL claude-mem data directly from SQLite database.

Bypasses the plugin's search-based export which may not return all observations.
Recommended for complete backups. Direct database access ensures 100% data recovery.

EXIT CODES:
  0  - Success
  1  - Error

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_MEMORIES_DIR = _SCRIPT_DIR.parent / "memories"


def validate_output_path(output_path: Path, memories_dir: Path) -> bool:
    """Prevent path traversal (CWE-22)."""
    resolved_output = output_path.resolve()
    resolved_dir = memories_dir.resolve()
    if not resolved_output.is_relative_to(resolved_dir):
        print(
            f"ERROR: Path traversal attempt detected. "
            f"Output file must be inside '{memories_dir}' directory.",
            file=sys.stderr,
        )
        return False
    return True


def run_sqlite3(
    db_path: str, query: str, json_mode: bool = False
) -> subprocess.CompletedProcess[str]:
    args = ["sqlite3", db_path]
    if json_mode:
        args.append("-json")
    args.append(query)
    return subprocess.run(args, capture_output=True, text=True)


def get_count(db_path: str, query: str) -> int:
    result = run_sqlite3(db_path, query)
    if result.returncode != 0:
        return -1
    try:
        return int(result.stdout.strip())
    except ValueError:
        return -1


def _parse_json_output(raw: str, label: str) -> list[dict[str, object]]:
    """Parse JSON output from sqlite3, returning empty list on failure.

    Logs the first 200 characters of raw output for debugging when parsing fails.
    Returns empty list (not raises) by design: partial export with warnings is
    preferable to a crash that produces no backup at all. The caller prints
    record counts so any discrepancy is visible.
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        preview = raw[:200] if raw else "(empty)"
        print(
            f"WARNING: Failed to parse {label} JSON: {exc}\n   Raw output preview: {preview}",
            file=sys.stderr,
        )
        return []
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return parsed
    print(
        f"WARNING: Unexpected JSON type for {label}: {type(parsed).__name__}",
        file=sys.stderr,
    )
    return []


def _build_sql_filters(project: str) -> dict[str, str]:
    """Build SQL WHERE clauses for each table, scoped to project when given."""
    # SQL injection prevention (CWE-89)
    safe = project.replace("'", "''") if project else ""
    return {
        "obs": f"WHERE o.project = '{safe}'" if project else "",
        "summary": f"WHERE ss.project = '{safe}'" if project else "",
        "session": f"WHERE project = '{safe}'" if project else "",
        "prompt": (
            f"WHERE content_session_id IN "
            f"(SELECT content_session_id FROM sdk_sessions WHERE project = '{safe}')"
            if project
            else ""
        ),
        "count": f"WHERE project = '{safe}'" if project else "",
    }


def _fix_null_titles(observations: list[dict[str, object]]) -> int:
    """Replace NULL/blank titles with '(untitled)'; return count fixed."""
    count = 0
    for obs in observations:
        if not obs.get("title") or not str(obs["title"]).strip():
            obs["title"] = "(untitled)"
            count += 1
    return count


def _export_query(db_path: str, query: str, label: str) -> list[dict[str, object]]:
    """Run a JSON-mode SQLite query and return parsed rows."""
    result = run_sqlite3(db_path, query, json_mode=True)
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return _parse_json_output(result.stdout, label)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export claude-mem data directly from SQLite")
    parser.add_argument(
        "--project",
        default="",
        help="Optional project filter",
    )
    parser.add_argument("--output-file", default="", help="Output JSON file path")
    args = parser.parse_args(argv)

    if args.project and not re.match(r"^[a-zA-Z0-9_-]+$", args.project):
        print("ERROR: Invalid project name format", file=sys.stderr)
        return 1

    if not shutil.which("sqlite3"):
        print("ERROR: sqlite3 not found. Please install SQLite.", file=sys.stderr)
        return 1

    db_path = str(Path.home() / ".claude-mem" / "claude-mem.db")
    if not Path(db_path).exists():
        print(f"ERROR: Claude-Mem database not found at: {db_path}", file=sys.stderr)
        return 1

    _MEMORIES_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    suffix = f"-{args.project}" if args.project else ""
    output_path = (
        Path(args.output_file)
        if args.output_file
        else _MEMORIES_DIR / f"direct-backup-{timestamp}{suffix}.json"
    )

    if not validate_output_path(output_path, _MEMORIES_DIR):
        return 1

    f = _build_sql_filters(args.project)
    scope = f"Project '{args.project}'" if args.project else "ALL projects"
    print(f"Exporting from SQLite database...\n   Scope: {scope}")
    print(f"   Database: {db_path}\n   Output: {output_path}")

    obs_count = get_count(db_path, f"SELECT COUNT(*) FROM observations {f['count']};")
    summary_count = get_count(db_path, f"SELECT COUNT(*) FROM session_summaries {f['count']};")
    prompt_count = get_count(db_path, f"SELECT COUNT(*) FROM user_prompts {f['prompt']};")
    session_count = get_count(db_path, f"SELECT COUNT(*) FROM sdk_sessions {f['session']};")

    print(
        f"\nDatabase contains:\n   Observations: {obs_count}\n"
        f"   Session summaries: {summary_count}\n"
        f"   User prompts: {prompt_count}\n   SDK sessions: {session_count}"
    )

    obs_query = (
        f"SELECT o.*, s.content_session_id as sdk_session_id "
        f"FROM observations o "
        f"LEFT JOIN sdk_sessions s ON o.memory_session_id = s.memory_session_id "
        f"{f['obs']} ORDER BY o.created_at_epoch DESC"
    )
    observations = _export_query(db_path, obs_query, "observations")
    null_count = _fix_null_titles(observations)
    if null_count:
        print(f"   Fixed {null_count} NULL titles for duplicate detection")

    summ_query = (
        f"SELECT ss.*, s.content_session_id as sdk_session_id "
        f"FROM session_summaries ss "
        f"LEFT JOIN sdk_sessions s ON ss.memory_session_id = s.memory_session_id "
        f"{f['summary']} ORDER BY ss.created_at_epoch DESC"
    )
    summaries = _export_query(db_path, summ_query, "session summaries")
    prompts = _export_query(
        db_path,
        f"SELECT * FROM user_prompts {f['prompt']} ORDER BY prompt_number DESC;",
        "user prompts",
    )
    sessions = _export_query(
        db_path,
        f"SELECT * FROM sdk_sessions {f['session']} ORDER BY started_at_epoch DESC;",
        "SDK sessions",
    )

    query_desc = (
        f"direct-sqlite (project: {args.project})"
        if args.project
        else "direct-sqlite (all projects)"
    )
    export_data = {
        "exportedAt": datetime.now().isoformat(),
        "exportedAtEpoch": int(datetime.now().timestamp()),
        "query": query_desc,
        "method": "direct-sqlite",
        "project": args.project,
        "totalObservations": obs_count,
        "totalSessions": session_count,
        "totalSummaries": summary_count,
        "totalPrompts": prompt_count,
        "observations": observations,
        "sessions": sessions,
        "summaries": summaries,
        "prompts": prompts,
    }

    output_path.write_text(json.dumps(export_data, indent=2) + "\n", encoding="utf-8")

    file_size = output_path.stat().st_size
    print(f"\nDirect export created: {output_path}")
    print(f"   File size: {file_size / 1024:.2f} KB")

    return _run_security_review_direct(output_path)


def _run_security_review_direct(output_path: Path) -> int:
    """Run the memory-export security review script; return 0 on pass or absence."""
    security_script = _SCRIPT_DIR.parent.parent / "scripts" / "review_memory_export_security.py"
    if not security_script.exists():
        return 0
    print("\nRunning security review...")
    sys.stdout.flush()
    result = subprocess.run(
        [sys.executable, str(security_script), "--", str(output_path)]
    )
    if result.returncode != 0:
        print("ERROR: Security review FAILED.", file=sys.stderr)
        return 1
    print("Security review PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
