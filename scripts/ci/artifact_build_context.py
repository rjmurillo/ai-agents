#!/usr/bin/env python3
"""Build artifact context file for AI analysis.

Replaces the bash 'Build artifact context' block in
artifact-insight-scanner.yml (ADR-006).

ENV:
  ARTIFACT_FILE - path to file listing artifacts (from collect step)
  RUNNER_TEMP   - directory for intermediate files (default: ".")
  GITHUB_OUTPUT - path to step output file

Outputs:
  context_file - path to the built context markdown file
  context_size - size in bytes of the context file

EXIT CODES (ADR-035):
  0 - context file built
  1 - ARTIFACT_FILE env var missing or file not found
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from scripts.redact_secrets import redact as redact_token_shapes

_SECRET_ENVIRONMENT_VARIABLES = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "COPILOT_GITHUB_TOKEN",
    "BOT_PAT",
)


def redact_artifact_text(value: str) -> str:
    """Redact installed credentials and recognized shapes from artifact text."""
    redacted = value
    for variable in _SECRET_ENVIRONMENT_VARIABLES:
        secret = os.environ.get(variable, "")
        if len(secret) >= 8:
            redacted = redacted.replace(secret, "***")
    return redact_token_shapes(redacted, include_hex=False).text


def write_github_output(key: str, value: str) -> None:
    """Append key=value to GITHUB_OUTPUT; fall back to stdout."""
    path = os.environ.get("GITHUB_OUTPUT", "")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")
    else:
        print(f"{key}={value}")


_MAX_LINES_PER_FILE = 500


def run(_argv: list[str] | None = None) -> int:
    """Build context markdown from the artifact list."""
    artifact_file_path = os.environ.get("ARTIFACT_FILE", "")
    if not artifact_file_path:
        print("::error::ARTIFACT_FILE env var is required")
        return 1

    artifact_file = Path(artifact_file_path)
    if not artifact_file.exists():
        print(f"::error::ARTIFACT_FILE not found: {artifact_file}")
        return 1

    runner_temp = os.environ.get("RUNNER_TEMP", ".")
    context_file = Path(runner_temp) / "artifact-context.md"

    lines_in = artifact_file.read_text(encoding="utf-8").splitlines()
    artifacts = [ln for ln in lines_in if ln.strip()]

    context_parts = ["## Artifacts to Analyze\n\n"]
    for artifact in artifacts:
        p = Path(artifact)
        if p.is_file():
            artifact_lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            context_parts.extend(
                [
                    f"### {artifact}\n",
                    "```\n",
                    "\n".join(artifact_lines[:_MAX_LINES_PER_FILE]),
                    "\n```\n\n",
                ]
            )
    context_file.write_text(
        redact_artifact_text("".join(context_parts)),
        encoding="utf-8",
    )

    context_size = context_file.stat().st_size
    write_github_output("context_file", str(context_file))
    write_github_output("context_size", str(context_size))
    print(f"Built context file: {context_size} bytes")
    return 0


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
