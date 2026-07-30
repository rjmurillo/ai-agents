#!/usr/bin/env python3
"""Load spec content from files and linked GitHub issues.

Replaces the bash 'Load Spec Content' block in
ai-spec-validation.yml (ADR-006).

ENV:
  SPEC_REFS         - space-delimited spec references (REQ-NNN, file paths)
  ISSUE_REFS        - space-delimited issue refs (numeric or owner/repo#N)
  GITHUB_REPOSITORY - owner/repo (used for simple numeric issue refs)
  RUNNER_TEMP       - temp directory (default ".")
  GITHUB_OUTPUT     - path to step output file

Outputs:
  spec_file - absolute path to the spec content markdown file

EXIT CODES (ADR-035):
  0 - content loaded (or no content found; still 0)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def write_github_output(key: str, value: str) -> None:
    """Append key=value to GITHUB_OUTPUT; fall back to stdout."""
    path = os.environ.get("GITHUB_OUTPUT", "")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")
    else:
        print(f"{key}={value}")


def _gh_issue_body(issue_ref: str, default_repo: str) -> str:
    """Fetch title + body for an issue ref."""
    if "/" in issue_ref and "#" in issue_ref:
        repo, num = issue_ref.rsplit("#", 1)
    else:
        repo = default_repo
        num = issue_ref

    result = subprocess.run(
        [
            "gh",
            "issue",
            "view",
            num,
            "--repo",
            repo,
            "--json",
            "title,body",
            "-q",
            '.title + "\n\n" + .body',
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def run(argv: list[str] | None = None) -> int:  # noqa: ARG001
    """Load spec content and write to temp file."""
    spec_refs_raw = os.environ.get("SPEC_REFS", "")
    issue_refs_raw = os.environ.get("ISSUE_REFS", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    runner_temp = os.environ.get("RUNNER_TEMP", ".")

    spec_refs = spec_refs_raw.split() if spec_refs_raw.strip() else []
    issue_refs = issue_refs_raw.split() if issue_refs_raw.strip() else []

    parts: list[str] = []

    for ref in spec_refs:
        if ref.endswith(".md"):
            p = Path(ref)
            if p.is_file():
                parts.append(f"## Spec: {ref}\n\n{p.read_text(encoding='utf-8')}")
        else:
            # Search for spec file by ID
            import glob as glob_module

            matches = glob_module.glob(f".agents/specs/*{ref}*")
            if matches:
                matched_path = matches[0]
                parts.append(
                    f"## Spec: {matched_path}\n\n{Path(matched_path).read_text(encoding='utf-8')}"
                )

    for issue in issue_refs:
        body = _gh_issue_body(issue, repository)
        if body:
            display = f"#{issue}" if "/" not in issue else issue
            parts.append(f"## Issue {display}\n\n{body}")

    spec_content = "\n\n".join(parts)
    if not spec_content:
        print("Warning: Could not load any spec content")
        spec_content = f"No spec content found for references: {spec_refs_raw} {issue_refs_raw}"

    spec_file = Path(runner_temp) / f"spec-content-{os.environ.get('GITHUB_RUN_ID', '0')}.md"
    spec_file.write_text(spec_content, encoding="utf-8")
    write_github_output("spec_file", str(spec_file))

    return 0


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
