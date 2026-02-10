#!/usr/bin/env python3
"""Check spec validation verdicts and fail the workflow if needed.

Input env vars:
    TRACE_VERDICT          - Verdict from traceability check
    COMPLETENESS_VERDICT   - Verdict from completeness check
    GITHUB_WORKSPACE       - Workspace root (for package imports)
"""

from __future__ import annotations

import os
import sys

workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
sys.path.insert(0, workspace)

from scripts.ai_review_common import spec_validation_failed  # noqa: E402


def main() -> None:
    trace = os.environ.get("TRACE_VERDICT", "")
    completeness = os.environ.get("COMPLETENESS_VERDICT", "")

    if spec_validation_failed(trace, completeness):
        print(
            "::error::Spec validation failed"
            " - implementation does not fully satisfy requirements"
        )
        sys.exit(1)

    print("Spec validation passed")


if __name__ == "__main__":
    main()
