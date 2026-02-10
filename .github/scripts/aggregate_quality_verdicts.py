#!/usr/bin/env python3
"""Aggregate quality gate verdicts from six AI review agents.

Input env vars (used as defaults for CLI args, 6 agents x 2 = 12):
    SECURITY_VERDICT, QA_VERDICT, ANALYST_VERDICT,
    ARCHITECT_VERDICT, DEVOPS_VERDICT, ROADMAP_VERDICT
    SECURITY_INFRA, QA_INFRA, ANALYST_INFRA,
    ARCHITECT_INFRA, DEVOPS_INFRA, ROADMAP_INFRA
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

from scripts.ai_review_common import (  # noqa: E402
    FAIL_VERDICTS,
    merge_verdicts,
    write_log,
    write_output,
)

_AGENTS = ("security", "qa", "analyst", "architect", "devops", "roadmap")


def get_category(verdict: str, infra_flag: bool) -> str:
    """Categorize a verdict as INFRASTRUCTURE, CODE_QUALITY, or N/A."""
    if verdict in FAIL_VERDICTS:
        return "INFRASTRUCTURE" if infra_flag else "CODE_QUALITY"
    return "N/A"


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Aggregate quality gate verdicts from six AI review agents.",
    )
    for agent in _AGENTS:
        upper = agent.upper()
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
        verdicts[agent] = getattr(args, f"{agent}_verdict")
        infra_flags[agent] = getattr(args, f"{agent}_infra") == "true"

    if not any(verdicts.values()):
        write_log("ERROR: No agent verdicts found. All verdict env vars are empty.")
        print(
            "::error::No agent verdicts found. Check workflow YAML passes verdict outputs.",
            file=sys.stderr,
        )
        write_output("final_verdict", "CRITICAL_FAIL")
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

    if final in FAIL_VERDICTS and not code_quality_failures:
        write_log("All failures are INFRASTRUCTURE - downgrading to WARN")
        final = "WARN"

    write_output("final_verdict", final)
    for agent in _AGENTS:
        write_output(f"{agent}_verdict", verdicts[agent])
        write_output(f"{agent}_category", categories[agent])
    return 0


if __name__ == "__main__":
    sys.exit(main())
