#!/usr/bin/env python3
"""Detect a superseded AI PR quality-gate run so it does not leave a stale block.

Issue #2347. When a newer run cancels an in-progress ``AI PR Quality Gate`` run
(``cancel-in-progress: true``), GitHub marks the in-flight review jobs as
``cancelled``. The ``aggregate`` job still runs (``if: always()``) and, with empty
verdicts, the downstream ``Check for Critical Failures`` step blocks the merge.
The cancelled run's ``Aggregate Results`` check is keyed by the head SHA, so the
PR stays ``BLOCKED`` until a successor run re-emits the check on that SHA. When
the cancelling run has no jobs (a bare ``workflow_dispatch`` on the same head),
no successor ever replaces it, so the PR is wedged until a no-op commit creates a
new head.

This module decides whether the current ``aggregate`` invocation is a superseded
run that should emit a neutral, non-blocking status instead of a stale failure.

Signal source: the per-agent review job results that the ``aggregate`` job reads
from its ``needs.<agent>-review.result`` context. GitHub sets these to:

    - ``cancelled`` for a job interrupted by concurrency cancellation,
    - ``failure`` for a genuine job failure,
    - ``success`` / ``skipped`` for a job that ran or was gated off.

Decision rule (superseded => neutral, do not block):

    A run is SUPERSEDED when at least one review job is ``cancelled`` AND no
    review job is ``failure``. A cancellation with no genuine failure means the
    run was interrupted, not that review found a blocking problem.

    A run is NOT superseded when any review job is ``failure`` (a genuine failure
    must still block) or when no review job is ``cancelled`` (a normal run).

This is intentionally conservative: a single genuine ``failure`` keeps the gate
blocking, so a real problem is never masked by a coincident cancellation.

Input env vars (one ``<AGENT>_RESULT`` per quality-gate agent, mirroring
``check_failed_agents.py``):
    SECURITY_RESULT, QA_RESULT, ANALYST_RESULT, ARCHITECT_RESULT,
    DEVOPS_RESULT, ROADMAP_RESULT, RELIABILITY_RESULT, OBSERVABILITY_RESULT,
    AGENT_SAFETY_RESULT, DECISION_RIGOR_RESULT
    GITHUB_OUTPUT - path to the GitHub Actions output file.

Output:
    ``superseded=true|false`` appended to ``GITHUB_OUTPUT``.

Exit codes (ADR-035):
    0 - results inspected and ``superseded`` written (a superseded run is not an
        error; this step never fails the build).
    2 - GITHUB_OUTPUT is not set (config error).
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

_GITHUB_SCRIPTS = REPOSITORY_ROOT / ".github" / "scripts"
sys.path.insert(0, str(_GITHUB_SCRIPTS))

from quality_gate_agents import (  # noqa: E402
    QUALITY_GATE_AGENTS,
    agent_env_name,
)

_CANCELLED = "cancelled"
_FAILURE = "failure"


def collect_results(env: dict[str, str]) -> list[str]:
    """Return each review job's result in the canonical agent order."""

    return [
        env.get(f"{agent_env_name(agent)}_RESULT", "")
        for agent in QUALITY_GATE_AGENTS
    ]


def is_superseded(results: list[str]) -> bool:
    """Return True when the run was cancelled (superseded) without a real failure.

    Superseded => at least one ``cancelled`` AND no ``failure``. A genuine
    ``failure`` always wins so a real blocking problem is never neutralized.
    """

    has_cancelled = any(result == _CANCELLED for result in results)
    has_failure = any(result == _FAILURE for result in results)
    return has_cancelled and not has_failure


def write_superseded(output_path: Path, superseded: bool) -> None:
    """Append ``superseded=true|false`` to the GitHub output file."""

    value = "true" if superseded else "false"
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(f"superseded={value}\n")


def report(results: list[str], superseded: bool) -> None:
    """Print the per-agent results and the supersession decision."""

    print("Review job results:")
    for agent, result in zip(QUALITY_GATE_AGENTS, results):
        print(f"  {agent}: {result}")
    if superseded:
        print(
            "::notice::Run superseded by a newer AI PR Quality Gate run "
            "(review jobs cancelled, no genuine failure). Emitting a neutral, "
            "non-blocking status instead of a stale failure (Issue #2347)."
        )
    else:
        print("Run not superseded; normal gate evaluation applies.")


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0]).parse_args(argv)

    results = collect_results(dict(os.environ))
    superseded = is_superseded(results)
    report(results, superseded)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        print("error: GITHUB_OUTPUT is not set", file=sys.stderr)
        return 2

    write_superseded(Path(github_output), superseded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
