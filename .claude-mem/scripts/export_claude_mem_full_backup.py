#!/usr/bin/env python3
"""Export complete claude-mem institutional knowledge backup.

Exports ALL claude-mem data (observations, sessions, summaries, prompts)
across ALL projects (default) or scoped to a single project.

Uses the claude-mem plugin export script via npx tsx.
For guaranteed complete non-FTS backup, prefer export_claude_mem_direct.py.

EXIT CODES:
  0  - Success
  1  - Error

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
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
        description="Export complete claude-mem backup via plugin"
    )
    parser.add_argument("--project", default="", help="Optional project filter")
    parser.add_argument("--output-file", default="", help="Override default filename")
    args = parser.parse_args(argv)

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
        print(
            f"ERROR: Claude-Mem plugin script not found at: {plugin_script}",
            file=sys.stderr,
        )
        return 1

    _MEMORIES_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    default_name = f"backup-{timestamp}"
    if args.project:
        default_name += f"-{args.project}"
    default_name += ".json"

    output_path = Path(args.output_file) if args.output_file else _MEMORIES_DIR / default_name

    if not validate_output_path(output_path, _MEMORIES_DIR):
        return 1

    # Use "." as query to match all observations via search
    plugin_args = ["npx", "tsx", str(plugin_script), ".", str(output_path)]
    if args.project:
        plugin_args.append(f"--project={args.project}")

    print("Exporting full claude-mem backup...")
    print("   Query: . (matches all data)")
    if args.project:
        print(f"   Scope: Project '{args.project}'")
    else:
        print("   Scope: ALL projects")
    print(f"   Output: {output_path}")

    subprocess.run(plugin_args)

    if not output_path.exists():
        print("ERROR: Export failed: Output file not created", file=sys.stderr)
        return 1

    data = json.loads(output_path.read_text(encoding="utf-8"))
    file_size = output_path.stat().st_size

    print(f"\nFull backup created: {output_path}")
    print(f"   File size: {file_size / 1024:.2f} KB")
    print("\nExported:")
    print(f"   Observations: {data.get('totalObservations', 0)}")
    print(f"   Sessions: {data.get('totalSessions', 0)}")
    print(f"   Summaries: {data.get('totalSummaries', 0)}")
    print(f"   Prompts: {data.get('totalPrompts', 0)}")

    total = (
        data.get("totalObservations", 0)
        + data.get("totalSessions", 0)
        + data.get("totalSummaries", 0)
        + data.get("totalPrompts", 0)
    )
    if total == 0:
        print("\nWARNING: Empty Export - No data found in claude-mem database")
        if args.project:
            print("   Try without --project to check other projects")

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
