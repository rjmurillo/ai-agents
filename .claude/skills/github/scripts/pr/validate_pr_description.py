#!/usr/bin/env python3
"""Validate a PR description against GitHub standards and template compliance.

Checks:
  - Conventional commit title format
  - GitHub issue linking keywords (Closes, Fixes, Resolves)
  - PR template section completion

Exit codes follow ADR-035:
    0 - All validations pass or warnings only (default mode)
    1 - Validation failures (when --fail-on-violation specified)
    2 - Usage/environment error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

_CONVENTIONAL_COMMIT_PATTERN = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert)"
    r"(\(.+\))?!?: .+"
)

_ISSUE_KEYWORD_PATTERN = re.compile(
    r"(?i)(close[sd]?|fix(?:es|ed)?|resolve[sd]?)\s+([\w-]+/[\w-]+)?#\d+"
)


def validate_conventional_commit(title: str) -> dict:
    """Check title follows conventional commit format."""
    if _CONVENTIONAL_COMMIT_PATTERN.match(title):
        return {"Status": "PASS", "Message": "Title follows conventional commit format"}
    return {
        "Status": "FAIL",
        "Message": (
            "Title must follow conventional commit format: type(scope): description. "
            "Valid types: feat, fix, docs, style, refactor, perf, test, chore, ci, build, revert"
        ),
    }


def validate_issue_keywords(text: str) -> dict:
    """Check for GitHub issue linking keywords."""
    keywords = [m.group() for m in _ISSUE_KEYWORD_PATTERN.finditer(text)]
    if keywords:
        return {
            "Status": "PASS",
            "Message": f"Found {len(keywords)} issue linking keyword(s)",
            "Keywords": keywords,
        }
    return {
        "Status": "WARN",
        "Message": (
            "No GitHub issue linking keywords found (Closes, Fixes, Resolves). "
            "Consider adding: Closes #<issue-number>"
        ),
        "Keywords": [],
    }


def validate_template_compliance(body: str) -> dict:
    """Check PR template section completion.

    Note: Patterns are coupled to .github/PULL_REQUEST_TEMPLATE.md format.
    Update patterns here if the template structure changes.
    """
    sections: dict[str, str] = {}

    # Summary section
    has_summary = bool(
        re.search(r"(?m)^##\s+Summary", body)
        and re.search(r"(?ms)##\s+Summary\s*\n+(?!##)(.+)", body)
    )
    sections["Summary"] = "PASS" if has_summary else "WARN"

    # Specification References
    has_spec_refs = bool(
        re.search(r"(?m)\|\s*\*?\*?Issue\*?\*?\s*\|", body)
        or re.search(r"(?m)\|\s*\*?\*?Spec\*?\*?\s*\|", body)
    )
    sections["SpecificationReferences"] = "PASS" if has_spec_refs else "WARN"

    # Type of Change (at least one [x] checkbox)
    has_type = bool(re.search(r"\[x\]", body, re.IGNORECASE))
    sections["TypeOfChange"] = "PASS" if has_type else "WARN"

    # Changes section
    has_changes = bool(
        re.search(r"(?m)^##\s+Changes", body)
        and re.search(r"(?ms)##\s+Changes\s*\n+(?!##)\s*[-*]", body)
    )
    sections["Changes"] = "PASS" if has_changes else "WARN"

    pass_count = sum(1 for v in sections.values() if v == "PASS")
    total = len(sections)
    overall = "PASS" if pass_count == total else "WARN"

    return {
        "Status": overall,
        "Message": f"Template compliance: {pass_count}/{total} sections complete",
        "Sections": sections,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Validate PR description against GitHub standards")
    p.add_argument("--title", required=True, help="PR title to validate")
    p.add_argument("--body", default="", help="PR description body text")
    p.add_argument("--body-file", default="", help="Path to file containing PR body")
    p.add_argument(
        "--fail-on-violation",
        action="store_true",
        help="Exit with code 1 on any validation failure",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Resolve body content
    body = args.body
    if args.body_file and not body:
        path = Path(args.body_file)
        if not path.exists():
            print(f"Body file not found: {args.body_file}", file=sys.stderr)
            return 2
        body = path.read_text(encoding="utf-8")

    full_text = f"{args.title}\n{body}"

    # Run validations
    conv = validate_conventional_commit(args.title)
    keywords = validate_issue_keywords(full_text)
    template = validate_template_compliance(body)

    # Collect warnings/errors
    warnings: list[str] = []
    errors: list[str] = []

    if conv["Status"] == "FAIL":
        errors.append(conv["Message"])
    if keywords["Status"] == "WARN":
        warnings.append(keywords["Message"])
    if template["Status"] == "WARN":
        warn_sections = [k for k, v in template["Sections"].items() if v == "WARN"]
        if warn_sections:
            warnings.append(f"Incomplete template sections: {', '.join(warn_sections)}")

    success = len(errors) == 0

    result = {
        "Success": success,
        "Validations": {
            "ConventionalCommit": conv,
            "IssueKeywords": keywords,
            "TemplateCompliance": template,
        },
        "Warnings": warnings,
        "Errors": errors,
    }

    # JSON output to stdout
    print(json.dumps(result, indent=2))

    # Human-readable summary to stderr
    print("\nPR Description Validation Results", file=sys.stderr)
    print("=================================", file=sys.stderr)
    print(f"Conventional Commit: {conv['Status']} - {conv['Message']}", file=sys.stderr)
    print(f"Issue Keywords:      {keywords['Status']} - {keywords['Message']}", file=sys.stderr)
    print(f"Template Compliance: {template['Status']} - {template['Message']}", file=sys.stderr)

    if warnings:
        print("\nWarnings:", file=sys.stderr)
        for w in warnings:
            print(f"  ⚠ {w}", file=sys.stderr)

    if errors:
        print("\nErrors:", file=sys.stderr)
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)

    if success:
        print("\n✓ Validation passed", file=sys.stderr)

    has_issues = not success or (args.fail_on_violation and warnings)
    if has_issues and args.fail_on_violation:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
