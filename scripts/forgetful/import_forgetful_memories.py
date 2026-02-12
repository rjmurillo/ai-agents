#!/usr/bin/env python3
"""Import Forgetful database from JSON format.

Idempotent import of JSON memory files into Forgetful SQLite database.
Merges with existing data using upsert semantics (INSERT OR REPLACE).

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
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_EXPORTS_DIR = _SCRIPT_DIR.parent.parent / ".forgetful" / "exports"

IMPORT_ORDER = [
    "users",
    "projects",
    "entities",
    "memories",
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

PRIMARY_KEYS: dict[str, list[str]] = {
    "memory_project_association": ["memory_id", "project_id"],
    "memory_code_artifact_association": ["memory_id", "code_artifact_id"],
    "memory_document_association": ["memory_id", "document_id"],
    "memory_entity_association": ["memory_id", "entity_id"],
    "entity_project_association": ["entity_id", "project_id"],
}


def run_sqlite3(db_path: str, query: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sqlite3", db_path, query],
        capture_output=True,
        text=True,
    )


def get_schema_columns(db_path: str, table: str) -> list[str]:
    result = run_sqlite3(db_path, f"PRAGMA table_info({table});")
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return [line.split("|")[1] for line in result.stdout.strip().splitlines() if "|" in line]


def escape_sql_value(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, dict)):
        return "'" + json.dumps(value, separators=(",", ":")).replace("'", "''") + "'"
    return "'" + str(value).replace("'", "''") + "'"


def import_table(
    db_path: str,
    table: str,
    rows: list[dict],
    schema_columns: list[str],
    merge_mode: str,
) -> tuple[int, int, int]:
    if not rows:
        return 0, 0, 0

    sql_op = {
        "replace": "INSERT OR REPLACE INTO",
        "skip": "INSERT OR IGNORE INTO",
        "fail": "INSERT INTO",
    }[merge_mode]

    pk_columns = PRIMARY_KEYS.get(table, ["id"])

    inserted = 0
    updated = 0
    skipped = 0

    for row in rows:
        columns = [c for c in row if c in schema_columns]
        col_names = ", ".join(columns)
        values = ", ".join(escape_sql_value(row.get(c)) for c in columns)

        # Check existence before insert
        all_keys = all(row.get(k) is not None for k in pk_columns)
        existed = False
        if all_keys and pk_columns:
            where_parts = []
            for k in pk_columns:
                v = row[k]
                where_parts.append(f"{k} = {escape_sql_value(v)}")
            where_clause = " AND ".join(where_parts)
            check = run_sqlite3(db_path, f"SELECT COUNT(*) FROM {table} WHERE {where_clause};")
            existed = check.stdout.strip() == "1"

        sql = f"{sql_op} {table} ({col_names}) VALUES ({values});"
        result = run_sqlite3(db_path, sql)

        if merge_mode == "fail" and result.returncode != 0 and "UNIQUE constraint" in result.stderr:
            raise RuntimeError(f"Duplicate record in {table} (fail mode)")

        if result.returncode != 0 and "UNIQUE constraint" not in result.stderr:
            skipped += 1
        elif merge_mode == "replace":
            if existed:
                updated += 1
            else:
                inserted += 1
        elif merge_mode == "skip":
            if existed:
                skipped += 1
            else:
                inserted += 1
        else:
            inserted += 1

    return inserted, updated, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import Forgetful database from JSON")
    parser.add_argument("--input-files", nargs="*", default=[], help="JSON files to import")
    parser.add_argument(
        "--database-path",
        default=str(Path.home() / ".local" / "share" / "forgetful" / "forgetful.db"),
        help="Path to Forgetful SQLite database",
    )
    parser.add_argument(
        "--merge-mode",
        choices=["replace", "skip", "fail"],
        default="replace",
        help="How to handle existing records",
    )
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args(argv)

    if not shutil.which("sqlite3"):
        print("ERROR: sqlite3 is not installed or not in PATH", file=sys.stderr)
        return 1

    if not Path(args.database_path).exists():
        print(f"ERROR: Forgetful database not found at: {args.database_path}", file=sys.stderr)
        return 1

    input_files = args.input_files
    if not input_files:
        if not _EXPORTS_DIR.exists():
            _EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
            print("No memory files to import")
            return 0
        input_files = [str(f) for f in sorted(_EXPORTS_DIR.glob("*.json"))]
        if not input_files:
            print(f"No memory files to import from: {_EXPORTS_DIR}")
            return 0

    missing = [f for f in input_files if not Path(f).exists()]
    if missing:
        print("ERROR: Input files not found:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 1

    print(f"Importing {len(input_files)} memory file(s)")
    print(f"   Merge mode: {args.merge_mode}")

    total_inserted = 0
    total_updated = 0
    total_skipped = 0
    failed_files: list[tuple[str, str]] = []

    for file_path in input_files:
        file_name = Path(file_path).name
        print(f"  {file_name}")

        try:
            data = json.loads(Path(file_path).read_text(encoding="utf-8"))

            if "export_metadata" not in data:
                print(f"    WARNING: Invalid format: missing export_metadata (skipping)")
                failed_files.append((file_name, "Invalid export format"))
                continue

            if "data" not in data:
                print(f"    WARNING: Invalid format: missing data section (skipping)")
                failed_files.append((file_name, "Invalid export format"))
                continue

            for table in IMPORT_ORDER:
                rows = data["data"].get(table, [])
                if not rows:
                    continue

                schema_cols = get_schema_columns(args.database_path, table)
                if not schema_cols:
                    print(f"    WARNING: Could not get schema for {table} (skipping)")
                    continue

                print(f"     Importing {table} ({len(rows)} rows)...")
                ins, upd, skp = import_table(
                    args.database_path, table, rows, schema_cols, args.merge_mode
                )
                total_inserted += ins
                total_updated += upd
                total_skipped += skp
                print(f"       Inserted: {ins}, Updated: {upd}, Skipped: {skp}")

        except Exception as e:
            failed_files.append((file_name, str(e)))
            print(f"    WARNING: Failed to import {file_name}: {e}")

    print()
    if not failed_files:
        if args.merge_mode == "replace":
            print(
                f"Import complete: {total_inserted} inserted, "
                f"{total_updated} updated, {total_skipped} unchanged"
            )
        else:
            print(f"Import complete: {total_inserted} inserted, {total_skipped} skipped")
    else:
        print(f"Import completed with failures: {total_inserted} succeeded, {len(failed_files)} failed")
        for name, reason in failed_files:
            print(f"  FAIL {name}: {reason}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
