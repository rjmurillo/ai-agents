#!/usr/bin/env python3
"""Aggregate quality gate verdicts from ten AI review agents.

Input env vars (used as defaults for CLI args, 10 agents x 2 = 20):
    SECURITY_VERDICT, QA_VERDICT, ANALYST_VERDICT,
    ARCHITECT_VERDICT, DEVOPS_VERDICT, ROADMAP_VERDICT,
    RELIABILITY_VERDICT, OBSERVABILITY_VERDICT, AGENT_SAFETY_VERDICT,
    DECISION_RIGOR_VERDICT
    SECURITY_INFRA, QA_INFRA, ANALYST_INFRA,
    ARCHITECT_INFRA, DEVOPS_INFRA, ROADMAP_INFRA,
    RELIABILITY_INFRA, OBSERVABILITY_INFRA, AGENT_SAFETY_INFRA,
    DECISION_RIGOR_INFRA
    GITHUB_OUTPUT      - Path to GitHub Actions output file
    GITHUB_WORKSPACE   - Workspace root (for package imports)
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
script_dir = os.path.dirname(__file__)
sys.path.insert(0, script_dir)

from quality_gate_agents import (  # noqa: E402
    QUALITY_GATE_AGENTS,
    agent_arg_name,
    agent_env_name,
)

from scripts.ai_review_common import (  # noqa: E402
    FAIL_VERDICTS,
    merge_verdicts,
    write_log,
    write_output,
)

_AGENTS = QUALITY_GATE_AGENTS
ATTENTION_VERDICTS = FAIL_VERDICTS | {"UNKNOWN", "DID_NOT_RUN"}
DOWNGRADEABLE_INFRA_VERDICTS = FAIL_VERDICTS | {"DID_NOT_RUN"}


def get_category(verdict: str, infra_flag: bool) -> str:
    """Categorize a verdict as INFRASTRUCTURE, CODE_QUALITY, or N/A."""
    if verdict in ATTENTION_VERDICTS:
        return "INFRASTRUCTURE" if infra_flag else "CODE_QUALITY"
    return "N/A"


def is_blocking_unknown_verdict(verdict: str) -> bool:
    """Return True when a raw verdict normalizes to blocking UNKNOWN."""
    return merge_verdicts([verdict]) == "UNKNOWN" and verdict != "DID_NOT_RUN"


def has_infra_masked_unknown_verdict(
    verdicts: dict[str, str],
    infra_flags: dict[str, bool],
) -> bool:
    """Return True when an infra-flagged agent's verdict is blocking-unknown
    but is not one of the recognized infra-failure tokens.

    merge_verdicts() ranks a real WARN above UNKNOWN: WARN/PARTIAL is checked
    before the DID_NOT_RUN/UNKNOWN/unrecognized-token branch (see
    scripts/ai_review_common/verdict.py merge_verdicts priority list, steps 2
    and 3). That means a genuine WARN from one agent can silently mask a raw
    or unrecognized token (e.g. FOOBAR) or a literal UNKNOWN from a
    *different*, infra-flagged agent: the merged result reads as a normal,
    non-blocking WARN even though an infra-flagged axis never produced a
    trustworthy verdict.

    should_downgrade_infra_only_failures() already refuses to downgrade in
    this situation (it returns False whenever an infra-flagged agent's
    verdict is outside DOWNGRADEABLE_INFRA_VERDICTS and is blocking-unknown),
    but refusing to downgrade only stops WARN from being *introduced* by the
    downgrade step; it does nothing when merge_verdicts() already produced
    WARN on its own from a real WARN elsewhere. This helper names that exact
    condition so the caller can force the aggregate back to UNKNOWN instead
    of leaving the masked WARN in place.

    Deliberately excludes DID_NOT_RUN and any token in FAIL_VERDICTS: those
    are the expected, recognized infra-failure vocabulary
    (DOWNGRADEABLE_INFRA_VERDICTS) and are handled by the existing downgrade
    path, not by this guard.

    Does not need the private _KNOWN_VERDICT_TOKENS set from
    scripts.ai_review_common.verdict: is_blocking_unknown_verdict() already
    treats a literal "UNKNOWN" token and an unrecognized raw token
    identically (both normalize to "UNKNOWN" via merge_verdicts), which is
    exactly the behavior this guard needs.
    """
    return any(
        infra_flags[agent]
        and verdicts[agent] not in DOWNGRADEABLE_INFRA_VERDICTS
        and is_blocking_unknown_verdict(verdicts[agent])
        for agent in _AGENTS
    )


def should_downgrade_infra_only_failures(
    verdicts: dict[str, str],
    infra_flags: dict[str, bool],
) -> bool:
    """Return True when every failing verdict is an explicit infra-only failure."""
    saw_downgradeable_failure = False
    for agent in _AGENTS:
        verdict = verdicts[agent]
        if verdict in DOWNGRADEABLE_INFRA_VERDICTS:
            if not infra_flags[agent]:
                return False
            saw_downgradeable_failure = True
            continue
        if is_blocking_unknown_verdict(verdict):
            return False
    return saw_downgradeable_failure


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Aggregate quality gate verdicts from ten AI review agents.",
    )
    for agent in _AGENTS:
        upper = agent_env_name(agent)
        parser.add_argument(
            f"--{agent}-verdict",
            default=os.environ.get(f"{upper}_VERDICT", ""),
            help=f"{agent.capitalize()} agent verdict",
        )
        parser.add_argument(
            f"--{agent}-infra",
            default=os.environ.get(f"{upper}_INFRA", ""),
            help=f"{agent.capitalize()} infrastructure flag (true/false)",
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    verdicts: dict[str, str] = {}
    infra_flags: dict[str, bool] = {}
    for agent in _AGENTS:
        verdicts[agent] = getattr(args, f"{agent_arg_name(agent)}_verdict")
        infra_flags[agent] = getattr(args, f"{agent_arg_name(agent)}_infra") == "true"

    if not any(verdicts.values()):
        write_log("ERROR: No agent verdicts found. All verdict env vars are empty.")
        print(
            "::error::No agent verdicts found. Check workflow YAML passes verdict outputs.",
            file=sys.stderr,
        )
        write_output("final_verdict", "CRITICAL_FAIL")
        write_output("security_review_ran", "false")
        for agent in _AGENTS:
            write_output(f"{agent}_verdict", "")
            write_output(f"{agent}_category", "N/A")
        return 1

    categories: dict[str, str] = {}
    for agent in _AGENTS:
        write_log(f"{agent.capitalize()} verdict: {verdicts[agent]} (infra: {infra_flags[agent]})")
        categories[agent] = get_category(verdicts[agent], infra_flags[agent])
        write_log(f"{agent.capitalize()} category: {categories[agent]}")

    code_quality_failures = any(cat == "CODE_QUALITY" for cat in categories.values())

    final = merge_verdicts([verdicts[agent] for agent in _AGENTS])
    write_log(f"Final verdict: {final}")

    if not code_quality_failures and should_downgrade_infra_only_failures(verdicts, infra_flags):
        write_log("All failures are explicit infra verdicts - downgrading to WARN")
        final = "WARN"
    elif final == "WARN" and has_infra_masked_unknown_verdict(verdicts, infra_flags):
        # A real WARN from one agent outranks UNKNOWN in merge_verdicts()'s
        # own precedence, which can mask an infra-flagged agent's raw or
        # unrecognized token (or a literal UNKNOWN) that should have kept the
        # gate blocking. should_downgrade_infra_only_failures() already
        # refused to downgrade for this reason; restore the blocking verdict
        # instead of leaving the masked WARN in place.
        write_log(
            "Infra-flagged blocking-unknown verdict masked by WARN - "
            "restoring UNKNOWN"
        )
        final = "UNKNOWN"

    # Issue #2821 option c: the WARN downgrade is owner policy, but a security
    # review that never ran must not be indistinguishable from one that
    # passed. Surface a distinct annotation and a dedicated output so the PR
    # comment and downstream tooling can render a non-ignorable notice.
    security_review_ran = categories.get("security") != "INFRASTRUCTURE"
    if not security_review_ran:
        write_log("Security review did not run (infrastructure failure)")
        print(
            "::warning title=Security review did not run::The AI security "
            "review hit an infrastructure failure and did not evaluate this "
            "PR. The gate verdict does not certify a security review; re-run "
            "the gate or review security manually before merge (issue #2821)."
        )
    write_output("security_review_ran", "true" if security_review_ran else "false")

    write_output("final_verdict", final)
    for agent in _AGENTS:
        write_output(f"{agent}_verdict", verdicts[agent])
        write_output(f"{agent}_category", categories[agent])
    return 0


if __name__ == "__main__":
    sys.exit(main())
