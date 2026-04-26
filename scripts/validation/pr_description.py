#!/usr/bin/env python3
"""Validate PR description matches actual code changes.

BLOCKING validation that prevents PR description vs diff mismatches.
Detects when PR description claims files were changed that are not in the diff,
or when major changes are not mentioned in the description.

Exit codes follow ADR-035:
    0 - Success (validation passed, or warnings only)
    1 - Logic error (CRITICAL issues found, CI mode only)
    2 - Config error (missing dependency, failed to fetch PR data)
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.github_core.api import RepoInfo  # noqa: E402

# File extensions considered significant for mention checking
SIGNIFICANT_EXTENSIONS: frozenset[str] = frozenset(
    {".ps1", ".cs", ".ts", ".js", ".py", ".yml", ".yaml"}
)

# Directories whose files are flagged when changed but not mentioned
SIGNIFICANT_DIRS_PATTERN: re.Pattern[str] = re.compile(
    r"^(\.github|scripts|src|\.agents)"
)

# File extension pattern for extracting file references from description
_EXT_GROUP = r"ps1|md|yml|yaml|json|cs|ts|js|py|sh|bash"

# Default label name that bypasses CRITICAL description-validation failures.
# Mirrors the existing 'commit-limit-bypass' pattern in pr-validation.yml.
DEFAULT_BYPASS_LABEL = "description-validation-bypass"

# Section names whose file mentions are contextual references, not change
# claims. Matches `## Heading` (h2) at the start of a line, case-insensitive.
# Each entry is a regex fragment for the heading text only.
_CONTEXTUAL_SECTION_NAMES: tuple[str, ...] = (
    r"Test\s*Plan",
    r"Design\s*Decisions?",
    r"Related",
    r"References?",
    r"See\s*Also",
    r"Notes?",
    r"Background",
    r"Inspired\s*By",
    r"Pattern\s*From",
    r"Prior\s*Art",
)

# Patterns to extract file paths from PR description text
# List item pattern accepts both unwrapped paths (`- path/file.ext`) and
# backtick-wrapped paths (`- \`path/file.ext\`: description`). The autonomous
# PR template uses backtick-wrapped paths; using [^\s`]+ stops cleanly at the
# trailing backtick instead of relying on normalize_path to strip it.
FILE_MENTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(rf"`([^`]+\.({_EXT_GROUP}))`"),  # inline code
    re.compile(rf"\*\*([^*]+\.({_EXT_GROUP}))\*\*"),  # bold
    re.compile(
        rf"^\s*[-*+]\s+`?([^\s`]+\.({_EXT_GROUP}))`?",
        re.MULTILINE,
    ),  # list items (optionally backtick-wrapped)
    re.compile(rf"\[([^\]]+\.({_EXT_GROUP}))\]"),  # markdown links
]


@dataclass
class Issue:
    """A validation issue found during PR description checking."""

    severity: str
    issue_type: str
    file: str
    message: str


def get_repo_info() -> RepoInfo:
    """Parse owner/repo from git remote origin URL.

    Returns RepoInfo with owner and repo.
    Raises RuntimeError on failure.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise RuntimeError("Could not determine git remote origin") from exc

    if result.returncode != 0:
        raise RuntimeError("Could not determine git remote origin")

    remote_url = result.stdout.strip()
    match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", remote_url)
    if not match:
        raise RuntimeError(
            f"Could not parse GitHub owner/repo from remote URL: {remote_url}"
        )

    return RepoInfo(owner=match.group(1), repo=match.group(2))


def fetch_pr_data(
    pr_number: int, owner: str, repo: str
) -> dict[str, Any]:
    """Fetch PR data (title, body, files, labels) via gh CLI.

    Returns parsed JSON dict. Raises RuntimeError on failure.
    """
    try:
        result = subprocess.run(
            [
                "gh", "pr", "view", str(pr_number),
                "--json", "title,body,files,labels",
                "--repo", f"{owner}/{repo}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "gh CLI not found. Install: https://cli.github.com/"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Timed out fetching PR #{pr_number}") from exc

    if result.returncode != 0:
        raise RuntimeError(f"Failed to fetch PR #{pr_number}")

    data: dict[str, Any] = json.loads(result.stdout)
    return data


def normalize_path(path: str) -> str:
    """Normalize a file path for comparison.

    Strips whitespace, markdown bold markers, and normalizes slashes.
    """
    path = path.strip()
    # Strip markdown formatting that may be captured by list item pattern
    path = path.strip("*")
    path = path.strip("`")
    path = path.replace("\\", "/")
    if path.startswith("./"):
        path = path[2:]
    return path


def _strip_informational_sections(description: str) -> str:
    """Remove bot-generated informational sections before file extraction.

    Strips <details> blocks and "Detected Package Files" sections that list
    files for informational purposes (e.g. Renovate onboarding PRs) rather
    than claiming those files were changed.

    Also masks fenced code blocks before any heading-based stripping so a
    sample heading inside a fenced ```markdown block does not cause the
    contextual-section regex to over-strip across the real document
    structure.
    """
    # Mask fenced code blocks (```...```) so headings or filenames inside
    # samples do not interact with the contextual-section regex below. Without
    # this, an AI-generated description containing `## Design Decisions`
    # inside a markdown sample would over-strip everything up to the next
    # real `^##` heading, exposing a phantom `## Changes` block from inside
    # the fence as an apparent change claim.
    text = re.sub(r"```.*?```", "<CODE_BLOCK>", description, flags=re.DOTALL)
    # Strip <details>...</details> blocks (used by Renovate, Dependabot, etc.)
    text = re.sub(r"<details>.*?</details>", "", text, flags=re.DOTALL)
    # Strip "Detected Package Files" section up to the next heading or <hr>
    text = re.sub(
        r"###\s*Detected Package Files.*?(?=^###|\n---|\Z)",
        "",
        text,
        flags=re.DOTALL | re.MULTILINE,
    )
    # Strip GitHub admonition blockquote blocks (> [!WARNING], > [!NOTE], etc.)
    # These contain informational file references, not change claims.
    text = re.sub(
        r"^>\s*\[!(WARNING|NOTE|CAUTION|IMPORTANT|TIP)\].*?(?=\n(?!>)|\Z)",
        "",
        text,
        flags=re.DOTALL | re.MULTILINE,
    )
    # Strip contextual h2 sections (Test Plan, Design Decisions, Related,
    # References, See Also, Notes, Background, Inspired By, Pattern From,
    # Prior Art). Files mentioned in these sections are references or
    # validation targets, not claims that those files were modified by the PR.
    contextual_pattern = (
        r"^##\s*(?:" + "|".join(_CONTEXTUAL_SECTION_NAMES) + r")\b.*?(?=^##|\Z)"
    )
    text = re.sub(
        contextual_pattern,
        "",
        text,
        flags=re.DOTALL | re.MULTILINE | re.IGNORECASE,
    )
    return text


def extract_mentioned_files(description: str) -> list[str]:
    """Extract unique file paths mentioned in PR description text."""
    if not description:
        return []

    cleaned = _strip_informational_sections(description)

    mentioned: list[str] = []
    for pattern in FILE_MENTION_PATTERNS:
        for match in pattern.finditer(cleaned):
            raw = match.group(1)
            # Skip command-like strings (file paths never contain spaces)
            if " " in raw.strip():
                continue
            mentioned.append(normalize_path(raw))

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for path in mentioned:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def file_matches(actual: str, mentioned: str) -> bool:
    """Check if an actual diff path matches a mentioned path.

    Supports exact match, suffix match (e.g. "file.ps1" matches
    "path/to/file.ps1"), and glob patterns (e.g. "src/*.py" matches
    "src/main.py").
    """
    if actual == mentioned:
        return True
    if actual.endswith(f"/{mentioned}"):
        return True
    if "*" in mentioned or "?" in mentioned:
        return fnmatch.fnmatch(actual, mentioned)
    return False


def validate_pr_description(
    pr_files: list[str],
    mentioned_files: list[str],
) -> list[Issue]:
    """Compare mentioned files against actual PR files. Return list of issues."""
    issues: list[Issue] = []

    # Check 1: Files mentioned but not in diff (CRITICAL)
    for mentioned in mentioned_files:
        found = any(file_matches(actual, mentioned) for actual in pr_files)
        if not found:
            issues.append(
                Issue(
                    severity="CRITICAL",
                    issue_type="File mentioned but not in diff",
                    file=mentioned,
                    message=(
                        "Description claims this file was changed, "
                        "but it's not in the PR diff"
                    ),
                )
            )

    # Check 2: Major files changed but not mentioned (WARNING)
    for changed in pr_files:
        ext = os.path.splitext(changed)[1]
        if ext not in SIGNIFICANT_EXTENSIONS:
            continue
        if not SIGNIFICANT_DIRS_PATTERN.match(changed):
            continue

        is_mentioned = any(
            file_matches(changed, mentioned) for mentioned in mentioned_files
        )
        if not is_mentioned:
            issues.append(
                Issue(
                    severity="WARNING",
                    issue_type="Significant file not mentioned",
                    file=changed,
                    message="This file was changed but not mentioned in the description",
                )
            )

    return issues


def print_results(issues: list[Issue], ci: bool) -> int:
    """Print validation results and return exit code."""
    if not issues:
        print("\nPR description matches diff (no mismatches found)")
        return 0

    critical_count = sum(1 for i in issues if i.severity == "CRITICAL")
    warning_count = sum(1 for i in issues if i.severity == "WARNING")

    print(f"\nFound {len(issues)} issue(s):")
    print(f"  CRITICAL: {critical_count}")
    print(f"  WARNING: {warning_count}")
    print()

    for issue in issues:
        print(f"[{issue.severity}] {issue.issue_type}")
        print(f"  File: {issue.file}")
        print(f"  {issue.message}")
        print()

    if critical_count > 0:
        print("CRITICAL issues found. Update PR description to match actual changes.")
        if ci:
            return 1
    elif warning_count > 0:
        print(
            "Warnings found. Consider mentioning significant files in PR description."
        )

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with env var defaults."""
    parser = argparse.ArgumentParser(
        description="Validate PR description matches actual code changes.",
    )
    parser.add_argument(
        "--pr-number",
        type=int,
        required="PR_NUMBER" not in os.environ,
        default=int(os.environ.get("PR_NUMBER", "0")) or None,
        help="PR number to validate (env: PR_NUMBER)",
    )
    parser.add_argument(
        "--owner",
        default=os.environ.get("REPO_OWNER", ""),
        help="Repository owner (env: REPO_OWNER, or inferred from git remote)",
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("REPO_NAME", ""),
        help="Repository name (env: REPO_NAME, or inferred from git remote)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        default=os.environ.get("CI", "").lower() in ("true", "1"),
        help="CI mode: exit non-zero on CRITICAL failures (env: CI)",
    )
    parser.add_argument(
        "--bypass-label",
        default=os.environ.get(
            "DESCRIPTION_VALIDATION_BYPASS_LABEL", DEFAULT_BYPASS_LABEL
        ),
        help=(
            "PR label that suppresses CRITICAL failures in CI mode "
            f"(env: DESCRIPTION_VALIDATION_BYPASS_LABEL, "
            f"default: {DEFAULT_BYPASS_LABEL})"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    owner: str = args.owner
    repo: str = args.repo

    # Resolve owner/repo from git remote if not provided
    if not owner or not repo:
        try:
            repo_info = get_repo_info()
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        if not owner:
            owner = repo_info.owner
        if not repo:
            repo = repo_info.repo

    # Fetch PR data
    print(f"Fetching PR #{args.pr_number} data...")
    try:
        pr_data = fetch_pr_data(args.pr_number, owner, repo)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    # Extract file lists
    pr_files: list[str] = [f["path"] for f in pr_data.get("files", [])]
    description: str = pr_data.get("body", "") or ""

    print(f"PR has {len(pr_files)} changed files")

    mentioned_files = extract_mentioned_files(description)
    print(f"Description mentions {len(mentioned_files)} files")

    # Validate
    issues = validate_pr_description(pr_files, mentioned_files)

    # Honor the bypass label only when CI mode would otherwise fail. The label
    # is the documented escape hatch for false-positive contextual references
    # that the section allowlist does not cover. The issues are still printed
    # for visibility, but the script exits 0 so the workflow's overall_status
    # propagates as PASS.
    pr_labels: list[str] = [
        label.get("name", "")
        for label in (pr_data.get("labels") or [])
        if isinstance(label, dict)
    ]
    has_critical = any(i.severity == "CRITICAL" for i in issues)
    if args.ci and has_critical and args.bypass_label in pr_labels:
        print_results(issues, ci=False)
        print(
            f"\nCRITICAL issues bypassed by '{args.bypass_label}' label. "
            "Exiting 0."
        )
        return 0

    return print_results(issues, ci=args.ci)


if __name__ == "__main__":
    raise SystemExit(main())
