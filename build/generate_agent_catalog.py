#!/usr/bin/env python3
"""Generate docs/agent-catalog.md from templates/agents/*.shared.md.

Reads each shared agent source under templates/agents/, parses its YAML
frontmatter for the agent description and tier, derives the agent name from
the filename, counts the file's lines of code, and emits a single markdown
table to docs/agent-catalog.md.

The generated file is a derived artifact: templates/agents/ is the system of
record. Run this script and commit the output whenever an agent template
changes. scripts/validation/validate_agent_catalog.py regenerates to a buffer
and fails on drift so a stale catalog cannot ship.

Agent name is derived from the filename (the ``<name>.shared.md`` stem) because
the templates carry no ``name:`` field; the description and tier come from the
frontmatter.

EXIT CODES (ADR-035):
  0  - Success (or --check passed with no drift)
  1  - Logic error (--check found drift, or generation failed)
  2  - Configuration error (templates directory missing)
  3  - External error (a template could not be read or parsed)

This generator follows the conventions in build/generate_agents.py.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from collections.abc import Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent

# Frontmatter delimiter regex. Mirrors build/generate_agents_common.py:
#   _FRONTMATTER_RE = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$")
# Same contract: capture the YAML block between the leading and the second
# ``---`` fence, then the body. Quoted verbatim per canonical-source-mirror.md.
_FRONTMATTER_RE = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$")

_TEMPLATE_GLOB = "*.shared.md"
_OUTPUT_RELATIVE = Path("docs") / "agent-catalog.md"

_HEADER = (
    "# Agent Catalog\n"
    "\n"
    "> [!NOTE]\n"
    "> Generated file. Do not edit by hand.\n"
    "> Source: `templates/agents/*.shared.md`.\n"
    "> Regenerate: `python3 build/generate_agent_catalog.py`.\n"
    "> Validated by: `scripts/validation/validate_agent_catalog.py`.\n"
    "\n"
    "Auto-generated index of every agent template under `templates/agents/`.\n"
    "Each row links the agent name to its tier, line count, and description.\n"
    "Run `python3 build/generate_agent_catalog.py` to refresh after a template\n"
    "change; CI fails if this file drifts from the templates.\n"
    "\n"
)

_TABLE_HEADER = "| Agent | Tier | LOC | Description |\n| --- | --- | --- | --- |\n"


@dataclass(frozen=True, slots=True)
class AgentEntry:
    """One row of the catalog, derived from a single agent template."""

    name: str
    tier: str
    loc: int
    description: str


class CatalogError(Exception):
    """A template could not be read or parsed."""


def _escape_cell(text: str) -> str:
    """Make ``text`` safe to place in a single markdown table cell.

    Collapses internal whitespace to single spaces and escapes the pipe so a
    description containing ``|`` cannot break the table structure.
    """
    collapsed = " ".join(text.split())
    return collapsed.replace("|", "\\|")


def _agent_name_from_path(template: Path) -> str:
    """Derive the agent name from a ``<name>.shared.md`` filename."""
    # Path.stem on "analyst.shared.md" yields "analyst.shared"; strip the
    # trailing ".shared" suffix the convention adds.
    name = template.name
    suffix = ".shared.md"
    if name.endswith(suffix):
        return name[: -len(suffix)]
    return template.stem


def _count_loc(content: str) -> int:
    """Count lines of code in the file content.

    Counts every line including frontmatter and blanks so the number is a
    stable, reproducible measure of template size. A trailing newline does not
    add a phantom empty line.
    """
    if not content:
        return 0
    normalized = content.replace("\r\n", "\n")
    lines = normalized.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return len(lines)


def _parse_frontmatter(content: str, template: Path) -> dict[str, object]:
    """Extract and parse the YAML frontmatter block.

    Raises CatalogError if the file has no frontmatter or the YAML is invalid.
    """
    match = _FRONTMATTER_RE.match(content.replace("\r\n", "\n"))
    if match is None:
        raise CatalogError(f"no YAML frontmatter found in {template}")
    try:
        parsed = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise CatalogError(f"invalid YAML frontmatter in {template}: {exc}") from exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise CatalogError(f"frontmatter in {template} is not a mapping")
    return parsed


def build_entry(template: Path) -> AgentEntry:
    """Build a catalog entry from one agent template file."""
    try:
        content = template.read_text(encoding="utf-8")
    except OSError as exc:
        raise CatalogError(f"cannot read {template}: {exc}") from exc

    frontmatter = _parse_frontmatter(content, template)
    description_value = frontmatter.get("description")
    description = str(description_value).strip() if description_value is not None else ""
    tier_value = frontmatter.get("tier")
    tier = str(tier_value).strip() if tier_value is not None else "unknown"

    return AgentEntry(
        name=_agent_name_from_path(template),
        tier=tier,
        loc=_count_loc(content),
        description=description,
    )


def collect_entries(templates_dir: Path) -> list[AgentEntry]:
    """Collect catalog entries for every template, sorted by agent name."""
    templates = sorted(templates_dir.glob(_TEMPLATE_GLOB))
    entries = [build_entry(template) for template in templates]
    return sorted(entries, key=lambda entry: entry.name)


def render_catalog(entries: Sequence[AgentEntry]) -> str:
    """Render the full markdown catalog from the collected entries."""
    rows = [
        f"| [{entry.name}](../templates/agents/{entry.name}.shared.md) "
        f"| {_escape_cell(entry.tier)} "
        f"| {entry.loc} "
        f"| {_escape_cell(entry.description)} |"
        for entry in entries
    ]
    plural = "" if len(entries) == 1 else "s"
    count_line = f"\n_{len(entries)} agent template{plural} indexed._\n"
    table = _TABLE_HEADER + ("\n".join(rows) + "\n" if rows else "")
    return _HEADER + table + count_line


def generate(templates_dir: Path, output_path: Path) -> str:
    """Generate the catalog content from templates and write it to disk."""
    content = render_catalog(collect_entries(templates_dir))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return content


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Generate docs/agent-catalog.md from templates/agents/*.shared.md.",
    )
    parser.add_argument(
        "--templates-path",
        type=Path,
        default=None,
        help="Path to templates/agents directory. Defaults to templates/agents/ in repo root.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path. Defaults to docs/agent-catalog.md in repo root.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="CI mode: regenerate to a buffer and exit non-zero on drift; do not write.",
    )
    return parser


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    """Resolve the templates directory and output path from parsed args."""
    if args.templates_path is not None:
        templates_dir = _resolve_cli_path(args.templates_path)
        candidate_agents_dir = templates_dir / "agents"
        if candidate_agents_dir.is_dir() and not any(templates_dir.glob(_TEMPLATE_GLOB)):
            templates_dir = candidate_agents_dir
    else:
        templates_dir = _REPO_ROOT / "templates" / "agents"

    output_path = (
        _resolve_cli_path(args.output) if args.output is not None else (_REPO_ROOT / _OUTPUT_RELATIVE)
    )
    return templates_dir, output_path


def _resolve_cli_path(path: Path) -> Path:
    """Resolve CLI paths relative to the repository root, not the caller CWD."""
    if path.is_absolute():
        return path.resolve()
    return (_REPO_ROOT / path).resolve()


def _run_check(templates_dir: Path, output_path: Path) -> int:
    """Compare the committed catalog to freshly generated content."""
    generated = render_catalog(collect_entries(templates_dir)).replace("\r\n", "\n")
    if not output_path.exists():
        print(f"MISSING: {output_path} does not exist", file=sys.stderr)
        print("To fix: python3 build/generate_agent_catalog.py", file=sys.stderr)
        return 1

    committed = output_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if committed != generated:
        print(f"DRIFT: {output_path} differs from generated output", file=sys.stderr)
        print("To fix: python3 build/generate_agent_catalog.py", file=sys.stderr)
        return 1

    print(f"OK: {output_path} matches templates/agents/")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for catalog generation. Returns an ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    templates_dir, output_path = _resolve_paths(args)

    if not templates_dir.is_dir():
        print(f"Error: templates directory not found: {templates_dir}", file=sys.stderr)
        return 2

    try:
        if args.check:
            return _run_check(templates_dir, output_path)
        generate(templates_dir, output_path)
    except (CatalogError, OSError, UnicodeDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 3

    print(f"Generated: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
