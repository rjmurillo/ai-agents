#!/usr/bin/env python3
"""Decide whether a rule ships or stays repo-only (ADR-119 decision 13).

A rule whose ``paths:`` scope is internal end to end names only this
repository's own trees (``.agents/``, ``.claude/``, ``.project-toolkit/``,
``.serena/``). A consumer may have ``.claude/`` too, but such a rule cites this
repository's internals, so it is repo-only (the issue #4317 precedent): it ships in no
plugin tree, renders straight to ``.claude/rules/<name>.md``, and reaches
``.github/instructions/`` as a real file. Every other rule ships, and the
repository's copies are links into the plugin trees.

``generate_rules.py`` has applied the same test since issue #4317 to skip a
rule from a shipped instruction tree. This module owns the shared
``INTERNAL_PATH_PREFIXES`` tuple; ``generate_rules._filter_internal_globs``
keeps its own per-glob filter.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Protocol

import yaml

INTERNAL_PATH_PREFIXES = (".agents/", ".project-toolkit/", ".claude/", ".serena/")


class _Outcome(Protocol):
    """The fields of ``rule_templates.CompileResult`` this module updates."""

    drifted: list[str]
    written: list[str]
    exit_code: int


_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)


def scope_globs(text: str) -> list[str]:
    """Return the rule's ``paths:`` globs, or ``[]`` when it declares none."""
    match = _FRONTMATTER.match(text)
    if match is None:
        return []
    frontmatter = yaml.safe_load(match.group(1))
    if not isinstance(frontmatter, dict):
        return []
    value = frontmatter.get("paths")
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def is_repo_only(text: str) -> bool:
    """Whether every declared scope glob is internal. An unscoped rule ships."""
    globs = scope_globs(text)
    return bool(globs) and all(glob.startswith(INTERNAL_PATH_PREFIXES) for glob in globs)


def repo_only_rule_names(repo_root: Path) -> frozenset[str]:
    """Return ``<name>`` for every repo-only ``templates/rules/<name>.md``."""
    templates = repo_root / "templates" / "rules"
    if not templates.is_dir():
        return frozenset()
    return frozenset(
        path.stem
        for path in templates.glob("*.md")
        if path.is_file() and is_repo_only(path.read_text(encoding="utf-8"))
    )


def render_target(repo_root: Path, name: str, tmpl_path: Path) -> Path:
    """Where ``name`` renders: the plugin tree, or ``.claude/rules`` when repo-only.

    ADR-119 decision 13: a rule whose scope is internal end to end ships in no
    plugin tree (``rule_distribution.is_repo_only``). It renders straight to
    ``.claude/rules/<name>.md`` as a real file; every shipped rule renders to
    ``src/claude/rules/<name>.md`` and ``.claude/rules`` links to it.
    """
    repo_only = is_repo_only(tmpl_path.read_text(encoding="utf-8"))
    root = repo_root / ".claude" if repo_only else repo_root / "src" / "claude"
    return root / "rules" / f"{name}.md"


def is_former_shipped_link(repo_root: Path, name: str, target: Path) -> bool:
    """Whether ``target`` is the binplace link a shipped ``name`` left behind.

    Only the exact computed link ``.claude/rules/<name>.md ->
    ../../src/claude/rules/<name>.md`` qualifies; any other symlink stays
    refused, so a planted link is never written through.
    """
    expected = repo_root / ".claude" / "rules" / f"{name}.md"
    if target != expected or not target.is_symlink():
        return False
    return os.readlink(target) == f"../../src/claude/rules/{name}.md"


def remove_stale_plugin_copy(
    repo_root: Path,
    name: str,
    target: Path,
    *,
    validate: bool,
    what_if: bool,
    result: _Outcome,
) -> None:
    """Remove ``src/claude/rules/<name>.md`` once the rule is repo-only.

    A rule that becomes repo-only would otherwise keep shipping its last
    plugin copy. ``validate`` reports it as drift; ``what_if`` only says so.
    """
    plugin_copy = repo_root / "src" / "claude" / "rules" / f"{name}.md"
    if target == plugin_copy or plugin_copy.is_symlink() or not plugin_copy.is_file():
        return
    if validate:
        print(f"DRIFT: {plugin_copy} ships a repo-only rule", file=sys.stderr)
        result.drifted.append(str(plugin_copy))
        result.exit_code = max(result.exit_code, 1)
        return
    if what_if:
        print(f"  Would remove: {plugin_copy}")
        return
    plugin_copy.unlink()
    result.written.append(str(plugin_copy))
