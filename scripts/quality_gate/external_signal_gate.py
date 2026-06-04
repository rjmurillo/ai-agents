#!/usr/bin/env python3
"""Build gate-aggregator signals from pytest status and agent verdicts.

Issue #2108 / #1855: no quality gate may pass on LLM verdicts alone. This
adapter collects the deterministic ``pytest`` status (an external signal) plus
the ten LLM agent verdicts and feeds them to
``scripts/external_signals/gate_aggregator.py``, which refuses ``PASS`` when no
external signal is present (the closed-loop rule).

This job is ADDITIVE and OBSERVABLE. It does NOT replace the authoritative gate
in ``scripts/quality_gate/check_critical_failures.py``; it surfaces the
externally-grounded verdict alongside it so the closed-loop guarantee from
#1855 is enforced and visible. Swapping the final gate to this aggregator is a
separate, higher-risk change (see PR description).

Verdict vocabulary mapping (gate_aggregator accepts
PASS, WARN, FAIL, CRITICAL_FAIL, REJECTED, NEEDS_REVIEW, UNKNOWN):

* pytest_status:
    PASS -> PASS, FAIL -> FAIL, ERROR -> UNKNOWN (tool could not run),
    SKIPPED -> UNKNOWN (no deterministic result available).
* agent verdict NON_COMPLIANT -> FAIL (NON_COMPLIANT is in
  scripts/ai_review_common/verdict.py:FAIL_VERDICTS; gate_aggregator has no
  NON_COMPLIANT token, so it maps to the equivalent blocking FAIL).
* an empty/missing agent verdict -> UNKNOWN (forces attention, never silent
  PASS).
* any other verdict is passed through and validated by gate_aggregator.

Input env vars:
    PYTEST_STATUS                       - run-tests job pytest-status output.
    SECURITY_VERDICT ... DECISION_RIGOR_VERDICT (10) - aggregated agent verdicts.

Exit codes: delegated to gate_aggregator.main (ADR-035):
    0 - final verdict PASS or WARN
    1 - blocking verdict, or closed-loop refusal (no external signal)
    2 - bad invocation
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_WORKSPACE = _SCRIPT_DIR.parents[1]
sys.path.insert(0, str(_WORKSPACE))
_GITHUB_SCRIPTS = _WORKSPACE / ".github" / "scripts"
sys.path.insert(0, str(_GITHUB_SCRIPTS))

from quality_gate_agents import QUALITY_GATE_AGENTS, agent_env_name  # noqa: E402
from scripts.external_signals import gate_aggregator  # noqa: E402

# pytest_status -> gate_aggregator verdict token.
_PYTEST_VERDICT = {
    "PASS": "PASS",
    "FAIL": "FAIL",
    "ERROR": "UNKNOWN",
    "SKIPPED": "UNKNOWN",
}

# Agent verdict tokens that gate_aggregator does not know, mapped to one it does.
_AGENT_VERDICT_ALIAS = {
    "NON_COMPLIANT": "FAIL",
    "": "UNKNOWN",
}


def pytest_signal(pytest_status: str) -> str:
    """Return an ``external:pytest=VERDICT`` spec for the gate aggregator."""

    verdict = _PYTEST_VERDICT.get(pytest_status.strip().upper(), "UNKNOWN")
    return f"external:pytest={verdict}"


def agent_signal(agent: str, verdict: str) -> str:
    """Return an ``llm:<agent>=VERDICT`` spec, aliasing unknown tokens."""

    normalized = verdict.strip().upper()
    normalized = _AGENT_VERDICT_ALIAS.get(normalized, normalized)
    return f"llm:{agent}={normalized}"


def build_signals(env: dict[str, str]) -> list[str]:
    """Return the full ``--signal`` argument list for gate_aggregator."""

    signals = [pytest_signal(env.get("PYTEST_STATUS", ""))]
    for agent in QUALITY_GATE_AGENTS:
        verdict = env.get(f"{agent_env_name(agent)}_VERDICT", "")
        signals.append(agent_signal(agent, verdict))
    return signals


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0]).parse_args(argv)

    signals = build_signals(dict(os.environ))
    aggregator_argv: list[str] = ["--json"]
    for signal in signals:
        aggregator_argv.extend(["--signal", signal])

    return gate_aggregator.main(aggregator_argv)


if __name__ == "__main__":
    sys.exit(main())
