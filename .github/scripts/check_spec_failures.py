#!/usr/bin/env python3
"""Check spec validation verdicts and fail the workflow if needed.

Exit codes: 0 when both checks ran and none failed. 1 when either check
failed, when either check did not run because of an infrastructure failure
(fail closed, issue #5738), or when either check left no evidence that it
completed: a step outcome other than success, or an empty verdict (fail
closed, issue #5636). The two review steps carry continue-on-error so a crash
cannot skip the report steps; this script is the fail-closed adapter that
reads the outcome the workflow would otherwise discard.

Input env vars (used as defaults for CLI args):
    TRACE_OUTCOME              - steps.<id>.outcome of the traceability step
    COMPLETENESS_OUTCOME       - steps.<id>.outcome of the completeness step
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
# The reviewer is Claude through the Anthropic Messages API, authenticated by
# the ANTHROPIC_API_KEY secret, so an infrastructure failure points at that
# secret first (issue #5738, owner decision D28). The Copilot reviewer was
# retired after "You have exceeded your monthly quota" failed every run.
INFRA_FAILURE_ERROR = (
    "::error::Spec validation could not run due to infrastructure failure, "
    "so this check fails closed. Operator action: check the "
    "ANTHROPIC_API_KEY secret (it is missing, expired, or out of credit), "
    "then re-run this workflow. Also check the Anthropic rate limits and "
    "network connectivity."
)

INCOMPLETE_ERROR = (
    "::error::Spec validation left no evidence that a required check "
    "completed, so this check fails closed. Re-run this workflow and read "
    "the review step log for the crash."
)


def _is_infra_failure(flag: str, _findings: str = "") -> bool:
    """Return True only when the structured infrastructure flag is set."""
    return flag.lower() in ("true", "1", "yes")


def _incomplete_reason(outcome: str, verdict: str) -> str:
    """Return why a check left no evidence of completing, or "" when it did.

    A step that crashes under continue-on-error reports outcome "failure" or
    "cancelled" and leaves its verdict output empty. An empty outcome is
    treated as unknown, not as success, so only the verdict can clear it.
    """
    outcome = outcome.strip().lower()
    if outcome and outcome != "success":
        return f"step outcome was '{outcome}'"
    # Outcome success with no verdict means the review action reported success
    # without parsing a verdict. That is an action defect, and passing on it
    # would be the false green this gate exists to prevent.
    if not verdict.strip():
        return "no verdict was recorded"
    return ""


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
        "--trace-outcome",
        default=os.environ.get("TRACE_OUTCOME", ""),
        help="steps.<id>.outcome of the traceability step",
    )
    parser.add_argument(
        "--completeness-outcome",
        default=os.environ.get("COMPLETENESS_OUTCOME", ""),
        help="steps.<id>.outcome of the completeness step",
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

    trace_gap = "" if trace_infra else _incomplete_reason(args.trace_outcome, trace)
    completeness_gap = (
        "" if completeness_infra
        else _incomplete_reason(args.completeness_outcome, completeness)
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

    if trace_gap:
        print(f"::error::Traceability check did not complete: {trace_gap}.")

    if completeness_gap:
        print(f"::error::Completeness check did not complete: {completeness_gap}.")

    if spec_validation_failed(trace, completeness):
        print(
            "::error::Spec validation failed"
            " - implementation does not fully satisfy requirements"
        )
        return 1

    if trace_infra or completeness_infra:
        print(INFRA_FAILURE_ERROR)
        return 1

    if trace_gap or completeness_gap:
        print(INCOMPLETE_ERROR)
        return 1

    print("Spec validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
