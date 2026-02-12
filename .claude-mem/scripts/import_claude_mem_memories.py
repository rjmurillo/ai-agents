#!/usr/bin/env python3
"""Import Claude-Mem memory snapshots from .claude-mem/memories/.

Idempotent import of all JSON memory files from the memories directory.
Automatically prevents duplicates using composite keys.

EXIT CODES:
  0  - Success
  1  - Error

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_MEMORIES_DIR = _SCRIPT_DIR.parent / "memories"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import Claude-Mem memory snapshots"
    )
    parser.parse_args(argv)

    plugin_script = (
        Path.home()
        / ".claude"
        / "plugins"
        / "marketplaces"
        / "thedotmack"
        / "scripts"
        / "import-memories.ts"
    )
    if not plugin_script.exists():
        print(
            f"ERROR: Claude-Mem plugin script not found at: {plugin_script}",
            file=sys.stderr,
        )
        return 1

    if not _MEMORIES_DIR.exists():
        _MEMORIES_DIR.mkdir(parents=True, exist_ok=True)
        print("No memory files to import")
        return 0

    # Only top-level .json files
    files = sorted(_MEMORIES_DIR.glob("*.json"))
    if not files:
        print(f"No memory files to import from: {_MEMORIES_DIR}")
        return 0

    print(f"Importing {len(files)} memory file(s) from .claude-mem/memories/")

    import_count = 0
    failed_files: list[tuple[str, str]] = []

    for file_path in files:
        print(f"  {file_path.name}")
        try:
            result = subprocess.run(
                ["npx", "tsx", str(plugin_script), str(file_path)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                failed_files.append((file_path.name, f"Plugin exited with code {result.returncode}"))
                print(f"    WARNING: Import failed: exit code {result.returncode}")
            else:
                import_count += 1
        except Exception as e:
            failed_files.append((file_path.name, str(e)))
            print(f"    WARNING: Failed to import: {e}")

    print()
    if not failed_files:
        print(f"Import complete: {import_count} file(s) processed successfully")
        print("   Duplicates automatically skipped via composite key matching")
    else:
        print(
            f"Import completed with failures: {import_count} succeeded, "
            f"{len(failed_files)} failed"
        )
        print("\nFailed files:")
        for name, reason in failed_files:
            print(f"  FAIL {name}: {reason}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
