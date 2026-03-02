#!/usr/bin/env python3
"""Validate slash command file for quality gates.

Validates slash command (.md) files for 5 categories:
1. Frontmatter - Required YAML frontmatter with description
2. Arguments - Consistency between argument-hint and $ARGUMENTS usage
3. Security - allowed-tools required when bash execution (!) is used
4. Length - Warning if >200 lines (suggest converting to skill)
5. Lint - Markdown lint via markdownlint-cli2

Exit codes follow ADR-035:
    0 - All validations passed
    1 - One or more BLOCKING violations found
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate slash command file for quality gates.",
    )
    parser.add_argument(
        "--path", required=True, help="Path to slash command .md file",
    )
    parser.add_argument(
        "--skip-lint",
        action="store_true",
        help="Skip markdown lint validation",
    )
    return parser


def _validate_frontmatter(content: str, violations: list[str]) -> tuple[str | None, bool]:
    """Validate YAML frontmatter block. Returns (frontmatter_text, has_arg_hint)."""
    # WHY: Use regex for YAML parsing instead of PyYAML module dependency.
    # LIMITATION: Won't handle multi-line YAML values or complex nesting.
    # MITIGATION: pytest tests validate against real-world command files.
    fm_match = re.match(r"(?s)^---\s*\n(.*?)\n---", content)
    if not fm_match:
        violations.append("BLOCKING: Missing YAML frontmatter block")
        return None, False

    frontmatter = fm_match.group(1)

    # Parse description field
    desc_match = re.search(r"description:\s*(.+)", frontmatter)
    if not desc_match:
        violations.append("BLOCKING: Missing 'description' in frontmatter")
    else:
        description = desc_match.group(1).strip()
        trigger_re = re.compile(
            r"^(Use when|Generate|Research|Invoke|Create|Analyze|Review|Search)"
        )
        if not trigger_re.match(description):
            violations.append(
                "WARNING: Description should start with action verb or 'Use when...'"
            )

    has_arg_hint = bool(re.search(r"argument-hint:\s*(.+)", frontmatter))
    return frontmatter, has_arg_hint


def _validate_arguments(
    content: str,
    has_arg_hint: bool,
    violations: list[str],
) -> None:
    """Validate argument consistency."""
    uses_arguments = bool(re.search(r"\$ARGUMENTS|\$1|\$2|\$3", content))

    if uses_arguments and not has_arg_hint:
        violations.append(
            "BLOCKING: Prompt uses arguments but no 'argument-hint' in frontmatter"
        )

    if has_arg_hint and not uses_arguments:
        violations.append(
            "WARNING: Frontmatter has 'argument-hint' but prompt doesn't use arguments"
        )


def _validate_security(
    content: str,
    frontmatter: str | None,
    violations: list[str],
) -> None:
    """Validate security constraints for bash execution."""
    uses_bash = bool(re.search(r"!\s*\w+", content))

    if not uses_bash or frontmatter is None:
        return

    tools_match = re.search(r"allowed-tools:\s*\[(.+)\]", frontmatter)
    if not tools_match:
        violations.append(
            "BLOCKING: Prompt uses bash execution (!) but no "
            "'allowed-tools' in frontmatter"
        )
        return

    allowed_tools = tools_match.group(1)

    # Check for overly permissive wildcards
    # WHY: Allow scoped namespaces like mcp__* but reject bare *
    tool_list = [t.strip() for t in allowed_tools.split(",")]
    for tool in tool_list:
        if "*" in tool and not tool.startswith("mcp__"):
            violations.append(
                "BLOCKING: 'allowed-tools' has overly permissive wildcard "
                "(use mcp__* for scoped namespaces)"
            )
            break


def _validate_length(content: str, violations: list[str]) -> None:
    """Warn if file exceeds 200 lines."""
    line_count = len(content.split("\n"))
    if line_count > 200:
        violations.append(
            f"WARNING: File has {line_count} lines (>200). "
            f"Consider converting to skill."
        )


def _validate_lint(path: str, violations: list[str]) -> None:
    """Run markdownlint-cli2 on the file."""
    print("Running markdownlint-cli2...")
    result = subprocess.run(
        ["npx", "markdownlint-cli2", "--", path],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        violations.append("BLOCKING: Markdown lint errors:")
        lint_output = result.stdout or result.stderr
        if lint_output:
            violations.append(lint_output.strip())
        violations.append(f"  To auto-fix: npx markdownlint-cli2 --fix {path}")


def validate_slash_command(
    path: str,
    skip_lint: bool = False,
) -> tuple[list[str], int, int]:
    """Validate a slash command file.

    Returns:
        Tuple of (violations, blocking_count, warning_count).
    """
    file_path = Path(path)

    if not file_path.exists():
        print(f"[FAIL] File not found: {path}")
        print("  Troubleshooting:")
        print("    - Verify file path is correct")
        print("    - Check if file has been moved or deleted")
        print("    - Use absolute path if relative path is ambiguous")
        return ["BLOCKING: File not found"], 1, 0

    content = file_path.read_text(encoding="utf-8")
    violations: list[str] = []

    # 1. Frontmatter validation
    frontmatter, has_arg_hint = _validate_frontmatter(content, violations)

    # 2. Argument validation
    _validate_arguments(content, has_arg_hint, violations)

    # 3. Security validation
    _validate_security(content, frontmatter, violations)

    # 4. Length validation
    _validate_length(content, violations)

    # 5. Lint validation
    if not skip_lint:
        _validate_lint(path, violations)

    blocking_count = sum(1 for v in violations if v.startswith("BLOCKING:"))
    warning_count = sum(1 for v in violations if v.startswith("WARNING:"))

    return violations, blocking_count, warning_count


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    violations, blocking_count, warning_count = validate_slash_command(
        args.path, args.skip_lint,
    )

    if violations:
        # Check if first violation is file-not-found (already printed)
        if violations == ["BLOCKING: File not found"]:
            return 1

        print(f"\n[FAIL] Validation FAILED: {args.path}")
        print(f"\nViolations ({blocking_count} blocking, {warning_count} warnings):")
        for v in violations:
            print(f"  - {v}")

        if blocking_count > 0:
            return 1

        print(f"\n[PASS] Validation PASSED with warnings: {args.path}")
        return 0

    print(f"\n[PASS] Validation PASSED: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
