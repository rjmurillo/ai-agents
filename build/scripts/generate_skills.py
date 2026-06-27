#!/usr/bin/env python3
"""Generate Copilot CLI skill artifacts from .claude/skills/ (REQ-003-001).

Reads ``artifacts.skills`` from a platform YAML and copies each skill
directory (one whose top-level entry contains a ``SKILL.md``) into the
configured output directory. Honors NO-REGEN sentinels (REQ-003-008) and
the AGENTS.md/CLAUDE.md exclude policy (REQ-003-010).

Mode supported: ``directory-copy`` (whole tree). Other modes raise
:class:`ValueError`.

EXIT CODES:
  0 - success (or validate passed)
  1 - logic error (no SKILL.md found in source, copy failure, etc.)
  2 - configuration error (config missing, stanza absent, mode unknown)

Per ADR-035 Exit Code Standardization.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

from copilot_body_translation import translate_skill_file  # noqa: E402
from regen_guard import detect_reason as regen_detect_reason  # noqa: E402
from yaml_loader import ConfigError, load_platform_config, validate_relative_path  # noqa: E402

_DEFAULT_EXCLUDES = ("AGENTS.md", "CLAUDE.md")


class GenerateSkillsError(Exception):
    """Domain error for skill generation. Wraps copy/load issues."""


def _resolve_paths(repo_root: Path, source_dir: str, output_dir: str) -> tuple[Path, Path]:
    """Resolve source/output relative paths and reject traversal."""
    for field, value in (("sourceDir", source_dir), ("outputDir", output_dir)):
        errs = validate_relative_path(field, value)
        if errs:
            raise GenerateSkillsError("; ".join(errs))
    return repo_root / source_dir, repo_root / output_dir


def _iter_skill_sources(source_dir: Path, excludes: set[str]) -> list[Path]:
    """Return immediate subdirectories that contain a SKILL.md file.

    Excludes top-level files (AGENTS.md / CLAUDE.md). The check is by
    presence of a SKILL.md inside the immediate child directory; nested
    skill-like layouts are not recursed.
    """
    if not source_dir.is_dir():
        raise GenerateSkillsError(f"sourceDir not found: {source_dir}")
    skills: list[Path] = []
    for child in sorted(source_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name in excludes:
            continue
        if not (child / "SKILL.md").is_file():
            continue
        skills.append(child)
    return skills


def _copy_skill_tree(
    source: Path,
    target: Path,
    *,
    what_if: bool,
    skills_output_dir: Path | None = None,
) -> tuple[int, int]:
    """Copy a single skill directory into ``target``.

    Returns ``(written, skipped)`` counts; skipped reflects NO-REGEN
    protections per file. Existing files are overwritten unless protected.

    When ``skills_output_dir`` is provided (Copilot CLI target), the
    top-level ``SKILL.md`` body is translated from Claude Code conventions
    to Copilot CLI equivalents (issue #2743) instead of copied verbatim.
    Every other file is copied byte-for-byte.
    """
    written = 0
    skipped = 0
    for src_path in source.rglob("*"):
        if src_path.is_dir():
            continue
        # Skip Python cache artifacts; they're build-time noise that
        # belongs in .gitignore, not in a customer-facing plugin install.
        if "__pycache__" in src_path.parts or src_path.suffix in (".pyc", ".pyo"):
            continue
        rel = src_path.relative_to(source)
        dst_path = target / rel

        reason = regen_detect_reason(dst_path)
        if reason is not None:
            print(f"  NOTICE: skipped {dst_path} (NO-REGEN: {reason})")
            skipped += 1
            continue

        if what_if:
            print(f"  Would copy: {src_path} -> {dst_path}")
            continue

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        if skills_output_dir is not None and rel == Path("SKILL.md"):
            content = src_path.read_text(encoding="utf-8")
            dst_path.write_text(
                translate_skill_file(content, skills_output_dir), encoding="utf-8"
            )
        else:
            shutil.copy2(src_path, dst_path)
        written += 1
    return written, skipped


def generate_skills(
    config_path: Path,
    repo_root: Path,
    *,
    what_if: bool = False,
) -> int:
    """Generate skill outputs per the artifacts.skills stanza.

    Returns:
        Exit code (0/1/2) per ADR-035.
    """
    print()
    print("=== Skills Generation ===")
    print(f"Config: {config_path}")
    print(f"Repo root: {repo_root}")
    print(f"Mode: {'WhatIf' if what_if else 'Generate'}")
    print()

    try:
        cfg = load_platform_config(config_path)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    artifacts = cfg.get("artifacts")
    if not isinstance(artifacts, dict):
        print(f"Error: {config_path} has no `artifacts` mapping", file=sys.stderr)
        return 2
    stanza = artifacts.get("skills")
    if not isinstance(stanza, dict):
        print(f"Error: {config_path} has no `artifacts.skills` stanza", file=sys.stderr)
        return 2

    mode = str(stanza.get("mode", "directory-copy"))
    if mode != "directory-copy":
        print(
            f"Error: unsupported skills mode '{mode}' "
            "(only 'directory-copy' implemented)",
            file=sys.stderr,
        )
        return 2

    source_dir_str = str(stanza.get("sourceDir", ""))
    output_dir_str = str(stanza.get("outputDir", ""))
    excludes = set(stanza.get("excludeFilenames") or _DEFAULT_EXCLUDES)

    try:
        source_dir, output_dir = _resolve_paths(repo_root, source_dir_str, output_dir_str)
    except GenerateSkillsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    start_time = time.monotonic()

    try:
        skills = _iter_skill_sources(source_dir, excludes)
    except GenerateSkillsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not skills:
        print(f"Error: no skills with SKILL.md found under {source_dir}", file=sys.stderr)
        return 1

    is_copilot = str(cfg.get("provider", "")) == "copilot-cli"
    print(f"Found {len(skills)} skill(s)")
    total_written = 0
    total_skipped = 0
    for src in skills:
        target = output_dir / src.name
        print(f"Processing: {src.name}")
        written, skipped = _copy_skill_tree(
            src,
            target,
            what_if=what_if,
            skills_output_dir=output_dir if is_copilot else None,
        )
        total_written += written
        total_skipped += skipped
    duration = time.monotonic() - start_time

    print()
    print("=== Summary ===")
    print(f"Duration: {duration:.2f}s")
    if what_if:
        print("Dry run complete.")
        return 0
    print(f"Skills processed: {len(skills)}")
    print(f"Files written: {total_written}")
    if total_skipped:
        print(f"Files skipped (NO-REGEN): {total_skipped}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """CLI parser for skill generation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Platform YAML config (defaults to templates/platforms/copilot-cli.yaml).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (defaults to script's grandparent: build/scripts/../..).",
    )
    parser.add_argument("--what-if", action="store_true", help="Dry-run mode.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = args.repo_root or _SCRIPT_DIR.parent.parent
    config_path = args.config or (repo_root / "templates" / "platforms" / "copilot-cli.yaml")
    if not config_path.is_file():
        print(f"Error: config not found: {config_path}", file=sys.stderr)
        return 2
    return generate_skills(config_path, repo_root, what_if=args.what_if)


if __name__ == "__main__":
    sys.exit(main())
