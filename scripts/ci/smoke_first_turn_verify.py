#!/usr/bin/env python3
"""First-turn verification: assert excluded paths are NOT vendored.

Replaces the PowerShell 'First-turn verification' block in
cli-smoke.yml (ADR-006).

ENV:
  DEMO - absolute path to the demo directory

EXIT CODES (ADR-035):
  0 - none of the excluded paths are present
  1 - one or more excluded paths are present
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def run(argv: list[str] | None = None) -> int:  # noqa: ARG001
    """Assert excluded trees are not in the vendored kit."""
    demo = os.environ.get("DEMO", "")
    if not demo:
        print("::error::DEMO env var is required")
        return 1

    demo_path = Path(demo)
    claude_dir = demo_path / ".claude"

    banned: list[Path] = [
        claude_dir / "hooks",
        claude_dir / "lib",
        claude_dir / "settings.json",
        claude_dir / "skills" / "github",
    ]

    present: list[str] = [str(p) for p in banned if p.exists()]
    if present:
        for p in present:
            print(f"::error::excluded path vendored: {p}")
        return 1

    print("First-turn lint OK (no excluded trees vendored)")
    return 0


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
