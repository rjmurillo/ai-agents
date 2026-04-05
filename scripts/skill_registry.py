#!/usr/bin/env python3
"""Generate a skill registry with metadata for all skills in .claude/skills/.

Scans skill directories, extracts YAML frontmatter from SKILL.md files,
and determines last-used dates from git history. Outputs JSON or markdown.

EXIT CODES:
  0  - Success: Registry generated
  1  - Error: Logic or validation error
  2  - Error: Configuration or path error

See: ADR-035 Exit Code Standardization
See: Issue #1266 - Implement skill utilization tracking
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
_SKILLS_DIR = _PROJECT_ROOT / ".claude" / "skills"

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.utils.path_validation import validate_safe_path  # noqa: E402


@dataclass(frozen=True)
class SkillMetadata:
    """Metadata extracted from a single skill directory."""

    name: str
    path: str
    description: str
    category: str
    last_modified: str
    model: str
    has_tests: bool
    has_scripts: bool
    file_count: int


def parse_frontmatter(skill_md: Path) -> dict[str, str]:
    """Extract YAML frontmatter fields from a SKILL.md file.

    Parses the region between the opening and closing '---' delimiters.
    Returns a flat dict of key-value pairs (no nested parsing).

    Args:
        skill_md: Path to a SKILL.md file.

    Returns:
        Dict of frontmatter key-value pairs.
    """
    text = skill_md.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    try:
        end_index = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration:
        return {}

    frontmatter: dict[str, str] = {}
    for line in lines[1:end_index]:
        stripped = line.strip()
        if ":" in stripped and not stripped.startswith("-"):
            key, _, value = stripped.partition(":")
            frontmatter[key.strip()] = value.strip()
    return frontmatter


def get_last_modified_date(path: Path, project_root: Path) -> str:
    """Get the most recent git commit date for any file under path.

    Args:
        path: Directory or file to check.
        project_root: Git repository root.

    Returns:
        ISO date string (YYYY-MM-DD) or "unknown" if git fails.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                "-1",
                "--format=%aI",
                "--",
                str(path.relative_to(project_root)),
            ],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            dt = datetime.fromisoformat(result.stdout.strip())
            return dt.strftime("%Y-%m-%d")
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return "unknown"


def categorize_skill(name: str, description: str) -> str:
    """Assign a category based on skill name and description keywords.

    Categories: process, implementation, analysis, documentation,
    security, memory, infrastructure, workflow, other.

    Args:
        name: Skill directory name.
        description: Skill description from frontmatter.

    Returns:
        Category string.
    """
    combined = f"{name} {description}".lower()

    category_keywords = {
        "security": ["security", "threat", "owasp", "cwe", "codeql", "vulnerability"],
        "memory": ["memory", "forgetful", "serena", "knowledge", "curating"],
        "analysis": [
            "analy",
            "critic",
            "review",
            "assess",
            "audit",
            "incoherence",
            "qualities",
        ],
        "documentation": ["doc", "explain", "coverage"],
        "workflow": ["workflow", "session", "pipeline", "ci/cd", "devops"],
        "process": [
            "plan",
            "brainstorm",
            "debug",
            "reflect",
            "pre-mortem",
            "decision",
            "cynefin",
        ],
        "infrastructure": [
            "install",
            "config",
            "github",
            "git-advanced",
            "merge",
            "style",
            "validation",
            "fix-markdown",
        ],
        "implementation": [
            "implement",
            "build",
            "cva",
            "encode",
            "prompt-engineer",
            "slashcommand",
        ],
    }

    for category, keywords in category_keywords.items():
        if any(kw in combined for kw in keywords):
            return category
    return "other"


def scan_skill(skill_dir: Path, project_root: Path) -> SkillMetadata:
    """Extract metadata from a single skill directory.

    Args:
        skill_dir: Path to the skill directory.
        project_root: Git repository root.

    Returns:
        SkillMetadata for the skill.
    """
    skill_md = skill_dir / "SKILL.md"
    frontmatter = parse_frontmatter(skill_md) if skill_md.exists() else {}

    name = frontmatter.get("name", skill_dir.name)
    description = frontmatter.get("description", "")
    model = frontmatter.get("model", "")
    category = categorize_skill(name, description)
    last_modified = get_last_modified_date(skill_dir, project_root)
    has_tests = (skill_dir / "tests").is_dir() and any((skill_dir / "tests").iterdir())
    has_scripts = (skill_dir / "scripts").is_dir() and any((skill_dir / "scripts").iterdir())

    all_files = list(skill_dir.rglob("*"))
    file_count = sum(1 for f in all_files if f.is_file() and f.name != "CLAUDE.md")

    return SkillMetadata(
        name=name,
        path=str(skill_dir.relative_to(project_root)),
        description=description[:120] if description else "",
        category=category,
        last_modified=last_modified,
        model=model,
        has_tests=has_tests,
        has_scripts=has_scripts,
        file_count=file_count,
    )


def build_registry(skills_dir: Path, project_root: Path) -> list[SkillMetadata]:
    """Scan all skill directories and build the registry.

    Args:
        skills_dir: Path to .claude/skills/.
        project_root: Git repository root.

    Returns:
        List of SkillMetadata sorted by name.
    """
    skills: list[SkillMetadata] = []
    for entry in sorted(skills_dir.iterdir()):
        if entry.is_symlink():
            continue
        if not entry.is_dir():
            continue
        if entry.name.startswith(".") or entry.name == "__pycache__":
            continue
        skills.append(scan_skill(entry, project_root))
    return skills


def format_json(skills: list[SkillMetadata]) -> str:
    """Format registry as JSON.

    Args:
        skills: List of skill metadata.

    Returns:
        JSON string.
    """
    payload = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%d"),
        "skills": [asdict(s) for s in skills],
    }
    return json.dumps(payload, indent=2)


def format_markdown(skills: list[SkillMetadata]) -> str:
    """Format registry as a markdown table.

    Args:
        skills: List of skill metadata.

    Returns:
        Markdown string.
    """
    lines = [
        "# Skill Registry",
        "",
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d')}",
        f"Total skills: {len(skills)}",
        "",
        "| Name | Category | Last Modified | Model | Tests | Files |",
        "|------|----------|---------------|-------|-------|-------|",
    ]
    for s in skills:
        tests = "Y" if s.has_tests else "N"
        lines.append(
            f"| {s.name} | {s.category} | {s.last_modified} "
            f"| {s.model or '-'} | {tests} | {s.file_count} |"
        )

    # Category summary
    categories: dict[str, int] = {}
    for s in skills:
        categories[s.category] = categories.get(s.category, 0) + 1

    lines.extend(["", "## By Category", ""])
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        lines.append(f"- **{cat}**: {count} skills")

    return "\n".join(lines) + "\n"


def format_session_message(stale_skills: list[SkillMetadata], stale_days: int) -> str:
    """Format a session-ready message listing underutilized skills.

    Designed for integration with session-init or reflect skills.
    Outputs a concise notification when stale skills exist, or empty
    string when all skills are recently used.

    Args:
        stale_skills: Skills not modified within the threshold.
        stale_days: Threshold in days.

    Returns:
        Session message string, or empty string if no stale skills.
    """
    if not stale_skills:
        return ""
    names = ", ".join(s.name for s in stale_skills[:10])
    remaining = len(stale_skills) - 10
    msg = f"These skills haven't been used in {stale_days}+ days: {names}"
    if remaining > 0:
        msg += f" (and {remaining} more)"
    return msg


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=None,
        help="Path to skills directory (defaults to .claude/skills/)",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root directory (defaults to auto-detection)",
    )
    def _non_negative_int(value: str) -> int:
        parsed = int(value)
        if parsed < 0:
            raise argparse.ArgumentTypeError("--stale-days must be >= 0")
        return parsed

    parser.add_argument(
        "--stale-days",
        type=_non_negative_int,
        default=30,
        help="Days without modification to consider a skill stale (default: 30)",
    )
    parser.add_argument(
        "--show-stale",
        action="store_true",
        help="Only show skills not modified in --stale-days",
    )
    parser.add_argument(
        "--session-message",
        action="store_true",
        help="Output a session-ready message about stale skills for session integration",
    )
    return parser.parse_args(argv)


def filter_stale(skills: list[SkillMetadata], stale_days: int) -> list[SkillMetadata]:
    """Filter skills to only those not modified within stale_days.

    Args:
        skills: Full skill list.
        stale_days: Threshold in days.

    Returns:
        Skills older than the threshold.
    """
    from datetime import timedelta

    cutoff_date = (datetime.now(UTC) - timedelta(days=stale_days)).strftime("%Y-%m-%d")

    return [s for s in skills if s.last_modified != "unknown" and s.last_modified <= cutoff_date]


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Argument list for testing.

    Returns:
        Exit code.
    """
    try:
        args = parse_args(argv)

        project_root = Path(args.project_root or _PROJECT_ROOT).resolve()

        raw_skills_dir = Path(args.skills_dir or (project_root / ".claude" / "skills"))
        try:
            skills_dir = validate_safe_path(raw_skills_dir, project_root)
        except (ValueError, FileNotFoundError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

        if not skills_dir.is_dir():
            print(
                f"ERROR: Skills directory not found: {skills_dir}",
                file=sys.stderr,
            )
            return 2

        skills = build_registry(skills_dir, project_root)

        if args.session_message:
            stale = filter_stale(skills, args.stale_days)
            msg = format_session_message(stale, args.stale_days)
            if msg:
                print(msg)
            return 0

        if args.show_stale:
            skills = filter_stale(skills, args.stale_days)
            if not skills:
                print(
                    f"No skills older than {args.stale_days} days.",
                    file=sys.stderr,
                )

        if args.format == "json":
            print(format_json(skills))
        else:
            print(format_markdown(skills))

        return 0

    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 1
    except (OSError, subprocess.SubprocessError) as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
