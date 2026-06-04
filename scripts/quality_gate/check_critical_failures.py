#!/usr/bin/env python3
"""Decide whether the AI PR quality gate blocks the merge.

Extracted from the inline ``Check for Critical Failures`` step in
``.github/workflows/ai-pr-quality-gate.yml`` (ADR-006: no logic in YAML).

The step reads the final verdict and the ten per-agent verdicts from the
environment, then:

1. Fails (exit 1) if any agent verdict is missing (null/whitespace), printing
   ``::error::`` per missing agent.
2. Fails (exit 1) if the final verdict is a blocking verdict, printing the
   agents with blocking verdicts.
3. Otherwise passes (exit 0).

Blocking verdict set (canonical source + documented divergence):

    scripts/ai_review_common/verdict.py:FAIL_VERDICTS =
        {"CRITICAL_FAIL", "REJECTED", "FAIL", "NEEDS_REVIEW", "NON_COMPLIANT"}

This gate is STRICTER than canonical: it ALSO blocks on ``UNKNOWN``. Per
REQ-008-05 (issue #1934) an UNKNOWN verdict from a crashed or unparseable skill
must force explicit attention, so the workflow gate adds it. The blocking set
here is therefore ``FAIL_VERDICTS | {"UNKNOWN"}``, matching the original pwsh
``$blockingVerdicts`` array exactly
(CRITICAL_FAIL, REJECTED, FAIL, NEEDS_REVIEW, NON_COMPLIANT, UNKNOWN).

Input env vars:
    FINAL_VERDICT
    SECURITY_VERDICT, QA_VERDICT, ANALYST_VERDICT, ARCHITECT_VERDICT,
    DEVOPS_VERDICT, ROADMAP_VERDICT, RELIABILITY_VERDICT,
    OBSERVABILITY_VERDICT, AGENT_SAFETY_VERDICT, DECISION_RIGOR_VERDICT

Exit codes (ADR-035):
    0 - gate passed
    1 - gate failed (missing verdicts or a blocking final verdict)
"""

from __future__ import annotations

import argparse
import os
import sys

try:
    from .path_utils import REPOSITORY_ROOT
except ImportError:  # pragma: no cover - script execution path
    from path_utils import REPOSITORY_ROOT

_WORKSPACE = REPOSITORY_ROOT
sys.path.insert(0, str(_WORKSPACE))

from scripts.ai_review_common import FAIL_VERDICTS  # noqa: E402

# FAIL_VERDICTS plus UNKNOWN; see module docstring for the divergence rationale.
BLOCKING_VERDICTS = frozenset(FAIL_VERDICTS | {"UNKNOWN"})

# Agent display names with emoji, in the canonical order. Mirrors the original
# $agentVerdicts array in the workflow block.
_AGENT_DISPLAY: tuple[tuple[str, str], ...] = (
    ("\U0001f512 Security", "SECURITY_VERDICT"),
    ("\U0001f9ea QA", "QA_VERDICT"),
    ("\U0001f4ca Analyst", "ANALYST_VERDICT"),
    ("\U0001f4d0 Architect", "ARCHITECT_VERDICT"),
    ("⚙️ DevOps", "DEVOPS_VERDICT"),
    ("\U0001f5fa️ Roadmap", "ROADMAP_VERDICT"),
    ("\U0001f6e1️ Reliability", "RELIABILITY_VERDICT"),
    ("\U0001f52d Observability", "OBSERVABILITY_VERDICT"),
    ("\U0001f916 Agent Safety", "AGENT_SAFETY_VERDICT"),
    ("⚖️ Decision Rigor", "DECISION_RIGOR_VERDICT"),
)


def collect_verdicts(env: dict[str, str]) -> list[tuple[str, str]]:
    """Return ``(display_name, verdict)`` pairs in canonical agent order."""

    return [(name, env.get(key, "")) for name, key in _AGENT_DISPLAY]


def find_missing(verdicts: list[tuple[str, str]]) -> list[str]:
    """Return display names whose verdict is null or whitespace-only."""

    return [name for name, verdict in verdicts if not verdict.strip()]


def find_blocking(verdicts: list[tuple[str, str]]) -> list[str]:
    """Return ``"name: verdict"`` for agents with a blocking verdict."""

    return [
        f"{name}: {verdict}"
        for name, verdict in verdicts
        if verdict in BLOCKING_VERDICTS
    ]


def _report_missing(missing: list[str]) -> None:
    print("")
    print("❌ Quality gate failed - missing verdicts")
    print("")
    print("Agents with missing verdicts:")
    for name in missing:
        print(f"  - {name}")
    print("")
    print("This indicates agent review jobs failed or artifacts are incomplete")


def _report_blocking(failed: list[str]) -> None:
    print("")
    print("❌ AI Quality Gate FAILED")
    print("")
    print("Agents with blocking verdicts:")
    for entry in failed:
        print(f"  - {entry}")
    print("")
    print("Click on individual agent jobs above to see detailed findings.")


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0]).parse_args(argv)

    env = dict(os.environ)
    final_verdict = env.get("FINAL_VERDICT", "")
    verdicts = collect_verdicts(env)

    missing = find_missing(verdicts)
    for name, verdict in verdicts:
        if not verdict.strip():
            print(f"::error::{name}: No verdict received from aggregate step")
        elif verdict in BLOCKING_VERDICTS:
            print(f"::error::{name}: {verdict}")

    if missing:
        _report_missing(missing)
        return 1

    if final_verdict in BLOCKING_VERDICTS:
        _report_blocking(find_blocking(verdicts))
        return 1

    print(f"✅ AI Quality Gate passed with verdict: {final_verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
