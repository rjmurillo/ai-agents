#!/usr/bin/env python3
"""Validate Claude skill installation across supported platforms.

Checks that skills in .claude/skills/ are properly structured and
accessible at expected installation paths.

Usage:
    python3 scripts/validate_skill_installation.py
    python3 scripts/validate_skill_installation.py --check-global
    python3 scripts/validate_skill_installation.py --verbose

Exit Codes:
    0: All skills valid (or installed correctly with --check-global)
    1: Validation errors found
    2: Configuration error (missing source directory)

Per ADR-042: Python-first for new scripts.
Per ADR-035: Standardized exit codes.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

REQUIRED_FRONTMATTER_FIELDS = ("name", "description")
OPTIONAL_FRONTMATTER_FIELDS = ("version", "model", "license", "metadata")

GLOBAL_SKILL_PATHS = {
    "claude": Path.home() / ".claude" / "skills",
}


def parse_frontmatter(skill_md: Path) -> dict | None:
    """Extract YAML frontmatter from a SKILL.md file."""
    try:
        content = skill_md.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("  Cannot read %s: %s", skill_md, e)
        return None

    if not content.startswith("---"):
        return None

    end = content.find("---", 3)
    if end == -1:
        return None

    try:
        return yaml.safe_load(content[3:end])
    except yaml.YAMLError as e:
        logger.error("  Invalid YAML frontmatter in %s: %s", skill_md, e)
        return None


def validate_skill_dir(skill_dir: Path, verbose: bool = False) -> list[str]:
    """Validate a single skill directory. Returns list of error messages."""
    errors: list[str] = []
    skill_name = skill_dir.name

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        errors.append(f"{skill_name}: missing SKILL.md")
        return errors

    frontmatter = parse_frontmatter(skill_md)
    if frontmatter is None:
        errors.append(f"{skill_name}: missing or invalid YAML frontmatter in SKILL.md")
        return errors

    for field in REQUIRED_FRONTMATTER_FIELDS:
        if field not in frontmatter:
            errors.append(f"{skill_name}: missing required field '{field}' in frontmatter")

    fm_name = frontmatter.get("name", "")
    if fm_name and fm_name.lower() != skill_name.lower():
        errors.append(f"{skill_name}: frontmatter name '{fm_name}' does not match directory name")

    if verbose and not errors:
        version = frontmatter.get("version", "unversioned")
        logger.info("  OK: %s (v%s)", skill_name, version)

    return errors


def validate_source_skills(source_dir: Path, verbose: bool = False) -> int:
    """Validate all skills in the source directory."""
    skills_dir = source_dir / ".claude" / "skills"
    if not skills_dir.exists():
        logger.error("Skills directory not found: %s", skills_dir)
        return 2

    skill_dirs = sorted(
        d for d in skills_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    )

    if not skill_dirs:
        logger.error("No skill directories found in %s", skills_dir)
        return 2

    logger.info("Validating %d skills in %s", len(skill_dirs), skills_dir)

    all_errors: list[str] = []
    for skill_dir in skill_dirs:
        errors = validate_skill_dir(skill_dir, verbose)
        all_errors.extend(errors)

    if all_errors:
        logger.info("")
        logger.info("=== Validation Errors ===")
        for err in all_errors:
            logger.error("  %s", err)
        logger.info("")
        logger.info("Result: FAILED (%d errors in %d skills)", len(all_errors), len(skill_dirs))
        return 1

    logger.info("")
    logger.info("Result: PASSED (%d skills validated)", len(skill_dirs))
    return 0


def check_global_installation(verbose: bool = False) -> int:
    """Check skills installed at global paths."""
    found_any = False
    all_errors: list[str] = []

    for platform_name, global_path in GLOBAL_SKILL_PATHS.items():
        if not global_path.exists():
            logger.info("  %s: not installed (%s not found)", platform_name, global_path)
            continue

        found_any = True
        skill_dirs = sorted(
            d for d in global_path.iterdir() if d.is_dir() and not d.name.startswith(".")
        )

        logger.info("  %s: %d skills at %s", platform_name, len(skill_dirs), global_path)

        if verbose:
            for skill_dir in skill_dirs:
                errors = validate_skill_dir(skill_dir, verbose)
                all_errors.extend(errors)

    if not found_any:
        logger.info("")
        logger.info("No global skill installations found.")
        logger.info("Install with: skill-installer install project-toolkit --platform claude")
        return 0

    if all_errors:
        logger.info("")
        logger.info("=== Global Installation Errors ===")
        for err in all_errors:
            logger.error("  %s", err)
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for skill installation validation."""
    parser = argparse.ArgumentParser(description="Validate Claude skill installation")
    parser.add_argument(
        "--source",
        default=".",
        help="Path to repository root (default: current directory)",
    )
    parser.add_argument(
        "--check-global",
        action="store_true",
        help="Also check global installation paths",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show details for each skill",
    )
    args = parser.parse_args(argv)

    source = Path(args.source).resolve()
    result = validate_source_skills(source, args.verbose)

    if args.check_global:
        logger.info("")
        logger.info("Checking global installations...")
        global_result = check_global_installation(args.verbose)
        if global_result != 0 and result == 0:
            result = global_result

    return result


if __name__ == "__main__":
    sys.exit(main())
