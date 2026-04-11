#!/usr/bin/env python3
"""Load skills from multiple directories with precedence-based resolution.

Scans skill directories in precedence order (project > built-in), parses
YAML frontmatter and protocol/process sections from SKILL.md files, and
provides list, show, and load operations.

Phase 1 implementation for issue #1608 (Skill-Based Slash Commands v0.4.0).

EXIT CODES:
  0  - Success
  1  - Error: Skill not found or logic error
  2  - Error: Configuration or path error

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent

# Default skill search paths in precedence order (highest first).
# Project-level skills override built-in skills.
_DEFAULT_SKILL_PATHS = [
    _PROJECT_ROOT / ".agents" / "skills",
    _PROJECT_ROOT / ".claude" / "skills",
]


@dataclass(frozen=True)
class ProtocolStep:
    """A single step extracted from a skill's Protocol/Process section."""

    order: int
    description: str
    tool: str = ""
    substeps: tuple[str, ...] = ()


@dataclass(frozen=True)
class Skill:
    """Parsed skill with frontmatter metadata and protocol steps."""

    name: str
    description: str
    version: str = ""
    model: str = ""
    author: str = ""
    tags: tuple[str, ...] = ()
    source_path: str = ""
    protocol: tuple[ProtocolStep, ...] = ()
    tools: tuple[str, ...] = ()
    user_invocable: bool = False


def parse_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML frontmatter fields from skill markdown text.

    Parses the region between opening and closing '---' delimiters.
    Returns a flat dict of key-value pairs.

    Args:
        text: Full markdown content of a SKILL.md file.

    Returns:
        Dict of frontmatter key-value pairs.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    try:
        end_index = next(
            i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration:
        return {}

    result: dict[str, str] = {}
    for line in lines[1:end_index]:
        stripped = line.strip()
        if ":" in stripped and not stripped.startswith("-"):
            key, _, value = stripped.partition(":")
            result[key.strip()] = value.strip()
    return result


def parse_protocol(text: str) -> list[ProtocolStep]:
    """Extract structured steps from Protocol or Process sections.

    Looks for '## Protocol' or '## Process' headings and parses numbered
    steps beneath them. Each step may reference a tool (in backticks after
    'Tool:') and have indented substeps.

    Args:
        text: Full markdown content of a SKILL.md file.

    Returns:
        List of ProtocolStep objects in order.
    """
    lines = text.splitlines()

    # Find the Protocol/Process section
    section_start = -1
    for i, line in enumerate(lines):
        if re.match(r"^##\s+(Protocol|Process)\s*$", line):
            section_start = i + 1
            break

    if section_start < 0:
        return []

    # Find section end (next h2 heading or end of file)
    section_end = len(lines)
    for i in range(section_start, len(lines)):
        if re.match(r"^##\s+", lines[i]) and i > section_start:
            section_end = i
            break

    section_lines = lines[section_start:section_end]

    steps: list[ProtocolStep] = []
    step_pattern = re.compile(r"^\d+\.\s+(.+)")
    tool_pattern = re.compile(r"Tool:\s*`([^`]+)`")
    substep_pattern = re.compile(r"^\s+-\s+(.+)")

    current_order = 0
    current_desc = ""
    current_tool = ""
    current_substeps: list[str] = []

    def _flush_step() -> None:
        nonlocal current_desc, current_tool, current_substeps
        if current_desc:
            steps.append(ProtocolStep(
                order=current_order,
                description=current_desc,
                tool=current_tool,
                substeps=tuple(current_substeps),
            ))
        current_desc = ""
        current_tool = ""
        current_substeps = []

    for line in section_lines:
        step_match = step_pattern.match(line)
        if step_match:
            _flush_step()
            current_order = len(steps) + 1
            current_desc = step_match.group(1).strip()
            # Check for inline tool reference
            tool_match = tool_pattern.search(line)
            if tool_match:
                current_tool = tool_match.group(1)
            continue

        if current_desc:
            # Check for tool reference in substep lines
            tool_match = tool_pattern.search(line)
            if tool_match:
                if not current_tool:
                    current_tool = tool_match.group(1)
                # Tool lines are metadata, not substeps
                continue

            substep_match = substep_pattern.match(line)
            if substep_match:
                current_substeps.append(substep_match.group(1).strip())

    _flush_step()
    return steps


def parse_tags(raw: str) -> tuple[str, ...]:
    """Parse a YAML-style tag list into a tuple of strings.

    Handles both bracket notation [a, b] and bare comma-separated values.

    Args:
        raw: Raw tag string from frontmatter.

    Returns:
        Tuple of tag strings.
    """
    cleaned = raw.strip().strip("[]")
    if not cleaned:
        return ()
    return tuple(t.strip().strip("\"'") for t in cleaned.split(",") if t.strip())


def parse_tools_required(text: str) -> tuple[str, ...]:
    """Extract tools from a '## Tools Required' section.

    Args:
        text: Full markdown content.

    Returns:
        Tuple of tool names.
    """
    lines = text.splitlines()
    section_start = -1
    for i, line in enumerate(lines):
        if re.match(r"^##\s+Tools\s+Required\s*$", line):
            section_start = i + 1
            break

    if section_start < 0:
        return ()

    tools: list[str] = []
    for i in range(section_start, len(lines)):
        line = lines[i]
        if re.match(r"^##\s+", line):
            break
        item_match = re.match(r"^\s*-\s+`?([^`\s]+)`?", line)
        if item_match:
            tools.append(item_match.group(1))
    return tuple(tools)


def load_skill(skill_path: Path) -> Skill:
    """Load a single skill from its directory.

    Reads the SKILL.md file, parses frontmatter and protocol sections,
    and returns a structured Skill object.

    Args:
        skill_path: Path to the skill directory containing SKILL.md.

    Returns:
        Parsed Skill object.

    Raises:
        FileNotFoundError: If SKILL.md does not exist in the directory.
    """
    skill_md = skill_path / "SKILL.md"
    if not skill_md.is_file():
        msg = f"SKILL.md not found in {skill_path}"
        raise FileNotFoundError(msg)

    text = skill_md.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    protocol = parse_protocol(text)
    tools = parse_tools_required(text)

    return Skill(
        name=fm.get("name", skill_path.name),
        description=fm.get("description", ""),
        version=fm.get("version", ""),
        model=fm.get("model", ""),
        author=fm.get("author", ""),
        tags=parse_tags(fm.get("tags", "")),
        source_path=str(skill_path),
        protocol=tuple(protocol),
        tools=tools,
        user_invocable=fm.get("user-invocable", "").lower() == "true",
    )


def discover_skills(
    search_paths: list[Path] | None = None,
) -> dict[str, Skill]:
    """Discover all skills across search paths with precedence resolution.

    Scans each path in order. When the same skill name appears in multiple
    paths, the first occurrence wins (highest precedence).

    Args:
        search_paths: Ordered list of directories to scan.
            Defaults to project .agents/skills/ then .claude/skills/.

    Returns:
        Dict mapping skill name to Skill, deduplicated by precedence.
    """
    paths = search_paths if search_paths is not None else list(_DEFAULT_SKILL_PATHS)
    skills: dict[str, Skill] = {}

    for base_path in paths:
        if not base_path.is_dir():
            continue
        for entry in sorted(base_path.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith(".") or entry.name == "__pycache__":
                continue
            skill_md = entry / "SKILL.md"
            if not skill_md.is_file():
                continue

            try:
                skill = load_skill(entry)
            except (FileNotFoundError, OSError):
                continue

            # First occurrence wins (highest precedence path)
            if skill.name not in skills:
                skills[skill.name] = skill

    return skills


def format_skill_list(skills: dict[str, Skill], output_format: str = "json") -> str:
    """Format skill listing for output.

    Args:
        skills: Dict of skill name to Skill.
        output_format: 'json' or 'table'.

    Returns:
        Formatted string.
    """
    if output_format == "json":
        payload = [
            {
                "name": s.name,
                "description": s.description[:120],
                "version": s.version,
                "model": s.model,
                "source": s.source_path,
                "user_invocable": s.user_invocable,
                "steps": len(s.protocol),
            }
            for s in sorted(skills.values(), key=lambda x: x.name)
        ]
        return json.dumps(payload, indent=2)

    # Table format
    lines = [
        "| Name | Description | Version | Steps | Invocable |",
        "|------|-------------|---------|-------|-----------|",
    ]
    for s in sorted(skills.values(), key=lambda x: x.name):
        desc = s.description[:60] + "..." if len(s.description) > 60 else s.description
        invocable = "Y" if s.user_invocable else "N"
        lines.append(
            f"| {s.name} | {desc} | {s.version or '-'} "
            f"| {len(s.protocol)} | {invocable} |"
        )
    return "\n".join(lines) + "\n"


def format_skill_show(skill: Skill) -> str:
    """Format a single skill for detailed display.

    Args:
        skill: Skill to display.

    Returns:
        Formatted string with full skill details.
    """
    lines = [
        f"# {skill.name}",
        "",
        f"**Description**: {skill.description}" if skill.description else "",
        f"**Version**: {skill.version}" if skill.version else "",
        f"**Model**: {skill.model}" if skill.model else "",
        f"**Author**: {skill.author}" if skill.author else "",
        f"**Tags**: {', '.join(skill.tags)}" if skill.tags else "",
        f"**Source**: {skill.source_path}",
        f"**User-invocable**: {'Yes' if skill.user_invocable else 'No'}",
    ]

    if skill.tools:
        lines.extend(["", "## Tools Required", ""])
        for tool in skill.tools:
            lines.append(f"- `{tool}`")

    if skill.protocol:
        lines.extend(["", "## Protocol Steps", ""])
        for step in skill.protocol:
            tool_ref = f" (Tool: `{step.tool}`)" if step.tool else ""
            lines.append(f"{step.order}. {step.description}{tool_ref}")
            for sub in step.substeps:
                lines.append(f"   - {sub}")

    # Filter empty lines from conditional fields
    return "\n".join(line for line in lines if line is not None) + "\n"


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
    subparsers = parser.add_subparsers(dest="command", help="Skill operation")

    # list subcommand
    list_parser = subparsers.add_parser("list", help="List available skills")
    list_parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="json",
        help="Output format (default: json)",
    )
    list_parser.add_argument(
        "--search-paths",
        nargs="+",
        type=Path,
        default=None,
        help="Skill directories to scan (in precedence order)",
    )

    # show subcommand
    show_parser = subparsers.add_parser("show", help="Show skill details")
    show_parser.add_argument("name", help="Skill name to display")
    show_parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    show_parser.add_argument(
        "--search-paths",
        nargs="+",
        type=Path,
        default=None,
        help="Skill directories to scan (in precedence order)",
    )

    # load subcommand
    load_parser = subparsers.add_parser("load", help="Load skill as JSON")
    load_parser.add_argument("name", help="Skill name to load")
    load_parser.add_argument(
        "--search-paths",
        nargs="+",
        type=Path,
        default=None,
        help="Skill directories to scan (in precedence order)",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Argument list for testing.

    Returns:
        Exit code.
    """
    args = parse_args(argv)

    if not args.command:
        parse_args(["--help"])
        return 2

    search_paths = args.search_paths

    if args.command == "list":
        skills = discover_skills(search_paths)
        print(format_skill_list(skills, args.format))
        return 0

    if args.command == "show":
        skills = discover_skills(search_paths)
        if args.name not in skills:
            print(f"ERROR: Skill '{args.name}' not found", file=sys.stderr)
            return 1
        skill = skills[args.name]
        if args.format == "json":
            print(json.dumps(asdict(skill), indent=2))
        else:
            print(format_skill_show(skill))
        return 0

    if args.command == "load":
        skills = discover_skills(search_paths)
        if args.name not in skills:
            print(f"ERROR: Skill '{args.name}' not found", file=sys.stderr)
            return 1
        print(json.dumps(asdict(skills[args.name]), indent=2))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
