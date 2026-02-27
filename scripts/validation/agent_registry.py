#!/usr/bin/env python3
"""Parse and validate agent definitions from src/claude/*.md against AGENTS.md.

Parses YAML frontmatter from agent markdown files and validates
each definition against the canonical agent catalog in AGENTS.md.

Exit codes follow ADR-035:
    0 - Success: all agents valid
    1 - Logic error: validation failures detected
    2 - Config error: missing paths or bad configuration
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Reuse existing frontmatter parsing from build utilities
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "build"))
from generate_agents_common import parse_simple_frontmatter, read_yaml_frontmatter  # noqa: E402

# Files in src/claude/ that are not agent definitions
_EXCLUDED_FILES = frozenset({"AGENTS.md", "claude-instructions.template.md"})

# Required frontmatter fields for every agent definition
_REQUIRED_FIELDS = ("name", "description", "model")

# Allowed model values
_VALID_MODELS = frozenset({"opus", "sonnet", "haiku"})

# Pattern for extracting agent rows from AGENTS.md markdown table
_AGENT_TABLE_ROW = re.compile(
    r"^\|\s*(?P<name>[\w-]+)\s*\|[^|]*\|\s*(?P<model>opus|sonnet|haiku)\s*\|",
)


@dataclass(frozen=True)
class AgentDefinition:
    """Parsed agent definition from a markdown file."""

    name: str
    description: str
    model: str
    argument_hint: str
    file_path: Path


@dataclass
class CatalogEntry:
    """Expected agent from AGENTS.md catalog."""

    name: str
    model: str


@dataclass
class ValidationResult:
    """Collected validation errors and warnings."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def parse_agent_file(file_path: Path) -> AgentDefinition | None:
    """Parse a single agent markdown file.

    Returns AgentDefinition on success, None if frontmatter is missing.
    """
    content = file_path.read_text(encoding="utf-8")
    raw = read_yaml_frontmatter(content)
    if raw is None:
        return None

    fm = parse_simple_frontmatter(raw["frontmatter_raw"])
    name = (fm.get("name") or "").strip()
    description = (fm.get("description") or "").strip()
    model = (fm.get("model") or "").strip()
    argument_hint = (fm.get("argument-hint") or "").strip()

    if not name:
        return None

    return AgentDefinition(
        name=name,
        description=description,
        model=model,
        argument_hint=argument_hint,
        file_path=file_path,
    )


def parse_agent_files(agent_dir: Path) -> tuple[list[AgentDefinition], list[str]]:
    """Parse all agent definitions from a directory of markdown files.

    Skips non-agent files listed in _EXCLUDED_FILES.
    Returns a tuple of parsed agents and a list of file-level errors.
    """
    agents: list[AgentDefinition] = []
    errors: list[str] = []
    for md_file in sorted(agent_dir.glob("*.md")):
        if md_file.name in _EXCLUDED_FILES:
            continue
        try:
            defn = parse_agent_file(md_file)
            if defn is not None:
                agents.append(defn)
        except OSError as e:
            errors.append(f"Cannot read file {md_file.name}: {e}")
    return agents, errors


def parse_catalog(agents_md_path: Path) -> list[CatalogEntry]:
    """Parse the agent catalog table from AGENTS.md.

    Extracts agent name and model from the markdown table in the
    Agent Catalog section.
    """
    content = agents_md_path.read_text(encoding="utf-8")
    entries: list[CatalogEntry] = []
    for line in content.splitlines():
        m = _AGENT_TABLE_ROW.match(line)
        if m:
            entries.append(CatalogEntry(name=m.group("name"), model=m.group("model")))
    return entries


def validate(
    agents: list[AgentDefinition],
    catalog: list[CatalogEntry],
) -> ValidationResult:
    """Validate parsed agents against the canonical catalog.

    Checks:
    - Required frontmatter fields present
    - Model value is valid (opus, sonnet, haiku)
    - Every catalog agent has a corresponding file
    - Model assignments match between file and catalog
    - No duplicate agent names in parsed files
    """
    result = ValidationResult()
    catalog_by_name = {e.name: e for e in catalog}
    agents_by_name: dict[str, AgentDefinition] = {}

    for agent in agents:
        # Duplicate check
        if agent.name in agents_by_name:
            result.errors.append(
                f"Duplicate agent name '{agent.name}' in "
                f"{agent.file_path.name} and {agents_by_name[agent.name].file_path.name}"
            )
        agents_by_name[agent.name] = agent

        # Required fields
        for fld in _REQUIRED_FIELDS:
            val = getattr(agent, fld, None)
            if not val:
                result.errors.append(
                    f"Agent '{agent.name}' ({agent.file_path.name}): missing required field '{fld}'"
                )

        # Valid model
        if agent.model and agent.model not in _VALID_MODELS:
            result.errors.append(
                f"Agent '{agent.name}' ({agent.file_path.name}): "
                f"invalid model '{agent.model}', expected one of {sorted(_VALID_MODELS)}"
            )

        # Model match against catalog
        if agent.name in catalog_by_name:
            expected_model = catalog_by_name[agent.name].model
            if agent.model and agent.model != expected_model:
                result.errors.append(
                    f"Agent '{agent.name}' ({agent.file_path.name}): "
                    f"model '{agent.model}' does not match catalog '{expected_model}'"
                )

    # Missing agents: in catalog but no file
    for entry in catalog:
        if entry.name not in agents_by_name:
            result.warnings.append(
                f"Catalog agent '{entry.name}' has no definition file in src/claude/"
            )

    # Extra agents: file exists but not in catalog
    for name in agents_by_name:
        if name not in catalog_by_name:
            result.warnings.append(
                f"Agent '{name}' has a definition file but is not in the AGENTS.md catalog"
            )

    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for agent registry validation."""
    parser = argparse.ArgumentParser(
        description="Parse and validate agent registry against AGENTS.md catalog.",
    )
    parser.add_argument(
        "--agent-dir",
        type=Path,
        default=Path("src/claude"),
        help="Directory containing agent markdown files (default: src/claude)",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("AGENTS.md"),
        help="Path to AGENTS.md with canonical agent catalog (default: AGENTS.md)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args(argv)

    if not args.agent_dir.is_dir():
        print(f"Error: agent directory not found: {args.agent_dir}", file=sys.stderr)
        return 2

    if not args.catalog.is_file():
        print(f"Error: catalog file not found: {args.catalog}", file=sys.stderr)
        return 2

    agents, parsing_errors = parse_agent_files(args.agent_dir)

    try:
        catalog = parse_catalog(args.catalog)
    except OSError as e:
        print(f"Error reading catalog file {args.catalog}: {e}", file=sys.stderr)
        return 2

    result = validate(agents, catalog)
    result.errors.extend(parsing_errors)

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "agents_parsed": len(agents),
                    "catalog_entries": len(catalog),
                    "errors": result.errors,
                    "warnings": result.warnings,
                    "ok": result.ok,
                },
                indent=2,
            )
        )
    else:
        print(f"Parsed {len(agents)} agents, {len(catalog)} catalog entries")
        for err in result.errors:
            print(f"  ERROR: {err}")
        for warn in result.warnings:
            print(f"  WARN: {warn}")
        if result.ok:
            print("Validation passed")
        else:
            print(f"Validation failed with {len(result.errors)} error(s)")

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
