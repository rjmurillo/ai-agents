#!/usr/bin/env python3
"""Write the agent drift detection job summary to GITHUB_STEP_SUMMARY.

Reads VALIDATE_CONCLUSION, LIB_MIRROR_CONCLUSION, and
MANIFEST_PARITY_CONCLUSION from environment variables and writes a markdown
pass/fail summary with monitored paths.
Replaces the "Write job summary" step in agent-drift-detection.yml (issue #3521).

EXIT CODES (ADR-035):
  0  - Summary written to GITHUB_STEP_SUMMARY, or printed to stdout when unset
  2  - Usage error
"""

from __future__ import annotations

import os
import sys

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

_MONITORED_PATHS_SECTION = """\

### Monitored Paths
- `templates/` - source templates
- `src/vs-code-agents/` - generated VS Code agents
- `src/copilot-cli/` - generated Copilot CLI agents
"""


def build_summary(
    validate_conclusion: str,
    lib_mirror_conclusion: str,
    manifest_parity_conclusion: str,
) -> str:
    """Return the full markdown summary string."""
    all_passed = (
        validate_conclusion == "success"
        and lib_mirror_conclusion == "success"
        and manifest_parity_conclusion == "success"
    )

    if all_passed:
        body = (
            "## Agent Drift Detection Passed\n"
            "\n"
            "All generated agent files match their source templates."
        )
    else:
        body = (
            "## Agent Drift Detection Failed\n"
            "\n"
            "Generated agent files have drifted from their source templates.\n"
            "\n"
            "### Fix\n"
            "1. Edit the source template in `templates/agents/*.shared.md`\n"
            "2. Run: `python3 build/generate_agents.py`\n"
            "3. Commit the regenerated files"
        )

    return body + _MONITORED_PATHS_SECTION


def main(argv: list[str] | None = None) -> int:
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    validate_conclusion = os.environ.get("VALIDATE_CONCLUSION", "")
    lib_mirror_conclusion = os.environ.get("LIB_MIRROR_CONCLUSION", "")
    manifest_parity_conclusion = os.environ.get("MANIFEST_PARITY_CONCLUSION", "")

    text = build_summary(validate_conclusion, lib_mirror_conclusion, manifest_parity_conclusion)

    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(text)
    else:
        print(text)

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
