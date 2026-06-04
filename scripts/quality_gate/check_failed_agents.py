#!/usr/bin/env python3
"""Surface agent review jobs that failed, before downloading artifacts.

Extracted from the inline ``Check for failed agents`` step in
``.github/workflows/ai-pr-quality-gate.yml`` (ADR-006: no logic in YAML).

The step reads each agent job's ``needs.<agent>-review.result`` from the
environment, prints every result, emits a GitHub ``::error::`` annotation for
any agent whose result is ``failure`` or ``cancelled``, and writes
``has_failures=true|false`` to ``GITHUB_OUTPUT``.

The agent roster and display names are sourced from
``quality_gate_agents.QUALITY_GATE_AGENT_DISPLAY_NAMES`` so the workflow has a
single source of truth for the ten quality-gate agents. The original block
hardcoded the same ten display names in the same order
('Security', 'QA', 'Analyst', 'Architect', 'DevOps', 'Roadmap', 'Reliability',
'Observability', 'Agent Safety', 'Decision Rigor').

Input env vars (one per agent):
    SECURITY_RESULT, QA_RESULT, ANALYST_RESULT, ARCHITECT_RESULT,
    DEVOPS_RESULT, ROADMAP_RESULT, RELIABILITY_RESULT, OBSERVABILITY_RESULT,
    AGENT_SAFETY_RESULT, DECISION_RIGOR_RESULT
    GITHUB_OUTPUT - path to the GitHub Actions output file.

Exit codes (ADR-035):
    0 - results inspected and has_failures written (failures do NOT fail this
        step; the original block also exited 0 on failures)
    2 - GITHUB_OUTPUT is not set (config error)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_GITHUB_SCRIPTS = _SCRIPT_DIR.parents[1] / ".github" / "scripts"
sys.path.insert(0, str(_GITHUB_SCRIPTS))

from quality_gate_agents import (  # noqa: E402
    QUALITY_GATE_AGENT_DISPLAY_NAMES,
    QUALITY_GATE_AGENTS,
    agent_env_name,
)

_FAILED_RESULTS = frozenset({"failure", "cancelled"})


def collect_results(env: dict[str, str]) -> list[tuple[str, str]]:
    """Return ``(display_name, result)`` pairs in the canonical agent order."""

    pairs: list[tuple[str, str]] = []
    for agent in QUALITY_GATE_AGENTS:
        display = QUALITY_GATE_AGENT_DISPLAY_NAMES[agent]
        result = env.get(f"{agent_env_name(agent)}_RESULT", "")
        pairs.append((display, result))
    return pairs


def find_failures(results: list[tuple[str, str]]) -> list[str]:
    """Return display names whose result is ``failure`` or ``cancelled``."""

    return [name for name, result in results if result in _FAILED_RESULTS]


def write_has_failures(output_path: Path, has_failures: bool) -> None:
    """Append ``has_failures=true|false`` to the GitHub output file."""

    value = "true" if has_failures else "false"
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(f"has_failures={value}\n")


def report(results: list[tuple[str, str]], failed: list[str]) -> None:
    """Print results and GitHub annotations, mirroring the original block."""

    print("Individual review results:")
    for name, result in results:
        print(f"  {name}: {result}")
    for name, result in results:
        if result in _FAILED_RESULTS:
            print(f"::error::{name} agent failed with result: {result}")
    if failed:
        print(f"::warning::Failed agents: {', '.join(failed)}")
        print("::warning::Check individual job logs for details")


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0]).parse_args(argv)

    results = collect_results(dict(os.environ))
    failed = find_failures(results)
    report(results, failed)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        print("error: GITHUB_OUTPUT is not set", file=sys.stderr)
        return 2

    write_has_failures(Path(github_output), bool(failed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
