#!/usr/bin/env python3
"""Audit skill modularity based on SkillsBench research findings.

SkillsBench (Feb 2026) found that smaller, modular skills (2-3 modules)
significantly outperform large data dumps. This script audits all skills
in .claude/skills/ and produces a report with modularity scores and
refactoring recommendations.

Modularity scoring:
    - Lines: penalized above 300 (warning) and 500 (error) thresholds
    - Section density: high h2 count relative to size signals mixed concerns
    - Progressive disclosure: rewarded for using scripts/, references/, templates/
    - Focus: penalized for excessive top-level sections (>10 h2 headings)

Exit codes follow ADR-035:
    0 - Success
    1 - Oversized skills found (CI mode)

Related: Issue #1267 (SkillsBench-informed skill modularity audit)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Add script directory to path for sibling imports
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parents[3]
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_PROJECT_ROOT))

from frontmatter import has_size_exception  # noqa: E402

# Thresholds aligned with skill_size.py
LINE_LIMIT: int = 500
LINE_WARNING: int = 300

# Modularity thresholds
MAX_H2_SECTIONS: int = 10
IDEAL_MAX_LINES: int = 300


@dataclass
class SkillAuditResult:
    """Audit result for a single skill."""

    name: str
    file_path: str
    line_count: int
    h2_count: int
    h3_count: int
    has_scripts: bool
    has_references: bool
    has_templates: bool
    has_modules: bool
    has_size_exception: bool
    modularity_score: int  # 0-100, higher is better
    rating: str  # "good", "warning", "oversized"
    recommendations: list[str] = field(default_factory=list)


def _count_headings(content: str) -> tuple[int, int]:
    """Count h2 and h3 headings in markdown content."""
    h2 = len(re.findall(r"^## ", content, re.MULTILINE))
    h3 = len(re.findall(r"^### ", content, re.MULTILINE))
    return h2, h3


def _score_modularity(
    line_count: int,
    h2_count: int,
    has_scripts: bool,
    has_references: bool,
    has_templates: bool,
    has_modules: bool,
) -> int:
    """Calculate modularity score (0-100).

    Higher score means better modularity. Factors:
    - Size penalty: lines above IDEAL_MAX_LINES reduce score
    - Section focus: too many h2 sections reduce score
    - Progressive disclosure bonus: subdirectories add score
    """
    score = 100

    # Size penalty: -1 point per 10 lines above ideal
    if line_count > IDEAL_MAX_LINES:
        overage = line_count - IDEAL_MAX_LINES
        score -= min(overage // 10, 40)

    # Section focus penalty: -3 per h2 above threshold
    if h2_count > MAX_H2_SECTIONS:
        score -= (h2_count - MAX_H2_SECTIONS) * 3

    # Progressive disclosure bonus
    if has_scripts:
        score += 5
    if has_references:
        score += 5
    if has_templates:
        score += 3
    if has_modules:
        score += 5

    return max(0, min(100, score))


def _generate_recommendations(result: SkillAuditResult) -> list[str]:
    """Generate refactoring recommendations for a skill."""
    recs: list[str] = []

    if result.line_count > LINE_LIMIT and not result.has_size_exception:
        recs.append(
            f"Exceeds {LINE_LIMIT}-line limit ({result.line_count} lines). "
            f"Extract reference material to references/ subdirectory."
        )

    if result.line_count > LINE_WARNING and not result.has_references:
        recs.append(
            "Add references/ subdirectory for lookup tables, examples, and detailed documentation."
        )

    if result.h2_count > MAX_H2_SECTIONS:
        recs.append(
            f"Has {result.h2_count} top-level sections (target: <={MAX_H2_SECTIONS}). "
            f"Consider splitting into focused sub-skills."
        )

    if result.line_count > LINE_WARNING and not result.has_scripts:
        recs.append("Extract procedural logic to scripts/ subdirectory.")

    return recs


def audit_skill(skill_dir: Path) -> SkillAuditResult | None:
    """Audit a single skill directory."""
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return None

    content = skill_file.read_text(encoding="utf-8")
    line_count = len(content.splitlines())
    h2_count, h3_count = _count_headings(content)
    has_exception = has_size_exception(content)

    has_scripts = (skill_dir / "scripts").is_dir()
    has_references = (skill_dir / "references").is_dir()
    has_templates = (skill_dir / "templates").is_dir()
    has_modules = (skill_dir / "modules").is_dir()

    modularity_score = _score_modularity(
        line_count,
        h2_count,
        has_scripts,
        has_references,
        has_templates,
        has_modules,
    )

    if line_count > LINE_LIMIT and not has_exception:
        rating = "oversized"
    elif line_count > LINE_WARNING or modularity_score < 60:
        rating = "warning"
    else:
        rating = "good"

    result = SkillAuditResult(
        name=skill_dir.name,
        file_path=str(skill_file),
        line_count=line_count,
        h2_count=h2_count,
        h3_count=h3_count,
        has_scripts=has_scripts,
        has_references=has_references,
        has_templates=has_templates,
        has_modules=has_modules,
        has_size_exception=has_exception,
        modularity_score=modularity_score,
        rating=rating,
    )
    result.recommendations = _generate_recommendations(result)
    return result


def audit_all_skills(skills_path: Path) -> list[SkillAuditResult]:
    """Audit all skills in the given directory."""
    results: list[SkillAuditResult] = []
    if not skills_path.is_dir():
        return results

    for skill_dir in sorted(skills_path.iterdir()):
        if not skill_dir.is_dir():
            continue
        result = audit_skill(skill_dir)
        if result:
            results.append(result)

    return results


def print_report(results: list[SkillAuditResult]) -> None:
    """Print a human-readable audit report."""
    if not results:
        print("No skills found to audit.")
        return

    oversized = [r for r in results if r.rating == "oversized"]
    warnings = [r for r in results if r.rating == "warning"]
    good = [r for r in results if r.rating == "good"]

    print("=" * 60)
    print("Skill Modularity Audit Report")
    print("=" * 60)
    print(f"Total skills: {len(results)}")
    print(f"Good:         {len(good)}")
    print(f"Warning:      {len(warnings)}")
    print(f"Oversized:    {len(oversized)}")
    print()

    if oversized:
        print("-" * 60)
        print("OVERSIZED (exceed 500-line limit)")
        print("-" * 60)
        for r in sorted(oversized, key=lambda x: -x.line_count):
            print(f"  {r.name}: {r.line_count} lines, score={r.modularity_score}")
            for rec in r.recommendations:
                print(f"    -> {rec}")
        print()

    if warnings:
        print("-" * 60)
        print("WARNING (300-500 lines or low modularity score)")
        print("-" * 60)
        for r in sorted(warnings, key=lambda x: -x.line_count):
            print(f"  {r.name}: {r.line_count} lines, score={r.modularity_score}")
            for rec in r.recommendations:
                print(f"    -> {rec}")
        print()

    print("-" * 60)
    print("ALL SKILLS (sorted by modularity score)")
    print("-" * 60)
    for r in sorted(results, key=lambda x: x.modularity_score):
        marker = {"oversized": "[!]", "warning": "[~]", "good": "[+]"}[r.rating]
        print(
            f"  {marker} {r.name:40s} "
            f"{r.line_count:4d} lines  "
            f"score={r.modularity_score:3d}  "
            f"h2={r.h2_count}"
        )
    print()


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="Audit skill modularity based on SkillsBench research.",
    )
    parser.add_argument(
        "--path",
        default=".claude/skills",
        help="Path to skills directory (default: .claude/skills)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI mode: exit non-zero if oversized skills found",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    return parser


def validate_path_safety(raw_path: str) -> Path | None:
    """Validate a CLI path argument against traversal attacks (CWE-22).

    Allows absolute paths (resolved). Blocks '..' in relative paths.

    Returns:
        Resolved Path if safe, None if traversal detected.
    """
    input_path = Path(raw_path)
    if input_path.is_absolute():
        return input_path.resolve()
    if ".." in input_path.parts:
        return None
    return (Path.cwd() / input_path).resolve()


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    skills_path = validate_path_safety(args.path)
    if skills_path is None:
        print(
            f"Error: Relative path traversal attempt detected. "
            f"Path '{args.path}' contains '..'.",
            file=sys.stderr,
        )
        return 2

    if not skills_path.is_dir():
        print(f"Skills directory not found: {skills_path}", file=sys.stderr)
        return 2

    results = audit_all_skills(skills_path)

    if args.json_output:
        print(json.dumps([asdict(r) for r in results], indent=2))
    else:
        print_report(results)

    oversized = [r for r in results if r.rating == "oversized"]
    if oversized and args.ci:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
