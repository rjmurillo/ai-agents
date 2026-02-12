#!/usr/bin/env python3
"""Export Forgetful database to JSON format.

Exports all data from Forgetful SQLite database to JSON file for backup,
version control, and sharing across team members and installations.

IMPORTANT: Security review is REQUIRED before committing exports to git.
Run: python3 scripts/review_memory_export_security.py --export-file [file].json

EXIT CODES:
  0  - Success
  1  - Error

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_EXPORTS_DIR = _SCRIPT_DIR.parent.parent / ".forgetful" / "exports"

DATA_TABLES = [
    "users",
    "memories",
    "projects",
    "entities",
    "documents",
    "code_artifacts",
    "memory_links",
    "memory_project_association",
    "memory_code_artifact_association",
    "memory_document_association",
    "memory_entity_association",
    "entity_project_association",
    "entity_relationships",
]

TABLE_MAPPING: dict[str, list[str]] = {
    "memories": ["memories", "memory_links"],
    "projects": ["projects", "memory_project_association", "entity_project_association"],
    "entities": ["entities", "memory_entity_association", "entity_relationships"],
    "documents": ["documents", "memory_document_association"],
    "code_artifacts": ["code_artifacts", "memory_code_artifact_association"],
    "associations": [
        "memory_project_association",
        "memory_code_artifact_association",
        "memory_document_association",
        "memory_entity_association",
        "entity_project_association",
    ],
}


def validate_output_path(output_path: Path, exports_dir: Path) -> bool:
    """Prevent path traversal (CWE-22)."""
    resolved_output = output_path.resolve()
    resolved_dir = exports_dir.resolve()
    if not resolved_output.is_relative_to(resolved_dir):
        print(
            f"ERROR: Path traversal attempt detected. "
            f"Output file must be inside '{exports_dir}' directory.",
            file=sys.stderr,
        )
        return False
    return True


def run_sqlite3(db_path: str, query: str) -> str | None:
    result = subprocess.run(
        ["sqlite3", db_path, query],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def get_table_columns(db_path: str, table: str) -> list[str]:
    output = run_sqlite3(db_path, f"PRAGMA table_info({table});")
    if not output:
        return []
    return [line.split("|")[1] for line in output.splitlines() if "|" in line]


def export_table(db_path: str, table: str) -> list[dict[str, Any]]:
    columns = get_table_columns(db_path, table)
    if not columns:
        return []

    col_expr = ", ".join(f"'{c}', {c}" for c in columns)
    query = f"SELECT json_group_array(json_object({col_expr})) FROM {table};"
    output = run_sqlite3(db_path, query)

    if not output:
        return []

    try:
        rows: list[dict[str, Any]] = json.loads(output)
        return rows
    except json.JSONDecodeError:
        return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export Forgetful database to JSON")
    parser.add_argument("--output-file", default="", help="Path to output JSON file")
    parser.add_argument("--session-number", type=int, default=0, help="Session number for filename")
    parser.add_argument("--topic", default="", help="Topic for filename")
    parser.add_argument(
        "--database-path",
        default=str(Path.home() / ".local" / "share" / "forgetful" / "forgetful.db"),
        help="Path to Forgetful SQLite database",
    )
    parser.add_argument("--include-tables", default="all", help="Comma-separated tables to export")
    args = parser.parse_args(argv)

    if not shutil.which("sqlite3"):
        print("ERROR: sqlite3 is not installed or not in PATH", file=sys.stderr)
        return 1

    if not Path(args.database_path).exists():
        print(f"ERROR: Forgetful database not found at: {args.database_path}", file=sys.stderr)
        return 1

    _EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.output_file:
        output_path = Path(args.output_file)
    else:
        parts = [date.today().isoformat()]
        if args.session_number:
            parts.append(f"session-{args.session_number}")
        if args.topic:
            parts.append(args.topic)
        output_path = _EXPORTS_DIR / (("-".join(parts)) + ".json")

    if not validate_output_path(output_path, _EXPORTS_DIR):
        return 1

    tables = list(DATA_TABLES)
    if args.include_tables != "all":
        requested = [t.strip() for t in args.include_tables.split(",")]
        expanded = ["users"]
        for req in requested:
            if req in TABLE_MAPPING:
                expanded.extend(TABLE_MAPPING[req])
            elif req in DATA_TABLES:
                expanded.append(req)
            else:
                print(f"WARNING: Unknown table: {req} (skipping)")
        tables = list(dict.fromkeys(expanded))

    print("Exporting Forgetful database...")
    print(f"   Database: {args.database_path}")
    print(f"   Output: {output_path}")
    print(f"   Tables: {args.include_tables}")

    schema_version = run_sqlite3(
        args.database_path,
        "SELECT version_num FROM alembic_version LIMIT 1;",
    ) or "unknown"

    export_data: dict[str, Any] = {
        "export_metadata": {
            "export_timestamp": __import__("datetime").datetime.now().isoformat(),
            "database_path": args.database_path,
            "forgetful_version": "unknown",
            "schema_version": schema_version,
            "exported_tables": tables,
            "export_tool": "export_forgetful_memories.py",
        },
        "data": {},
    }

    for table in tables:
        print(f"  Exporting {table}...")
        rows = export_table(args.database_path, table)
        export_data["data"][table] = rows
        print(f"     {len(rows)} rows")

    output_path.write_text(json.dumps(export_data, indent=2) + "\n", encoding="utf-8")
    print(f"\nExport complete: {output_path} ({output_path.stat().st_size} bytes)")

    # Run security review if script exists
    security_script = _SCRIPT_DIR.parent / "review_memory_export_security.py"
    if security_script.exists():
        print("\nRunning mandatory security review...")
        result = subprocess.run(
            [sys.executable, str(security_script), "--export-file", str(output_path)]
        )
        if result.returncode != 0:
            print("ERROR: Security review FAILED.", file=sys.stderr)
            return 1
        print("Security review PASSED - Safe to commit")

    return 0


if __name__ == "__main__":
    sys.exit(main())
