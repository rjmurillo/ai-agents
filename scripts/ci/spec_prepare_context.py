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
  GITHUB_OUTPUT      - path to step output file

Outputs:
  spec_context - multiline spec context for the AI review step

EXIT CODES (ADR-035):
  0 - context written
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path


def _write_multiline_output(key: str, value: str, github_output: str) -> None:
    """Write a multiline value using a random EOF delimiter (CWE-78 safe)."""
    delimiter = f"EOF_{secrets.token_hex(16)}"
    with open(github_output, "a", encoding="utf-8") as fh:
        fh.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")


def run(argv: list[str] | None = None) -> int:  # noqa: ARG001
    """Prepare and write spec_context output."""
    spec_file_path = os.environ.get("SPEC_FILE", "")
    incremental_scope = os.environ.get("INCREMENTAL_SCOPE", "")
    github_output = os.environ.get("GITHUB_OUTPUT", "")

    spec_file = Path(spec_file_path) if spec_file_path else None

    if spec_file and spec_file.is_file():
        spec_content = spec_file.read_text(encoding="utf-8")
        context_parts = ["## Specification Content", "", spec_content]

        if incremental_scope:
            context_parts += [
                "",
                "## Incremental Scope Declaration",
                "",
                f"This PR explicitly declares it implements: {incremental_scope}",
                "Evaluate coverage ONLY against the acceptance criteria",
                "relevant to this declared scope. Criteria belonging to",
                "other phases or future PRs are NOT expected to be covered",
                "and must be treated as N/A for this evaluation.",
            ]

        context_value = "\n".join(context_parts)
    else:
        context_value = "No spec content loaded"

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
