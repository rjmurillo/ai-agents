#!/usr/bin/env python3
"""Aggregate quality gate verdicts from six AI review agents.

Input env vars (6 agents x 2 = 12):
    SECURITY_VERDICT, QA_VERDICT, ANALYST_VERDICT,
    ARCHITECT_VERDICT, DEVOPS_VERDICT, ROADMAP_VERDICT
    SECURITY_INFRA, QA_INFRA, ANALYST_INFRA,
    ARCHITECT_INFRA, DEVOPS_INFRA, ROADMAP_INFRA
    GITHUB_OUTPUT      - Path to GitHub Actions output file
    GITHUB_WORKSPACE   - Workspace root (for package imports)
"""

from __future__ import annotations

import os
import sys

workspace = os.environ.get("GITHUB_WORKSPACE", ".")
sys.path.insert(0, workspace)

from scripts.ai_review_common import merge_verdicts, write_log  # noqa: E402

_FAILURE_VERDICTS = frozenset({"CRITICAL_FAIL", "REJECTED", "FAIL", "NEEDS_REVIEW"})

_AGENTS = ("security", "qa", "analyst", "architect", "devops", "roadmap")


def write_output(key: str, value: str) -> None:
    """Append a key=value line to the GitHub Actions output file."""
    output_file = os.environ.get("GITHUB_OUTPUT", "")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def get_category(verdict: str, infra_flag: bool) -> str:
    """Categorize a verdict as INFRASTRUCTURE, CODE_QUALITY, or N/A."""
    if verdict in _FAILURE_VERDICTS:
        return "INFRASTRUCTURE" if infra_flag else "CODE_QUALITY"
    return "N/A"


def main() -> None:
    verdicts: dict[str, str] = {}
    infra_flags: dict[str, bool] = {}
    for agent in _AGENTS:
        verdicts[agent] = os.environ.get(f"{agent.upper()}_VERDICT", "")
        infra_flags[agent] = os.environ.get(f"{agent.upper()}_INFRA", "") == "true"

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
        sys.exit(1)

    categories: dict[str, str] = {}
    for agent in _AGENTS:
        write_log(f"{agent.capitalize()} verdict: {verdicts[agent]} (infra: {infra_flags[agent]})")
        categories[agent] = get_category(verdicts[agent], infra_flags[agent])
        write_log(f"{agent.capitalize()} category: {categories[agent]}")

    code_quality_failures = any(cat == "CODE_QUALITY" for cat in categories.values())

    final = merge_verdicts([verdicts[agent] for agent in _AGENTS])
    write_log(f"Final verdict: {final}")

    if final in _FAILURE_VERDICTS and not code_quality_failures:
        write_log("All failures are INFRASTRUCTURE - downgrading to WARN")
        final = "WARN"

    write_output("final_verdict", final)
    for agent in _AGENTS:
        write_output(f"{agent}_verdict", verdicts[agent])
        write_output(f"{agent}_category", categories[agent])


if __name__ == "__main__":
    main()
