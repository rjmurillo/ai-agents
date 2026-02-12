#!/usr/bin/env python3
"""Export Claude-Mem memory snapshots to .claude-mem/memories/.

Exports matching Claude-Mem observations to JSON file for version control
and team sharing.

IMPORTANT: Security review is REQUIRED before committing exports to git.

EXIT CODES:
  0  - Success
  1  - Error

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_MEMORIES_DIR = _SCRIPT_DIR.parent / "memories"


def validate_output_path(output_path: Path, memories_dir: Path) -> bool:
    """Prevent path traversal (CWE-22)."""
    normalized_output = output_path.resolve()
    normalized_dir = memories_dir.resolve()
    normalized_dir_str = str(normalized_dir) + os.sep
    if not str(normalized_output).startswith(normalized_dir_str):
        print(
            f"ERROR: Path traversal attempt detected. "
            f"Output file must be inside '{memories_dir}' directory.",
            file=sys.stderr,
        )
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export Claude-Mem memory snapshots"
    )
    parser.add_argument("query", help="Search query to filter memories")
    parser.add_argument("--output-file", default="", help="Path to output JSON file")
    parser.add_argument("--session-number", type=int, default=0, help="Session number for filename")
    parser.add_argument("--topic", default="", help="Topic for filename")
    args = parser.parse_args(argv)

    # Validate query
    if not re.match(r"^[a-zA-Z0-9\s\-_.,()]*$", args.query):
        print("ERROR: Invalid query format. Use alphanumeric characters only.", file=sys.stderr)
        return 1

    plugin_script = (
        Path.home()
        / ".claude"
        / "plugins"
        / "marketplaces"
        / "thedotmack"
        / "scripts"
        / "export-memories.ts"
    )
    if not plugin_script.exists():
        print(f"ERROR: Claude-Mem plugin script not found at: {plugin_script}", file=sys.stderr)
        return 1

    _MEMORIES_DIR.mkdir(parents=True, exist_ok=True)

    if args.output_file:
        output_path = Path(args.output_file)
    else:
        parts = [date.today().isoformat()]
        if args.session_number:
            parts.append(f"session-{args.session_number}")
        if args.topic:
            parts.append(args.topic)
        output_path = _MEMORIES_DIR / (("-".join(parts)) + ".json")

    if not validate_output_path(output_path, _MEMORIES_DIR):
        return 1

    print("Exporting Claude-Mem observations...")
    print(f"   Query: '{args.query}'")
    print(f"   Output: {output_path}")

    try:
        result = subprocess.run(
            ["npx", "tsx", str(plugin_script), args.query, str(output_path)],
            capture_output=False,
        )
        if result.returncode != 0:
            print(
                f"ERROR: Export plugin failed with exit code: "
                f"{result.returncode}",
                file=sys.stderr,
            )
            return result.returncode

        if not output_path.exists():
            print("ERROR: Export file not created despite successful exit code.", file=sys.stderr)
            return 1

        file_info = output_path.stat()
        file_age = (datetime.now().timestamp() - file_info.st_mtime)

        if file_age > 60:
            print("ERROR: Export file exists but is stale", file=sys.stderr)
            return 1

        if file_info.st_size == 0:
            print("ERROR: Export file created but is empty", file=sys.stderr)
            return 1

        print(f"\nExport complete: {output_path} ({file_info.st_size} bytes)")

        # Security review
        security_script = _SCRIPT_DIR.parent.parent / "scripts" / "review_memory_export_security.py"
        if security_script.exists():
            print("\nRunning mandatory security review...")
            sec_result = subprocess.run(
                [sys.executable, str(security_script), "--export-file", str(output_path)]
            )
            if sec_result.returncode != 0:
                print("ERROR: Security review FAILED.", file=sys.stderr)
                return 1
            print("Security review PASSED - Safe to commit")
        else:
            print("WARNING: Security review script not found")
            print("   Manually review for sensitive data before committing")

    except Exception as e:
        print(f"ERROR: Export failed: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
