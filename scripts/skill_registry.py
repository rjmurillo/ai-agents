#!/usr/bin/env python3
"""Generate a skill utilization registry from .claude/skills/.

Scans all skills, extracts SKILL.md frontmatter metadata, estimates last-used
dates from git history, and outputs a JSON or markdown registry report.

EXIT CODES:
  0  - Success: Registry generated
  1  - Error: No skills found
  2  - Error: Configuration/path error or unexpected failure

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

# Days threshold for underutilized skill detection
_STALE_DAYS_DEFAULT = 30


@dataclass
class SkillEntry:
    """Registry entry for a single skill."""

    name: str
    path: str
    description: str = ""
    version: str = ""
    model: str = ""
    category: str = ""
    last_commit_date: str = ""
    last_commit_days_ago: int = -1


def parse_frontmatter(skill_md: Path) -> dict[str, str]:
    """Extract YAML frontmatter key-value pairs from a SKILL.md file.

    Only handles simple scalar values (no nested YAML). Stops at the
    closing --- delimiter.

    Args:
        skill_md: Path to the SKILL.md file.

    Returns:
        Dictionary of frontmatter key-value pairs.
    """
    result: dict[str, str] = {}
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return result

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return result

    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if key and value:
            result[key] = value

    return result


def git_last_commit_date(path: Path, project_root: Path) -> str | None:
    """Get the ISO date of the most recent commit touching a path.

    Args:
        path: File or directory path to check.
        project_root: Repository root for running git commands.

    Returns:
        ISO date string (YYYY-MM-DD) or None if no history found.
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
            cwd=str(project_root),
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()[:10]
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def categorize_skill(name: str) -> str:
    """Assign a category to a skill based on its name.

    Args:
        name: The skill directory name.

    Returns:
        A category string.
    """
    categories = {
        "session": ["session", "session-init", "session-end", "session-log-fixer",
                     "session-migration", "session-qa-eligibility"],
        "memory": ["memory", "memory-documentary", "memory-enhancement",
                    "curating-memories", "using-forgetful-memory",
                    "exploring-knowledge-graph", "encode-repo-serena",
                    "using-serena-symbols", "serena-code-architecture"],
        "security": ["security-scan", "security-detection", "threat-modeling",
                      "codeql-scan"],
        "quality": ["analyze", "code-qualities-assessment", "quality-grades",
                     "golden-principles", "taste-lints", "style-enforcement",
                     "incoherence", "doc-accuracy", "doc-coverage", "doc-sync"],
        "planning": ["planner", "execution-plans", "cynefin-classifier",
                      "pre-mortem", "cva-analysis", "decision-critic"],
        "github": ["github", "github-url-intercept", "pr-comment-responder",
                    "merge-resolver", "fix-markdown-fences"],
        "devops": ["pipeline-validator", "observability", "slo-designer",
                    "chaos-experiment", "context-optimizer", "validation-authority"],
        "meta": ["SkillForge", "slashcommandcreator", "reflect", "metrics",
                 "steering-matcher", "prompt-engineer"],
        "workflow": ["workflow", "git-advanced-workflows",
                     "windows-image-updater"],
        "research": ["research-and-incorporate", "programming-advisor",
                      "buy-vs-build-framework", "analysis-provenance",
                      "chestertons-fence"],
    }
    for category, names in categories.items():
        if name in names:
            return category
    return "other"


def scan_skills(
    skills_dir: Path,
    project_root: Path,
) -> list[SkillEntry]:
    """Scan the skills directory and build registry entries.

    Args:
        skills_dir: Path to .claude/skills/.
        project_root: Repository root.

    Returns:
        List of SkillEntry objects sorted by name.
    """
    entries: list[SkillEntry] = []
    now = datetime.now(tz=UTC)

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue

        skill_md = skill_dir / "SKILL.md"
        fm = parse_frontmatter(skill_md) if skill_md.exists() else {}

        name = fm.get("name", skill_dir.name)
        last_date = git_last_commit_date(skill_dir, project_root)
        days_ago = -1
        if last_date:
            try:
                commit_dt = datetime.strptime(last_date, "%Y-%m-%d").replace(
                    tzinfo=UTC
                )
                days_ago = (now - commit_dt).days
            except ValueError:
                pass

        entry = SkillEntry(
            name=name,
            path=str(skill_dir.relative_to(project_root)),
            description=fm.get("description", "")[:120],
            version=fm.get("version", ""),
            model=fm.get("model", ""),
            category=fm.get("category") or categorize_skill(skill_dir.name),
            last_commit_date=last_date or "",
            last_commit_days_ago=days_ago,
        )
        entries.append(entry)

    return entries


def format_json(entries: list[SkillEntry]) -> str:
    """Format registry as JSON.

    Args:
        entries: List of skill entries.

    Returns:
        JSON string.
    """
    data = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "total_skills": len(entries),
        "skills": [asdict(e) for e in entries],
    }
    return json.dumps(data, indent=2)


def format_markdown(
    entries: list[SkillEntry],
    stale_days: int,
) -> str:
    """Format registry as a markdown report.

    Args:
        entries: List of skill entries.
        stale_days: Threshold in days for underutilized detection.

    Returns:
        Markdown string.
    """
    lines: list[str] = []
    lines.append(f"# Skill Registry ({len(entries)} skills)")
    lines.append("")
    lines.append(f"Generated: {datetime.now(tz=UTC).strftime('%Y-%m-%d')}")
    lines.append("")

    # Underutilized skills
    stale = [
        e for e in entries
        if e.last_commit_days_ago >= stale_days
    ]
    if stale:
        lines.append(f"## Underutilized Skills (>{stale_days} days since last change)")
        lines.append("")
        for e in sorted(stale, key=lambda x: x.last_commit_days_ago, reverse=True):
            lines.append(
                f"- **{e.name}** ({e.category}) - {e.last_commit_days_ago}d ago"
            )
        lines.append("")

    # By category
    categories: dict[str, list[SkillEntry]] = {}
    for e in entries:
        categories.setdefault(e.category, []).append(e)

    lines.append("## Skills by Category")
    lines.append("")
    for cat in sorted(categories):
        lines.append(f"### {cat} ({len(categories[cat])})")
        lines.append("")
        lines.append("| Skill | Version | Model | Last Changed | Days Ago |")
        lines.append("|-------|---------|-------|-------------|----------|")
        for e in sorted(categories[cat], key=lambda x: x.name):
            days_display = (
                str(e.last_commit_days_ago)
                if e.last_commit_days_ago >= 0
                else "-"
            )
            lines.append(
                f"| {e.name} | {e.version or '-'} | {e.model or '-'} "
                f"| {e.last_commit_date or '-'} | {days_display} |"
            )
        lines.append("")

    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Parsed arguments namespace.
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
        "--stale-days",
        type=int,
        default=_STALE_DAYS_DEFAULT,
        help=f"Days threshold for underutilized detection (default: {_STALE_DAYS_DEFAULT})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write output to file instead of stdout (any writable path accepted)",
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=None,
        help="Skills directory (default: auto-detect)",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root directory (default: auto-detect)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Optional argument list for testing.

    Returns:
        Exit code: 0 success, 1 error, 2 unexpected.
    """
    try:
        args = parse_args(argv)

        project_root = Path(args.project_root or _PROJECT_ROOT).resolve()
        skills_dir = Path(
            args.skills_dir or (project_root / ".claude" / "skills")
        ).resolve()

        if not skills_dir.is_dir():
            print(
                f"ERROR: Skills directory not found: {skills_dir}",
                file=sys.stderr,
            )
            return 2

        entries = scan_skills(skills_dir, project_root)
        if not entries:
            print("ERROR: No skills found", file=sys.stderr)
            return 1

        if args.format == "json":
            output = format_json(entries)
        else:
            output = format_markdown(entries, args.stale_days)

        if args.output:
            out_path = args.output.resolve()
            out_path.write_text(output, encoding="utf-8")
            print(f"Registry written to {out_path}", file=sys.stderr)
        else:
            print(output)

        return 0

    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
