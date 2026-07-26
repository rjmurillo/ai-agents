#!/usr/bin/env python3
"""Parse and validate agent definitions from src/claude/*.md.

Parses YAML frontmatter from agent markdown files and validates each
definition (required fields, allowed model, no duplicate names).

Exit codes follow ADR-035:
    0 - Success: all agents valid
    1 - Logic error: validation failures detected
    2 - Config error: missing paths or bad configuration
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Reuse existing frontmatter parsing from build utilities
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "build"))
from generate_agents_common import parse_simple_frontmatter, read_yaml_frontmatter  # noqa: E402

# Files in src/claude/ that are not agent definitions
_EXCLUDED_FILES = frozenset({"AGENTS.md", "claude-instructions.template.md"})

# Required frontmatter fields for every agent definition
_REQUIRED_FIELDS = ("name", "description", "model")

# Allowed model values
_VALID_MODELS = frozenset({"opus", "sonnet", "haiku"})


@dataclass(frozen=True)
class AgentDefinition:
    """Parsed agent definition from a markdown file."""

    name: str
    description: str
    model: str
    argument_hint: str
    file_path: Path


@dataclass
class ValidationResult:
    """Collected validation errors and warnings."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


class MalformedAgentFileError(Exception):
    """A markdown file in the agent directory is not a usable agent definition."""


def parse_agent_file(file_path: Path) -> AgentDefinition:
    """Parse a single agent markdown file.

    Raises MalformedAgentFileError when the file cannot be read as UTF-8, or
    carries no YAML frontmatter, or has no name. All three used to end the
    run badly: the first two as a traceback, the last two as a silent None
    that dropped the file from the registry and left validate() with nothing
    to complain about, so an agent that had lost its frontmatter passed the
    check that exists to catch exactly that. Every file here is meant to be
    an agent; the ones that are not are listed in _EXCLUDED_FILES.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise MalformedAgentFileError(
            f"{file_path.name}: not valid UTF-8 at byte {exc.start}"
        ) from exc
    except OSError as exc:
        raise MalformedAgentFileError(f"{file_path.name}: unreadable ({exc})") from exc

    raw = read_yaml_frontmatter(content)
    if raw is None:
        raise MalformedAgentFileError(f"{file_path.name}: no YAML frontmatter")

    fm = parse_simple_frontmatter(raw["frontmatter_raw"])
    name = (fm.get("name") or "").strip()
    description = (fm.get("description") or "").strip()
    model = (fm.get("model") or "").strip()
    argument_hint = (fm.get("argument-hint") or "").strip()

    if not name:
        raise MalformedAgentFileError(f"{file_path.name}: frontmatter has no name")

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

    MalformedAgentFileError is the only failure parse_agent_file raises;
    it already converts an unreadable file into one. A second except OSError
    here would be unreachable and would give the same condition a second
    message format.
    """
    agents: list[AgentDefinition] = []
    errors: list[str] = []
    for md_file in sorted(agent_dir.glob("*.md")):
        if md_file.name in _EXCLUDED_FILES:
            continue
        try:
            agents.append(parse_agent_file(md_file))
        except MalformedAgentFileError as e:
            errors.append(str(e))
    return agents, errors


def validate(agents: list[AgentDefinition]) -> ValidationResult:
    """Validate parsed agents.

    Checks:
    - Required frontmatter fields present
    - Model value is valid (opus, sonnet, haiku)
    - No duplicate agent names across parsed files
    """
    result = ValidationResult()
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

    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for agent registry validation."""
    parser = argparse.ArgumentParser(
        description="Parse and validate agent definitions in src/claude/.",
    )
    parser.add_argument(
        "--agent-dir",
        type=Path,
        default=Path("src/claude"),
        help="Directory containing agent markdown files (default: src/claude)",
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

    agents, parsing_errors = parse_agent_files(args.agent_dir)
    result = validate(agents)
    result.errors.extend(parsing_errors)

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "agents_parsed": len(agents),
                    "errors": result.errors,
                    "warnings": result.warnings,
                    "ok": result.ok,
                },
                indent=2,
            )
        )
    else:
        print(f"Parsed {len(agents)} agents")
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
