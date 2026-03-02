#!/usr/bin/env python3
"""Validate slash command file for quality gates.

Validates slash command (.md) files for 5 categories:
1. Frontmatter - Required YAML frontmatter with description
2. Arguments - Consistency between argument-hint and $ARGUMENTS usage
3. Security - allowed-tools required when bash execution (!) is used
4. Length - Warning if >200 lines (suggest converting to skill)
5. Lint - Markdown lint via markdownlint-cli2

EXIT CODES (ADR-035):
    0 - All validations passed (or warnings only)
    1 - One or more BLOCKING violations found
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path


def validate_slash_command(path: str, skip_lint: bool = False) -> int:
    """Validate a slash command file.

    Returns exit code: 0 on success, 1 on blocking violations.
    """
    file_path = Path(path)
    violations: list[str] = []

    if not file_path.exists():
        print(f"[FAIL] File not found: {path}")
        print("  Troubleshooting:")
        print("    - Verify file path is correct")
        print("    - Check if file has been moved or deleted")
        print("    - Use absolute path if relative path is ambiguous")
        return 1

    content = file_path.read_text(encoding="utf-8")

    # 1. Frontmatter Validation
    has_arg_hint = False
    frontmatter = None

    fm_match = re.search(r"(?s)^---\s*\n(.*?)\n---", content)
    if not fm_match:
        violations.append("BLOCKING: Missing YAML frontmatter block")
    else:
        frontmatter = fm_match.group(1)

        desc_match = re.search(r"description:\s*(.+)", frontmatter)
        if not desc_match:
            violations.append("BLOCKING: Missing 'description' in frontmatter")
        else:
            description = desc_match.group(1).strip()
            if not re.match(
                r"^(Use when|Generate|Research|Invoke|Create|Analyze|Review|Search)",
                description,
            ):
                violations.append(
                    "WARNING: Description should start with"
                    " action verb or 'Use when...'"
                )

        arg_match = re.search(r"argument-hint:\s*(.+)", frontmatter)
        has_arg_hint = arg_match is not None

    # 2. Argument Validation
    uses_arguments = bool(re.search(r"\$ARGUMENTS|\$1|\$2|\$3", content))

    if uses_arguments and not has_arg_hint:
        violations.append("BLOCKING: Prompt uses arguments but no 'argument-hint' in frontmatter")

    if has_arg_hint and not uses_arguments:
        violations.append(
            "WARNING: Frontmatter has 'argument-hint'"
            " but prompt doesn't use arguments"
        )

    # 3. Security Validation
    uses_bash_execution = bool(re.search(r"!\s*\w+", content))

    if uses_bash_execution and frontmatter is not None:
        allowed_tools_match = re.search(r"allowed-tools:\s*\[(.+)\]", frontmatter)

        if not allowed_tools_match:
            violations.append(
                "BLOCKING: Prompt uses bash execution (!)"
                " but no 'allowed-tools' in frontmatter"
            )
        else:
            allowed_tools = allowed_tools_match.group(1)
            tool_list = [t.strip() for t in allowed_tools.split(",")]
            has_overly_permissive = False
            for tool in tool_list:
                if "*" in tool and not tool.startswith("mcp__"):
                    has_overly_permissive = True
                    break
            if has_overly_permissive:
                violations.append(
                    "BLOCKING: 'allowed-tools' has overly permissive wildcard "
                    "(use mcp__* for scoped namespaces)"
                )

        # Verify common bash commands exist (warning only)
        bash_commands = re.findall(r"!\s*(\w+)", content)
        for cmd in bash_commands:
            if cmd in ("git", "gh", "npm", "npx"):
                if not shutil.which(cmd):
                    violations.append(
                        f"WARNING: Bash command '{cmd}'"
                        " not found in PATH (runtime may fail)"
                    )

    # 4. Length Validation
    line_count = len(content.splitlines())
    if line_count > 200:
        violations.append(
            f"WARNING: File has {line_count} lines (>200)."
            " Consider converting to skill."
        )

    # 5. Lint Validation
    if not skip_lint:
        print("Running markdownlint-cli2...", file=sys.stderr)
        try:
            lint_result = subprocess.run(
                ["npx", "markdownlint-cli2", path],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if lint_result.returncode != 0:
                violations.append("BLOCKING: Markdown lint errors:")
                if lint_result.stdout.strip():
                    violations.append(lint_result.stdout.strip())
                if lint_result.stderr.strip():
                    violations.append(lint_result.stderr.strip())
                violations.append("")
                violations.append(f"  To auto-fix: npx markdownlint-cli2 --fix {path}")
                violations.append("  Configuration: .markdownlint.json (if exists) or defaults")
        except FileNotFoundError:
            violations.append("WARNING: npx not found, skipping markdown lint")
        except subprocess.TimeoutExpired:
            violations.append("WARNING: markdownlint-cli2 timed out")

    # Determine results
    blocking_count = sum(1 for v in violations if v.startswith("BLOCKING:"))
    warning_count = sum(1 for v in violations if v.startswith("WARNING:"))

    if violations:
        print(f"\n[FAIL] Validation FAILED: {path}")
        print(f"\nViolations ({blocking_count} blocking, {warning_count} warnings):")
        for violation in violations:
            print(f"  - {violation}")

        if blocking_count > 0:
            return 1

        print(f"\n[PASS] Validation PASSED with warnings: {path}")
        return 0

    print(f"\n[PASS] Validation PASSED: {path}")
    return 0


def main() -> int:
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate slash command file for quality gates")
    parser.add_argument("--path", required=True, help="Path to slash command .md file")
    parser.add_argument("--skip-lint", action="store_true", help="Skip markdown lint validation")
    args = parser.parse_args()

    return validate_slash_command(args.path, args.skip_lint)


if __name__ == "__main__":
    sys.exit(main())
