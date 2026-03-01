#!/usr/bin/env python3
"""E2E tests for workspace file budget.

Target: 6.6KB total for injected files, 3KB per file max.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

MAX_TOTAL = 6758  # 6.6KB
MAX_PER_FILE = 3072  # 3KB

INJECTED_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
]


def get_workspace() -> Path:
    """Return the git repo root or current directory."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


def main() -> int:
    """Check workspace file sizes against budget limits."""
    workspace = get_workspace()
    total = 0
    failed = False

    print("=== Workspace Budget Test ===")
    print()

    for name in INJECTED_FILES:
        filepath = workspace / name
        if filepath.is_file():
            size = filepath.stat().st_size
            total += size

            if size > MAX_PER_FILE:
                print(f"x {name}: {size} bytes (exceeds {MAX_PER_FILE} max)")
                failed = True
            else:
                print(f"v {name}: {size} bytes")

    print()
    print("---")
    print(f"Total: {total} / {MAX_TOTAL} bytes")

    if total > MAX_TOTAL:
        print(f"x FAIL: Total exceeds budget by {total - MAX_TOTAL} bytes")
        return 1
    if failed:
        print("x FAIL: One or more files exceed per-file limit")
        return 1

    budget_kb = total / 1024
    max_kb = MAX_TOTAL / 1024
    print(f"v ALL TESTS PASSED - {budget_kb:.1f}KB / {max_kb:.1f}KB budget")
    return 0


if __name__ == "__main__":
    sys.exit(main())
