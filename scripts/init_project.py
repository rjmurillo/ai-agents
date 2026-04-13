#!/usr/bin/env python3
"""Initialize ai-agents project scaffolding for a new repository.

Creates the directory structure and configuration files needed to use
the ai-agents system with Claude Code, VS Code, or Copilot CLI.

Usage:
    python3 scripts/init_project.py
    python3 scripts/init_project.py --minimal
    python3 scripts/init_project.py --dry-run
    python3 scripts/init_project.py --target-dir /path/to/project
    python3 scripts/init_project.py --force

Exit Codes:
    0: Success
    1: Logic error (e.g., files already exist without --force)
    2: Configuration error (e.g., invalid target directory)

Per ADR-042: Python-first for new scripts.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)

# Directories to create under .agents/
_AGENTS_DIRS: list[str] = [
    "architecture",
    "governance",
    "sessions",
    "planning",
    "memory",
]

# Directories for the minimal scaffold
_AGENTS_DIRS_MINIMAL: list[str] = [
    "architecture",
    "sessions",
]

_CLAUDE_MD_TEMPLATE = """\
# Claude Code Instructions

@AGENTS.md
"""

_AGENTS_MD_TEMPLATE = """\
# AGENTS.md

Cross-platform agent instructions for Claude Code, Copilot CLI, and VS Code.

## Session Protocol

Session logs go in `.agents/sessions/`.

## Architecture Decisions

ADRs go in `.agents/architecture/`.

## Coding Standards

| Topic | Standard |
|-------|----------|
| Commit format | `<type>(<scope>): <desc>` |
| Exit codes | 0=success, 1=logic, 2=config, 3=external, 4=auth |
"""

_GITIGNORE_ENTRIES: list[str] = [
    "# ai-agents session logs",
    ".agents/sessions/*.json",
]

_SERENA_PROJECT_TEMPLATE = """\
# Serena project configuration for ai-agents
# See https://github.com/rjmurillo/ai-agents for details.
languages:
- python
- markdown

encoding: "utf-8"
ignore_all_files_in_gitignore: true
ignored_paths: []
read_only: false
excluded_tools: []
initial_prompt: ""
project_name: "{project_name}"
included_optional_tools: []
base_modes:
default_modes:
fixed_tools: []
symbol_info_budget:
language_backend:
line_ending:
read_only_memory_patterns: []
ignored_memory_patterns: []
ls_specific_settings: {{}}
"""

_TEAM_YAML_TEMPLATE = """\
# Default agent team configuration
# Defines the starter set of agents available after `ai-agents init`.
# Each agent maps to a shared template in templates/agents/.
#
# Customize roles, add new agents, or remove unused ones as your project grows.
team:
  - name: orchestrator
    role: Task coordination and multi-step workflow management
  - name: implementer
    role: Code implementation with quality standards
  - name: analyst
    role: Research, investigation, and root cause analysis
  - name: architect
    role: System design, ADRs, and architectural governance
  - name: qa
    role: Testing, verification, and coverage validation
  - name: security
    role: Threat modeling, vulnerability scanning, OWASP compliance
  - name: devops
    role: CI/CD pipelines, build automation, deployment
  - name: critic
    role: Plan validation and gap analysis
"""

_COPILOT_INSTRUCTIONS_TEMPLATE = """\
# GitHub Copilot Instructions

See AGENTS.md for cross-platform agent instructions.
"""

_STARTER_AGENTS: dict[str, str] = {
    "orchestrator": """\
---
name: orchestrator
description: >-
  Task coordinator that routes work to specialized agents,
  manages handoffs, and synthesizes results.
model: sonnet
---
# Orchestrator Agent

Coordinate multi-step tasks by delegating to specialized agents.
Classify complexity, sequence workflows, and synthesize results.

## Workflow

1. Analyze the request and identify required capabilities.
2. Delegate to the appropriate specialist agent.
3. Verify outputs meet acceptance criteria.
4. Synthesize results into a coherent response.
""",
    "implementer": """\
---
name: implementer
description: >-
  Engineering expert that implements plans with production-quality code.
  Enforces testability, encapsulation, and intentional coupling.
model: sonnet
---
# Implementer Agent

Implement approved plans with production-quality code.
Write tests alongside code. Commit atomically with conventional messages.

## Standards

- Cyclomatic complexity <=10, methods <=60 lines
- SOLID, DRY, YAGNI
- Programming by intention: sergeant methods direct workflow
""",
    "analyst": """\
---
name: analyst
description: >-
  Research specialist that investigates root causes, surfaces unknowns,
  and gathers evidence before implementation.
model: sonnet
---
# Analyst Agent

Investigate before implementing. Gather evidence, evaluate feasibility,
identify dependencies and risks. Document findings with sources.

## Process

1. Define the question precisely.
2. Search code, docs, and history for evidence.
3. Evaluate feasibility and identify risks.
4. Report findings with confidence levels.
""",
    "architect": """\
---
name: architect
description: >-
  System design authority that guards architectural coherence,
  enforces patterns, and maintains boundaries.
model: sonnet
---
# Architect Agent

Guard architectural coherence. Create ADRs, conduct design reviews,
ensure decisions align with separation, extensibility, and consistency.

## Responsibilities

- Review proposed changes for architectural impact.
- Create Architecture Decision Records for significant decisions.
- Enforce module boundaries and dependency direction.
""",
    "qa": """\
---
name: qa
description: >-
  Quality assurance specialist that verifies implementations work
  correctly for real users, not just passing tests.
model: sonnet
---
# QA Agent

Verify implementations work for real users. Design test strategies,
validate coverage against acceptance criteria, report results with evidence.

## Approach

1. Identify acceptance criteria and edge cases.
2. Design test scenarios covering happy path and failure modes.
3. Execute tests and document results.
4. Report gaps between expected and actual behavior.
""",
    "security": """\
---
name: security
description: >-
  Security specialist fluent in threat modeling, vulnerability assessment,
  and OWASP Top 10.
model: sonnet
---
# Security Agent

Defense-first security analysis. Scan for CWE patterns, detect secrets,
audit dependencies, map attack surfaces.

## Focus Areas

- OWASP Top 10 vulnerability patterns
- Secret and credential detection
- Dependency supply chain risks
- Input validation and output encoding
""",
    "devops": """\
---
name: devops
description: >-
  CI/CD specialist that designs pipelines, configures build systems,
  and manages deployment workflows.
model: sonnet
---
# DevOps Agent

Design and maintain CI/CD pipelines. Configure build systems,
manage secrets, optimize caching, ensure reliable deployments.

## Capabilities

- GitHub Actions workflow design
- Build optimization and caching
- Environment and secrets management
- Deployment strategy and rollback planning
""",
    "critic": """\
---
name: critic
description: >-
  Constructive reviewer that stress-tests plans before implementation.
  Validates completeness, identifies gaps, catches ambiguity.
model: sonnet
---
# Critic Agent

Stress-test plans before implementation. Challenge assumptions,
check alignment, block approval when risks are not mitigated.

## Review Checklist

1. Are acceptance criteria complete and testable?
2. Are edge cases and failure modes addressed?
3. Are dependencies identified and risks mitigated?
4. Is the scope appropriately bounded?
""",
}

_NEXT_STEPS_MESSAGE = """\
Next steps:

  1. Review the generated files and customize for your project.
  2. Edit AGENTS.md to add project-specific conventions.
  3. Customize agent definitions in .claude/agents/ as needed.
  4. Start working: agents are ready to use immediately.

Documentation: https://github.com/rjmurillo/ai-agents
"""


class ProjectInitializer:
    """Scaffolds ai-agents directory structure for a project."""

    def __init__(
        self,
        target_dir: Path,
        minimal: bool = False,
        force: bool = False,
        dry_run: bool = False,
        no_agents: bool = False,
    ) -> None:
        self.target_dir = target_dir.resolve()
        self.minimal = minimal
        self.force = force
        self.dry_run = dry_run
        self.no_agents = no_agents
        self.created_dirs: list[Path] = []
        self.created_files: list[Path] = []
        self.skipped_files: list[Path] = []

    def validate_target(self) -> bool:
        """Verify target directory exists and is a directory."""
        if not self.target_dir.exists():
            logger.error("Target directory does not exist: %s", self.target_dir)
            return False
        if not self.target_dir.is_dir():
            logger.error("Target path is not a directory: %s", self.target_dir)
            return False
        return True

    def _write_file(self, path: Path, content: str) -> bool:
        """Write content to a file. Respects --force and --dry-run."""
        if path.exists() and not self.force:
            self.skipped_files.append(path)
            rel = path.relative_to(self.target_dir)
            logger.info("  SKIP %s (exists, use --force to overwrite)", rel)
            return True

        if self.dry_run:
            self.created_files.append(path)
            logger.info("  WOULD CREATE %s", path.relative_to(self.target_dir))
            return True

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.created_files.append(path)
        logger.info("  CREATE %s", path.relative_to(self.target_dir))
        return True

    def _make_dir(self, path: Path) -> bool:
        """Create a directory. Respects --dry-run."""
        if path.exists():
            return True

        if self.dry_run:
            self.created_dirs.append(path)
            logger.info("  WOULD CREATE %s/", path.relative_to(self.target_dir))
            return True

        path.mkdir(parents=True, exist_ok=True)
        self.created_dirs.append(path)
        logger.info("  CREATE %s/", path.relative_to(self.target_dir))
        return True

    def scaffold_agents_dirs(self) -> bool:
        """Create .agents/ directory structure."""
        dirs = _AGENTS_DIRS_MINIMAL if self.minimal else _AGENTS_DIRS
        agents_root = self.target_dir / ".agents"

        for dir_name in dirs:
            if not self._make_dir(agents_root / dir_name):
                return False
        return True

    def scaffold_agents_md(self) -> bool:
        """Create AGENTS.md at project root."""
        return self._write_file(
            self.target_dir / "AGENTS.md",
            _AGENTS_MD_TEMPLATE,
        )

    def scaffold_claude_md(self) -> bool:
        """Create CLAUDE.md at project root."""
        return self._write_file(
            self.target_dir / "CLAUDE.md",
            _CLAUDE_MD_TEMPLATE,
        )

    def scaffold_serena(self) -> bool:
        """Create .serena/ directory with project.yml and memories/."""
        serena_root = self.target_dir / ".serena"
        project_name = self.target_dir.name

        if not self._make_dir(serena_root / "memories"):
            return False

        return self._write_file(
            serena_root / "project.yml",
            _SERENA_PROJECT_TEMPLATE.format(project_name=project_name),
        )

    def scaffold_team_manifest(self) -> bool:
        """Create .agents/team.yaml with the default agent team."""
        if self.minimal:
            return True
        return self._write_file(
            self.target_dir / ".agents" / "team.yaml",
            _TEAM_YAML_TEMPLATE,
        )

    def scaffold_starter_agents(self) -> bool:
        """Create .claude/agents/ with starter agent definitions."""
        if self.no_agents or self.minimal:
            return True

        agents_dir = self.target_dir / ".claude" / "agents"
        if not self._make_dir(agents_dir):
            return False

        for name, content in _STARTER_AGENTS.items():
            if not self._write_file(agents_dir / f"{name}.md", content):
                return False
        return True

    def scaffold_copilot_instructions(self) -> bool:
        """Create .github/copilot-instructions.md."""
        if self.minimal:
            return True
        return self._write_file(
            self.target_dir / ".github" / "copilot-instructions.md",
            _COPILOT_INSTRUCTIONS_TEMPLATE,
        )

    def update_gitignore(self) -> bool:
        """Append ai-agents entries to .gitignore if not present."""
        gitignore_path = self.target_dir / ".gitignore"
        existing = ""
        if gitignore_path.exists():
            existing = gitignore_path.read_text(encoding="utf-8")

        existing_lines = {line.strip() for line in existing.splitlines()}
        entries_to_add = [
            entry
            for entry in _GITIGNORE_ENTRIES
            if entry.strip() not in existing_lines
        ]

        if not entries_to_add:
            logger.info("  SKIP .gitignore (entries already present)")
            return True

        new_content = existing.rstrip("\n") + "\n\n" + "\n".join(entries_to_add) + "\n"

        if self.dry_run:
            logger.info("  WOULD UPDATE .gitignore")
            return True

        gitignore_path.write_text(new_content, encoding="utf-8")
        logger.info("  UPDATE .gitignore")
        return True

    def run(self) -> int:
        """Execute the scaffolding workflow."""
        if not self.validate_target():
            return 2

        mode = "minimal" if self.minimal else "full"
        prefix = "[DRY RUN] " if self.dry_run else ""
        logger.info("%sInitializing ai-agents (%s) in %s", prefix, mode, self.target_dir)
        logger.info("")

        steps = [
            self.scaffold_agents_dirs,
            self.scaffold_agents_md,
            self.scaffold_claude_md,
            self.scaffold_serena,
            self.scaffold_team_manifest,
            self.scaffold_starter_agents,
            self.scaffold_copilot_instructions,
            self.update_gitignore,
        ]

        for step in steps:
            if not step():
                return 1

        logger.info("")
        self._print_summary()
        return 0

    def _print_summary(self) -> None:
        """Print a summary of actions taken and next steps."""
        if self.dry_run:
            logger.info(
                "Dry run complete. %d files and %d directories would be created.",
                len(self.created_files),
                len(self.created_dirs),
            )
        else:
            logger.info(
                "Done. Created %d files and %d directories. Skipped %d existing files.",
                len(self.created_files),
                len(self.created_dirs),
                len(self.skipped_files),
            )
            logger.info("")
            logger.info(_NEXT_STEPS_MESSAGE)


def _add_init_args(parser: argparse.ArgumentParser) -> None:
    """Add shared init arguments to a parser."""
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=Path.cwd(),
        help="Target project directory (default: current directory)",
    )
    parser.add_argument(
        "--minimal",
        action="store_true",
        help="Create minimal scaffold (fewer directories, no copilot config)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing files",
    )
    parser.add_argument(
        "--no-agents",
        action="store_true",
        help="Skip scaffolding starter agent definitions in .claude/agents/",
    )


def _run_init(args: argparse.Namespace) -> int:
    """Run the init command from parsed args."""
    initializer = ProjectInitializer(
        target_dir=args.target_dir,
        minimal=args.minimal,
        force=args.force,
        dry_run=args.dry_run,
        no_agents=args.no_agents,
    )
    return initializer.run()


def main() -> int:
    """Entry point for the ai-agents CLI.

    Supports subcommands:
        ai-agents init [--target-dir DIR] [--minimal] [--force] [--dry-run]

    When invoked without a subcommand (for backwards compatibility),
    behaves as if 'init' was specified.
    """
    parser = argparse.ArgumentParser(
        prog="ai-agents",
        description="AI agent orchestration framework",
    )
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser(
        "init",
        help="Initialize ai-agents project scaffolding",
    )
    _add_init_args(init_parser)

    # Backwards compatibility: support direct flags without 'init' subcommand
    _add_init_args(parser)

    args = parser.parse_args()

    if args.command == "init" or args.command is None:
        return _run_init(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
