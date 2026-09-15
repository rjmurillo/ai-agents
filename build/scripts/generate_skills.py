#!/usr/bin/env python3
"""Generate Copilot CLI skill artifacts from .claude/skills/ (REQ-003-001).

Reads ``artifacts.skills`` from a platform YAML and copies each skill
directory (one whose top-level entry contains a ``SKILL.md``) into the
configured output directory. Honors NO-REGEN sentinels (REQ-003-008) and
the AGENTS.md/CLAUDE.md exclude policy (REQ-003-010).

Mode supported: ``directory-copy`` (whole tree). Other modes raise
:class:`ValueError`.

Before the copy loop, :func:`generate_skills` runs
``skill_templates.compile_all`` (ADR-108, "Template-Owned Skill Files Under
``.claude/skills/``"). That record amends REQ-003-010 and ADR-107 property 1
for exactly one artifact class: a skill whose canonical source is a mustache
template under ``templates/skills/``. Quoted verbatim from ADR-108 section 2:

    "The build shall never write to ``.claude/<artifact>/`` or
    ``.claude/settings.json``, except the template-owned skill files whose
    template exists under ``templates/skills/`` at run time (ADR-108). All
    other generation targets ``src/copilot-cli/`` or ``.github/instructions/``."

A repository with no ``templates/skills/`` directory yet (this module's own
first landing) compiles zero templates and behaves exactly as before this
change: :func:`skill_templates.discover` returns an empty mapping and
``compile_all`` is a no-op, exit 0.

EXIT CODES:
  0 - success (or validate passed)
  1 - logic error (no SKILL.md found in source, copy failure, a template
      rendered content that drifted from the committed file under
      ``--validate``, etc.)
  2 - configuration error (config missing, stanza absent, mode unknown, a
      template used a disallowed tag or named a missing partial)

Per ADR-035 Exit Code Standardization.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

import skill_templates  # noqa: E402

# _copy_skill_tree, GenerateSkillsError, SkillSupportSyncError,
# _iter_skill_sources, _DEFAULT_EXCLUDES, and sync_claude_plugin_skill_support
# live in skill_support_mirror.py (split for the taste-lint file-size ceiling,
# ADR-109 B3's support-file follow-up), re-exported here so every existing
# caller and test that reaches them through generate_skills.<name> keeps
# working unchanged.
from skill_support_mirror import (  # noqa: E402,F401
    _DEFAULT_EXCLUDES,
    GenerateSkillsError,
    SkillSupportSyncError,
    _copy_skill_tree,
    _iter_skill_sources,
    sync_claude_plugin_skill_support,
)
from yaml_loader import ConfigError, load_platform_config, validate_relative_path  # noqa: E402


def _resolve_paths(repo_root: Path, source_dir: str, output_dir: str) -> tuple[Path, Path]:
    """Resolve source/output relative paths and reject traversal."""
    for field, value in (("sourceDir", source_dir), ("outputDir", output_dir)):
        errs = validate_relative_path(field, value)
        if errs:
            raise GenerateSkillsError("; ".join(errs))
    return repo_root / source_dir, repo_root / output_dir


def generate_skills(
    config_path: Path,
    repo_root: Path,
    *,
    what_if: bool = False,
    validate: bool = False,
) -> int:
    """Generate skill outputs per the artifacts.skills stanza.

    ``validate`` controls only the template compile step's write mode
    (ADR-108): ``True`` renders every ``templates/skills/*.SKILL.md.tmpl``
    and compares against the committed ``.claude/skills/<name>/SKILL.md``
    without writing; ``False`` writes when the render differs. Either way
    the copy loop below still runs once the compile step returns 0, so
    ``build/scripts/build_all.py --check`` can pass ``validate=True`` and
    still exercise the existing Copilot-mirror staleness detection over the
    (untouched) compiled output. The standalone ``--validate`` CLI flag is a
    separate code path in :func:`main` that skips this function entirely,
    because that flag's contract is "check templates only, do not copy".

    Returns:
        Exit code (0/1/2) per ADR-035.
    """
    print()
    print("=== Skills Generation ===")
    print(f"Config: {config_path}")
    print(f"Repo root: {repo_root}")
    print(f"Mode: {'WhatIf' if what_if else 'Generate'}")
    print()

    compile_result = skill_templates.compile_all(repo_root, validate=validate, what_if=what_if)
    if compile_result.written:
        print(f"Templates compiled: {len(compile_result.written)}")
    if compile_result.skipped:
        print(f"Templates skipped (NO-REGEN): {len(compile_result.skipped)}")
    if compile_result.drifted:
        print(f"Templates drifted from committed SKILL.md: {len(compile_result.drifted)}")
    if compile_result.exit_code != 0:
        # int(...): mypy resolves this sibling sys.path import as
        # `scripts.skill_templates` (its build/scripts/__init__.py-derived
        # qualified name) rather than the bare `skill_templates` this module
        # imports it as, so it cannot match the two names and treats the
        # attribute access as Any. Pre-existing for every sibling import in
        # this file (regen_guard, copilot_body_translation, yaml_loader);
        # this is the first place a value crosses a typed function boundary
        # directly enough for --warn-return-any to notice.
        return int(compile_result.exit_code)

    sync_written, sync_removed, sync_skipped, sync_errors = sync_claude_plugin_skill_support(
        repo_root, what_if=what_if, check=validate
    )
    if sync_written or sync_removed:
        label = "drift" if validate else "written"
        removed_label = "stale drift" if validate else "stale removed"
        print(
            f"Claude plugin skill support files: {sync_written} {label}, "
            f"{sync_removed} {removed_label}"
        )
    if sync_skipped:
        print(f"Claude plugin skill support files skipped (NO-REGEN): {sync_skipped}")
    if sync_errors:
        for err in sync_errors:
            print(f"Error: {err}", file=sys.stderr)
        return 1
    if validate and (sync_written or sync_removed):
        # Direct comparison against .claude/skills/, independent of git
        # diff: catches a hand edit or an extra file under
        # src/claude/skills/ that was never committed, which git diff has
        # no signal for. Exit 1 here (generate_skills.py's own drift code);
        # build_all._build_skills escalates it to 2 under --check the same
        # way it already escalates skill_templates.compile_all's drift.
        return 1

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
            f"Error: unsupported skills mode '{mode}' (only 'directory-copy' implemented)",
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
    # ADR-109 B3: the plugin tree src/claude/skills/<name>/SKILL.md was just
    # rendered by skill_templates.compile_all above (this call's own
    # compile_result), so its bytes are fresher than .claude/skills/, which
    # this platform's binplace step will not refresh until later in the
    # pipeline. discover() names every skill with a template; a skill
    # without one has no plugin-tree file, and _copy_skill_tree falls back
    # to source / "SKILL.md" for it.
    templated = skill_templates.discover(repo_root)
    print(f"Found {len(skills)} skill(s)")
    total_written = 0
    total_skipped = 0
    for src in skills:
        target = output_dir / src.name
        print(f"Processing: {src.name}")
        plugin_skill_md = (
            repo_root / "src" / "claude" / "skills" / src.name / "SKILL.md"
            if src.name in templated
            else None
        )
        written, skipped = _copy_skill_tree(
            src,
            target,
            what_if=what_if,
            skills_output_dir=output_dir if is_copilot else None,
            plugin_skill_md=plugin_skill_md,
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
    parser.add_argument(
        "--validate",
        action="store_true",
        help=(
            "Check every templates/skills/*.SKILL.md.tmpl against its committed "
            ".claude/skills/<name>/SKILL.md and exit; never writes, never copies."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = args.repo_root or _SCRIPT_DIR.parent.parent

    if args.validate:
        # Skips generate_skills() entirely: --validate's contract is "check
        # the templates, don't touch the copy loop or require a platform
        # config at all" (ADR-108 section 4, "Drift is a gate, not a header").
        result = skill_templates.compile_all(repo_root, validate=True, what_if=False)
        if result.drifted:
            print("DRIFTED (template renders differ from committed SKILL.md):")
            for path in result.drifted:
                print(f"  {path}")
        elif result.exit_code == 0:
            print("Templates match their compiled SKILL.md files.")
        return int(result.exit_code)  # see the compile_result int(...) note above

    config_path = args.config or (repo_root / "templates" / "platforms" / "copilot-cli.yaml")
    if not config_path.is_file():
        print(f"Error: config not found: {config_path}", file=sys.stderr)
        return 2
    return generate_skills(config_path, repo_root, what_if=args.what_if)


if __name__ == "__main__":
    sys.exit(main())
