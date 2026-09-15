#!/usr/bin/env python3
"""Check that the plugin lib trees are in sync.

Runs `build_all.py --check`, which now covers the whole `scripts/` ->
plugin tree -> install tree chain in one command (ADR-109 B5, TASK-035).
Before B5 this ran `scripts/sync_plugin_lib.py --check` first, then
`build_all.py --check`, because the two hops were separate scripts whose
order mattered (issue #3521, issue #2613); B5 folded the first hop into
`build_all.py`'s own lib step, so a single check now covers both hops
atomically and there is no longer a second command to run first.

Replaces the "Check plugin lib mirrors" step in agent-drift-detection.yml.

EXIT CODES (ADR-035):
  0      - build_all.py --check passed
  other  - build_all.py --check's own exit code
"""

from __future__ import annotations

import subprocess
import sys

_BUILD_SCRIPT = "build/scripts/build_all.py"


def run_check(script: str, description: str) -> int:
    """Run a python3 --check script and return its exit code."""
    print(description)
    sys.stdout.flush()
    result = subprocess.run(
        [sys.executable, script, "--check"],
        check=False,
    )
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    print("Checking scripts/ -> lib plugin trees -> .claude/lib/ sync via build_all.py --check")
    return run_check(_BUILD_SCRIPT, "")


if __name__ == "__main__":
    sys.exit(main())
