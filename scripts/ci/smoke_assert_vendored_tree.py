#!/usr/bin/env python3
"""Assert the vendored tree contains the expected paths.

Replaces the PowerShell 'Assert vendored tree' block in cli-smoke.yml (ADR-006).

ENV:
  DEMO - absolute path to the demo directory

EXIT CODES (ADR-035):
  0 - all expected paths present
  1 - one or more paths missing
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def run(argv: list[str] | None = None) -> int:  # noqa: ARG001
    """Assert expected paths exist in the vendored tree."""
    demo = os.environ.get("DEMO", "")
    if not demo:
        print("::error::DEMO env var is required")
        return 1

    demo_path = Path(demo)
    claude_dir = demo_path / ".claude"

    # (path, is_dir) tuples; is_dir=True checks for directory, False for file.
    expected: list[tuple[Path, bool]] = [
        (claude_dir / "agents", True),
        (claude_dir / "commands", True),
        (claude_dir / "skills", True),
        (demo_path / "CLAUDE.md", False),
        (demo_path / "AGENTS.md", False),
        (claude_dir / ".ai-agents-version.json", False),
    ]

    missing: list[str] = []
    for path, is_dir in expected:
        kind = "container" if is_dir else "leaf"
        if is_dir and not path.is_dir():
            print(f"::error::missing {kind} {path}")
            missing.append(str(path))
        elif not is_dir and not path.is_file():
            print(f"::error::missing {kind} {path}")
            missing.append(str(path))

    if missing:
        return 1

    print(f"Vendored tree OK ({len(expected)} paths present)")
    return 0


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
