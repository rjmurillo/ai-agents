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
  3 - a GitHub issue lookup failed for a reason other than the reference
      not being an issue
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

# Internal classification, never a process exit code: the reference resolved to
# something that is not an issue in this repository, most often a pull request
# number. `.claude/rules/universal.md` MUST 2 linkage legitimately points at
# pull requests (PR #5609 carries one, PR #5630 another), so this case is
# skippable. A genuine gh launch failure or API outage is not: it leaves the
# judge reasoning about a subset of the requirements while the gate reports
# success, which is the silent-failure class `ci-scripts.md` SHOULD 4 warns a
# repair like this one tends to introduce.
NOT_AN_ISSUE = -1

# Narrow on purpose, and it fails closed. Any stderr this does not recognize is
# treated as an external failure, so an unrecognized benign message costs a red
# check that names the reference, while no unrecognized outage can ever be
# mistaken for a skippable reference. The exact wording is GitHub's GraphQL
# error for `repository.issue(number:)` against a non-issue; it could not be
# re-verified from this environment, and that is precisely why the default is
# to fail rather than to skip.
_NOT_AN_ISSUE_SIGNALS = ("could not resolve to an issue",)


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

    try:
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
    except OSError as exc:
        print(f"::error::failed to launch gh for issue {issue_ref}: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL, ""
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if any(signal in stderr.casefold() for signal in _NOT_AN_ISSUE_SIGNALS):
            print(
                f"::warning::{issue_ref} is not an issue in this repository: {stderr}",
                file=sys.stderr,
            )
            return NOT_AN_ISSUE, ""
        print(
            f"::error::gh issue view failed for {issue_ref}: {stderr}",
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


def _load_spec_refs(spec_refs: list[str]) -> tuple[int, list[str]]:
    """Load local spec references."""
    parts: list[str] = []
    for ref in spec_refs:
        path = Path(ref) if ref.endswith(".md") else _find_spec_by_id(ref)
        if path is None or not path.is_file():
            label = "spec file" if ref.endswith(".md") else "spec ID"
            print(f"::error::{label} not found: {ref}", file=sys.stderr)
            return EXIT_CONFIG, []
        exit_code, content = _read_spec(path, ref)
        if exit_code != EXIT_OK:
            return exit_code, []
        parts.append(f"## Spec: {path}\n\n{content}")
    return EXIT_OK, parts


def _load_issue_refs(issue_refs: list[str], repository: str) -> tuple[int, list[str]]:
    """Load linked issue references, skipping those that are not issues at all.

    Returns the first genuine external failure alongside whatever loaded. The
    two failure kinds are deliberately not merged. A reference that is simply
    not an issue (a pull request number) is skipped, because
    `spec_extract_refs.py` now extracts every non-closing linkage in the body
    and `.claude/rules/universal.md` MUST 2 linkage legitimately points at pull
    requests. A gh launch failure or API outage is propagated, because skipping
    it would let the judge run against a subset of the requirements while the
    required check reported success.
    """
    parts: list[str] = []
    external_failure = EXIT_OK
    for issue in issue_refs:
        exit_code, body = _gh_issue_body(issue, repository)
        if exit_code == NOT_AN_ISSUE:
            continue
        if exit_code != EXIT_OK:
            if external_failure == EXIT_OK:
                external_failure = exit_code
            continue
        if body:
            display = f"#{issue}" if "/" not in issue else issue
            parts.append(f"## Issue {display}\n\n{body}")
    return external_failure, parts


def run(_argv: list[str] | None = None) -> int:
    """Load spec content and write to temp file."""
    spec_refs_raw = os.environ.get("SPEC_REFS", "")
    issue_refs_raw = os.environ.get("ISSUE_REFS", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    runner_temp = os.environ.get("RUNNER_TEMP", ".")

    spec_refs = spec_refs_raw.split() if spec_refs_raw.strip() else []
    issue_refs = issue_refs_raw.split() if issue_refs_raw.strip() else []

    exit_code, parts = _load_spec_refs(spec_refs)
    if exit_code != EXIT_OK:
        return exit_code
    external_failure, issue_parts = _load_issue_refs(issue_refs, repository)
    parts.extend(issue_parts)

    # Fail closed on a genuine lookup failure even when other content loaded.
    # Proceeding would hand the judge a subset of the requirements and let the
    # required check pass against context it never saw.
    if external_failure != EXIT_OK:
        print(
            "::error::an issue lookup failed, so the spec context would be "
            f"incomplete: {issue_refs_raw}",
            file=sys.stderr,
        )
        return external_failure

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
