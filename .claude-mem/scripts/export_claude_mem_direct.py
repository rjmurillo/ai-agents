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
    """
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        preview = raw[:200] if raw else "(empty)"
        print(
            f"WARNING: Failed to parse {label} JSON: {exc}\n"
            f"   Raw output preview: {preview}",
            file=sys.stderr,
        )
        return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export claude-mem data directly from SQLite"
    )
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
    default_name = f"direct-backup-{timestamp}"
    if args.project:
        default_name += f"-{args.project}"
    default_name += ".json"

    output_path = Path(args.output_file) if args.output_file else _MEMORIES_DIR / default_name

    if not validate_output_path(output_path, _MEMORIES_DIR):
        return 1

    # SQL injection prevention (CWE-89)
    safe_project = args.project.replace("'", "''") if args.project else ""
    obs_filter = f"WHERE o.project = '{safe_project}'" if args.project else ""
    summary_filter = f"WHERE ss.project = '{safe_project}'" if args.project else ""
    session_filter = f"WHERE project = '{safe_project}'" if args.project else ""
    prompt_filter = (
        f"WHERE content_session_id IN "
        f"(SELECT content_session_id FROM sdk_sessions WHERE project = '{safe_project}')"
        if args.project
        else ""
    )
    count_filter = f"WHERE project = '{safe_project}'" if args.project else ""

    print("Exporting from SQLite database...")
    if args.project:
        print(f"   Scope: Project '{args.project}'")
    else:
        print("   Scope: ALL projects")
    print(f"   Database: {db_path}")
    print(f"   Output: {output_path}")

    obs_count = get_count(db_path, f"SELECT COUNT(*) FROM observations {count_filter};")
    summary_count = get_count(db_path, f"SELECT COUNT(*) FROM session_summaries {count_filter};")
    prompt_count = get_count(db_path, f"SELECT COUNT(*) FROM user_prompts {prompt_filter};")
    session_count = get_count(db_path, f"SELECT COUNT(*) FROM sdk_sessions {session_filter};")

    print("\nDatabase contains:")
    print(f"   Observations: {obs_count}")
    print(f"   Session summaries: {summary_count}")
    print(f"   User prompts: {prompt_count}")
    print(f"   SDK sessions: {session_count}")

    # Export observations
    obs_query = (
        f"SELECT o.*, s.content_session_id as sdk_session_id "
        f"FROM observations o "
        f"LEFT JOIN sdk_sessions s ON o.memory_session_id = s.memory_session_id "
        f"{obs_filter} ORDER BY o.created_at_epoch DESC"
    )
    obs_result = run_sqlite3(db_path, obs_query, json_mode=True)
    has_obs = (
        obs_result.returncode == 0 and obs_result.stdout.strip()
    )
    observations = _parse_json_output(obs_result.stdout, "observations") if has_obs else []

    # Fix NULL titles
    null_count = 0
    for obs in observations:
        if not obs.get("title") or not str(obs["title"]).strip():
            obs["title"] = "(untitled)"
            null_count += 1
    if null_count:
        print(f"   Fixed {null_count} NULL titles for duplicate detection")

    # Export session summaries
    summ_query = (
        f"SELECT ss.*, s.content_session_id as sdk_session_id "
        f"FROM session_summaries ss "
        f"LEFT JOIN sdk_sessions s ON ss.memory_session_id = s.memory_session_id "
        f"{summary_filter} ORDER BY ss.created_at_epoch DESC"
    )
    summ_result = run_sqlite3(db_path, summ_query, json_mode=True)
    has_summ = (
        summ_result.returncode == 0 and summ_result.stdout.strip()
    )
    summaries = _parse_json_output(summ_result.stdout, "session summaries") if has_summ else []

    # Export user prompts
    prompt_result = run_sqlite3(
        db_path,
        f"SELECT * FROM user_prompts {prompt_filter} ORDER BY prompt_number DESC;",
        json_mode=True,
    )
    has_prompts = (
        prompt_result.returncode == 0
        and prompt_result.stdout.strip()
    )
    prompts = _parse_json_output(prompt_result.stdout, "user prompts") if has_prompts else []

    # Export SDK sessions
    sess_result = run_sqlite3(
        db_path,
        f"SELECT * FROM sdk_sessions {session_filter} ORDER BY started_at_epoch DESC;",
        json_mode=True,
    )
    has_sess = (
        sess_result.returncode == 0 and sess_result.stdout.strip()
    )
    sessions = _parse_json_output(sess_result.stdout, "SDK sessions") if has_sess else []

    if args.project:
        query_desc = f"direct-sqlite (project: {args.project})"
    else:
        query_desc = "direct-sqlite (all projects)"
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

    output_path.write_text(
        json.dumps(export_data, indent=2) + "\n", encoding="utf-8"
    )

    file_size = output_path.stat().st_size
    print(f"\nDirect export created: {output_path}")
    print(f"   File size: {file_size / 1024:.2f} KB")

    # Security review
    security_script = _SCRIPT_DIR.parent.parent / "scripts" / "review_memory_export_security.py"
    if security_script.exists():
        print("\nRunning security review...")
        result = subprocess.run(
            [sys.executable, str(security_script), "--export-file", str(output_path)]
        )
        if result.returncode != 0:
            print("ERROR: Security review FAILED.", file=sys.stderr)
            return 1
        print("Security review PASSED")

    return 0


if __name__ == "__main__":
    sys.exit(main())
