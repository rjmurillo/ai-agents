#!/usr/bin/env python3
"""Bridge Claude commands to Copilot CLI user-invocable skills (REQ-003-001).

Reads ``artifacts.commands`` from a platform YAML and rewrites every
``.claude/commands/<name>.md`` into a Copilot CLI skill at
``src/copilot-cli/skills/<name>/SKILL.md`` whose frontmatter declares
``user-invocable: true``. Copilot CLI plugins have no native custom slash
command surface; user-invocable skills fire as ``/SKILL-NAME`` and serve
as the bridge for Claude's slash commands.

The transform is intentionally narrow:

- top-level ``.md`` files only (sub-directories like ``forgetful/`` and
  ``pr-quality/`` are skipped — they are namespaced sub-commands the
  Copilot CLI runtime cannot model today)
- ``CLAUDE.md`` excluded (per the AGENTS.md/CLAUDE.md exclude policy)
- the source frontmatter is preserved; ``user-invocable: true`` (and any
  other ``appendFrontmatter`` keys) is merged in
- ``name`` is set from the file stem when absent, ``description`` from the
  source frontmatter or the first non-blank body line when absent — the
  Copilot CLI skill schema requires both
- collisions with hand-authored skills (an existing
  ``src/<provider>/skills/<name>/`` whose source lives at
  ``.claude/skills/<name>/``) abort with exit 1: do NOT silently overwrite
  authored content. The generator only writes to its own outputs.
- NO-REGEN sentinel honored (``regen_guard.is_protected``)

EXIT CODES:
  0 - success
  1 - logic error (collision with an authored skill, source missing)
  2 - configuration error (config missing or stanza absent)

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
sys.path.insert(0, str(_SCRIPT_DIR.parent))

from copilot_body_translation import translate_body  # noqa: E402
from generate_agents_common import (  # noqa: E402
    format_frontmatter_yaml,
    parse_simple_frontmatter,
    read_yaml_frontmatter,
)
from regen_guard import detect_reason as regen_detect_reason  # noqa: E402
from yaml_loader import ConfigError, load_platform_config, validate_relative_path  # noqa: E402

_DEFAULT_EXCLUDES = ("CLAUDE.md",)


class GenerateCommandsError(Exception):
    """Domain error for command-to-skill bridging."""


def _resolve_paths(
    repo_root: Path, source_dir: str, output_dir: str
) -> tuple[Path, Path]:
    """Resolve source/output relative paths and reject traversal."""
    for field, value in (("sourceDir", source_dir), ("outputDir", output_dir)):
        errs = validate_relative_path(field, value)
        if errs:
            raise GenerateCommandsError("; ".join(errs))
    return repo_root / source_dir, repo_root / output_dir


def _iter_command_sources(source_dir: Path, excludes: set[str]) -> list[Path]:
    """Return top-level ``*.md`` files (no recursion into subdirs).

    Sub-directories under ``.claude/commands/`` (e.g. ``forgetful/``,
    ``pr-quality/``) hold namespaced sub-commands. Copilot CLI's user-
    invocable skill surface is flat; mapping nested commands would lose
    the namespace prefix and collide with existing skill names. Treat
    them as out-of-scope for the bridge.
    """
    if not source_dir.is_dir():
        raise GenerateCommandsError(f"sourceDir not found: {source_dir}")
    sources: list[Path] = []
    for child in sorted(source_dir.iterdir()):
        if not child.is_file():
            continue
        if child.suffix != ".md":
            continue
        if child.name in excludes:
            continue
        sources.append(child)
    return sources


def _first_nonblank_line(body: str) -> str:
    """Return the first non-blank, non-heading line from a body, stripped.

    Used to derive a ``description`` when the source frontmatter omits one.
    Markdown headings (``#``) are skipped because the skill description
    should describe behavior, not restate the title.
    """
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        return line
    return ""


def _merge_frontmatter(
    source_frontmatter: dict[str, str | None],
    append: dict[str, object],
    *,
    name: str,
    body: str,
) -> dict[str, str | None]:
    """Merge source frontmatter with ``appendFrontmatter`` config keys.

    Adds ``name`` and ``description`` defaults so the output satisfies the
    Copilot CLI skill schema. ``appendFrontmatter`` keys overwrite source
    keys: the YAML config is the policy and the source is the data.
    """
    merged: dict[str, str | None] = dict(source_frontmatter)
    merged.setdefault("name", name)
    if not merged.get("description"):
        first = _first_nonblank_line(body)
        if first:
            merged["description"] = first

    for key, value in append.items():
        # Booleans and other scalars are stringified; format_frontmatter_yaml
        # treats values as strings. ``user-invocable: true`` should land as
        # a literal `true`, not a quoted string.
        if isinstance(value, bool):
            merged[key] = "true" if value else "false"
        elif value is None:
            merged[key] = None
        else:
            merged[key] = str(value)
    return merged


def _detect_authored_skill_collision(
    repo_root: Path, output_dir: Path, name: str
) -> str | None:
    """Return a collision message when ``name`` is already an authored skill.

    A collision exists when ``.claude/skills/<name>/SKILL.md`` exists AND
    that source is unrelated to the command (i.e. there is hand-authored
    skill content already). Bridging would silently shadow it.

    The check is intentionally conservative: presence of the source skill
    directory is the signal. The output dir collision (already-generated
    skill at the target) is allowed because the skills generator runs
    first in the orchestrator and we want the command bridge to layer on
    top — but we must not co-locate two SKILL.md sources for one skill
    name. Surface the conflict so a human can rename the command or the
    skill.
    """
    authored = repo_root / ".claude" / "skills" / name / "SKILL.md"
    if authored.is_file():
        return (
            f"name collision: command '{name}' would overwrite "
            f"authored skill '{authored}'. Rename the command or the skill."
        )
    return None


def _write_skill(
    target_md: Path,
    frontmatter: dict[str, str | None],
    body: str,
    *,
    what_if: bool,
) -> bool:
    """Write the bridged SKILL.md. Returns ``True`` on write, ``False`` on skip."""
    reason = regen_detect_reason(target_md)
    if reason is not None:
        print(f"  NOTICE: skipped {target_md} (NO-REGEN: {reason})")
        return False

    fm_yaml = format_frontmatter_yaml(frontmatter)
    # format_frontmatter_yaml joins with "\n" and omits a trailing newline,
    # so the closing fence needs one inserted before it; otherwise the
    # output reads `last-key: value---` and breaks frontmatter parsing.
    if fm_yaml and not fm_yaml.endswith("\n"):
        fm_yaml += "\n"
    content = f"---\n{fm_yaml}---\n{body}"
    if not content.endswith("\n"):
        content += "\n"

    if what_if:
        print(f"  Would write: {target_md}")
        return True

    target_md.parent.mkdir(parents=True, exist_ok=True)
    target_md.write_text(content, encoding="utf-8")
    return True


def generate_commands(
    config_path: Path,
    repo_root: Path,
    *,
    what_if: bool = False,
) -> int:
    """Bridge Claude commands to Copilot CLI user-invocable skills."""
    print()
    print("=== Commands -> Skills Bridge ===")
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
    stanza = artifacts.get("commands")
    if not isinstance(stanza, dict):
        print(
            f"Error: {config_path} has no `artifacts.commands` stanza",
            file=sys.stderr,
        )
        return 2

    transform = str(stanza.get("transform", "command-to-skill"))
    if transform != "command-to-skill":
        print(
            f"Error: unsupported commands transform '{transform}' "
            "(only 'command-to-skill' implemented)",
            file=sys.stderr,
        )
        return 2

    is_copilot = str(cfg.get("provider", "")) == "copilot-cli"
    source_dir_str = str(stanza.get("sourceDir", ""))
    output_dir_str = str(stanza.get("outputDir", ""))
    excludes = set(stanza.get("excludeFilenames") or _DEFAULT_EXCLUDES)
    append = stanza.get("appendFrontmatter") or {}
    if not isinstance(append, dict):
        print(
            "Error: `artifacts.commands.appendFrontmatter` must be a mapping",
            file=sys.stderr,
        )
        return 2

    try:
        source_dir, output_dir = _resolve_paths(
            repo_root, source_dir_str, output_dir_str
        )
    except GenerateCommandsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    start = time.monotonic()
    try:
        sources = _iter_command_sources(source_dir, excludes)
    except GenerateCommandsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not sources:
        print(f"Error: no command files found under {source_dir}", file=sys.stderr)
        return 1

    print(f"Found {len(sources)} command(s)")
    written = 0
    skipped = 0
    collisions: list[str] = []

    for src in sources:
        name = src.stem
        collision = _detect_authored_skill_collision(repo_root, output_dir, name)
        if collision is not None:
            collisions.append(collision)
            continue

        text = src.read_text(encoding="utf-8")
        match = read_yaml_frontmatter(text)
        if match is None:
            source_fm: dict[str, str | None] = {}
            body = text
        else:
            source_fm = parse_simple_frontmatter(match["frontmatter_raw"])
            body = match["body"]

        merged = _merge_frontmatter(source_fm, append, name=name, body=body)
        out_body = translate_body(body, output_dir) if is_copilot else body
        target_md = output_dir / name / "SKILL.md"
        if _write_skill(target_md, merged, out_body, what_if=what_if):
            written += 1
        else:
            skipped += 1

    duration = time.monotonic() - start

    if collisions:
        print()
        print("=== Collisions ===", file=sys.stderr)
        for msg in collisions:
            print(f"  ERROR: {msg}", file=sys.stderr)
        return 1

    print()
    print("=== Summary ===")
    print(f"Duration: {duration:.2f}s")
    if what_if:
        print("Dry run complete.")
        return 0
    print(f"Commands processed: {len(sources)}")
    print(f"Skills written: {written}")
    if skipped:
        print(f"Skills skipped (NO-REGEN): {skipped}")
    return 0


def build_parser() -> argparse.ArgumentParser:
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
        help="Repository root (defaults to script's grandparent).",
    )
    parser.add_argument("--what-if", action="store_true", help="Dry-run mode.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root or _SCRIPT_DIR.parent.parent
    config_path = args.config or (
        repo_root / "templates" / "platforms" / "copilot-cli.yaml"
    )
    if not config_path.is_file():
        print(f"Error: config not found: {config_path}", file=sys.stderr)
        return 2
    return generate_commands(config_path, repo_root, what_if=args.what_if)


if __name__ == "__main__":
    sys.exit(main())
