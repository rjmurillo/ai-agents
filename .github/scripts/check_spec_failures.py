#!/usr/bin/env python3
"""Check spec validation verdicts and fail the workflow if needed.

Input env vars (used as defaults for CLI args):
    TRACE_VERDICT          - Verdict from traceability check
    COMPLETENESS_VERDICT   - Verdict from completeness check
    GITHUB_WORKSPACE       - Workspace root (for package imports)
"""

from __future__ import annotations

import argparse
import os
import sys

workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
sys.path.insert(0, workspace)

from scripts.ai_review_common import spec_validation_failed  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Check spec validation verdicts and fail the workflow if needed.",
    )
    parser.add_argument(
        "--trace-verdict",
        default=os.environ.get("TRACE_VERDICT", ""),
        help="Verdict from traceability check",
    )
    parser.add_argument(
        "--completeness-verdict",
        default=os.environ.get("COMPLETENESS_VERDICT", ""),
        help="Verdict from completeness check",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    trace: str = args.trace_verdict
    completeness: str = args.completeness_verdict

    if spec_validation_failed(trace, completeness):
        print(
            "::error::Spec validation failed"
            " - implementation does not fully satisfy requirements"
        )
        return 1

    print("Spec validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
