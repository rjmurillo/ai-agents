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
  2 - referenced spec content is missing
  3 - GitHub issue lookup failed
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3


def write_github_output(key: str, value: str) -> None:
    """Append key=value to GITHUB_OUTPUT; fall back to stdout."""
    path = os.environ.get("GITHUB_OUTPUT", "")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")
    else:
        print(f"{key}={value}")


def _gh_issue_body(issue_ref: str, default_repo: str) -> tuple[int, str]:
    """Fetch title and body for an issue ref."""
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
        print(
            f"::error::gh issue view failed for {issue_ref}: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return EXIT_EXTERNAL, ""
    return EXIT_OK, result.stdout.strip()


def _find_spec_by_id(ref: str) -> Path | None:
    """Find a spec ID in the recursive specs tree."""
    specs_root = Path(".agents/specs")
    if not specs_root.is_dir():
        return None
    return next(
        (path for path in sorted(specs_root.rglob(f"*{ref}*")) if path.is_file()),
        None,
    )


def _read_spec(path: Path, display: str) -> tuple[int, str]:
    """Read nonempty spec content."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"::error::failed to read spec {display}: {exc}", file=sys.stderr)
        return EXIT_CONFIG, ""
    if not content.strip():
        print(f"::error::spec content is empty: {display}", file=sys.stderr)
        return EXIT_CONFIG, ""
    return EXIT_OK, content


def run(_argv: list[str] | None = None) -> int:
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
            if not p.is_file():
                print(f"::error::spec file not found: {ref}", file=sys.stderr)
                return EXIT_CONFIG
            exit_code, content = _read_spec(p, ref)
            if exit_code != EXIT_OK:
                return exit_code
            parts.append(f"## Spec: {ref}\n\n{content}")
        else:
            matched_path = _find_spec_by_id(ref)
            if matched_path is None:
                print(f"::error::spec ID not found: {ref}", file=sys.stderr)
                return EXIT_CONFIG
            exit_code, content = _read_spec(matched_path, str(matched_path))
            if exit_code != EXIT_OK:
                return exit_code
            parts.append(f"## Spec: {matched_path}\n\n{content}")

    for issue in issue_refs:
        exit_code, body = _gh_issue_body(issue, repository)
        if exit_code != EXIT_OK:
            return exit_code
        if body:
            display = f"#{issue}" if "/" not in issue else issue
            parts.append(f"## Issue {display}\n\n{body}")

    spec_content = "\n\n".join(parts)
    if not spec_content:
        print(
            f"::error::no spec content found for references: {spec_refs_raw} {issue_refs_raw}",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    spec_file = Path(runner_temp) / f"spec-content-{os.environ.get('GITHUB_RUN_ID', '0')}.md"
    spec_file.write_text(spec_content, encoding="utf-8")
    write_github_output("spec_file", str(spec_file))

    return EXIT_OK


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
