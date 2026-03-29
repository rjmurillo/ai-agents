#!/usr/bin/env python3
"""Skill registry for tracking skill metadata and utilization.

Scans .claude/skills/ directory and extracts metadata from SKILL.md frontmatter.
Reports skill inventory with categories, last-modified dates, and usage estimates
based on git history.

EXIT CODES:
  0  - Success: Registry generated or list completed
  1  - Error: Invalid parameters or skill directory not found
  2  - Error: Unexpected error

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add project root to path for imports
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))


@dataclass
class SkillMetadata:
    """Metadata for a single skill."""

    name: str
    path: Path
    description: str = ""
    version: str = ""
    model: str = ""
    license: str = ""
    last_modified: datetime | None = None
    git_commits_30d: int = 0
    category: str = "uncategorized"
    extra: dict[str, Any] = field(default_factory=dict)


def parse_yaml_frontmatter(content: str) -> dict[str, Any]:
    """Parse YAML frontmatter from SKILL.md content.

    Args:
        content: The full content of a SKILL.md file.

    Returns:
        Dictionary of frontmatter key-value pairs.
    """
    # Match YAML frontmatter between --- delimiters
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}

    frontmatter_text = match.group(1)
    result: dict[str, Any] = {}

    # Simple YAML parsing for common skill frontmatter fields
    for line in frontmatter_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Handle key: value pairs
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()

            # Remove quotes if present
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]

            result[key] = value

    return result


def get_git_commits_count(skill_path: Path, days: int = 30) -> int:
    """Count git commits touching a skill directory in the last N days.

    Args:
        skill_path: Path to the skill directory.
        days: Number of days to look back.

    Returns:
        Number of commits touching files in the skill directory.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                "--oneline",
                f"--since={days} days ago",
                "--",
                str(skill_path),
            ],
            capture_output=True,
            text=True,
            cwd=_PROJECT_ROOT,
            timeout=30,
        )
        if result.returncode == 0:
            lines = [line for line in result.stdout.strip().split("\n") if line]
            return len(lines)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return 0


def get_last_modified_date(skill_path: Path) -> datetime | None:
    """Get the last modified date for a skill from git history.

    Args:
        skill_path: Path to the skill directory.

    Returns:
        Datetime of last modification, or None if not available.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                "-1",
                "--format=%cI",
                "--",
                str(skill_path),
            ],
            capture_output=True,
            text=True,
            cwd=_PROJECT_ROOT,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return datetime.fromisoformat(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return None


def infer_category(skill_name: str, description: str) -> str:
    """Infer a category for a skill based on name and description.

    Args:
        skill_name: The skill's name.
        description: The skill's description.

    Returns:
        Inferred category string.
    """
    name_lower = skill_name.lower()
    desc_lower = description.lower()

    # Category inference rules
    if any(kw in name_lower for kw in ["github", "pr-", "issue", "merge"]):
        return "github"
    if any(kw in name_lower for kw in ["session", "workflow"]):
        return "workflow"
    if any(kw in name_lower for kw in ["memory", "serena", "forgetful"]):
        return "memory"
    if any(kw in name_lower for kw in ["security", "codeql", "threat"]):
        return "security"
    if any(kw in name_lower for kw in ["doc", "explain"]):
        return "documentation"
    if any(kw in name_lower for kw in ["adr", "architect", "decision"]):
        return "architecture"
    if any(kw in name_lower for kw in ["test", "qa", "quality"]):
        return "quality"
    if any(kw in name_lower for kw in ["plan", "roadmap", "milestone"]):
        return "planning"
    if any(kw in desc_lower for kw in ["analyze", "analysis", "assess"]):
        return "analysis"

    return "utility"


def scan_skills(skills_dir: Path) -> list[SkillMetadata]:
    """Scan the skills directory and extract metadata from each skill.

    Args:
        skills_dir: Path to the .claude/skills directory.

    Returns:
        List of SkillMetadata objects for each discovered skill.
    """
    skills: list[SkillMetadata] = []

    if not skills_dir.exists():
        return skills

    for skill_path in sorted(skills_dir.iterdir()):
        if not skill_path.is_dir():
            continue

        # Skip non-skill directories
        if skill_path.name.startswith(".") or skill_path.name == "__pycache__":
            continue

        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            # Still track directories without SKILL.md
            skills.append(
                SkillMetadata(
                    name=skill_path.name,
                    path=skill_path,
                    description="No SKILL.md found",
                    category="uncategorized",
                )
            )
            continue

        # Parse frontmatter
        try:
            content = skill_md.read_text(encoding="utf-8")
            frontmatter = parse_yaml_frontmatter(content)
        except (OSError, UnicodeDecodeError):
            frontmatter = {}

        name = frontmatter.get("name", skill_path.name)
        description = frontmatter.get("description", "")

        skill = SkillMetadata(
            name=name,
            path=skill_path,
            description=description[:200] if description else "",
            version=frontmatter.get("version", ""),
            model=frontmatter.get("model", ""),
            license=frontmatter.get("license", ""),
            last_modified=get_last_modified_date(skill_path),
            git_commits_30d=get_git_commits_count(skill_path),
            category=infer_category(name, description),
        )

        # Store any extra frontmatter fields
        known_keys = {"name", "description", "version", "model", "license", "metadata"}
        skill.extra = {k: v for k, v in frontmatter.items() if k not in known_keys}

        skills.append(skill)

    return skills


def format_summary(skills: list[SkillMetadata]) -> str:
    """Format a summary of skills.

    Args:
        skills: List of skill metadata.

    Returns:
        Formatted summary string.
    """
    lines = [
        f"Skill Registry: {len(skills)} skills found",
        "=" * 50,
        "",
    ]

    # Group by category
    by_category: dict[str, list[SkillMetadata]] = {}
    for skill in skills:
        by_category.setdefault(skill.category, []).append(skill)

    for category in sorted(by_category.keys()):
        cat_skills = by_category[category]
        lines.append(f"## {category.title()} ({len(cat_skills)})")
        lines.append("")

        for skill in sorted(cat_skills, key=lambda s: s.name):
            last_mod = ""
            if skill.last_modified:
                last_mod = skill.last_modified.strftime("%Y-%m-%d")
            if skill.git_commits_30d:
                commits = f"({skill.git_commits_30d} commits/30d)"
            else:
                commits = "(inactive)"
            lines.append(f"  - {skill.name}: {last_mod} {commits}")
            if skill.description:
                if len(skill.description) > 80:
                    desc = skill.description[:80] + "..."
                else:
                    desc = skill.description
                lines.append(f"    {desc}")
        lines.append("")

    # Underutilized skills (no commits in 30 days)
    inactive = [s for s in skills if s.git_commits_30d == 0 and s.last_modified]
    if inactive:
        lines.append("## Underutilized Skills (0 commits in 30 days)")
        lines.append("")
        for skill in sorted(inactive, key=lambda s: s.last_modified or datetime.min):
            if skill.last_modified:
                last_mod = skill.last_modified.strftime("%Y-%m-%d")
            else:
                last_mod = "unknown"
            lines.append(f"  - {skill.name}: last modified {last_mod}")
        lines.append("")

    return "\n".join(lines)


def _format_path(path: Path) -> str:
    """Format a path as a relative string if possible.

    Args:
        path: The path to format.

    Returns:
        Relative path string if within project root, otherwise absolute path.
    """
    if path.is_relative_to(_PROJECT_ROOT):
        return str(path.relative_to(_PROJECT_ROOT))
    return str(path)


def format_json(skills: list[SkillMetadata]) -> str:
    """Format skills as JSON.

    Args:
        skills: List of skill metadata.

    Returns:
        JSON string representation.
    """
    # Group by category
    by_category: dict[str, list[str]] = {}
    for skill in skills:
        cat = skill.category
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(skill.name)

    # Underutilized
    underutilized = [s.name for s in skills if s.git_commits_30d == 0]

    data: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_skills": len(skills),
        "skills": [
            {
                "name": s.name,
                "path": _format_path(s.path),
                "description": s.description,
                "version": s.version,
                "model": s.model,
                "license": s.license,
                "last_modified": s.last_modified.isoformat() if s.last_modified else None,
                "git_commits_30d": s.git_commits_30d,
                "category": s.category,
            }
            for s in skills
        ],
        "by_category": by_category,
        "underutilized": underutilized,
    }

    return json.dumps(data, indent=2)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--output",
        choices=["summary", "json"],
        default="summary",
        help="Output format (default: summary)",
    )

    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=None,
        help="Skills directory (default: .claude/skills)",
    )

    parser.add_argument(
        "--underutilized-only",
        action="store_true",
        help="Only show skills with 0 commits in the last 30 days",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point. Returns exit code.

    Returns:
        0 on success, 1 if skills directory not found, 2 on unexpected error.
    """
    try:
        args = parse_args()

        # Determine skills directory
        skills_dir = args.skills_dir or (_PROJECT_ROOT / ".claude" / "skills")

        if not skills_dir.exists():
            print(f"ERROR: Skills directory not found: {skills_dir}", file=sys.stderr)
            return 1

        # Scan skills
        skills = scan_skills(skills_dir)

        if not skills:
            print("No skills found.", file=sys.stderr)
            return 1

        # Filter if requested
        if args.underutilized_only:
            skills = [s for s in skills if s.git_commits_30d == 0]

        # Output
        if args.output == "json":
            print(format_json(skills))
        else:
            print(format_summary(skills))

        return 0

    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
