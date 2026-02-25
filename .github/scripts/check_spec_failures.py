#!/usr/bin/env python3
"""Check spec validation verdicts and fail the workflow if needed.

Input env vars (used as defaults for CLI args):
    TRACE_VERDICT              - Verdict from traceability check
    COMPLETENESS_VERDICT       - Verdict from completeness check
    TRACE_INFRA_FAILURE        - Whether trace failure was infrastructure-related
    COMPLETENESS_INFRA_FAILURE - Whether completeness failure was infrastructure-related
    GITHUB_WORKSPACE           - Workspace root (for package imports)
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


def _is_infra_failure(flag: str) -> bool:
    """Return True if the infrastructure failure flag is set."""
    return flag.lower() in ("true", "1", "yes")


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
    parser.add_argument(
        "--trace-infra-failure",
        default=os.environ.get("TRACE_INFRA_FAILURE", ""),
        help="Whether trace failure was infrastructure-related",
    )
    parser.add_argument(
        "--completeness-infra-failure",
        default=os.environ.get("COMPLETENESS_INFRA_FAILURE", ""),
        help="Whether completeness failure was infrastructure-related",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    trace: str = args.trace_verdict
    completeness: str = args.completeness_verdict

    trace_infra = _is_infra_failure(args.trace_infra_failure)
    completeness_infra = _is_infra_failure(args.completeness_infra_failure)

    if trace_infra and completeness_infra:
        print(
            "::warning::Spec validation skipped due to infrastructure failure"
            " (Copilot CLI unavailable). Not blocking merge."
        )
        return 0

    if trace_infra:
        print(
            "::warning::Traceability check skipped due to infrastructure failure."
        )
        trace = ""

    if completeness_infra:
        print(
            "::warning::Completeness check skipped due to infrastructure failure."
        )
        completeness = ""

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
