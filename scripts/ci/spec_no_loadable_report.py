#!/usr/bin/env python3
"""Write the advisory report for a PR whose references name no loadable requirements.

Runs in `ai-spec-review.yml` when `spec_load_content.py` reports `loadable=false`
(issue #6506 fail-open-27): the model steps were skipped, so the report states
that nothing was reviewed and claims no verdict. The job stays advisory and the
PR comment still posts.

ENV:
  ISSUE_REFS        - space-delimited issue refs from the extractor
  AZURE_REFS        - space-delimited Azure Boards tokens (`AB#<n>`)
  GITHUB_REPOSITORY - owner/repo, used in the footer link
  RUNNER_TEMP       - directory for the report file (default ".")
  GITHUB_RUN_ID     - run id, used in the report file name
  GITHUB_OUTPUT     - step output file; receives `report_file`

EXIT CODES (ADR-035):
  0 - report written
  2 - the report file could not be written

Standard library only: the workflow runs this with bare `python3`.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_CONFIG = 2

# The extractor emits plain reference tokens. Anything else is dropped rather
# than escaped, so a hostile value can never open markup, a link, or a mention.
_SAFE_REF = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?#?[0-9]*")
_MARKER = "<!-- AI-SPEC-VALIDATION -->"


def _cell(raw: str) -> str:
    """Return the safe reference tokens joined for one table cell, or `*None*`."""
    refs = [ref for ref in raw.split() if _SAFE_REF.fullmatch(ref)]
    return " ".join(refs) if refs else "*None*"


def build_report(issue_refs: str, azure_refs: str, repository: str) -> str:
    """Build the report body. It never names a verdict."""
    repository = repository if _SAFE_REF.fullmatch(repository) else "this repository"
    return f"""\
{_MARKER}

## Spec-to-Implementation Validation

> [!WARNING]
> **No requirements were loadable**
>
> No requirement text could be loaded for the references below, so the
> traceability and completeness reviews did not run. This workflow cannot read
> Azure Boards work items.

| Reference | Value |
|:----------|:------|
| **Issues** | {_cell(issue_refs)} |
| **Azure Boards** | {_cell(azure_refs)} |

Link a GitHub issue or a spec file (REQ-*, DESIGN-*, TASK-*) to enable the reviews.

---

<sub>Powered by [AI Spec Validator](https://github.com/{repository}) workflow</sub>
"""


def _write_output(key: str, value: str) -> None:
    """Append key=value to GITHUB_OUTPUT; fall back to stdout."""
    path = os.environ.get("GITHUB_OUTPUT", "")
    if not path:
        print(f"{key}={value}")
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{key}={value}\n")


def main(_argv: list[str] | None = None) -> int:
    """Write the report file and publish its path."""
    report = build_report(
        os.environ.get("ISSUE_REFS", ""),
        os.environ.get("AZURE_REFS", ""),
        os.environ.get("GITHUB_REPOSITORY", ""),
    )
    report_file = Path(os.environ.get("RUNNER_TEMP", ".")) / (
        f"spec-no-loadable-report-{os.environ.get('GITHUB_RUN_ID', '0')}.md"
    )
    try:
        report_file.write_text(report, encoding="utf-8")
        _write_output("report_file", str(report_file))
    except OSError as exc:
        print(f"::error::failed to write {report_file}: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
