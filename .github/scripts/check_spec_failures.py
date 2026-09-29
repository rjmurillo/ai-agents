#!/usr/bin/env python3
"""Check spec validation verdicts and fail the workflow if needed.

Exit codes: 0 when both checks ran and none failed. 1 when either check
failed, or when either check did not run because of an infrastructure
failure (fail closed, issue #5738).

Input env vars (used as defaults for CLI args):
    TRACE_VERDICT              - Verdict from traceability check
    COMPLETENESS_VERDICT       - Verdict from completeness check
    TRACE_INFRA_FAILURE        - Whether trace failure was infrastructure-related
    COMPLETENESS_INFRA_FAILURE - Whether completeness failure was infrastructure-related
    TRACE_FINDINGS             - Findings text from traceability check
    COMPLETENESS_FINDINGS      - Findings text from completeness check
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

# Fail closed: a required check that could not run is not a pass. Follows
# .claude/rules/security.md MUST 7: "A required security review that does not
# run MUST produce a blocking verdict. Infrastructure failure is not a
# security pass."
# Copilot CLI authenticates with COPILOT_GITHUB_TOKEN, so an infrastructure
# failure points at that secret first (issue #5738). Recent runs reported
# "You have exceeded your monthly quota", so the account behind the token
# matters as much as the token.
INFRA_FAILURE_ERROR = (
    "::error::Spec validation could not run due to infrastructure failure, "
    "so this check fails closed. Operator action: rotate the "
    "COPILOT_GITHUB_TOKEN secret (it is likely expired or revoked), then "
    "re-run this workflow. Also check the Copilot monthly quota, rate "
    "limits, and network connectivity."
)


def _is_infra_failure(flag: str, _findings: str = "") -> bool:
    """Return True only when the structured infrastructure flag is set."""
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
    parser.add_argument(
        "--trace-findings",
        default=os.environ.get("TRACE_FINDINGS", ""),
        help="Findings text from traceability check",
    )
    parser.add_argument(
        "--completeness-findings",
        default=os.environ.get("COMPLETENESS_FINDINGS", ""),
        help="Findings text from completeness check",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    trace: str = args.trace_verdict
    completeness: str = args.completeness_verdict

    trace_infra = _is_infra_failure(args.trace_infra_failure, args.trace_findings)
    completeness_infra = _is_infra_failure(
        args.completeness_infra_failure, args.completeness_findings
    )

    if trace_infra:
        print(
            "::error::Traceability check did not run due to infrastructure failure."
        )
        trace = ""

    if completeness_infra:
        print(
            "::error::Completeness check did not run due to infrastructure failure."
        )
        completeness = ""

    if spec_validation_failed(trace, completeness):
        print(
            "::error::Spec validation failed"
            " - implementation does not fully satisfy requirements"
        )
        return 1

    if trace_infra or completeness_infra:
        print(INFRA_FAILURE_ERROR)
        return 1

    print("Spec validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
