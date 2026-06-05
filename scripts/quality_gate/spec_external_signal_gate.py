#!/usr/bin/env python3
"""Build gate-aggregator signals for the spec-validation workflow.

Issue #2108 / #1855: no quality gate may pass on LLM verdicts alone. The
spec-validation workflow (``ai-spec-validation.yml``) decides requirements
coverage from two LLM agents (analyst traceability, critic completeness). This
adapter adds the deterministic acceptance-criteria extractor
(``scripts/external_signals/acceptance_criteria.py``) as an externally-grounded
signal, then feeds all three to
``scripts/external_signals/gate_aggregator.py``, which refuses ``PASS`` when no
external signal is present (the closed-loop rule).

This job is ADDITIVE and OBSERVABLE. It does NOT replace the authoritative gate
in ``.github/scripts/check_spec_failures.py``; it surfaces the
externally-grounded verdict alongside it so the closed-loop guarantee from
#1855 is enforced and visible. Swapping the final spec gate to this aggregator
is a separate, higher-risk change deferred to a canary (see PR #2361 and the
PR description).

Signals built:

* ``external:acceptance-criteria=VERDICT`` from the PR body. The extractor is
  deterministic (no model calls, no network):
    - criteria declared and all checked -> PASS
    - criteria declared with one or more unchecked -> FAIL
    - no acceptance section / no criteria found -> UNKNOWN (inconclusive;
      forces NEEDS_REVIEW under the closed-loop rule rather than blocking a PR
      that legitimately declares no checkbox section).
* ``llm:trace=VERDICT`` and ``llm:completeness=VERDICT`` from the two agents.
  Tokens are normalized to the gate_aggregator vocabulary:
    - COMPLIANT -> PASS, NON_COMPLIANT -> FAIL, PARTIAL -> WARN,
      NEEDS_REVIEW -> FAIL (matches scripts/ai_review_common/verdict.py
      FAIL_VERDICTS, which include NEEDS_REVIEW), empty/missing -> UNKNOWN.
    - any other verdict is passed through and validated by gate_aggregator.

Input env vars:
    PR_BODY_FILE         - path to a file holding the PR body markdown. When
                           unset or unreadable, the acceptance-criteria signal
                           is UNKNOWN (no deterministic result available).
    TRACE_VERDICT        - analyst traceability agent verdict.
    COMPLETENESS_VERDICT - critic completeness agent verdict.

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

try:
    from .path_utils import REPOSITORY_ROOT
except ImportError:  # pragma: no cover - script execution path
    from path_utils import REPOSITORY_ROOT

_WORKSPACE = REPOSITORY_ROOT
sys.path.insert(0, str(_WORKSPACE))

from scripts.external_signals import acceptance_criteria, gate_aggregator  # noqa: E402

# Agent verdict tokens normalized to preserve the authoritative gate semantics.
# Mirrors scripts/quality_gate/external_signal_gate.py:_AGENT_VERDICT_ALIAS.
_AGENT_VERDICT_ALIAS = {
    "COMPLIANT": "PASS",
    "NEEDS_REVIEW": "FAIL",
    "NON_COMPLIANT": "FAIL",
    "PARTIAL": "WARN",
    "": "UNKNOWN",
}


def acceptance_verdict(body: str) -> str:
    """Return the deterministic acceptance-criteria verdict token.

    * criteria declared and all checked -> PASS
    * criteria declared with unchecked items -> FAIL
    * no criteria declared -> UNKNOWN (inconclusive, not a hard block)
    """

    report = acceptance_criteria.evaluate(body)
    if not report.criteria:
        return "UNKNOWN"
    return "PASS" if report.passed else "FAIL"


def acceptance_signal(body: str) -> str:
    """Return an ``external:acceptance-criteria=VERDICT`` spec."""

    return f"external:acceptance-criteria={acceptance_verdict(body)}"


def agent_signal(agent: str, verdict: str) -> str:
    """Return an ``llm:<agent>=VERDICT`` spec, aliasing known tokens."""

    normalized = verdict.strip().upper()
    normalized = _AGENT_VERDICT_ALIAS.get(normalized, normalized)
    return f"llm:{agent}={normalized}"


def _read_body(path_str: str) -> str:
    """Read the PR body from ``path_str``; return '' on any miss.

    A missing or unreadable body file yields an empty string, which maps to an
    UNKNOWN acceptance-criteria signal (no deterministic result available)
    rather than crashing the observe step.
    """

    if not path_str:
        return ""
    path = Path(path_str)
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def build_signals(env: dict[str, str]) -> list[str]:
    """Return the full ``--signal`` argument list for gate_aggregator."""

    body = _read_body(env.get("PR_BODY_FILE", ""))
    return [
        acceptance_signal(body),
        agent_signal("trace", env.get("TRACE_VERDICT", "")),
        agent_signal("completeness", env.get("COMPLETENESS_VERDICT", "")),
    ]


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0]).parse_args(argv)

    signals = build_signals(dict(os.environ))
    aggregator_argv: list[str] = ["--json"]
    for signal in signals:
        aggregator_argv.extend(["--signal", signal])

    return gate_aggregator.main(aggregator_argv)


if __name__ == "__main__":
    sys.exit(main())
