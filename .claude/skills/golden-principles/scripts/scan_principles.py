#!/usr/bin/env python3
"""Golden principles scanner with agent-readable remediation instructions.

Checks repository files against mechanically enforced golden principles
defined in .agents/governance/golden-principles.md.

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
    r"#\s*golden-principle:\s*ignore\s+([\w-]+)",
    re.IGNORECASE,
)

ALL_RULES = (
    "script-language",
    "skill-frontmatter",
    "agent-definition",
    "yaml-logic",
    "actions-pinned",
)

REQUIRED_SKILL_FIELDS = ("name", "version", "model", "description", "license")

AGENT_REQUIRED_SECTIONS = ("description", "model")

# SHA pattern for pinned actions
SHA_PIN_PATTERN = re.compile(r"uses:\s+[\w-]+/[\w.-]+@([a-f0-9]{40})")
TAG_PIN_PATTERN = re.compile(r"uses:\s+([\w-]+/[\w.-]+)@(v[\d.]+|[\w.-]+)")
FIRST_PARTY_ACTIONS = {"actions/checkout", "actions/setup-python", "actions/setup-node"}

@dataclass
class Violation:
    """A detected principle violation with remediation."""

    rule: str
    principle: str
    severity: str
    file: str
    line: int
    message: str
    remediation: str

@dataclass
class ScanResult:
    """Scan result container."""

    files_scanned: int = 0
    applicable_files: int = 0
    violations: list[Violation] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")

def is_safe_path(filepath: str) -> bool:
    """Check if a path is safe from path traversal attacks (CWE-22)."""
    if os.path.isabs(filepath):
        return True
    parts = Path(filepath).parts
    return ".." not in parts

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

def get_repo_files(directory: str) -> list[str]:
    """Recursively collect files, skipping hidden dirs except .claude, .agents, .github."""
    files = []
    for root, dirs, filenames in os.walk(directory):
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".") or d in (".claude", ".agents", ".github")
        ]
        for filename in filenames:
            filepath = os.path.join(root, filename)
            if is_safe_path(filepath):
                files.append(filepath)
    return sorted(files)

# Bound git subprocess calls so a hung or wedged git process cannot stall the
# diff-scope pre-flight indefinitely.
_GIT_TIMEOUT_SECONDS = 30

def _git_root() -> str:
    """Return the absolute path of the git working tree root.

    Raises:
        RuntimeError: git is unavailable, times out, or the command fails (for
            example when run outside a repository). Surfacing the failure stops
            the gate from silently anchoring diff paths to the wrong place and
            scanning zero files.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=True,
            encoding="utf-8",
            errors="ignore",
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git is not available to compute --diff-scope") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("git rev-parse --show-toplevel timed out") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"git rev-parse --show-toplevel failed (exit {exc.returncode})"
        ) from exc
    return result.stdout.strip()


def get_diff_files(base: str) -> list[str]:
    """Collect files changed in the diff against a base branch.

    Derives the list from `git diff --name-only <base>...HEAD`. Path traversal
    candidates (CWE-22) are dropped, paths are anchored to the git root so they
    resolve regardless of the process working directory, and the result is
    sorted.

    Raises:
        ValueError: ``base`` is empty or starts with ``-`` (CWE-88 argument
            injection: a leading dash would be parsed by git as an option).
        RuntimeError: git is unavailable or the diff command fails (for example
            an unknown base). A git failure must not be mistaken for an empty
            diff, which would let a standards pre-flight pass without scanning.
    """
    if not base or base.startswith("-"):
        raise ValueError(f"invalid --diff-scope base: {base!r}")
    root = _git_root()
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            capture_output=True,
            check=True,
            encoding="utf-8",
            errors="ignore",
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git is not available to compute --diff-scope") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"git diff timed out for base {base!r}") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"git diff failed for base {base!r} (exit {exc.returncode})"
        ) from exc
    files = [f for f in result.stdout.splitlines() if f]
    return sorted(os.path.join(root, f) for f in files if is_safe_path(f))

def check_script_language(filepath: str, lines: list[str]) -> list[Violation]:
    """GP-001: No new .sh or .bash files."""
    suffix = Path(filepath).suffix
    if suffix not in (".sh", ".bash"):
        return []
    if has_suppression(lines, "script-language"):
        return []
    return [Violation(
        rule="script-language",
        principle="GP-001",
        severity="error",
        file=filepath,
        line=0,
        message=f"Shell script detected: {Path(filepath).name}",
        remediation=(
            "AGENT_REMEDIATION: Convert this shell script to Python per ADR-042.\n"
            "  1. Create a new Python file with the same base name\n"
            "  2. Use subprocess.run() for shell commands that have no Python equivalent\n"
            "  3. Use pathlib.Path for file operations\n"
            "  4. Add argparse for CLI arguments\n"
            "  5. Delete the original shell script"
        ),
    )]

def check_skill_frontmatter(filepath: str, lines: list[str]) -> list[Violation]:
    """GP-003: SKILL.md must have required frontmatter fields."""
    if not filepath.endswith("SKILL.md") or ".claude/skills/" not in filepath:
        return []
    if has_suppression(lines, "skill-frontmatter"):
        return []

    content = "".join(lines)
    if not content.startswith("---"):
        return [Violation(
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
                "  model: claude-sonnet-4-6\n"
                "  description: What it does and when to use it\n"
                "  license: MIT\n"
                "  ---"
            ),
        )]

    parts = content.split("---", 2)
    if len(parts) < 3:
        return [Violation(
            rule="skill-frontmatter",
            principle="GP-003",
            severity="error",
            file=filepath,
            line=1,
            message="SKILL.md has unclosed frontmatter block",
            remediation=(
                "AGENT_REMEDIATION: Close the frontmatter block with --- on its own line."
            ),
        )]

    frontmatter = parts[1]
    missing = [f for f in REQUIRED_SKILL_FIELDS if f"{f}:" not in frontmatter]
    if missing:
        return [Violation(
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
        )]
    return []

def check_agent_definition(filepath: str, lines: list[str]) -> list[Violation]:
    """GP-004: Agent definitions must have required frontmatter."""
    if not filepath.endswith(".md"):
        return []
    if ".claude/agents/" not in filepath:
        return []
    if Path(filepath).name in ("CLAUDE.md",):
        return []
    if has_suppression(lines, "agent-definition"):
        return []

    content = "".join(lines)
    if not content.startswith("---"):
        return [Violation(
            rule="agent-definition",
            principle="GP-004",
            severity="error",
            file=filepath,
            line=1,
            message="Agent definition missing YAML frontmatter",
            remediation=(
                "AGENT_REMEDIATION: Add YAML frontmatter with required fields.\n"
                "  ---\n"
                "  name: agent-name\n"
                "  description: What the agent does\n"
                "  model: sonnet\n"
                "  ---"
            ),
        )]

    parts = content.split("---", 2)
    if len(parts) < 3:
        return []

    frontmatter = parts[1]
    missing = [f for f in AGENT_REQUIRED_SECTIONS if f"{f}:" not in frontmatter]
    if missing:
        return [Violation(
            rule="agent-definition",
            principle="GP-004",
            severity="warning",
            file=filepath,
            line=1,
            message=f"Agent definition missing fields: {', '.join(missing)}",
            remediation=(
                "AGENT_REMEDIATION: Add the missing frontmatter fields:\n"
                + "\n".join(f"  {f}: <value>" for f in missing)
            ),
        )]
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
    if ".github/workflows/" not in filepath:
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
    if ".github/workflows/" not in filepath:
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

        violations.append(Violation(
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
        ))

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
      - script-language (GP-001): .sh / .bash scripts, plus .py / .ps1 / .psm1
        in the broader script-language domain.
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

    if suffix in (".sh", ".bash", ".py", ".ps1", ".psm1"):
        return True
    if name == "SKILL.md" and ".claude/skills/" in filepath:
        return True
    if suffix == ".md" and ".claude/agents/" in filepath and name != "CLAUDE.md":
        return True
    if suffix in (".yml", ".yaml") and ".github/workflows/" in filepath:
        return True
    return False

def run_scan(files: list[str], rules: tuple[str, ...]) -> ScanResult:
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
                result.violations.extend(checker(filepath, lines))

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
        "files", nargs="*", help="Files to scan",
    )
    parser.add_argument(
        "--directory", "-d",
        help="Scan all files in directory (default: repo root)",
    )
    parser.add_argument(
        "--diff-scope",
        metavar="BASE_BRANCH",
        help="Scan only files changed in 'git diff --name-only BASE_BRANCH...HEAD'",
    )
    parser.add_argument(
        "--format", choices=("text", "json"), default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--rules",
        help=f"Comma-separated rules to run (default: all). Options: {','.join(ALL_RULES)}",
    )
    parser.add_argument(
        "--output", "-o",
        help="Write output to file instead of stdout",
    )

    args = parser.parse_args()
    rules = parse_rules(args.rules)

    files: list[str] = []
    if args.diff_scope is not None:
        try:
            files = get_diff_files(args.diff_scope)
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

    result = run_scan(files, rules)

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
