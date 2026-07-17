#!/usr/bin/env python3
"""AI-review infrastructure gate (ADR-006 extraction, issue #2967).

Behavior-preserving extraction of the "context infrastructure failure" skip gate
that opened the "Invoke Copilot CLI" step in
``.github/actions/ai-review/action.yml``. That inline shell block decided whether
to skip the Copilot invocation when the Build context step reported an
infrastructure failure, and wrote the DID_NOT_RUN verdict the parse step reads.
This module owns the decision so the workflow becomes a thin caller
(ADR-006: no logic in YAML).

This module is the canonical source for the gate contract. The exact verdict and
message strings are the ``DID_NOT_RUN_VERDICT`` and ``DID_NOT_RUN_MESSAGE``
constants below, copied character-for-character from the former inline block.
Skip is triggered only by the exact string ``"true"``; any other value runs the
review. On skip, the module emits the warning, writes the verdict file, and
publishes ``infrastructure_failure=true``, ``retry_count=0``, and ``skip=true``.
On the run path it publishes ``skip=false``.

The file path comes from ``AI_REVIEW_OUTPUT_FILE``, then ``RUNNER_TEMP``, then the
system temp directory. The module publishes that path as ``output_file`` so the
gate, invoke, and parse steps use the same physical file on Windows and POSIX.
Both decisions exit 0 so the DID_NOT_RUN verdict reaches the unconditional parse
step (#2821). Every GitHub sink is optional so the module runs and is testable
outside GitHub Actions.

Exit codes (AGENTS.md): 0 ok, 2 config error (cannot write a sink).
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

OUTPUT_FILE_NAME = "ai-review-output.txt"

SKIP_TRIGGER = "true"
DID_NOT_RUN_VERDICT = "DID_NOT_RUN"
DID_NOT_RUN_MESSAGE = "AI review did not run because context build had an infrastructure failure."
SKIP_WARNING = (
    "::warning::Skipping Copilot CLI invocation due to context build infrastructure failure"
)


@dataclass(frozen=True, slots=True)
class GateDecision:
    """Outcome of the infrastructure-gate evaluation."""

    skip: bool
    verdict: str
    message: str
    infrastructure_failure: bool
    retry_count: int


def evaluate_gate(context_infra_failure: str) -> GateDecision:
    """Decide whether to skip the Copilot invocation.

    Skip only when the Build context step reported ``context_infra_failure`` as
    the exact string ``"true"`` (matching the shell ``= "true"`` compare). Any
    other value (including an empty string) runs the review.
    """
    if context_infra_failure == SKIP_TRIGGER:
        return GateDecision(
            skip=True,
            verdict=DID_NOT_RUN_VERDICT,
            message=DID_NOT_RUN_MESSAGE,
            infrastructure_failure=True,
            retry_count=0,
        )
    return GateDecision(
        skip=False,
        verdict="",
        message="",
        infrastructure_failure=False,
        retry_count=0,
    )


def render_output_file(decision: GateDecision) -> str:
    """Build the verdict file body the parse step reads on skip."""
    return f"VERDICT: {decision.verdict}\nMESSAGE: {decision.message}\n"


def resolve_output_file() -> str:
    """Resolve one cross-platform verdict path for every action step."""
    override = os.environ.get("AI_REVIEW_OUTPUT_FILE")
    if override:
        return override
    temp_dir = os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()
    return str(Path(temp_dir) / OUTPUT_FILE_NAME)


def _append_to_env_file(env_var: str, text: str) -> None:
    """Append text to the file named by env_var, when the var is set."""
    target = os.environ.get(env_var)
    if not target:
        return
    with Path(target).open("a", encoding="utf-8") as handle:
        handle.write(text)


def emit(decision: GateDecision, output_file: str) -> None:
    """Write outputs, the verdict file, and the skip warning to their sinks.

    The ``output_file`` and ``skip`` outputs are always written so later action
    steps share one file and the workflow ``if:`` guard has a value. On skip the
    verdict file, infrastructure flag, and retry count mirror the inline block;
    the ``::warning::`` annotation is printed to stdout.
    """
    _append_to_env_file("GITHUB_OUTPUT", f"output_file={output_file}\n")
    _append_to_env_file("GITHUB_OUTPUT", f"skip={'true' if decision.skip else 'false'}\n")
    if not decision.skip:
        return

    Path(output_file).write_text(render_output_file(decision), encoding="utf-8")
    _append_to_env_file("GITHUB_OUTPUT", "infrastructure_failure=true\n")
    _append_to_env_file("GITHUB_OUTPUT", f"retry_count={decision.retry_count}\n")
    print(SKIP_WARNING)


def main() -> int:
    context_infra_failure = os.environ.get("CONTEXT_INFRA_FAILURE", "")
    output_file = resolve_output_file()

    decision = evaluate_gate(context_infra_failure)
    try:
        emit(decision, output_file)
    except OSError as exc:
        print(f"::error::ai-review infra gate cannot write outputs: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
