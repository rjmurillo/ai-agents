#!/usr/bin/env python3
"""Check that plugin lib mirrors are in sync.

Runs sync_plugin_lib.py --check and build_all.py --check.
If the first script fails, exits with its code; otherwise exits with the
second script's code. Replaces the "Check plugin lib mirrors" step in
agent-drift-detection.yml (issue #3521).

EXIT CODES (ADR-035):
  0      - Both checks passed
  other  - First non-zero exit code from the two checks
"""

from __future__ import annotations

import subprocess
import sys

_MIRROR_SCRIPT = "scripts/sync_plugin_lib.py"
_BUILD_SCRIPT = "build/scripts/build_all.py"


def run_check(script: str, description: str) -> int:
    """Run a python3 --check script and return its exit code."""
    print(description)
    result = subprocess.run(
        [sys.executable, script, "--check"],
        check=False,
    )
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    print("Checking scripts/ -> .claude/lib/ sync via sync_plugin_lib.py --check")
    mirror_rc = run_check(_MIRROR_SCRIPT, "")

    print()
    print("Checking .claude/lib/ -> src/copilot-cli/lib/ sync via build_all.py --check")
    build_rc = run_check(_BUILD_SCRIPT, "")

    if mirror_rc != 0:
        return mirror_rc
    return build_rc


if __name__ == "__main__":
    sys.exit(main())
