#!/usr/bin/env python3
"""Assemble the AI-issue-triage summary comment (issue #2967, ADR-006 burn-down).

This is the assembly half of the "Post Triage Summary" step in
`.github/workflows/ai-issue-triage.yml`. That step used to build the triage
comment inline in a PowerShell here-string: a `switch` for the priority icon,
`if`/`else` blocks for the optional feature-review and PRD-escalation rows, and
`Test-Path`/`Get-Content` reads for the three analysis-output files. ADR-006
forbids that logic in YAML. It now lives here as a pure builder plus a thin CLI,
and the workflow step calls this module then posts the file it writes.

Behavior is preserved byte-for-byte against the original PowerShell output; the
golden fixtures under `tests/ci/fixtures/triage_summary/` were captured by
running the original block and are asserted by
`tests/ci/test_build_triage_summary_comment.py`.

The builder reproduces two non-obvious PowerShell semantics:

- ``-eq 'true'`` and ``-ne 'UNKNOWN'`` are case-insensitive, so ``ESCALATE_TO_PRD``
  of ``TRUE`` still shows the PRD row and ``FEATURE_REVIEW`` of ``unknown`` still
  hides the feature-review row.
- The priority ``switch`` currently maps every priority to an empty string, so
  the priority table cell renders with two leading spaces. That is preserved.

Exit Codes (ADR-035):
    0 = comment file written
    (argparse emits 2 for a malformed invocation.)
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

# The original PowerShell `switch ($env:PRIORITY)` mapped every case (P0..P3 and
# default) to an empty string. Kept as a table so a future icon restoration is a
# one-line edit rather than a new branch; empty values preserve current output.
_PRIORITY_EMOJI: dict[str, str] = {"P0": "", "P1": "", "P2": "", "P3": ""}

# Fixed analysis-output paths the workflow's upstream parse steps write. They are
# constants (not user-supplied), so no path validation is needed here.
_CATEGORIZE_FILE = "/tmp/categorize-output.txt"
_ALIGN_FILE = "/tmp/align-output.txt"
_FEATURE_REVIEW_FILE = "/tmp/feature-review-output.txt"
_DEFAULT_OUTPUT = "/tmp/triage-comment.md"

_TEMPLATE = """<!-- AI-ISSUE-TRIAGE -->

## AI Triage Summary

> [!NOTE]
> This issue has been automatically triaged by AI agents

<details>
<summary>What is AI Triage?</summary>

This issue was analyzed by AI agents:

- **Analyst Agent**: Categorizes the issue and suggests appropriate labels
- **Roadmap Agent**: Aligns the issue with project milestones and priorities
- **Explainer Agent** (if escalated): Generates comprehensive PRD

</details>

### Triage Results

| Property | Value |
|:---------|:------|
| **Category** | `{category}` |
| **Labels** | {labels_display} |
| {priority_emoji} **Priority** | `{priority}` |
| **Milestone** | {milestone_display} |
{feature_review_row}
{prd_row}

<details>
<summary>Categorization Analysis</summary>

```json
{categorize_output}
```

</details>

<details>
<summary>Roadmap Alignment</summary>

```json
{align_output}
```

</details>

{feature_block}

---

<sub>Powered by [AI Issue Triage](https://github.com/{repository}) workflow</sub>"""


def _prd_row(escalate_to_prd: str) -> str:
    """PRD-escalation row when escalation fired (case-insensitive, per ``-eq``)."""
    if escalate_to_prd.lower() == "true":
        return "| **PRD Escalation** | Generated (see below) |"
    return ""


def _feature_review_row(feature_review: str) -> str:
    """Feature-review row when a real recommendation exists (not empty/UNKNOWN)."""
    if feature_review and feature_review.upper() != "UNKNOWN":
        return f"| **Feature Review** | `{feature_review}` |"
    return ""


def _feature_block(feature_review_output: str) -> str:
    """Collapsible feature-review block, present only when the file had content."""
    if not feature_review_output:
        return ""
    return (
        "\n<details>\n<summary>Feature Request Review</summary>\n\n"
        f"{feature_review_output}\n\n</details>"
    )


def build_triage_comment(
    *,
    category: str,
    labels: str,
    priority: str,
    milestone: str,
    escalate_to_prd: str,
    feature_review: str,
    repository: str,
    categorize_output: str,
    align_output: str,
    feature_review_output: str,
) -> str:
    """Assemble the triage-summary markdown comment.

    Args:
        category: Issue category (analyst agent output).
        labels: Labels JSON string; empty renders "*None assigned*".
        priority: Priority code (P0..P4); rendered as inline code.
        milestone: Milestone title; empty renders "*Not assigned*".
        escalate_to_prd: "true" (case-insensitive) shows the PRD-escalation row.
        feature_review: Recommendation; non-empty and not "UNKNOWN" shows the row.
        repository: owner/name for the footer link.
        categorize_output: Categorization analysis JSON (or "N/A" when absent).
        align_output: Roadmap alignment JSON (or "N/A" when absent).
        feature_review_output: Feature-review body; non-empty shows the block.

    Returns:
        The comment markdown without a trailing newline (the CLI adds the
        newline that ``Set-Content`` appended in the original step).
    """
    return _TEMPLATE.format(
        category=category,
        labels_display=labels if labels else "*None assigned*",
        priority_emoji=_PRIORITY_EMOJI.get(priority, ""),
        priority=priority,
        milestone_display=milestone if milestone else "*Not assigned*",
        feature_review_row=_feature_review_row(feature_review),
        prd_row=_prd_row(escalate_to_prd),
        categorize_output=categorize_output,
        align_output=align_output,
        feature_block=_feature_block(feature_review_output),
        repository=repository,
    )


def _read_output(path: str, default: str) -> str:
    """Read an analysis-output file, mirroring Test-Path/Get-Content -Raw."""
    file = Path(path)
    if not file.exists():
        return default
    return file.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: read env plus the three analysis files, write the comment."""
    parser = argparse.ArgumentParser(
        description="Build the AI-issue-triage summary comment (issue #2967)."
    )
    parser.add_argument(
        "--output",
        default=_DEFAULT_OUTPUT,
        help=f"Path to write the comment markdown (default {_DEFAULT_OUTPUT}).",
    )
    args = parser.parse_args(argv)

    comment = build_triage_comment(
        category=os.environ.get("CATEGORY", ""),
        labels=os.environ.get("LABELS", ""),
        priority=os.environ.get("PRIORITY", ""),
        milestone=os.environ.get("MILESTONE", ""),
        escalate_to_prd=os.environ.get("ESCALATE_TO_PRD", ""),
        feature_review=os.environ.get("FEATURE_REVIEW", ""),
        repository=os.environ.get("GITHUB_REPOSITORY", ""),
        categorize_output=_read_output(_CATEGORIZE_FILE, "N/A"),
        align_output=_read_output(_ALIGN_FILE, "N/A"),
        feature_review_output=_read_output(_FEATURE_REVIEW_FILE, ""),
    )

    # Set-Content -Encoding UTF8 wrote UTF-8 (no BOM) and appended a newline.
    Path(args.output).write_bytes((comment + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
