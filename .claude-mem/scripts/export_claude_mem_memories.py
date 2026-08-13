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
import re
import subprocess
import sys
from datetime import date, datetime
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


def _build_output_path(args: argparse.Namespace) -> Path:
    """Build the output file path from args, using today's date and optional parts."""
    if args.output_file:
        return Path(args.output_file)
    parts = [date.today().isoformat()]
    if args.session_number:
        parts.append(f"session-{args.session_number}")
    if args.topic:
        parts.append(args.topic)
    return _MEMORIES_DIR / (("-".join(parts)) + ".json")


def _validate_export_output(output_path: Path) -> int:
    """Return non-zero if the export file is missing, stale, or empty."""
    if not output_path.exists():
        print("ERROR: Export file not created despite successful exit code.", file=sys.stderr)
        return 1
    file_info = output_path.stat()
    if (datetime.now().timestamp() - file_info.st_mtime) > 60:
        print("ERROR: Export file exists but is stale", file=sys.stderr)
        return 1
    if file_info.st_size == 0:
        print("ERROR: Export file created but is empty", file=sys.stderr)
        return 1
    print(f"\nExport complete: {output_path} ({file_info.st_size} bytes)")
    return 0


def _run_security_review_memories(output_path: Path) -> int:
    """Run the memory-export security review script; return 0 on pass or absence."""
    security_script = _SCRIPT_DIR.parent.parent / "scripts" / "review_memory_export_security.py"
    if not security_script.exists():
        print("WARNING: Security review script not found")
        print("   Manually review for sensitive data before committing")
        return 0
    print("\nRunning mandatory security review...")
    sys.stdout.flush()
    sec_result = subprocess.run(
        [sys.executable, str(security_script), "--", str(output_path)]
    )
    if sec_result.returncode != 0:
        print("ERROR: Security review FAILED.", file=sys.stderr)
        return 1
    print("Security review PASSED - Safe to commit")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export Claude-Mem memory snapshots")
    parser.add_argument("query", help="Search query to filter memories")
    parser.add_argument("--output-file", default="", help="Path to output JSON file")
    parser.add_argument("--session-number", type=int, default=0, help="Session number for filename")
    parser.add_argument("--topic", default="", help="Topic for filename")
    args = parser.parse_args(argv)

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
    output_path = _build_output_path(args)

    if not validate_output_path(output_path, _MEMORIES_DIR):
        return 1

    print("Exporting Claude-Mem observations...")
    print(f"   Query: '{args.query}'")
    print(f"   Output: {output_path}")

    try:
        sys.stdout.flush()
        result = subprocess.run(
            ["npx", "tsx", str(plugin_script), args.query, str(output_path)],
            capture_output=False,
        )
        if result.returncode != 0:
            print(
                f"ERROR: Export plugin failed with exit code: {result.returncode}",
                file=sys.stderr,
            )
            return result.returncode

        rc = _validate_export_output(output_path)
        if rc != 0:
            return rc

        return _run_security_review_memories(output_path)

    except Exception as e:
        print(f"ERROR: Export failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
