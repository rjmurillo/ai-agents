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

_COPILOT_INSTRUCTIONS_TEMPLATE = """\
# GitHub Copilot Instructions

See AGENTS.md for cross-platform agent instructions.
"""


class ProjectInitializer:
    """Scaffolds ai-agents directory structure for a project."""

    def __init__(
        self,
        target_dir: Path,
        minimal: bool = False,
        force: bool = False,
        dry_run: bool = False,
    ) -> None:
        self.target_dir = target_dir.resolve()
        self.minimal = minimal
        self.force = force
        self.dry_run = dry_run
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

        entries_to_add = [
            entry for entry in _GITIGNORE_ENTRIES if entry not in existing
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


def main() -> int:
    """Entry point for project initialization."""
    parser = argparse.ArgumentParser(
        description="Initialize ai-agents project scaffolding",
    )

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

    args = parser.parse_args()

    initializer = ProjectInitializer(
        target_dir=args.target_dir,
        minimal=args.minimal,
        force=args.force,
        dry_run=args.dry_run,
    )
    return initializer.run()


if __name__ == "__main__":
    sys.exit(main())
