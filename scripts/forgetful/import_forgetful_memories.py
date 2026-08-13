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
from dataclasses import dataclass
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


@dataclass
class ImportStats:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0

    def add(self, inserted: int, updated: int, skipped: int) -> None:
        self.inserted += inserted
        self.updated += updated
        self.skipped += skipped


def run_sqlite3(db_path: str, query: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sqlite3", db_path, query],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
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


def normalize_table_rows(table: str, value: object) -> list[dict[str, object]]:
    """Validate and normalize table rows.

    Producer contract from `scripts/forgetful/export_forgetful_memories.py`:
        def export_table(db_path: str, table: str) -> list[dict[str, Any]]:

    Different than canonical: the importer accepts ``None`` as an empty table
    and one object as one row for committed legacy exports. Other shapes fail
    before that table's database writes.
    """
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if not isinstance(value, list):
        raise RuntimeError(
            f"Table '{table}' must be an array of objects or one object; got {type(value).__name__}"
        )

    rows: list[dict[str, object]] = []
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            raise RuntimeError(
                f"Table '{table}' row {index} must be an object; got {type(row).__name__}"
            )
        rows.append(row)
    return rows


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
            raise RuntimeError(f"Insert failed for {table} row: {(result.stderr or '').strip()}")
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


def parse_args(argv: list[str] | None) -> argparse.Namespace:
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
    return parser.parse_args(argv)


def validate_environment(database_path: str) -> bool:
    if shutil.which("sqlite3") and Path(database_path).exists():
        return True
    if not shutil.which("sqlite3"):
        print("ERROR: sqlite3 is not installed or not in PATH", file=sys.stderr)
        return False
    print(f"ERROR: Forgetful database not found at: {database_path}", file=sys.stderr)
    return False


def resolve_input_files(input_files: list[str]) -> tuple[list[str], int | None]:
    if not input_files:
        if not _EXPORTS_DIR.exists():
            _EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
            print("No memory files to import")
            return [], 0
        input_files = [str(f) for f in sorted(_EXPORTS_DIR.glob("*.json"))]
        if not input_files:
            print(f"No memory files to import from: {_EXPORTS_DIR}")
            return [], 0

    missing = [f for f in input_files if not Path(f).exists()]
    if not missing:
        return input_files, None
    print("ERROR: Input files not found:", file=sys.stderr)
    for missing_file in missing:
        print(f"  - {missing_file}", file=sys.stderr)
    return [], 1


def import_tables(
    table_data: dict[str, object],
    database_path: str,
    merge_mode: str,
    totals: ImportStats,
) -> None:
    for table in IMPORT_ORDER:
        rows = normalize_table_rows(table, table_data.get(table, []))
        if not rows:
            continue

        schema_cols = get_schema_columns(database_path, table)
        if not schema_cols:
            print(f"    WARNING: Could not get schema for {table} (skipping)")
            continue

        print(f"     Importing {table} ({len(rows)} rows)...")
        inserted, updated, skipped = import_table(
            database_path,
            table,
            rows,
            schema_cols,
            merge_mode,
        )
        totals.add(inserted, updated, skipped)
        print(f"       Inserted: {inserted}, Updated: {updated}, Skipped: {skipped}")


def import_file(
    file_path: str,
    database_path: str,
    merge_mode: str,
    totals: ImportStats,
) -> str | None:
    file_name = Path(file_path).name
    try:
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError(f"Export root must be an object; got {type(data).__name__}")
        if "export_metadata" not in data:
            print("    WARNING: Invalid format: missing export_metadata (skipping)")
            return "Invalid export format"
        if "data" not in data:
            print("    WARNING: Invalid format: missing data section (skipping)")
            return "Invalid export format"

        table_data = data["data"]
        if not isinstance(table_data, dict):
            raise RuntimeError(
                f"Data section must be an object of tables; got {type(table_data).__name__}"
            )
        import_tables(table_data, database_path, merge_mode, totals)
        return None
    except json.JSONDecodeError as error:
        print(f"    WARNING: Failed to parse {file_name}: {error}")
        return f"Invalid JSON: {error}"
    except KeyError as error:
        print(f"    WARNING: Missing expected key {error} in {file_name}")
        return f"Missing key: {error}"
    except RuntimeError as error:
        print(f"    WARNING: Import failed for {file_name}: {error}")
        return str(error)
    except subprocess.TimeoutExpired as error:
        print(f"    WARNING: Timeout importing {file_name}: {error.timeout}s")
        return f"Timeout: {error.timeout}s"


def report_results(
    totals: ImportStats,
    merge_mode: str,
    failed_files: list[tuple[str, str]],
) -> int:
    print()
    if failed_files:
        print(
            f"Import completed with failures: {totals.inserted} succeeded, "
            f"{len(failed_files)} failed"
        )
        for name, reason in failed_files:
            print(f"  FAIL {name}: {reason}")
        return 1

    if merge_mode == "replace":
        print(
            f"Import complete: {totals.inserted} inserted, "
            f"{totals.updated} updated, {totals.skipped} unchanged"
        )
        return 0
    print(f"Import complete: {totals.inserted} inserted, {totals.skipped} skipped")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not validate_environment(args.database_path):
        return 1

    input_files, early_exit = resolve_input_files(args.input_files)
    if early_exit is not None:
        return early_exit

    print(f"Importing {len(input_files)} memory file(s)")
    print(f"   Merge mode: {args.merge_mode}")
    totals = ImportStats()
    failed_files: list[tuple[str, str]] = []
    for file_path in input_files:
        file_name = Path(file_path).name
        print(f"  {file_name}")
        failure = import_file(file_path, args.database_path, args.merge_mode, totals)
        if failure:
            failed_files.append((file_name, failure))

    return report_results(totals, args.merge_mode, failed_files)


if __name__ == "__main__":
    sys.exit(main())
