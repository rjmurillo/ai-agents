#!/usr/bin/env python3
"""Extract spec references from a PR title and body.

Replaces the bash 'Extract Spec References' block in
ai-spec-validation.yml (ADR-006).

ENV:
  PR_TITLE_INPUT      - PR title (may be empty; falls back to gh CLI)
  PR_BODY_INPUT       - PR body (may be empty; falls back to gh CLI)
  PR_NUMBER           - pull request number (used for gh CLI fallback)
  GITHUB_REPOSITORY   - owner/repo
  RUNNER_TEMP         - temp directory (default ".")
  GITHUB_OUTPUT       - path to step output file

Outputs:
  spec_refs          - space-delimited spec references (REQ-NNN, file paths)
  issue_refs         - space-delimited issue numbers / cross-repo refs
  incremental_scope  - incremental scope declaration from PR title
  has_specs          - "true" if any references were found, else "false"

EXIT CODES (ADR-035):
  0 - extraction complete
  3 - external PR metadata lookup failed
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


class SpecReferenceError(RuntimeError):
    """Raised when the script cannot enumerate PR text."""


def write_github_output(key: str, value: str) -> None:
    """Append key=value to GITHUB_OUTPUT; fall back to stdout."""
    path = os.environ.get("GITHUB_OUTPUT", "")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")
    else:
        print(f"{key}={value}")


def _gh_pr_field(pr_number: str, repository: str, field: str) -> str:
    """Fetch one field from a PR via gh CLI."""
    result = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            pr_number,
            "--repo",
            repository,
            "--json",
            field,
            "-q",
            f".{field}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() if result.stderr else "no stderr"
        raise SpecReferenceError(f"gh pr view failed for {field} (PR {pr_number} in {repository}): {detail}")
    return result.stdout.strip()


def _extract_spec_refs(combined: str) -> str:
    """Return space-delimited REQ/DESIGN/TASK IDs and spec file paths."""
    parts: list[str] = []

    req_ids = re.findall(r"(?:REQ|DESIGN|TASK)-\d+", combined)
    if req_ids:
        parts.extend(sorted(set(req_ids)))

    spec_paths = re.findall(r"\.agents/(?:specs|planning)/\S+\.md", combined)
    if spec_paths:
        parts.extend(sorted(set(spec_paths)))

    return " ".join(parts)


def _extract_issue_refs(combined: str) -> str:
    """Return space-delimited issue refs (numeric or owner/repo#N)."""
    raw = re.findall(
        r"(?:Closes|Fixes|Resolves|Implements)\s+((?:[A-Za-z0-9_-]+/[A-Za-z0-9_-]+)?#\d+)",
        combined,
    )
    results: list[str] = []
    for ref in sorted(set(raw)):
        if ref.startswith("#"):
            results.append(ref[1:])  # strip leading #
        else:
            results.append(ref)
    return " ".join(results)


def _extract_incremental_scope(pr_title: str) -> str:
    """Call extract_incremental_scope.py and return its output."""
    result = subprocess.run(
        [sys.executable, ".github/scripts/extract_incremental_scope.py", pr_title],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def run(_argv: list[str] | None = None) -> int:
    """Extract spec references and set outputs."""
    pr_title = os.environ.get("PR_TITLE_INPUT", "")
    pr_body = os.environ.get("PR_BODY_INPUT", "")
    pr_number = os.environ.get("PR_NUMBER", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    runner_temp = os.environ.get("RUNNER_TEMP", ".")

    try:
        if not pr_title and not pr_body and pr_number:
            pr_title = _gh_pr_field(pr_number, repository, "title")
            pr_body = _gh_pr_field(pr_number, repository, "body")
    except SpecReferenceError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 3

    # Write to temp files (keeps contents safe from shell injection)
    title_file = Path(runner_temp) / f"pr-title-{os.environ.get('GITHUB_RUN_ID', '0')}.txt"
    body_file = Path(runner_temp) / f"pr-body-{os.environ.get('GITHUB_RUN_ID', '0')}.txt"
    title_file.write_text(pr_title + "\n", encoding="utf-8")
    body_file.write_text(pr_body + "\n", encoding="utf-8")

    combined = f"{pr_body} {pr_title}"
    spec_refs = _extract_spec_refs(combined)
    issue_refs = _extract_issue_refs(combined)
    incremental_scope = _extract_incremental_scope(pr_title)

    write_github_output("spec_refs", spec_refs)
    write_github_output("issue_refs", issue_refs)
    write_github_output("incremental_scope", incremental_scope)

    if not spec_refs and not issue_refs:
        print("No spec references found in PR")
        write_github_output("has_specs", "false")
    else:
        if spec_refs:
            print(f"Found spec references: {spec_refs}")
        if issue_refs:
            print(f"Found issue references: {issue_refs}")
        write_github_output("has_specs", "true")

    # Clean up temp files
    title_file.unlink(missing_ok=True)
    body_file.unlink(missing_ok=True)

    return 0


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
