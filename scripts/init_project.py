#!/usr/bin/env python3
"""Initialize ai-agents project scaffolding for a new repository.

Creates the directory structure and configuration files needed to use
the ai-agents system with Claude Code, VS Code, or Copilot CLI.

Usage:
    python3 scripts/init_project.py init [--target-dir DIR] [--minimal] [--force]
    python3 scripts/init_project.py init [--only CATEGORIES] [--target-dir DIR]
    python3 scripts/init_project.py list [commands|agents|skills] [--target-dir DIR]
    python3 scripts/init_project.py update [--target-dir DIR]

Exit Codes:
    0: Success
    1: Logic error (e.g., files already exist without --force)
    2: Configuration error (e.g., invalid target directory)

Per ADR-042: Python-first for new scripts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from datetime import UTC, datetime
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

_GETTING_STARTED_TEMPLATE = """\
# Getting Started with ai-agents

## What you just got

The `ai-agents init` command scaffolded a ready-to-use agent team into your project:

- **`.agents/`** — session logs, architecture decisions, governance, and planning
- **`.agents/team.yaml`** — your agent roster (orchestrator, implementer, analyst, and more)
- **`AGENTS.md`** — cross-platform agent instructions for Claude Code and Copilot
- **`CLAUDE.md`** — Claude Code harness entry point

## First 5 things to try

1. Open this folder in Claude Code and run `/spec` to define what to build.
2. Run `/plan` to decompose your spec into milestones with dependencies.
3. Run `/build` to implement changes in thin vertical slices.
4. Run `/test` to prove your implementation works.
5. Run `/review` then `/ship` to land your changes.

## If something looks broken

- Run `ai-agents list` to see what was installed.
- Run `ai-agents init --force` to re-scaffold from scratch.
- Check `.agents/sessions/` for session logs that may show what changed.

## Where to ask for help

- GitHub Issues: https://github.com/rjmurillo/ai-agents/issues
- README: https://github.com/rjmurillo/ai-agents#readme
"""

_VERSION_FILE = ".claude/.ai-agents-version.json"

_VALID_ONLY_CATEGORIES = frozenset({"commands", "agents", "skills"})


def _read_version_file(target_dir: Path) -> dict[str, str] | None:
    version_path = target_dir / _VERSION_FILE
    if not version_path.exists():
        return None
    try:
        return json.loads(version_path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return None


def _write_version_file(target_dir: Path, version: str = "0.1.0") -> None:
    version_path = target_dir / _VERSION_FILE
    version_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": version,
        "manifestHash": hashlib.sha256(version.encode()).hexdigest()[:16],
        "installedAt": datetime.now(UTC).isoformat(),
        "source": "npx",
    }
    version_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _scan_directory(path: Path) -> list[dict[str, str]]:
    if not path.is_dir():
        return []
    items: list[dict[str, str]] = []
    for entry in sorted(path.iterdir()):
        if entry.name.startswith(".") or entry.name.startswith("_"):
            continue
        name = entry.stem if entry.is_file() else entry.name
        description = _extract_description(entry)
        items.append({"name": name, "description": description})
    return items


def _extract_description(path: Path) -> str:
    target = path
    if path.is_dir():
        for candidate in ["SKILL.md", "README.md"]:
            skill_file = path / candidate
            if skill_file.exists():
                target = skill_file
                break
        else:
            return ""

    if not target.is_file():
        return ""

    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return ""

    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
            return stripped[:80]
    return ""


class ProjectInitializer:
    """Scaffolds ai-agents directory structure for a project."""

    def __init__(
        self,
        target_dir: Path,
        minimal: bool = False,
        force: bool = False,
        dry_run: bool = False,
        only: frozenset[str] | None = None,
    ) -> None:
        self.target_dir = target_dir.resolve()
        self.minimal = minimal
        self.force = force
        self.dry_run = dry_run
        self.only = only
        self.created_dirs: list[Path] = []
        self.created_files: list[Path] = []
        self.skipped_files: list[Path] = []

    def _category_enabled(self, category: str) -> bool:
        if self.only is None:
            return True
        return category in self.only

    def validate_target(self) -> bool:
        """Verify target directory exists, is a directory, and has a safe name."""
        if not self.target_dir.exists():
            logger.error("Target directory does not exist: %s", self.target_dir)
            return False
        if not self.target_dir.is_dir():
            logger.error("Target path is not a directory: %s", self.target_dir)
            return False
        project_name = self.target_dir.name
        if not re.match(r"^[a-zA-Z0-9_-]+$", project_name):
            logger.error(
                "Error: project name must be alphanumeric with hyphens/underscores, got: %s",
                project_name,
            )
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

    def scaffold_team_manifest(self) -> bool:
        """Create .agents/team.yaml with the default agent team."""
        if self.minimal:
            return True
        return self._write_file(
            self.target_dir / ".agents" / "team.yaml",
            _TEAM_YAML_TEMPLATE,
        )

    def scaffold_copilot_instructions(self) -> bool:
        """Create .github/copilot-instructions.md."""
        if self.minimal:
            return True
        return self._write_file(
            self.target_dir / ".github" / "copilot-instructions.md",
            _COPILOT_INSTRUCTIONS_TEMPLATE,
        )

    def scaffold_getting_started(self) -> bool:
        """Create GETTING-STARTED.md at project root."""
        return self._write_file(
            self.target_dir / "GETTING-STARTED.md",
            _GETTING_STARTED_TEMPLATE,
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
        if self.only:
            mode = f"only={','.join(sorted(self.only))}"
        prefix = "[DRY RUN] " if self.dry_run else ""
        logger.info("%sInitializing ai-agents (%s) in %s", prefix, mode, self.target_dir)
        logger.info("")

        steps: list[tuple[str, object]] = [
            ("agents", self.scaffold_agents_dirs),
            ("agents", self.scaffold_agents_md),
            ("commands", self.scaffold_claude_md),
            ("agents", self.scaffold_team_manifest),
            ("commands", self.scaffold_copilot_instructions),
            ("commands", self.scaffold_getting_started),
            ("commands", self.update_gitignore),
        ]

        for category, step in steps:
            if not self._category_enabled(category):
                continue
            if not step():  # type: ignore[operator]
                return 1

        if not self.dry_run:
            _write_version_file(self.target_dir)

        logger.info("")
        self._print_summary()
        return 0

    def _print_summary(self) -> None:
        """Print a summary of actions taken."""
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
        "--only",
        type=str,
        default=None,
        help="Comma-separated categories to scaffold: commands,agents,skills",
    )


def _parse_only(raw: str | None) -> frozenset[str] | None:
    if raw is None:
        return None
    categories = frozenset(c.strip().lower() for c in raw.split(",") if c.strip())
    invalid = categories - _VALID_ONLY_CATEGORIES
    if invalid:
        logger.error(
            "Invalid --only categories: %s. Valid: %s",
            ", ".join(sorted(invalid)),
            ", ".join(sorted(_VALID_ONLY_CATEGORIES)),
        )
        return frozenset()
    return categories


def _run_init(args: argparse.Namespace) -> int:
    """Run the init command from parsed args."""
    only = _parse_only(getattr(args, "only", None))
    if only is not None and len(only) == 0:
        return 2

    initializer = ProjectInitializer(
        target_dir=args.target_dir,
        minimal=args.minimal,
        force=args.force,
        dry_run=args.dry_run,
        only=only,
    )
    return initializer.run()


def _run_list(args: argparse.Namespace) -> int:
    """Run the list command."""
    target_dir = args.target_dir.resolve()
    filter_type = args.filter_type

    sections: list[tuple[str, Path]] = [
        ("commands", target_dir / ".claude" / "commands"),
        ("agents", target_dir / ".claude" / "agents"),
        ("skills", target_dir / ".claude" / "skills"),
    ]

    found_any = False
    for section_name, section_path in sections:
        if filter_type and filter_type != section_name:
            continue

        items = _scan_directory(section_path)
        if not items:
            if filter_type:
                logger.info("No %s found in %s", section_name, section_path)
            continue

        found_any = True
        logger.info("\033[1;36m%s\033[0m (%d)", section_name.upper(), len(items))
        for item in items:
            desc = f"  \033[90m{item['description']}\033[0m" if item["description"] else ""
            logger.info("  \033[1m%s\033[0m%s", item["name"], desc)
        logger.info("")

    if not found_any:
        logger.info("No ai-agents content found. Run 'ai-agents init' first.")
        return 1

    return 0


def _run_update(args: argparse.Namespace) -> int:
    """Run the update command."""
    target_dir = args.target_dir.resolve()
    version_data = _read_version_file(target_dir)

    if version_data is None:
        logger.error(
            "No version file found at %s. Run 'ai-agents init' first.",
            target_dir / _VERSION_FILE,
        )
        return 2

    logger.info("Current install:")
    logger.info("  Version:   %s", version_data.get("version", "unknown"))
    logger.info("  Installed: %s", version_data.get("installedAt", "unknown"))
    logger.info("  Hash:      %s", version_data.get("manifestHash", "unknown"))
    logger.info("")
    logger.info("Re-initializing with --force to update vendored files...")
    logger.info("")

    initializer = ProjectInitializer(
        target_dir=target_dir,
        force=True,
    )
    return initializer.run()


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ai-agents CLI.

    Supports subcommands:
        ai-agents init [--target-dir DIR] [--minimal] [--force] [--dry-run] [--only CATEGORIES]
        ai-agents list [commands|agents|skills] [--target-dir DIR]
        ai-agents update [--target-dir DIR]

    Prints help and exits when no subcommand is given.
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

    list_parser = subparsers.add_parser(
        "list",
        help="List vendored commands, agents, and skills",
    )
    list_parser.add_argument(
        "filter_type",
        nargs="?",
        choices=["commands", "agents", "skills"],
        default=None,
        help="Show only a specific category",
    )
    list_parser.add_argument(
        "--target-dir",
        type=Path,
        default=Path.cwd(),
        help="Target project directory (default: current directory)",
    )

    update_parser = subparsers.add_parser(
        "update",
        help="Update vendored ai-agents files to latest version",
    )
    update_parser.add_argument(
        "--target-dir",
        type=Path,
        default=Path.cwd(),
        help="Target project directory (default: current directory)",
    )

    args = parser.parse_args(argv)

    if not hasattr(args, "func") and args.command is None:
        parser.print_help()
        return 0

    if args.command == "init":
        return _run_init(args)
    if args.command == "list":
        return _run_list(args)
    if args.command == "update":
        return _run_update(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
