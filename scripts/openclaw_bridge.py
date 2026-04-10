#!/usr/bin/env python3
"""Export ai-agents definitions to OpenClaw-compatible workspace format.

Reads agent definitions from src/claude/*.md (YAML frontmatter + markdown)
and generates an OpenClaw workspace with AGENTS.md routing table and
per-agent SOUL.md skill stubs.

Usage:
    python3 scripts/openclaw_bridge.py --agents-dir src/claude --output-dir ./openclaw-workspace
    python3 scripts/openclaw_bridge.py --dry-run
    python3 scripts/openclaw_bridge.py --format json

Exit Codes:
    0: Success
    1: Logic error
    2: Configuration error (invalid paths)

Per ADR-042: Python-first for new scripts.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

import frontmatter

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _validate_path_component(name: str, base_dir: Path) -> Path:
    """Validate that a name does not escape base_dir via path traversal.

    Args:
        name: Untrusted name from YAML frontmatter.
        base_dir: Directory the resulting path must stay within.

    Returns:
        Resolved safe path under base_dir.

    Raises:
        ValueError: If the name contains path traversal characters.
    """
    sanitized = name.replace("/", "_").replace("\\", "_").replace("..", "_")
    candidate = base_dir / sanitized
    if not candidate.resolve().is_relative_to(base_dir.resolve()):
        raise ValueError(f"Path traversal detected in agent name: {name}")
    return candidate

# OpenClaw tier mapping from ai-agents tiers
_TIER_TO_OPENCLAW_ROLE: dict[str, str] = {
    "expert": "strategic",
    "manager": "coordinator",
    "builder": "executor",
    "integration": "support",
}

# Default model mapping from ai-agents model names to OpenClaw provider format
_MODEL_MAP: dict[str, str] = {
    "opus": "anthropic/claude-opus-4-6",
    "sonnet": "anthropic/claude-sonnet-4-6",
    "haiku": "anthropic/claude-haiku-4-5",
}


@dataclass
class AgentDefinition:
    """Parsed ai-agents agent definition."""

    name: str
    description: str
    model: str
    tier: str
    argument_hint: str = ""
    body: str = ""
    source_path: str = ""


@dataclass
class ExportResult:
    """Result of an export operation."""

    agents_md: str = ""
    agent_skills: dict[str, str] = field(default_factory=dict)
    agent_count: int = 0
    errors: list[str] = field(default_factory=list)


def parse_agent_file(path: Path) -> AgentDefinition | None:
    """Parse a single ai-agents markdown file with YAML frontmatter.

    Args:
        path: Path to the agent definition file.

    Returns:
        AgentDefinition if valid, None if the file lacks required fields.
    """
    try:
        post = frontmatter.load(str(path))
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
        logger.warning("Failed to parse %s: %s", path.name, exc)
        return None

    metadata: dict[str, Any] = dict(post.metadata)
    name = metadata.get("name", "")
    description = metadata.get("description", "")
    model = metadata.get("model", "sonnet")
    tier = metadata.get("tier", "integration")

    if not name or not description:
        return None

    return AgentDefinition(
        name=name,
        description=description,
        model=model,
        tier=tier,
        argument_hint=metadata.get("argument-hint", ""),
        body=post.content,
        source_path=str(path),
    )


def load_agents(agents_dir: Path) -> list[AgentDefinition]:
    """Load all agent definitions from a directory.

    Args:
        agents_dir: Directory containing agent markdown files.

    Returns:
        Sorted list of AgentDefinition objects.
    """
    agents: list[AgentDefinition] = []
    for md_file in sorted(agents_dir.glob("*.md")):
        if md_file.name in ("AGENTS.md", "claude-instructions.template.md"):
            continue
        agent = parse_agent_file(md_file)
        if agent is not None:
            agents.append(agent)
    return agents


def generate_agents_md(agents: list[AgentDefinition]) -> str:
    """Generate OpenClaw-compatible AGENTS.md routing table.

    Args:
        agents: List of agent definitions to include.

    Returns:
        Markdown string with agent routing configuration.
    """
    lines: list[str] = [
        "# AGENTS.md",
        "",
        "Multi-agent routing table exported from ai-agents.",
        "Install as OpenClaw workspace agents via skills.",
        "",
        "## Agent Registry",
        "",
        "| Agent | Role | Model | Description |",
        "|-------|------|-------|-------------|",
    ]

    for agent in agents:
        role = _TIER_TO_OPENCLAW_ROLE.get(agent.tier, agent.tier)
        model = _MODEL_MAP.get(agent.model, agent.model)
        desc = agent.description[:80] + "..." if len(agent.description) > 80 else agent.description
        lines.append(f"| {agent.name} | {role} | {model} | {desc} |")

    lines.extend([
        "",
        "## Routing Rules",
        "",
        "Route tasks to agents by matching keywords in the request.",
        "The orchestrator agent coordinates multi-step workflows.",
        "",
    ])

    for agent in agents:
        if agent.argument_hint:
            lines.append(f"- **{agent.name}**: {agent.argument_hint}")

    lines.append("")
    return "\n".join(lines)


def generate_skill_md(agent: AgentDefinition) -> str:
    """Generate an OpenClaw SKILL.md for a single agent.

    Args:
        agent: Agent definition to convert.

    Returns:
        Markdown string for the skill definition.
    """
    model = _MODEL_MAP.get(agent.model, agent.model)
    lines: list[str] = [
        f"# {agent.name}",
        "",
        f"{agent.description}",
        "",
        "## Configuration",
        "",
        f"- **Model**: `{model}`",
        f"- **Role**: {_TIER_TO_OPENCLAW_ROLE.get(agent.tier, agent.tier)}",
        f"- **Source**: ai-agents (`{agent.source_path}`)" if agent.source_path else f"- **Source**: ai-agents ({agent.name})",
        "",
    ]

    if agent.argument_hint:
        lines.extend([
            "## Usage",
            "",
            f"{agent.argument_hint}",
            "",
        ])

    return "\n".join(lines)


def export_agents(agents: list[AgentDefinition]) -> ExportResult:
    """Export agent definitions to OpenClaw format.

    Args:
        agents: List of agents to export.

    Returns:
        ExportResult with generated content.
    """
    result = ExportResult()
    result.agents_md = generate_agents_md(agents)
    result.agent_count = len(agents)

    seen_names: set[str] = set()
    for agent in agents:
        if agent.name in seen_names:
            raise ValueError(f"Duplicate agent name: {agent.name}")
        seen_names.add(agent.name)
        result.agent_skills[agent.name] = generate_skill_md(agent)

    return result


def write_workspace(result: ExportResult, output_dir: Path, dry_run: bool = False) -> int:
    """Write OpenClaw workspace files to disk.

    Args:
        result: Export result containing generated content.
        output_dir: Target directory for the workspace.
        dry_run: If True, only log what would be created.

    Returns:
        Number of files written.
    """
    files_written = 0

    agents_md_path = output_dir / "AGENTS.md"
    if dry_run:
        logger.info("  WOULD CREATE %s", agents_md_path)
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        agents_md_path.write_text(result.agents_md, encoding="utf-8")
        logger.info("  CREATE %s", agents_md_path)
    files_written += 1

    skills_dir = output_dir / "skills"
    for agent_name, skill_content in result.agent_skills.items():
        safe_agent_dir = _validate_path_component(agent_name, skills_dir)
        skill_path = safe_agent_dir / "SKILL.md"
        if dry_run:
            logger.info("  WOULD CREATE %s", skill_path)
        else:
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            skill_path.write_text(skill_content, encoding="utf-8")
            logger.info("  CREATE %s", skill_path)
        files_written += 1

    return files_written


def export_json(agents: list[AgentDefinition]) -> str:
    """Export agent definitions as JSON for programmatic consumption.

    Args:
        agents: List of agents to export.

    Returns:
        JSON string with agent data.
    """
    data = []
    for agent in agents:
        data.append({
            "name": agent.name,
            "description": agent.description,
            "model": _MODEL_MAP.get(agent.model, agent.model),
            "role": _TIER_TO_OPENCLAW_ROLE.get(agent.tier, agent.tier),
            "argument_hint": agent.argument_hint,
            "source": agent.source_path if agent.source_path else agent.name,
        })
    return json.dumps({"agents": data, "count": len(data)}, indent=2)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the OpenClaw bridge script.

    Args:
        argv: Command-line arguments. Defaults to sys.argv[1:].

    Returns:
        Exit code (0 for success).
    """
    parser = argparse.ArgumentParser(
        description="Export ai-agents definitions to OpenClaw workspace format.",
    )
    parser.add_argument(
        "--agents-dir",
        type=Path,
        default=Path("src/claude"),
        help="Directory containing agent .md files (default: src/claude)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("openclaw-workspace"),
        help="Output directory for OpenClaw workspace (default: openclaw-workspace)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without writing files",
    )
    parser.add_argument(
        "--format",
        choices=["workspace", "json"],
        default="workspace",
        help="Output format: workspace (files) or json (stdout)",
    )

    args = parser.parse_args(argv)

    if not args.agents_dir.is_dir():
        logger.error("Agents directory does not exist: %s", args.agents_dir)
        return 2

    agents = load_agents(args.agents_dir)
    if not agents:
        logger.error("No valid agent definitions found in %s", args.agents_dir)
        return 1

    logger.info("Found %d agent definitions", len(agents))

    if args.format == "json":
        print(export_json(agents))
        return 0

    result = export_agents(agents)
    files_written = write_workspace(result, args.output_dir, dry_run=args.dry_run)

    action = "Would create" if args.dry_run else "Created"
    logger.info("%s %d files for %d agents", action, files_written, result.agent_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
