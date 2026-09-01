#!/usr/bin/env python3
"""Prepare spec context for AI review.

Replaces the bash 'Prepare Spec Context' block in
ai-spec-validation.yml (ADR-006).

Uses a cryptographically random heredoc delimiter to prevent content
injection (CWE-78) -- the original block used the static "EOF_SPEC"
delimiter, which would be exploited if spec content contained that string.

ENV:
  SPEC_FILE          - path to spec content file (from load-spec step)
  INCREMENTAL_SCOPE  - incremental scope declaration (may be empty)
  PR_BODY            - pull request body (may be empty; issue #5366)
  GITHUB_OUTPUT      - path to step output file

Outputs:
  spec_context - multiline spec context for the AI review step

EXIT CODES (ADR-035):
  0 - context written
  2 - spec content file missing or unreadable
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.spec_nonexecutable_criteria import find_nonexecutable_criteria
from scripts.gh_retry_helpers import SECRET_ENVIRONMENT_VARIABLES
from scripts.redact_secrets import redact_ci_sink


def _redact(value: str) -> str:
    """Redact credential shapes and installed secrets from injected text.

    Mirrors `scripts/ci/build_ai_review_context.py`, whose `_redact_secrets`
    (`scripts/gh_retry_helpers.py:110`) reads, quoted verbatim:

        secret_values = (os.environ.get(variable, "") for variable in
        SECRET_ENVIRONMENT_VARIABLES)
        return redact_ci_sink(value or "", secret_values=secret_values).text

    That builder redacts the PR title and body before they reach the reviewer.
    Criterion text is a slice of the same author-controlled body arriving at
    the same reviewer by a different route, so it needs the same treatment;
    without this a token written into an acceptance criterion reached the model
    unredacted while the identical bytes elsewhere in the body were masked
    (CWE-200).

    Applied here rather than inside the classifier so that module stays a pure
    text classifier with no environment access, and because this is the point
    where the text is injected, which is the same seam the builder redacts at.
    """
    secret_values = (os.environ.get(variable, "") for variable in SECRET_ENVIRONMENT_VARIABLES)
    return redact_ci_sink(value, secret_values=secret_values).text


def _write_multiline_output(key: str, value: str, github_output: str) -> None:
    """Write a multiline value using a random EOF delimiter (CWE-78 safe)."""
    delimiter = f"EOF_{secrets.token_hex(16)}"
    with open(github_output, "a", encoding="utf-8") as fh:
        fh.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")


def _incremental_scope_block(incremental_scope: str) -> list[str]:
    """Render the issue #2255 scope declaration, or nothing when unscoped."""
    if not incremental_scope:
        return []
    return [
        "",
        "## Incremental Scope Declaration",
        "",
        f"This PR explicitly declares it implements: {incremental_scope}",
        "Evaluate coverage ONLY against the acceptance criteria",
        "relevant to this declared scope. Criteria belonging to",
        "other phases or future PRs are NOT expected to be covered",
        "and must be treated as N/A for this evaluation.",
    ]


def _nonexecutable_criteria_block(pr_body: str) -> list[str]:
    """Render the issue #5366 declaration, or nothing when none was found.

    A criterion that asserts the outcome of running a command cannot be
    verified by a reviewer with no shell, so leaving it unannotated costs a
    permanent PARTIAL. Naming it here lets the reviewer mark it N/A instead.

    The traceability paragraph is in this text rather than in a prompt because
    `.github/workflows/ai-spec-validation.yml` hands this one string to two
    steps: traceability (analyst, `spec-trace-requirements.md`) and
    completeness (critic, `spec-check-completeness.md`). Naming completeness as
    the actor stops the analyst being told to exempt anything, but it still
    leaves a list of criteria in its context with nothing saying coverage
    applies to them. Traceability decides whether a requirement is covered at
    all, so that is where a classifier false positive costs the most.
    """
    criteria = find_nonexecutable_criteria(pr_body)
    if not criteria:
        return []
    return [
        "",
        "## Non-Executable Criteria Declaration",
        "",
        "These acceptance criteria from the PR description matched the",
        "run-evidence classifier. This review has no shell, so a listed",
        "criterion may be historical run evidence rather than an unmet",
        "requirement. This declaration is a hint, not an override: if a",
        "listed criterion reads as a behavioral contract on code this diff",
        "changes, keep it in scope and say why. Otherwise it is historical",
        "run evidence, so completeness should mark it N/A, exclude it from",
        "the percentage, and do NOT emit PARTIAL or FAIL because it could",
        "not be executed.",
        "",
        "N/A here refers to repeating the command, never to the underlying",
        "requirement. Traceability still has to trace every listed criterion",
        "to its implementation, so do NOT drop one from coverage because it",
        "appears below:",
        "",
        *[f"- {_redact(criterion)}" for criterion in criteria],
    ]


def run(_argv: list[str] | None = None) -> int:
    """Prepare and write spec_context output."""
    spec_file_path = os.environ.get("SPEC_FILE", "")
    incremental_scope = os.environ.get("INCREMENTAL_SCOPE", "")
    pr_body = os.environ.get("PR_BODY", "")
    github_output = os.environ.get("GITHUB_OUTPUT", "")

    if not spec_file_path:
        print("::error::SPEC_FILE is required when spec validation runs", file=sys.stderr)
        return 2

    spec_file = Path(spec_file_path)
    if not spec_file.is_file():
        print(f"::error::SPEC_FILE is not an existing file: {spec_file}", file=sys.stderr)
        return 2

    try:
        spec_content = spec_file.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"::error::Could not read SPEC_FILE {spec_file}: {exc}", file=sys.stderr)
        return 2

    context_parts = ["## Specification Content", "", spec_content]
    context_parts += _incremental_scope_block(incremental_scope)
    context_parts += _nonexecutable_criteria_block(pr_body)

    context_value = "\n".join(context_parts)

    if github_output:
        _write_multiline_output("spec_context", context_value, github_output)
    else:
        print(f"spec_context={context_value}")

    return 0


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
