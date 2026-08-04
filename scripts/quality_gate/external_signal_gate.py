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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .path_utils import REPOSITORY_ROOT
else:
    try:
        from .path_utils import REPOSITORY_ROOT
    except ImportError:  # pragma: no cover - script execution path
        from path_utils import REPOSITORY_ROOT

_WORKSPACE = REPOSITORY_ROOT
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

# Agent verdict tokens normalized to preserve the authoritative gate semantics.
# DID_NOT_RUN maps to UNKNOWN to match the two modules that already understand
# it: verdict.merge_verdicts collapses DID_NOT_RUN into UNKNOWN, and
# check_critical_failures.BLOCKING_VERDICTS lists the two together. In
# gate_aggregator an UNKNOWN resolves to NEEDS_REVIEW, so an agent that never
# ran blocks rather than passing silently.
_AGENT_VERDICT_ALIAS = {
    "COMPLIANT": "PASS",
    "DID_NOT_RUN": "UNKNOWN",
    "NEEDS_REVIEW": "FAIL",
    "NON_COMPLIANT": "FAIL",
    "PARTIAL": "WARN",
    "": "UNKNOWN",
}


def pytest_signal(pytest_status: str) -> str:
    """Return an ``external:pytest=VERDICT`` spec for the gate aggregator."""

    verdict = _PYTEST_VERDICT.get(pytest_status.strip().upper(), "UNKNOWN")
    return f"external:pytest={verdict}"


def agent_signal(agent: str, verdict: str) -> str:
    """Return an ``llm:<agent>=VERDICT`` spec, aliasing the repo vocabulary.

    The alias table covers the repo verdict tokens gate_aggregator does not
    accept. Anything still outside its vocabulary falls back to UNKNOWN rather
    than being passed through, because a token gate_aggregator rejects makes it
    exit 2 with no verdict at all. A gate that cannot name a result is worse
    than one that blocks: UNKNOWN resolves to NEEDS_REVIEW, which still refuses
    to pass. This mirrors merge_verdicts in scripts/ai_review_common/verdict.py,
    which coerces unrecognized tokens to UNKNOWN for the same reason.

    The fallback warns, and it warns in GitHub's annotation format. Silently
    absorbing an unrecognized token would hide the exact drift that made this
    function crash on DID_NOT_RUN: a producer grew a verdict the adapter never
    learned, and nothing surfaced it. An aliased token is a decided mapping and
    stays quiet; an unaliased one is a gap in the table and says so.

    The ``::warning::`` prefix is load-bearing, not cosmetic. A bare line on
    stderr is a dead channel: CI logs are read after a failure, and this path
    does not fail, it degrades. The annotation form surfaces in the run summary
    and on the diff without anyone opening the log. The repo already relies on
    this convention in 217 places, so this is the established surface rather
    than a new one.
    """

    normalized = verdict.strip().upper()
    aliased = _AGENT_VERDICT_ALIAS.get(normalized)
    if aliased is not None:
        return f"llm:{agent}={aliased}"
    if normalized not in gate_aggregator.KNOWN_VERDICTS:
        print(
            f"::warning::unrecognized verdict {normalized!r} for agent"
            f" {agent!r}; treating as UNKNOWN."
            " Add it to _AGENT_VERDICT_ALIAS.",
            file=sys.stderr,
        )
        normalized = "UNKNOWN"
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
