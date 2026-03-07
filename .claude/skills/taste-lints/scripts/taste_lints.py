#!/usr/bin/env python3
"""Taste invariant linter with agent-readable remediation instructions.

Exit codes: 0 = clean, 1 = script error, 10 = violations detected.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_VIOLATIONS = 10

SUPPRESSION_PATTERN = re.compile(
    r"#\s*taste-lint:\s*ignore\s+([\w-]+)",
    re.IGNORECASE,
)

ALL_RULES = ("file-size", "naming", "complexity", "skill-size")

# File extensions to scan
SCANNABLE_EXTENSIONS = {
    ".py", ".ps1", ".psm1", ".sh", ".bash",
    ".yml", ".yaml", ".md", ".json",
}


@dataclass
class Violation:
    """A detected taste violation with remediation."""

    rule: str
    severity: str
    file: str
    line: int
    message: str
    remediation: str


@dataclass
class LintResult:
    """Lint result container."""

    files_scanned: int = 0
    violations: list[Violation] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


def get_staged_files() -> list[str]:
    """Get list of staged files from git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
            check=True,
        )
        return [f for f in result.stdout.strip().split("\n") if f]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def get_files_from_directory(directory: str) -> list[str]:
    """Recursively get scannable files from a directory."""
    files = []
    for root, _dirs, filenames in os.walk(directory):
        for filename in filenames:
            filepath = os.path.join(root, filename)
            if Path(filepath).suffix in SCANNABLE_EXTENSIONS:
                files.append(filepath)
    return sorted(files)


def read_file_lines(filepath: str) -> list[str]:
    """Read file lines, returning empty list on error."""
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except OSError:
        return []


def has_suppression(lines: list[str], rule: str) -> bool:
    """Check if file has a suppression comment for the given rule."""
    for line in lines[:10]:
        match = SUPPRESSION_PATTERN.search(line)
        if match and match.group(1) == rule:
            return True
    return False


def check_file_size(filepath: str, lines: list[str]) -> list[Violation]:
    """Check file line count against thresholds."""
    if has_suppression(lines, "file-size"):
        return []
    line_count = len(lines)
    if line_count > 500:
        bn = Path(filepath).stem
        sx = Path(filepath).suffix
        return [Violation(
            rule="file-size", severity="error", file=filepath, line=line_count,
            message=f"File exceeds 500 lines ({line_count} lines)",
            remediation=(
                f"AGENT_REMEDIATION: Split this file into smaller modules. "
                f"Consider extracting:\n"
                f"  1. Helper functions -> {bn}_helpers{sx}\n"
                f"  2. Type definitions -> {bn}_types{sx}\n"
                f"  3. Constants -> {bn}_constants{sx}\n"
                f"  Target: each module under 300 lines for good cohesion."
            ),
        )]
    if line_count > 300:
        return [Violation(
            rule="file-size", severity="warning", file=filepath, line=line_count,
            message=f"File approaching size limit ({line_count}/500 lines)",
            remediation=(
                "AGENT_REMEDIATION: File is growing large. Plan extraction "
                "before it exceeds 500 lines. Look for:\n"
                "  1. Groups of related functions that form a cohesive module\n"
                "  2. Data classes or constants that can be separated\n"
                "  3. Test helpers that belong in a conftest or fixture file"
            ),
        )]
    return []


def _check_python_naming(filepath: str, name: str, suffix: str) -> Violation | None:
    if name == "__init__" or re.match(r"^[a-z][a-z0-9_]*$", name):
        return None
    path = Path(filepath)
    return Violation(
        rule="naming", severity="error", file=filepath, line=0,
        message=f"Python file '{name}{suffix}' is not snake_case",
        remediation=(
            f"AGENT_REMEDIATION: Rename to snake_case. "
            f"Suggested: {_to_snake_case(name)}{suffix}\n"
            f"  Update all imports that reference this module.\n"
            f"  Run: git mv {filepath} "
            f"{path.parent / (_to_snake_case(name) + suffix)}"
        ),
    )


def _check_yaml_naming(filepath: str, name: str, suffix: str) -> Violation | None:
    if re.match(r"^[a-z][a-z0-9-]*$", name) or name in ("CLAUDE", "project", "settings"):
        return None
    return Violation(
        rule="naming", severity="warning", file=filepath, line=0,
        message=f"YAML file '{name}{suffix}' is not kebab-case",
        remediation=(
            f"AGENT_REMEDIATION: Rename to kebab-case. "
            f"Suggested: {_to_kebab_case(name)}{suffix}\n"
            f"  Update any references in workflows or configs."
        ),
    )


def _check_hook_naming(filepath: str, name: str, suffix: str) -> Violation | None:
    if name.startswith("invoke_") or name in ("__init__", "skill_pattern_loader"):
        return None
    return Violation(
        rule="naming", severity="error", file=filepath, line=0,
        message=f"Hook script '{name}{suffix}' missing 'invoke_' prefix",
        remediation=(
            f"AGENT_REMEDIATION: Hook scripts must use invoke_ prefix "
            f"for consistency.\n"
            f"  Rename to: invoke_{name}{suffix}\n"
            f"  Update .claude/settings.json hook command references."
        ),
    )


def _check_skill_dir_naming(filepath: str) -> Violation | None:
    parts = Path(filepath).parts
    try:
        skills_idx = parts.index("skills")
    except ValueError:
        return None
    if skills_idx + 1 >= len(parts):
        return None
    skill_dir = parts[skills_idx + 1]
    if re.match(r"^[a-z][a-z0-9-]*$", skill_dir) or skill_dir == "CLAUDE.md":
        return None
    return Violation(
        rule="naming", severity="warning", file=filepath, line=0,
        message=f"Skill directory '{skill_dir}' is not kebab-case",
        remediation=(
            f"AGENT_REMEDIATION: Skill directories use kebab-case.\n"
            f"  Rename: {skill_dir} -> {_to_kebab_case(skill_dir)}\n"
            f"  Update SKILL.md name field to match."
        ),
    )


def check_naming(filepath: str, _lines: list[str]) -> list[Violation]:
    """Check file naming conventions."""
    if has_suppression(_lines, "naming"):
        return []

    violations: list[Violation] = []
    name = Path(filepath).stem
    suffix = Path(filepath).suffix

    checkers: list[tuple[bool, object]] = [
        (suffix == ".py", lambda: _check_python_naming(filepath, name, suffix)),
        (suffix in (".yml", ".yaml"), lambda: _check_yaml_naming(filepath, name, suffix)),
        (".claude/hooks/" in filepath and suffix == ".py",
         lambda: _check_hook_naming(filepath, name, suffix)),
        (".claude/skills/" in filepath, lambda: _check_skill_dir_naming(filepath)),
    ]
    for condition, checker in checkers:
        if condition:
            v = checker()
            if v:
                violations.append(v)

    return violations


def _emit_if_complex(
    violations: list[Violation], filepath: str,
    func_name: str | None, func_line: int, branch_count: int,
) -> None:
    """Append a complexity violation if the function exceeds the threshold."""
    if func_name and branch_count > 10:
        violations.append(_complexity_violation(filepath, func_name, func_line, branch_count))


def _is_func_body_end(line: str, indent: int, func_indent: int) -> bool:
    """Check if a line signals the end of a function body."""
    if indent > func_indent:
        return False
    if line.strip().startswith("#"):
        return False
    return not re.match(r"^\s*def\s+", line)


def check_complexity(filepath: str, lines: list[str]) -> list[Violation]:
    """Check function complexity (Python only, simple branch counting)."""
    if Path(filepath).suffix != ".py" or has_suppression(lines, "complexity"):
        return []

    violations: list[Violation] = []
    branch_keywords = re.compile(r"^\s*(if |elif |for |while |except |with )")
    current_func: str | None = None
    current_func_line = 0
    func_indent = 0
    branch_count = 0

    for i, line in enumerate(lines, 1):
        if not line.rstrip():
            continue

        indent = len(line) - len(line.lstrip())
        func_match = re.match(r"^(\s*)def\s+(\w+)", line)

        if func_match:
            _emit_if_complex(violations, filepath, current_func, current_func_line, branch_count)
            func_indent = len(func_match.group(1))
            current_func = func_match.group(2)
            current_func_line = i
            branch_count = 1
            continue

        if current_func and indent > func_indent and branch_keywords.match(line):
            branch_count += 1

        if current_func and _is_func_body_end(line, indent, func_indent):
            _emit_if_complex(violations, filepath, current_func, current_func_line, branch_count)
            current_func = None

    _emit_if_complex(violations, filepath, current_func, current_func_line, branch_count)
    return violations


def _complexity_violation(
    filepath: str, func_name: str, line: int, complexity: int,
) -> Violation:
    return Violation(
        rule="complexity",
        severity="error",
        file=filepath,
        line=line,
        message=f"Function '{func_name}' has complexity {complexity} (max 10)",
        remediation=(
            f"AGENT_REMEDIATION: Decompose '{func_name}' to reduce complexity.\n"
            f"  1. Extract conditional branches into named helper methods\n"
            f"  2. Use early returns to flatten nested conditions\n"
            f"  3. Replace complex conditionals with strategy pattern or lookup tables\n"
            f"  Target: cyclomatic complexity <= 10 per function."
        ),
    )


def check_skill_size(filepath: str, lines: list[str]) -> list[Violation]:
    """Check skill SKILL.md files for size limits."""
    if not filepath.endswith("SKILL.md") or ".claude/skills/" not in filepath:
        return []
    if has_suppression(lines, "skill-size"):
        return []
    if "size-exception: true" in "".join(lines[:20]):
        return []
    line_count = len(lines)
    if line_count > 500:
        sd = Path(filepath).parent.name
        return [Violation(
            rule="skill-size", severity="error", file=filepath, line=line_count,
            message=f"Skill prompt exceeds 500 lines ({line_count} lines)",
            remediation=(
                f"AGENT_REMEDIATION: Refactor using progressive disclosure:\n"
                f"  1. Move reference docs -> {sd}/references/\n"
                f"  2. Extract reusable logic -> {sd}/scripts/\n"
                f"  3. Use templates -> {sd}/templates/\n"
                f"  Or add 'size-exception: true' to frontmatter if justified."
            ),
        )]
    if line_count > 300:
        return [Violation(
            rule="skill-size", severity="warning", file=filepath, line=line_count,
            message=f"Skill prompt approaching limit ({line_count}/500 lines)",
            remediation=(
                "AGENT_REMEDIATION: Plan progressive disclosure refactoring "
                "before exceeding 500 lines.\n"
                "  Move reference material to references/ subdirectory."
            ),
        )]
    return []


def _to_snake_case(name: str) -> str:
    """Convert a name to snake_case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.replace("-", "_").lower()


def _to_kebab_case(name: str) -> str:
    """Convert a name to kebab-case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1-\2", s)
    return s.replace("_", "-").lower()


RULE_CHECKERS = {
    "file-size": check_file_size,
    "naming": check_naming,
    "complexity": check_complexity,
    "skill-size": check_skill_size,
}


def run_lint(files: list[str], rules: tuple[str, ...]) -> LintResult:
    """Run taste lints on the given files."""
    result = LintResult()

    for filepath in files:
        if not os.path.isfile(filepath):
            continue
        if Path(filepath).suffix not in SCANNABLE_EXTENSIONS:
            continue

        result.files_scanned += 1
        lines = read_file_lines(filepath)

        for rule in rules:
            checker = RULE_CHECKERS.get(rule)
            if checker:
                result.violations.extend(checker(filepath, lines))

    return result


def format_text(result: LintResult) -> str:
    """Format results as human/agent-readable text."""
    if not result.violations:
        return f"taste-lints: {result.files_scanned} files scanned, no violations found."

    output = []
    for v in result.violations:
        severity_marker = "ERROR" if v.severity == "error" else "WARNING"
        output.append(
            f"\n[{severity_marker}] {v.rule}: {v.file}:{v.line}\n"
            f"  {v.message}\n"
            f"  {v.remediation}"
        )

    summary = (
        f"\ntaste-lints: {result.files_scanned} files scanned, "
        f"{result.error_count} error(s), {result.warning_count} warning(s)"
    )
    output.append(summary)
    return "\n".join(output)


def format_json(result: LintResult) -> str:
    """Format results as JSON."""
    data = {
        "files_scanned": result.files_scanned,
        "error_count": result.error_count,
        "warning_count": result.warning_count,
        "violations": [
            {
                "rule": v.rule,
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Taste invariant linter with agent-readable remediation",
    )
    parser.add_argument(
        "files", nargs="*", help="Files to lint",
    )
    parser.add_argument(
        "--git-staged", action="store_true",
        help="Lint git staged files",
    )
    parser.add_argument(
        "--directory", "-d",
        help="Lint all scannable files in directory",
    )
    parser.add_argument(
        "--format", choices=("text", "json"), default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--rules",
        help=f"Comma-separated rules to run (default: all). Options: {','.join(ALL_RULES)}",
    )

    args = parser.parse_args()
    rules = parse_rules(args.rules)

    files: list[str] = []
    if args.git_staged:
        files = get_staged_files()
    elif args.directory:
        files = get_files_from_directory(args.directory)
    elif args.files:
        files = args.files
    else:
        parser.print_help()
        return EXIT_ERROR

    if not files:
        print("taste-lints: no files to scan.")
        return EXIT_SUCCESS

    result = run_lint(files, rules)

    if args.format == "json":
        print(format_json(result))
    else:
        print(format_text(result))

    if result.error_count > 0:
        return EXIT_VIOLATIONS
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
