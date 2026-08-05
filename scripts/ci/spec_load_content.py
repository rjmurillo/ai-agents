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
  0 - content loaded
  2 - referenced spec file could not be loaded
  3 - referenced GitHub issue could not be loaded
"""

from __future__ import annotations

import glob as glob_module
import os
import subprocess
import sys
from pathlib import Path


class SpecContentExternalError(RuntimeError):
    """Raised when external issue content cannot be loaded."""


class SpecContentConfigError(RuntimeError):
    """Raised when referenced local spec content cannot be loaded."""


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
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() if result.stderr else "no stderr"
        raise SpecContentExternalError(f"gh issue view failed for {repo}#{num}: {detail}")
    return result.stdout.strip()


def _read_spec_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecContentConfigError(f"could not read {path}: {exc}") from exc


def _spec_part_for_ref(ref: str) -> tuple[str | None, str | None]:
    if ref.endswith(".md"):
        path = Path(ref)
        if not path.is_file():
            return None, ref
        return f"## Spec: {ref}\n\n{_read_spec_file(path)}", None

    matches = glob_module.glob(f".agents/specs/*{ref}*")
    if not matches:
        return None, ref
    matched_path = matches[0]
    return f"## Spec: {matched_path}\n\n{_read_spec_file(Path(matched_path))}", None


def _load_spec_parts(spec_refs: list[str]) -> tuple[list[str], list[str]]:
    parts: list[str] = []
    missing_specs: list[str] = []
    for ref in spec_refs:
        part, missing = _spec_part_for_ref(ref)
        if part:
            parts.append(part)
        if missing:
            missing_specs.append(missing)
    return parts, missing_specs


def run(_argv: list[str] | None = None) -> int:
    """Load spec content and write to temp file."""
    spec_refs_raw = os.environ.get("SPEC_REFS", "")
    issue_refs_raw = os.environ.get("ISSUE_REFS", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    runner_temp = os.environ.get("RUNNER_TEMP", ".")

    spec_refs = spec_refs_raw.split() if spec_refs_raw.strip() else []
    issue_refs = issue_refs_raw.split() if issue_refs_raw.strip() else []

    try:
        parts, missing_specs = _load_spec_parts(spec_refs)
    except SpecContentConfigError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2

    if missing_specs:
        print(
            f"::error::Could not load referenced spec content: {', '.join(missing_specs)}",
            file=sys.stderr,
        )
        return 2

    for issue in issue_refs:
        try:
            body = _gh_issue_body(issue, repository)
        except SpecContentExternalError as exc:
            print(f"::error::{exc}", file=sys.stderr)
            return 3
        if body:
            display = f"#{issue}" if "/" not in issue else issue
            parts.append(f"## Issue {display}\n\n{body}")

    spec_content = "\n\n".join(parts)
    if not spec_content and (spec_refs or issue_refs):
        print("::error::Referenced specs or issues produced no content", file=sys.stderr)
        return 2
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
