#!/usr/bin/env python3
"""GITHUB_OUTPUT writes for new_issue.py (issue #6180).

A GitHub Actions caller reads ``steps.<id>.outputs.issue_number``. When the
issue exists but a later step (labels, milestone) fails, the step must still
publish the issue number, or the caller sees an empty value and may file the
issue again. ``write_created_failure`` publishes ``success=false`` with the
number and URL. A failure before creation writes nothing, so no
``issue_number`` is ever published for an issue that does not exist.
"""

from __future__ import annotations

import os


def write_github_output(outputs: dict[str, str]) -> None:
    """Write key=value pairs to GITHUB_OUTPUT if available."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    try:
        with open(output_file, "a", encoding="utf-8") as fh:
            for key, value in outputs.items():
                fh.write(f"{key}={value}\n")
    except OSError:
        pass


def write_created_failure(issue_number: int, url: str) -> None:
    """Publish the created issue after a post-creation step failed."""
    write_github_output({"success": "false", "issue_number": str(issue_number), "issue_url": url})
