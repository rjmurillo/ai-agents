#!/usr/bin/env python3
"""Load cached review results and write them to GITHUB_OUTPUT.

Replaces the bash 'Load cached results' block in
.github/actions/agent-review/action.yml (ADR-006).

Uses a cryptographically random heredoc delimiter to prevent content
injection from findings (CWE-78) -- the original used the prefix
"EOF_CACHED_FINDINGS_" + openssl hex, which is equivalent.

ENV:
  AGENT         - agent name (CWE-22 validated by caller)
  GITHUB_OUTPUT - path to step output file

Outputs:
  verdict               - cached verdict string
  infrastructure_failure - cached infra-failure flag
  retry_count           - always "0" for cached results
  findings              - multiline cached findings text

EXIT CODES (ADR-035):
  0 - cache loaded
  1 - AGENT env var missing or invalid
"""

from __future__ import annotations

import os
import re
import secrets
import sys
from pathlib import Path


def _write_multiline_output(key: str, value: str, github_output: str) -> None:
    """Write a multiline value using a random EOF delimiter (CWE-78 safe)."""
    delimiter = f"EOF_CACHED_FINDINGS_{secrets.token_hex(16)}"
    with open(github_output, "a", encoding="utf-8") as fh:
        fh.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")


def _write_output(key: str, value: str, github_output: str) -> None:
    with open(github_output, "a", encoding="utf-8") as fh:
        fh.write(f"{key}={value}\n")


_AGENT_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def run(argv: list[str] | None = None) -> int:  # noqa: ARG001
    """Load cache and write outputs."""
    agent = os.environ.get("AGENT", "")
    if not agent or not _AGENT_RE.match(agent):
        print(f"::error::Invalid agent name: {agent}. Must match '^[a-zA-Z0-9_-]+$'.")
        return 1

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if not github_output:
        print("GITHUB_OUTPUT not set; writing to stdout")

    cache_dir = Path(f"ai-review-cache/{agent}")
    print(f"Cache hit for {agent} review, skipping Copilot API call")

    verdict = (cache_dir / "verdict.txt").read_text(encoding="utf-8").strip()
    infra_file = cache_dir / "infrastructure-failure.txt"
    infra_failure = (
        infra_file.read_text(encoding="utf-8").strip() if infra_file.exists() else "false"
    )
    findings = (cache_dir / "findings.txt").read_text(encoding="utf-8")

    if github_output:
        _write_output("verdict", verdict, github_output)
        _write_output("infrastructure_failure", infra_failure, github_output)
        _write_output("retry_count", "0", github_output)
        _write_multiline_output("findings", findings, github_output)
    else:
        print(f"verdict={verdict}")
        print(f"infrastructure_failure={infra_failure}")
        print("retry_count=0")
        print(f"findings={findings}")

    return 0


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
