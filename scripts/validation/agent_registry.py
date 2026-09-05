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
import importlib.util
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import yaml
from yaml.nodes import MappingNode, ScalarNode

logger = logging.getLogger(__name__)


def _build_utility_path() -> Path:
    """Absolute path of the build helper this module borrows its parser from."""
    return Path(__file__).resolve().parents[2] / "build" / "generate_agents_common.py"


def _load_read_yaml_frontmatter(path: Path | None = None) -> Callable[[str], dict[str, str] | None]:
    """Load `read_yaml_frontmatter` from the build tree without touching sys.path.

    This runs at import time, so a failure here takes down every caller of this
    module. `spec_from_file_location` returns a populated spec even when the
    file does not exist, so the spec guard below only covers an unloadable
    suffix; a missing or broken file surfaces from `exec_module` instead. Both
    paths are wrapped so the failure says which utility could not be loaded,
    rather than a bare FileNotFoundError from inside a validation script.
    """
    path = path or _build_utility_path()
    spec = importlib.util.spec_from_file_location("_agent_registry_build_common", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load build utility {path}: no import spec")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise ImportError(f"Cannot load build utility {path}: {exc}") from exc
    try:
        loaded = module.read_yaml_frontmatter
    except AttributeError as exc:
        raise ImportError(f"Build utility {path} does not define read_yaml_frontmatter") from exc
    return cast(Callable[[str], dict[str, str] | None], loaded)


read_yaml_frontmatter = _load_read_yaml_frontmatter()

# Files in src/claude/ that are not agent definitions
_EXCLUDED_FILES = frozenset({"AGENTS.md", "claude-instructions.template.md"})

# Required frontmatter fields for every agent definition.
#
# ``model`` is deliberately absent. ADR-080 defaults every agent to the
# harness-inherited model and states that the absence of a ``model:`` line is
# correct and needs no justification, so requiring the field here would fail
# every agent the ADR-080 migration returned to the default. A pin that IS
# present is still checked against _VALID_MODELS below.
_REQUIRED_FIELDS = ("name", "description")

# Allowed model values when a unit does pin one. ADR-080 rule 1 bans versioned
# ids outside the agent-evidence path, so only the rolling aliases appear here;
# scripts/validation/check_model_pins.py owns the rest of the policy.
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
        return not self.errors


class MalformedAgentFileError(Exception):
    """A markdown file in the agent directory is not a usable agent definition."""


def _parse_frontmatter(file_path: Path, text: str) -> dict[str, object]:
    """Parse one frontmatter mapping and reject duplicate top-level keys."""
    try:
        node = yaml.compose(text, Loader=yaml.SafeLoader)
        if not isinstance(node, MappingNode):
            raise MalformedAgentFileError(f"{file_path.name}: frontmatter is not a YAML mapping")

        keys: set[tuple[str, str]] = set()
        for key_node, _ in node.value:
            if not isinstance(key_node, ScalarNode):
                raise MalformedAgentFileError(
                    f"{file_path.name}: frontmatter keys must be scalar values"
                )
            key = (key_node.tag, key_node.value)
            if key in keys:
                raise MalformedAgentFileError(
                    f"{file_path.name}: duplicate frontmatter key '{key_node.value}'"
                )
            keys.add(key)
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise MalformedAgentFileError(f"{file_path.name}: invalid YAML frontmatter: {exc}") from exc
    if not isinstance(parsed, dict):
        raise MalformedAgentFileError(f"{file_path.name}: frontmatter is not a YAML mapping")
    return parsed


def _text_field(frontmatter: dict[str, object], name: str) -> str:
    value = frontmatter.get(name)
    return value.strip() if isinstance(value, str) else ""


def parse_agent_file(file_path: Path) -> AgentDefinition:
    """Parse a single agent markdown file.

    Raises MalformedAgentFileError when the file carries no YAML frontmatter or no
    name. Both used to return None, which dropped the file from the registry
    and left validate() with nothing to complain about, so an agent that had
    lost its frontmatter passed the check that exists to catch exactly that.
    Every file here is meant to be an agent; the ones that are not are listed
    in _EXCLUDED_FILES.
    """
    content = file_path.read_text(encoding="utf-8")
    raw = read_yaml_frontmatter(content)
    if raw is None:
        raise MalformedAgentFileError(f"{file_path.name}: no YAML frontmatter")

    fm = _parse_frontmatter(file_path, raw["frontmatter_raw"])
    name = _text_field(fm, "name")
    description = _text_field(fm, "description")
    model = _text_field(fm, "model")
    argument_hint = _text_field(fm, "argument-hint")

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
        except UnicodeDecodeError as e:
            errors.append(f"{md_file.name}: cannot decode as UTF-8: {e}")
        except OSError as e:
            errors.append(f"Cannot read file {md_file.name}: {e}")
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
    if not agents and not result.errors:
        result.errors.append(f"No agent definitions found in {args.agent_dir}")

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
