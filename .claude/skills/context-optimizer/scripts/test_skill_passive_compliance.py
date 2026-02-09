#!/usr/bin/env python3
"""
Skill/Passive Context Compliance Validator.

Validates that content placement follows the skill vs passive context decision framework.
Checks 6 compliance rules and returns structured JSON with violations and recommendations.

Exit codes:
    0: All compliance checks passed
    1: One or more violations detected
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class CheckResult:
    """Result of a single compliance check."""

    passed: bool
    severity: str  # "none", "warning", "error"
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceResults:
    """Overall compliance check results."""

    timestamp: str
    path: str
    claude_md_path: str
    violations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    summary: dict[str, int] = field(
        default_factory=lambda: {
            "total_checks": 0,
            "passed": 0,
            "failed": 0,
            "warnings": 0,
        }
    )


def find_repository_root() -> Path:
    """Find the repository root by locating .git directory."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    raise RuntimeError("Not in a git repository")


def check_skill_has_actions(skill_path: Path) -> CheckResult:
    """Check if skill directory contains action verbs and tool execution."""
    skill_md = skill_path / "SKILL.md"

    if not skill_md.exists():
        return CheckResult(
            passed=False, severity="error", message="SKILL.md not found"
        )

    content = skill_md.read_text()

    # Check for action verbs
    action_verbs = [
        "create",
        "update",
        "delete",
        "execute",
        "run",
        "modify",
        "remove",
        "add",
        "generate",
        "process",
        "validate",
        "scan",
        "fix",
        "commit",
        "push",
        "merge",
        "resolve",
        "post",
        "reply",
        "close",
        "open",
    ]

    found_verbs = [
        verb for verb in action_verbs
        if re.search(rf"\b{verb}\b", content, re.IGNORECASE)
    ]

    # Check for PowerShell script references
    scripts_dir = skill_path / "scripts"
    has_scripts = scripts_dir.exists() and any(scripts_dir.glob("*.py"))

    # Check for tool execution in prompt
    tool_patterns = ["Bash", "Read", "Write", "Edit", "pwsh", "gh ", "git "]
    found_tools = [
        tool for tool in tool_patterns if re.search(re.escape(tool), content)
    ]

    if not found_verbs and not has_scripts and not found_tools:
        return CheckResult(
            passed=False,
            severity="warning",
            message="No action verbs, scripts, or tool execution found",
        )

    return CheckResult(
        passed=True,
        severity="none",
        message=f"Actions found (verbs: {len(found_verbs)}, scripts: {has_scripts})",
    )


def check_passive_context_knowledge_only(file_path: Path) -> CheckResult:
    """Check if passive context file contains knowledge only (no actions)."""
    content = file_path.read_text()

    # Check for action indicators that suggest this should be a skill
    action_indicators = [
        r"```powershell\npwsh ",
        r"```bash\n(?:gh|git) ",
        r"```python\n",
        r"Run the following",
        r"Execute:",
        r"Call.*tool",
        r"Invoke-",
    ]

    found_actions = [
        pattern for pattern in action_indicators if re.search(pattern, content)
    ]

    if found_actions:
        return CheckResult(
            passed=False,
            severity="warning",
            message=f"Contains {len(found_actions)} action pattern(s)",
        )

    return CheckResult(
        passed=True, severity="none", message="Knowledge-only content"
    )


def check_claude_md_line_count(file_path: Path) -> CheckResult:
    """Check if CLAUDE.md is under 200 lines (Anthropic recommendation)."""
    if not file_path.exists():
        return CheckResult(passed=False, severity="error", message="CLAUDE.md not found")

    line_count = len(file_path.read_text().splitlines())

    if line_count > 200:
        return CheckResult(
            passed=False,
            severity="error",
            message=f"CLAUDE.md has {line_count} lines (exceeds 200 limit)",
        )

    if line_count > 150:
        return CheckResult(
            passed=True,
            severity="warning",
            message=f"CLAUDE.md has {line_count} lines (approaching 200 line limit)",
        )

    return CheckResult(
        passed=True,
        severity="none",
        message=f"CLAUDE.md has {line_count} lines (within limit)",
    )


def check_imported_files_exist(
    claude_md_path: Path, repository_root: Path
) -> CheckResult:
    """Check if all @imported files exist and are readable."""
    if not claude_md_path.exists():
        return CheckResult(passed=False, severity="error", message="CLAUDE.md not found")

    content = claude_md_path.read_text()

    # Match @import patterns: @path/to/file.md
    import_pattern = r"@([^\s]+\.md)"
    imports = re.findall(import_pattern, content)

    if not imports:
        return CheckResult(
            passed=True,
            severity="none",
            message="No @imports found",
            details={"imports": []},
        )

    results = []
    for import_path in imports:
        try:
            # Prevent path traversal (CWE-22): reject ../ sequences and absolute paths
            if ".." in import_path or Path(import_path).is_absolute():
                raise PermissionError("Path traversal attempt detected")

            full_path = repository_root / import_path
            exists = full_path.exists()
            readable = False

            if exists:
                try:
                    full_path.read_text()
                    readable = True
                except Exception:
                    pass

            results.append({"path": import_path, "exists": exists, "readable": readable})
        except (PermissionError, ValueError):
            results.append({"path": import_path, "exists": False, "readable": False})

    missing = [r for r in results if not r["exists"]]
    unreadable = [r for r in results if r["exists"] and not r["readable"]]

    if missing:
        paths = ", ".join(r["path"] for r in missing)
        return CheckResult(
            passed=False,
            severity="error",
            message=f"{len(missing)} imported file(s) not found: {paths}",
            details={"imports": results},
        )

    if unreadable:
        paths = ", ".join(r["path"] for r in unreadable)
        return CheckResult(
            passed=False,
            severity="error",
            message=f"{len(unreadable)} imported file(s) not readable: {paths}",
            details={"imports": results},
        )

    return CheckResult(
        passed=True,
        severity="none",
        message=f"All {len(imports)} imported files exist and are readable",
        details={"imports": results},
    )


def check_skill_frontmatter(skill_path: Path) -> CheckResult:
    """Check if skill has required frontmatter."""
    skill_md = skill_path / "SKILL.md"

    if not skill_md.exists():
        return CheckResult(
            passed=False, severity="error", message="SKILL.md not found"
        )

    content = skill_md.read_text()

    # Check for frontmatter start
    if not content.startswith("---\n"):
        return CheckResult(
            passed=False,
            severity="error",
            message="Frontmatter not found (must start with --- on line 1)",
        )

    # Extract frontmatter
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return CheckResult(
            passed=False,
            severity="error",
            message="Frontmatter end delimiter (---) not found",
        )

    frontmatter = match.group(1)

    # Check for required fields
    has_name = re.search(r"^name:\s*\S+|^\s+name:\s*\S+", frontmatter, re.MULTILINE)
    has_description = re.search(
        r"^description:\s*\S+|^\s+description:\s*\S+", frontmatter, re.MULTILINE
    )

    if not has_name:
        return CheckResult(
            passed=False,
            severity="error",
            message="Missing required frontmatter field: name",
        )

    if not has_description:
        return CheckResult(
            passed=False,
            severity="error",
            message="Missing required frontmatter field: description",
        )

    # Validate name format
    name_match = re.search(r"name:\s*([^\r\n]+)", frontmatter)
    if name_match:
        name = name_match.group(1).strip()
        if not re.match(r"^[a-z0-9-]{1,64}$", name):
            return CheckResult(
                passed=False,
                severity="error",
                message=f"Invalid name format: '{name}' (lowercase alphanum+hyphens)",
            )

    return CheckResult(
        passed=True, severity="none", message="Valid frontmatter with required fields"
    )


def check_no_duplicate_content(
    skill_path: Path, passive_context_files: list[Path]
) -> CheckResult:
    """Check for duplicate content between skills and passive context."""
    skill_md = skill_path / "SKILL.md"

    if not skill_md.exists():
        return CheckResult(
            passed=True,
            severity="none",
            message="SKILL.md not found, skipping duplicate check",
        )

    skill_content = skill_md.read_text()

    # Extract significant phrases (3+ words) from skill content
    # Skip frontmatter
    match = re.match(r"^---\n.*?\n---\n(.*)$", skill_content, re.DOTALL)
    skill_body = match.group(1) if match else skill_content

    # Extract phrases (simple heuristic: lines with 20+ chars that aren't code blocks)
    skill_phrases = [
        line.strip()
        for line in skill_body.splitlines()
        if len(line.strip()) > 20
        and not line.strip().startswith("```")
        and not line.strip().startswith("#")
    ]

    duplicates = []

    for passive_file in passive_context_files:
        if not passive_file.exists():
            continue

        passive_content = passive_file.read_text()

        for phrase in skill_phrases:
            if len(phrase) > 30 and phrase in passive_content:
                duplicates.append(
                    {"phrase": phrase[:50], "file": passive_file.name}
                )

    if duplicates:
        return CheckResult(
            passed=False,
            severity="warning",
            message=f"Found {len(duplicates)} potential duplicate phrase(s) in passive context",
            details={"duplicates": duplicates},
        )

    return CheckResult(passed=True, severity="none", message="No obvious duplicates found")


def run_compliance_checks(
    path: Path, claude_md_path: Path
) -> ComplianceResults:
    """Run all compliance checks and return results."""
    repo_root = find_repository_root()
    full_path = path if path.is_absolute() else repo_root / path
    full_claude_md_path = (
        claude_md_path if claude_md_path.is_absolute() else repo_root / claude_md_path
    )

    results = ComplianceResults(
        timestamp=datetime.now().isoformat(),
        path=str(path),
        claude_md_path=str(claude_md_path),
    )

    # Check 1: CLAUDE.md line count
    results.summary["total_checks"] += 1
    line_check = check_claude_md_line_count(full_claude_md_path)

    if line_check.passed:
        results.summary["passed"] += 1
        if line_check.severity == "warning":
            results.warnings.append(
                {"check": "CLAUDE.md Line Count", "message": line_check.message}
            )
            results.summary["warnings"] += 1
    else:
        results.summary["failed"] += 1
        results.violations.append(
            {
                "check": "CLAUDE.md Line Count",
                "severity": line_check.severity,
                "message": line_check.message,
                "recommendation": "Split content into separate files and use @imports",
            }
        )

    # Check 2: @imported files exist
    results.summary["total_checks"] += 1
    import_check = check_imported_files_exist(full_claude_md_path, repo_root)

    if import_check.passed:
        results.summary["passed"] += 1
    else:
        results.summary["failed"] += 1
        results.violations.append(
            {
                "check": "@Imported Files Exist",
                "severity": import_check.severity,
                "message": import_check.message,
                "recommendation": "Create missing files or remove @import directives",
            }
        )

    # Get passive context files for duplicate checking
    passive_context_files = [full_claude_md_path]
    if import_check.details.get("imports"):
        for import_info in import_check.details["imports"]:
            if import_info["exists"]:
                passive_context_files.append(repo_root / import_info["path"])

    # Check 3-6: Passive context files (knowledge-only check)
    for file in passive_context_files:
        if file.exists():
            results.summary["total_checks"] += 1
            passive_check = check_passive_context_knowledge_only(file)

            if passive_check.passed:
                results.summary["passed"] += 1
            else:
                if passive_check.severity == "warning":
                    results.summary["warnings"] += 1
                    results.warnings.append(
                        {
                            "check": f"Passive Context Knowledge-Only ({file.name})",
                            "message": passive_check.message,
                        }
                    )
                    results.recommendations.append(
                        f"Extract action patterns from {file.name} to a skill"
                    )
                else:
                    results.summary["failed"] += 1
                    results.violations.append(
                        {
                            "check": f"Passive Context Knowledge-Only ({file.name})",
                            "severity": passive_check.severity,
                            "message": passive_check.message,
                            "recommendation": "Extract action patterns to a skill",
                        }
                    )

    # Check 4-6: Skills (if scanning skills directory)
    if full_path.exists():
        skill_dirs = [
            d
            for d in full_path.iterdir()
            if d.is_dir() and (d / "SKILL.md").exists()
        ]

        for skill_dir in skill_dirs:
            skill_name = skill_dir.name

            # Check: Skill has actions
            results.summary["total_checks"] += 1
            action_check = check_skill_has_actions(skill_dir)

            if action_check.passed:
                results.summary["passed"] += 1
            else:
                if action_check.severity == "warning":
                    results.summary["warnings"] += 1
                    results.warnings.append(
                        {
                            "check": f"Skill Has Actions ({skill_name})",
                            "message": action_check.message,
                        }
                    )
                    results.recommendations.append(
                        f"Consider moving {skill_name} to passive context (SKILL-QUICK-REF.md)"
                    )
                else:
                    results.summary["failed"] += 1
                    results.violations.append(
                        {
                            "check": f"Skill Has Actions ({skill_name})",
                            "severity": action_check.severity,
                            "message": action_check.message,
                            "recommendation": f"Add scripts to {skill_name}",
                        }
                    )

            # Check: Skill has required frontmatter
            results.summary["total_checks"] += 1
            frontmatter_check = check_skill_frontmatter(skill_dir)

            if frontmatter_check.passed:
                results.summary["passed"] += 1
            else:
                results.summary["failed"] += 1
                results.violations.append(
                    {
                        "check": f"Skill Frontmatter ({skill_name})",
                        "severity": frontmatter_check.severity,
                        "message": frontmatter_check.message,
                        "recommendation": f"Add frontmatter to {skill_name}/SKILL.md",
                    }
                )

            # Check: No duplicate content
            results.summary["total_checks"] += 1
            duplicate_check = check_no_duplicate_content(
                skill_dir, passive_context_files
            )

            if duplicate_check.passed:
                results.summary["passed"] += 1
            else:
                results.summary["warnings"] += 1
                results.warnings.append(
                    {
                        "check": f"No Duplicate Content ({skill_name})",
                        "message": duplicate_check.message,
                    }
                )
                results.recommendations.append(
                    f"Review {skill_name} for content that duplicates passive context"
                )

    return results


def print_table_format(results: ComplianceResults) -> None:
    """Print results in human-readable table format."""
    print("\nSkill/Passive Context Compliance Check")
    print("=" * 70)
    print(f"Timestamp: {results.timestamp}")
    print(f"Path: {results.path}")
    print(f"CLAUDE.md: {results.claude_md_path}")
    print()

    print("Summary:")
    print(f"  Total Checks: {results.summary['total_checks']}")
    print(f"  Passed: {results.summary['passed']}")
    print(f"  Failed: {results.summary['failed']}")
    print(f"  Warnings: {results.summary['warnings']}")

    if results.violations:
        print("\nViolations:")
        for violation in results.violations:
            print(f"  ❌ {violation['check']}")
            print(f"     Severity: {violation['severity'].upper()}")
            print(f"     Issue: {violation['message']}")
            print(f"     Fix: {violation['recommendation']}")
            print()

    if results.warnings:
        print("\nWarnings:")
        for warning in results.warnings:
            print(f"  ⚠️  {warning['check']}")
            print(f"     {warning['message']}")
            print()

    if results.recommendations:
        print("\nRecommendations:")
        for rec in results.recommendations:
            print(f"  💡 {rec}")

    print()
    if results.summary["failed"] == 0:
        print("[PASS] All compliance checks passed")
    else:
        print("[FAIL] Compliance violations detected")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate skill and passive context placement compliance"
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path(".claude"),
        help="Directory to scan (default: .claude)",
    )
    parser.add_argument(
        "--claude-md-path",
        type=Path,
        default=Path("CLAUDE.md"),
        help="Path to CLAUDE.md (default: CLAUDE.md)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="json",
        help="Output format (default: json)",
    )

    args = parser.parse_args()

    try:
        results = run_compliance_checks(args.path, args.claude_md_path)

        if args.format == "table":
            print_table_format(results)
        else:
            # Convert dataclass to dict for JSON serialization
            output = {
                "timestamp": results.timestamp,
                "path": results.path,
                "claudeMdPath": results.claude_md_path,
                "violations": results.violations,
                "warnings": results.warnings,
                "recommendations": results.recommendations,
                "summary": results.summary,
            }
            print(json.dumps(output, indent=2))

        return 1 if results.summary["failed"] > 0 else 0

    except Exception as e:
        print(f"Compliance check failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
