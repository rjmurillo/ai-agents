"""Best-effort milestone output to GitHub Actions environment files."""

from __future__ import annotations

import os
from collections.abc import Mapping


def write_github_output(outputs: Mapping[str, str]) -> None:
    """Append output values when GITHUB_OUTPUT names a writable file."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    try:
        with open(output_file, "a", encoding="utf-8") as stream:
            for key, value in outputs.items():
                stream.write(f"{key}={value}\n")
    except OSError:
        # Actions reporting remains optional, as in the milestone callers.
        pass


def write_step_summary(content: str) -> None:
    """Append summary text without failing the milestone operation."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return
    try:
        with open(summary_file, "a", encoding="utf-8") as stream:
            stream.write(content)
    except OSError:
        # A reporting failure must not replace the operation's exit status.
        pass
