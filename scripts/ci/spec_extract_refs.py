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
  3 - GitHub or incremental-scope subprocess failed
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_EXTERNAL = 3

# GitHub resolves closing keywords case-insensitively, in every tense, and
# tolerates a colon before the reference. This pattern also accepts the
# non-closing linkage this repository mandates: `.claude/rules/universal.md`
# MUST 2 offers `Refs #<n>`, and MUST 3 tells authors to downgrade an
# unsupported `Fixes` claim to `Refs`. While `Refs` was absent here, following
# that rule set `has_specs=false`, every judging step in
# `.github/workflows/ai-spec-validation.yml` skipped on its
# `has_specs == 'true'` guard, and the required `Validate Spec Coverage` check
# reported success having evaluated nothing (issue #5489). The missing GitHub
# spellings (`closed`, `fixed`, `resolved`, `Closes: #10`, `owner/repo.name#10`)
# opened the same fail-open (issue #5620). `AB#` work-item tokens are issue
# #5621 and are out of scope here.
#
# `See #<n>` is deliberately excluded. It reads as ordinary prose and in this
# repository most often points at a pull request rather than an issue, which
# `gh issue view` cannot resolve.
#
# The leading `\b` is load-bearing: without it `prefixes #42` matched on
# `fixes`. The trailing guard and the `[1-9][0-9]*` number are load-bearing for
# the same reason in the other direction: `#\d+` with no guard read
# `Refs #4054garbage` as issue 4054 and loaded an unrelated issue into the
# judge's context, and it accepted `#0` and `#007`, neither of which can resolve.
# Ordinary sentence punctuation after a reference still matches, because the
# guard excludes only identifier characters.
_ISSUE_REF_PATTERN = re.compile(
    r"\b(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?|implement(?:s|ed)?|refs?|part\s+of)"
    r"(?:\s*:\s*|\s+)"
    r"((?:[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*)?#[1-9][0-9]*)"
    r"(?![0-9A-Za-z_])",
    re.IGNORECASE,
)

# GitHub does not link an issue from a keyword inside a code span or a fenced
# block, so neither may arm this gate. Measured on PR #5648's own run: the body
# discussed the bug using `Closes: #10`, `Refs #5600` and `Refs #5623` as
# examples inside backticks, and the widened parser reported
# `ISSUE_REFS: 10 5489 5600 5620 5621 5623`. Three of those six are prose, two
# of them pull request numbers, and the loader fed all of them to the judge as
# if they were this PR's requirements. `validate_pr_description.py` already
# treats a closing keyword in a code span as not-a-link, for the same reason.
#
# Deliberately not applied to `_extract_spec_refs`: `.github/PULL_REQUEST_TEMPLATE.md`
# writes spec paths in backticks (`| **Spec** | `.agents/planning/...` |`), so
# masking there would disarm the gate on the template's own convention. The
# asymmetry is real, because a code span suppresses GitHub's issue linking and
# says nothing about a file path.
# Masking is a scanner rather than a regex because the delimiters carry length
# semantics a regex backreference gets wrong in both directions, and both
# directions were live defects found in review of PR #5648:
#
#   1. A fence closes on a run of the same character at least as long as the
#      opener. `\1` demanded an exact-length match, so an opener of three
#      backticks closed by four never matched, the block ran to `\Z`, and every
#      reference after it in the body was masked. That is the same
#      `has_specs=false` fail-open this file exists to close, reintroduced.
#   2. A code span closes on a backtick run of exactly the opener's length and
#      may contain shorter runs. ``a ` b`` ended the span at the inner single
#      backtick, exposing the rest of the span as prose.
#
# Masked characters become NUL rather than a space so the keyword-to-reference
# separator (`\s`) cannot bridge across removed content: `Fixes `x` #12` must
# not become a link that the unmasked body never had.
_MASK = "\x00"
_FENCE_OPENER = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


def _mask_fenced_blocks(text: str) -> str:
    """Blank fenced code blocks, honoring the same-character, at-least-as-long closer."""
    masked: list[str] = []
    fence_char = ""
    fence_len = 0
    for line in text.split("\n"):
        if not fence_char:
            opener = _FENCE_OPENER.match(line)
            if opener:
                run = opener.group(1)
                fence_char, fence_len = run[0], len(run)
                masked.append(_MASK)
                continue
            masked.append(line)
            continue
        closer = line.strip()
        if closer and set(closer) == {fence_char} and len(closer) >= fence_len:
            fence_char, fence_len = "", 0
        masked.append(_MASK)
    # An unclosed fence stays masked through the end of the body, which is what
    # a Markdown renderer does with it too.
    return "\n".join(masked)


def _mask_inline_code(text: str) -> str:
    """Blank inline code spans, closing each on a backtick run of the opener's length."""
    masked: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] != "`":
            masked.append(text[index])
            index += 1
            continue
        after_opener = index
        while after_opener < length and text[after_opener] == "`":
            after_opener += 1
        opener_len = after_opener - index
        close_at = _find_closing_run(text, after_opener, opener_len)
        if close_at < 0:
            # No closer of the right length: this is literal text, not a span.
            masked.append("`" * opener_len)
            index = after_opener
            continue
        masked.append(_MASK * (close_at + opener_len - index))
        index = close_at + opener_len
    return "".join(masked)


def _find_closing_run(text: str, start: int, run_len: int) -> int:
    """Return the index of the next backtick run of exactly run_len, or -1."""
    index = start
    length = len(text)
    while index < length:
        if text[index] != "`":
            index += 1
            continue
        run_end = index
        while run_end < length and text[run_end] == "`":
            run_end += 1
        if run_end - index == run_len:
            return index
        index = run_end
    return -1


def _strip_code(text: str) -> str:
    """Blank out fenced blocks and inline code spans, keeping the rest intact."""
    return _mask_inline_code(_mask_fenced_blocks(text))


def write_github_output(key: str, value: str) -> None:
    """Append key=value to GITHUB_OUTPUT; fall back to stdout."""
    path = os.environ.get("GITHUB_OUTPUT", "")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")
    else:
        print(f"{key}={value}")


def _gh_pr_field(pr_number: str, repository: str, field: str) -> tuple[int, str]:
    """Fetch one field from a PR via gh CLI."""
    try:
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
    except OSError as exc:
        print(f"::error::failed to launch gh while reading {field}: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL, ""
    if result.returncode != 0:
        print(
            f"::error::gh pr view failed while reading {field}: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return EXIT_EXTERNAL, ""
    return EXIT_OK, result.stdout.strip()


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
    """Return space-delimited issue refs (numeric or owner/repo#N).

    Accepts every GitHub closing keyword plus non-closing linkage, ignoring
    anything inside a code span or fenced block. See `_ISSUE_REF_PATTERN` and
    `_strip_code` for why each of those is a gate defect.
    """
    raw = [match.group(1) for match in _ISSUE_REF_PATTERN.finditer(_strip_code(combined))]
    results: list[str] = []
    for ref in sorted(set(raw)):
        if ref.startswith("#"):
            results.append(ref[1:])  # strip leading #
        else:
            results.append(ref)
    return " ".join(results)


def _extract_incremental_scope(pr_title: str) -> tuple[int, str]:
    """Call extract_incremental_scope.py and return its output."""
    try:
        result = subprocess.run(
            [sys.executable, ".github/scripts/extract_incremental_scope.py", pr_title],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        print(f"::error::failed to launch incremental scope parser: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL, ""
    if result.returncode != 0:
        print(
            f"::error::incremental scope extraction failed: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return EXIT_EXTERNAL, ""
    return EXIT_OK, result.stdout.strip()


def run(_argv: list[str] | None = None) -> int:
    """Extract spec references and set outputs."""
    pr_title = os.environ.get("PR_TITLE_INPUT", "")
    pr_body = os.environ.get("PR_BODY_INPUT", "")
    pr_number = os.environ.get("PR_NUMBER", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    runner_temp = os.environ.get("RUNNER_TEMP", ".")

    if not pr_title and not pr_body and pr_number:
        exit_code, pr_title = _gh_pr_field(pr_number, repository, "title")
        if exit_code != EXIT_OK:
            return exit_code
        exit_code, pr_body = _gh_pr_field(pr_number, repository, "body")
        if exit_code != EXIT_OK:
            return exit_code

    # Write to temp files (keeps contents safe from shell injection)
    title_file = Path(runner_temp) / f"pr-title-{os.environ.get('GITHUB_RUN_ID', '0')}.txt"
    body_file = Path(runner_temp) / f"pr-body-{os.environ.get('GITHUB_RUN_ID', '0')}.txt"
    title_file.write_text(pr_title + "\n", encoding="utf-8")
    body_file.write_text(pr_body + "\n", encoding="utf-8")

    combined = f"{pr_body} {pr_title}"
    spec_refs = _extract_spec_refs(combined)
    issue_refs = _extract_issue_refs(combined)
    exit_code, incremental_scope = _extract_incremental_scope(pr_title)
    if exit_code != EXIT_OK:
        title_file.unlink(missing_ok=True)
        body_file.unlink(missing_ok=True)
        return exit_code

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

    return EXIT_OK


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
