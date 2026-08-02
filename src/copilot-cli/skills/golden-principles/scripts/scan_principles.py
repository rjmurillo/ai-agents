#!/usr/bin/env python3
"""Golden principles scanner with agent-readable remediation instructions.

Checks repository files against mechanically enforced golden principles
defined in .agents/governance/golden-principles.md.

Core types, path utilities, model validation helpers, and git helpers live
in ``scan_principles_core.py`` (split per issue #4028 to keep both files
under the 500-line ceiling).

Exit codes: 0 = clean, 1 = script error, 10 = violations detected.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Allow sibling-module import of scan_principles_core when this script is run
# directly or loaded via importlib (tests). The scripts directory is not a
# package, so sys.path must include it for a bare ``import`` to resolve.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from scan_principles_core import (  # noqa: E402
    _AGENTS_PATH_PARTS,
    _SKILLS_PATH_PARTS,
    _WORKFLOWS_PATH_PARTS,
    ALL_RULES,
    EXIT_ERROR,
    EXIT_SUCCESS,
    EXIT_VIOLATIONS,
    FIRST_PARTY_ACTIONS,
    REQUIRED_SKILL_FIELDS,
    SHA_PIN_PATTERN,
    TAG_PIN_PATTERN,
    ScanResult,
    Violation,
    _check_skill_model_adr080,
    _has_path_parts,
    check_agent_definition,
    check_script_language,
    get_diff_files,
    get_diff_line_numbers,
    get_repo_files,
    has_suppression,
    is_safe_path,
    read_file_lines,
)


def check_skill_frontmatter(filepath: str, lines: list[str]) -> list[Violation]:
    """GP-003: SKILL.md must have required frontmatter fields (ADR-080 aware).

    model: is optional. Omitting it inherits the harness default, which is the
    correct default per ADR-080. When present, it must be a bare rolling alias
    (sonnet / opus / haiku) accompanied by a model-rationale: field. Versioned
    ids (e.g. claude-opus-4-6) are forbidden for skills.
    """
    if not filepath.endswith("SKILL.md") or not _has_path_parts(filepath, _SKILLS_PATH_PARTS):
        return []
    if has_suppression(lines, "skill-frontmatter"):
        return []

    content = "".join(lines)
    if not content.startswith("---"):
        return [
            Violation(
                rule="skill-frontmatter",
                principle="GP-003",
                severity="error",
                file=filepath,
                line=1,
                message="SKILL.md missing YAML frontmatter",
                remediation=(
                    "AGENT_REMEDIATION: Add YAML frontmatter block at line 1.\n"
                    "  ---\n"
                    "  name: skill-name\n"
                    "  version: 1.0.0\n"
                    "  description: What it does and when to use it\n"
                    "  license: MIT\n"
                    "  ---"
                ),
            )
        ]

    parts = content.split("---", 2)
    if len(parts) < 3:
        return [
            Violation(
                rule="skill-frontmatter",
                principle="GP-003",
                severity="error",
                file=filepath,
                line=1,
                message="SKILL.md has unclosed frontmatter block",
                remediation=(
                    "AGENT_REMEDIATION: Close the frontmatter block with --- on its own line."
                ),
            )
        ]

    frontmatter = parts[1]
    missing = [f for f in REQUIRED_SKILL_FIELDS if f"{f}:" not in frontmatter]
    if missing:
        return [
            Violation(
                rule="skill-frontmatter",
                principle="GP-003",
                severity="error",
                file=filepath,
                line=1,
                message=f"SKILL.md missing required fields: {', '.join(missing)}",
                remediation=(
                    "AGENT_REMEDIATION: Add the missing frontmatter fields:\n"
                    + "\n".join(f"  {f}: <value>" for f in missing)
                ),
            )
        ]

    # ADR-080: validate model field when present.
    adr080_violations = _check_skill_model_adr080(filepath, frontmatter)
    if adr080_violations:
        return adr080_violations

    return []


def _find_long_run_blocks(lines: list[str]) -> list[tuple[int, int]]:
    """Find multiline run blocks exceeding 5 lines. Returns (start_line, count) pairs."""
    blocks = []
    in_block = False
    start, count, block_indent = 0, 0, 0
    for i, line in enumerate(lines, 1):
        stripped = line.rstrip()
        if re.match(r"^\s+run:\s*\|", stripped):
            if in_block and count > 5:
                blocks.append((start, count))
            in_block, start, count = True, i, 0
            block_indent = len(line) - len(line.lstrip())
        elif in_block:
            indent = len(line) - len(line.lstrip())
            if stripped and indent > block_indent:
                count += 1
            elif stripped:
                if count > 5:
                    blocks.append((start, count))
                in_block = False
    if in_block and count > 5:
        blocks.append((start, count))
    return blocks


def check_yaml_logic(filepath: str, lines: list[str]) -> list[Violation]:
    """GP-005: No inline logic in workflow YAML."""
    if not _has_path_parts(filepath, _WORKFLOWS_PATH_PARTS):
        return []
    if Path(filepath).suffix not in (".yml", ".yaml"):
        return []
    if has_suppression(lines, "yaml-logic"):
        return []
    return [
        _yaml_logic_violation(filepath, start, count)
        for start, count in _find_long_run_blocks(lines)
    ]


def _yaml_logic_violation(filepath: str, line: int, count: int) -> Violation:
    return Violation(
        rule="yaml-logic",
        principle="GP-005",
        severity="warning",
        file=filepath,
        line=line,
        message=f"Multiline run block ({count} lines) should be a script",
        remediation=(
            "AGENT_REMEDIATION: Extract this run block to a script.\n"
            "  1. Create a Python script in scripts/ with the logic\n"
            "  2. Replace the run block with: run: python3 scripts/<name>.py\n"
            "  3. Add argparse for any inputs from workflow context"
        ),
    )


def check_actions_pinned(filepath: str, lines: list[str]) -> list[Violation]:
    """GP-006: GitHub Actions must be pinned to SHA."""
    if not _has_path_parts(filepath, _WORKFLOWS_PATH_PARTS):
        return []
    suffix = Path(filepath).suffix
    if suffix not in (".yml", ".yaml"):
        return []
    if has_suppression(lines, "actions-pinned"):
        return []

    violations = []
    for i, line in enumerate(lines, 1):
        tag_match = TAG_PIN_PATTERN.search(line)
        if not tag_match:
            continue
        sha_match = SHA_PIN_PATTERN.search(line)
        if sha_match:
            continue

        action_name = tag_match.group(1)
        tag = tag_match.group(2)

        if action_name in FIRST_PARTY_ACTIONS:
            continue

        violations.append(
            Violation(
                rule="actions-pinned",
                principle="GP-006",
                severity="error",
                file=filepath,
                line=i,
                message=f"Action '{action_name}' pinned to tag '{tag}' instead of SHA",
                remediation=(
                    f"AGENT_REMEDIATION: Pin '{action_name}' to a full SHA.\n"
                    f"  1. Find the commit SHA for tag '{tag}' on the action repo\n"
                    f"  2. Replace: uses: {action_name}@{tag}\n"
                    f"     With:    uses: {action_name}@<full-sha> # {tag}\n"
                    f"  3. Add a comment with the tag for readability"
                ),
            )
        )

    return violations


RULE_CHECKERS = {
    "script-language": check_script_language,
    "skill-frontmatter": check_skill_frontmatter,
    "agent-definition": check_agent_definition,
    "yaml-logic": check_yaml_logic,
    "actions-pinned": check_actions_pinned,
}


def _is_applicable(filepath: str) -> bool:
    """Return True when a file falls in any golden-principle rule's file-type domain.

    The domains mirror the per-rule checker guards in this module:
      - script-language (GP-001): .sh / .bash scripts.
      - skill-frontmatter (GP-003): SKILL.md under .claude/skills/.
      - agent-definition (GP-004): .md under .claude/agents/ (except CLAUDE.md).
      - yaml-logic (GP-005) and actions-pinned (GP-006): .yml / .yaml under
        .github/workflows/.

    A file outside all of these domains is not checked by any rule, so a clean
    scan over only such files reflects zero applicable rules, not a passing
    code-design review.
    """
    suffix = Path(filepath).suffix
    name = Path(filepath).name

    if suffix in (".sh", ".bash"):
        return True
    if name == "SKILL.md" and _has_path_parts(filepath, _SKILLS_PATH_PARTS):
        return True
    if suffix == ".md" and _has_path_parts(filepath, _AGENTS_PATH_PARTS) and name != "CLAUDE.md":
        return True
    if suffix in (".yml", ".yaml") and _has_path_parts(filepath, _WORKFLOWS_PATH_PARTS):
        return True
    return False


def run_scan(
    files: list[str],
    rules: tuple[str, ...],
    diff_lines: dict[str, set[int]] | None = None,
) -> ScanResult:
    """Run golden principle scan on the given files."""
    result = ScanResult()

    for filepath in files:
        if not is_safe_path(filepath):
            continue
        if not os.path.isfile(filepath):
            continue

        result.files_scanned += 1
        if _is_applicable(filepath):
            result.applicable_files += 1
        lines = read_file_lines(filepath)

        for rule in rules:
            checker = RULE_CHECKERS.get(rule)
            if checker:
                violations = checker(filepath, lines)
                if diff_lines is not None and filepath in diff_lines:
                    changed = diff_lines[filepath]
                    # line==0 means file-level; keep when the file is in the diff.
                    violations = [v for v in violations if v.line == 0 or v.line in changed]
                elif diff_lines is not None:
                    violations = []
                result.violations.extend(violations)

    return result


def format_text(result: ScanResult) -> str:
    """Format results as human/agent-readable text."""
    if not result.violations:
        if result.applicable_files == 0:
            return (
                f"golden-principles: {result.files_scanned} files scanned, "
                "0 applicable to golden-principle rules (this scanner checks "
                "toolkit artifacts: scripts, skills, YAML, GitHub Actions, agent "
                "files). No code-design check ran."
            )
        return f"golden-principles: {result.files_scanned} files scanned, no violations found."

    output = []
    for v in result.violations:
        severity_marker = "ERROR" if v.severity == "error" else "WARNING"
        output.append(
            f"\n[{severity_marker}] {v.principle} ({v.rule}): {v.file}:{v.line}\n"
            f"  {v.message}\n"
            f"  {v.remediation}"
        )

    summary = (
        f"\ngolden-principles: {result.files_scanned} files scanned, "
        f"{result.error_count} error(s), {result.warning_count} warning(s)"
    )
    output.append(summary)
    return "\n".join(output)


def format_json(result: ScanResult) -> str:
    """Format results as JSON."""
    data = {
        "files_scanned": result.files_scanned,
        "applicable_files": result.applicable_files,
        "error_count": result.error_count,
        "warning_count": result.warning_count,
        "violations": [
            {
                "rule": v.rule,
                "principle": v.principle,
                "severity": v.severity,
                "file": v.file,
                "line": v.line,
                "message": v.message,
                "remediation": v.remediation,
            }
            for v in result.violations
        ],
    }
    return json.dumps(data, indent=2)


def parse_rules(rules_str: str) -> tuple[str, ...]:
    """Parse comma-separated rule names."""
    if not rules_str:
        return ALL_RULES
    rules = tuple(r.strip() for r in rules_str.split(","))
    invalid = [r for r in rules if r not in ALL_RULES]
    if invalid:
        print(f"error: unknown rules: {', '.join(invalid)}", file=sys.stderr)
        print(f"valid rules: {', '.join(ALL_RULES)}", file=sys.stderr)
        sys.exit(EXIT_ERROR)
    return rules


def _find_repo_root() -> str | None:
    """Walk up from cwd to find .git directory."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return str(parent)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Golden principles scanner with agent-readable remediation",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Files to scan",
    )
    parser.add_argument(
        "--directory",
        "-d",
        help="Scan all files in directory (default: repo root)",
    )
    parser.add_argument(
        "--diff-scope",
        metavar="BASE_BRANCH",
        help="Scan only files changed in 'git diff --name-only BASE_BRANCH...HEAD'",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--rules",
        help=f"Comma-separated rules to run (default: all). Options: {','.join(ALL_RULES)}",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Write output to file instead of stdout",
    )

    args = parser.parse_args()
    rules = parse_rules(args.rules)

    files: list[str] = []
    diff_lines: dict[str, set[int]] | None = None
    if args.diff_scope is not None:
        try:
            files = get_diff_files(args.diff_scope)
            diff_lines = get_diff_line_numbers(args.diff_scope)
        except (ValueError, RuntimeError) as exc:
            print(f"golden-principles: {exc}", file=sys.stderr)
            return EXIT_ERROR
    elif args.directory:
        files = get_repo_files(args.directory)
    elif args.files:
        files = args.files
    else:
        repo_root = _find_repo_root()
        if repo_root:
            files = get_repo_files(repo_root)
        else:
            files = get_repo_files(".")

    if not files:
        print("golden-principles: no files to scan.")
        return EXIT_SUCCESS

    result = run_scan(files, rules, diff_lines)

    output = format_json(result) if args.format == "json" else format_text(result)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"golden-principles: results written to {args.output}")
    else:
        print(output)

    if result.error_count > 0:
        return EXIT_VIOLATIONS
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
