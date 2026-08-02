#!/usr/bin/env python3
"""Show drift failure details and regenerate files for inspection.

Reads VALIDATE_CONCLUSION, LIB_MIRROR_CONCLUSION, and
MANIFEST_PARITY_CONCLUSION from environment variables. Prints a drift header,
conditionally reruns generation scripts, shows drifted files, and prints a
full git diff. Replaces the "Show diff on failure" step in
agent-drift-detection.yml (issue #3521).

EXIT CODES (ADR-035):
  0  - Completed (drift diagnosis printed; does not fail on drift itself)
  2  - Usage error
"""

from __future__ import annotations

import os
import subprocess
import sys

EXIT_OK = 0
EXIT_USAGE = 2

_GENERATE_SCRIPT = "build/generate_agents.py"
_MIRROR_SCRIPT = "scripts/sync_plugin_lib.py"
_BUILD_SCRIPT = "build/scripts/build_all.py"

_REMEDIATION_GUIDE = """\
--- How to fix ---

  1. Edit the source template (NOT the generated file):
       templates/agents/<agent-name>.shared.md

  2. Regenerate platform-specific files:
       uv run python build/generate_agents.py

  3. Commit the regenerated files:
       git add src/vs-code-agents/ src/copilot-cli/
       git commit -m 'fix(agents): regenerate from updated template'

--- Bypass procedure (intentional divergence) ---

  If this divergence is intentional:
  1. Add [skip-drift-check] to a commit message in this PR
  2. Document the reason in your PR description
  3. Update templates/README.md with the intentional difference
  4. Ensure explicit code-owner approval on this PR
"""


def _run(cmd: list[str]) -> int:
    sys.stdout.flush()
    return subprocess.run(cmd, check=False).returncode


def show_drift_failure(
    validate_conclusion: str,
    lib_mirror_conclusion: str,
    manifest_parity_conclusion: str,
) -> None:
    """Print drift details and remediation guide."""
    print()
    print("===========================================================")
    print("  AGENT DRIFT DETECTED")
    print("===========================================================")
    print()
    print("Generated agent files or plugin mirrors do not match committed files.")
    print("Validation conclusions:")
    print(f"  generate_agents: {validate_conclusion}")
    print(f"  lib mirrors: {lib_mirror_conclusion}")
    print(f"  manifest parity: {manifest_parity_conclusion}")
    print()

    if validate_conclusion == "failure":
        _run([sys.executable, _GENERATE_SCRIPT])

    if lib_mirror_conclusion == "failure":
        _run([sys.executable, _MIRROR_SCRIPT])
        _run([sys.executable, _BUILD_SCRIPT])

    result = subprocess.run(
        ["git", "diff", "--name-only"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    changed_files = result.stdout.strip()

    if changed_files:
        print("--- Files with semantic drift ---")
        for f in changed_files.splitlines():
            print(f"  x  {f}")
        print()
        print(_REMEDIATION_GUIDE)
        print("--- Detailed diff ---")
        print()
        sys.stdout.flush()
        subprocess.run(["git", "diff"], check=False)


def main(argv: list[str] | None = None) -> int:
    validate_conclusion = os.environ.get("VALIDATE_CONCLUSION", "")
    lib_mirror_conclusion = os.environ.get("LIB_MIRROR_CONCLUSION", "")
    manifest_parity_conclusion = os.environ.get("MANIFEST_PARITY_CONCLUSION", "")

    show_drift_failure(validate_conclusion, lib_mirror_conclusion, manifest_parity_conclusion)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
