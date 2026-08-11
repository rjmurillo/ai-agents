#!/usr/bin/env python3
"""Validate a PR description against GitHub standards and template compliance.

Checks:
  - Conventional commit title format
  - GitHub issue linking keywords (Closes, Fixes, Resolves, Refs)
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
from typing import Any

# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

_CONVENTIONAL_COMMIT_PATTERN = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert)"
    r"(\(.+\))?!?: .+"
)

_ISSUE_KEYWORD_PATTERN = re.compile(
    r"(?i)\b(close[sd]?|fix(?:es|ed)?|resolve[sd]?|refs?)\s+([\w-]+/[\w-]+)?#\d+"
)


def validate_conventional_commit(title: str) -> dict[str, Any]:
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


def validate_issue_keywords(text: str) -> dict[str, Any]:
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
            "No GitHub issue linking keywords found (Closes, Fixes, Resolves, Refs #N). "
            "Consider adding: Closes #<issue-number> (auto-close on merge) "
            "or Refs #<issue-number> (partial-fix, leaves issue open)"
        ),
        "Keywords": [],
    }


def validate_template_compliance(body: str) -> dict[str, Any]:
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


def _resolve_body(args: argparse.Namespace) -> tuple[str, int | None]:
    """Resolve body text from an argument, file, or stdin."""
    body = args.body
    if not args.body_file or body:
        return body, None
    if args.body_file == "-":
        return sys.stdin.read(), None

    path = Path(args.body_file)
    if not path.exists():
        print(f"Body file not found: {args.body_file}", file=sys.stderr)
        return body, 2
    return path.read_text(encoding="utf-8"), None



def _collect_messages(
    conventional_commit: dict[str, Any],
    issue_keywords: dict[str, Any],
    template_compliance: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Collect validation warnings and errors in display order."""
    warnings: list[str] = []
    errors: list[str] = []

    if conventional_commit["Status"] == "FAIL":
        errors.append(conventional_commit["Message"])
    if issue_keywords["Status"] == "WARN":
        warnings.append(issue_keywords["Message"])
    if template_compliance["Status"] == "WARN":
        warning_sections = [
            name
            for name, status in template_compliance["Sections"].items()
            if status == "WARN"
        ]
        if warning_sections:
            warnings.append(
                f"Incomplete template sections: {', '.join(warning_sections)}"
            )
    return warnings, errors


def _build_result(
    title: str,
    body: str,
    *,
    fail_on_violation: bool,
) -> dict[str, Any]:
    """Run validations and build the JSON result payload."""
    conventional_commit = validate_conventional_commit(title)
    issue_keywords = validate_issue_keywords(f"{title}\n{body}")
    template_compliance = validate_template_compliance(body)
    warnings, errors = _collect_messages(
        conventional_commit,
        issue_keywords,
        template_compliance,
    )

    success = len(errors) == 0
    warnings_are_fatal = bool(fail_on_violation) and len(warnings) > 0
    effective_success = success and not warnings_are_fatal

    return {
        "Success": success,
        "EffectiveSuccess": effective_success,
        "FailOnViolation": bool(fail_on_violation),
        "WarningsAreFatal": warnings_are_fatal,
        "WarningCount": len(warnings),
        "ErrorCount": len(errors),
        "Validations": {
            "ConventionalCommit": conventional_commit,
            "IssueKeywords": issue_keywords,
            "TemplateCompliance": template_compliance,
        },
        "Warnings": warnings,
        "Errors": errors,
    }


def _print_messages(heading: str, marker: str, messages: list[str]) -> None:
    """Print one human-readable warning or error section."""
    if not messages:
        return
    print(f"\n{heading}:", file=sys.stderr)
    for message in messages:
        print(f"  {marker} {message}", file=sys.stderr)


def _print_outcome(result: dict[str, Any]) -> None:
    """Print the final status line corresponding to the exit policy."""
    warnings = result["Warnings"]
    errors = result["Errors"]
    if result["EffectiveSuccess"]:
        print("\n✓ Validation passed", file=sys.stderr)
    elif result["WarningsAreFatal"] and result["Success"]:
        print(
            f"\n✗ Validation failed: {len(warnings)} warning(s) treated as "
            "violations (--fail-on-violation)",
            file=sys.stderr,
        )
    else:
        print(
            f"\n✗ Validation failed: {len(errors)} error(s), {len(warnings)} warning(s)",
            file=sys.stderr,
        )


def _print_human_summary(result: dict[str, Any]) -> None:
    """Print the human-readable validation report to stderr."""
    validations = result["Validations"]
    conventional_commit = validations["ConventionalCommit"]
    issue_keywords = validations["IssueKeywords"]
    template_compliance = validations["TemplateCompliance"]

    print("\nPR Description Validation Results", file=sys.stderr)
    print("=================================", file=sys.stderr)
    print(
        f"Conventional Commit: {conventional_commit['Status']} - "
        f"{conventional_commit['Message']}",
        file=sys.stderr,
    )
    print(
        f"Issue Keywords:      {issue_keywords['Status']} - "
        f"{issue_keywords['Message']}",
        file=sys.stderr,
    )
    print(
        f"Template Compliance: {template_compliance['Status']} - "
        f"{template_compliance['Message']}",
        file=sys.stderr,
    )
    fatality_policy = (
        "warnings are fatal (--fail-on-violation)"
        if result["FailOnViolation"]
        else "warnings are advisory (default mode)"
    )
    print(f"Policy:              {fatality_policy}", file=sys.stderr)
    _print_messages("Warnings", "⚠", result["Warnings"])
    _print_messages("Errors", "✗", result["Errors"])
    _print_outcome(result)


def _exit_code(result: dict[str, Any]) -> int:
    """Return the process exit code for a completed validation."""
    if result["FailOnViolation"] and not result["EffectiveSuccess"]:
        return 1
    return 0



def validate_no_escaped_newlines(body_content: str) -> None:
    r"""Reject a body whose line breaks are literal backslash-n. Issue #3777.

    Issues #3598 and #3646 shipped with every line break written as the two
    characters backslash and n, so GitHub rendered each as one unbroken
    paragraph and dropped every heading, list and table. Nothing errored.

    Canonical implementation:
    scripts/github_core/validation.py::escaped_newline_body_error. That
    module is copied here rather than imported for the same reason _DASH_RE
    is inlined above: new_pr.py runs on the push path and resolves only its
    own directory on sys.path, so importing github_core would mean adding
    the lib bootstrap the other skill scripts use, which hard-exits 2
    whenever .claude/lib is absent. That trades a rendering bug for an
    outage. The canonical guard and predicate, quoted verbatim as the
    leading lines of that function's body::

        if not body:
            return None
        count = body.count("\\n")
        if count == 0 or "\n" in body.strip():
            return None

    strip() is load-bearing. The premise in #3777 says the two bad bodies
    have no real newlines; measured, #3598 has 15 literal sequences and 1
    real newline and #3646 has 9 and 1, in both cases a trailing newline
    from the API. A plain membership test misses both.

    Keep the two copies in step. tests/test_github_core.py pins the shared
    version; tests/test_new_pr.py::TestValidation6EscapedNewlineCheck pins
    this one, and test_quoted_canonical_predicate_is_verbatim compares the
    block above against the real source of the canonical function so the
    word "verbatim" is checked rather than asserted.

    Args:
        body_content: Resolved body text, from --body or --body-file.

    Raises:
        SystemExit: Exit 1 when the body carries the corruption.
    """
    escaped_count = body_content.count("\\n")
    if not escaped_count or "\n" in body_content.strip():
        return
    print(
        f"ERROR: Body carries {escaped_count} literal backslash-n"
        " sequence(s) and no line break, so GitHub would render it as one"
        " unbroken paragraph and drop every heading, list and table.",
        file=sys.stderr,
    )
    print(
        "  Write the body to a file and pass --body-file, which cannot"
        " express this error.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    body, body_error = _resolve_body(args)
    if body_error is not None:
        return body_error

    validate_no_escaped_newlines(body)

    result = _build_result(
        args.title,
        body,
        fail_on_violation=args.fail_on_violation,
    )
    print(json.dumps(result, indent=2))
    _print_human_summary(result)
    return _exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())


