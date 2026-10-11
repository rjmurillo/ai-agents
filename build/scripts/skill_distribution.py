#!/usr/bin/env python3
"""Decide whether a skill ships in the vendor plugin trees or stays repo-local.

A skill template marks a contributor-only skill with one frontmatter field::

    metadata:
      distribution: repo-local

An absent field means the skill ships. ``repo-local`` is the only allowed
value; any other value is a hard error (:class:`SkillDistributionError`), so
a typo such as ``repo_local`` cannot silently ship a contributor-only skill.

Every build stage reads this one field through :func:`is_repo_local` or
:func:`repo_local_names`: the template compile (``skill_templates``), the
support-file mirror into ``src/claude/skills`` (``skill_support_mirror``),
the Copilot mirror (``generate_skills``), and the plugin-tree copy onto
``.claude/skills`` (``binplace_manifest``). A repo-local skill renders
straight to ``.claude/skills/<name>/`` and appears in no plugin tree.

Resolution order for one skill: the template
``templates/skills/<name>.SKILL.md.tmpl`` when it exists (the canonical
source), else ``.claude/skills/<name>/SKILL.md``.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

DISTRIBUTION_KEY = "distribution"
REPO_LOCAL = "repo-local"
SHIPPED = "shipped"
ALLOWED_VALUES = frozenset({REPO_LOCAL})

_TEMPLATE_SUFFIX = ".SKILL.md.tmpl"
_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)


class SkillDistributionError(ValueError):
    """The ``metadata.distribution`` field is malformed or has an unknown value."""


def distribution_of_text(text: str, source: str) -> str:
    """Return ``"repo-local"`` or ``"shipped"`` for one SKILL.md or template body.

    ``source`` names the file in error messages. Text with no frontmatter, no
    ``metadata`` mapping, or no ``distribution`` key is ``"shipped"``.
    """
    match = _FRONTMATTER.match(text)
    if match is None:
        return SHIPPED
    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise SkillDistributionError(f"{source}: unparseable frontmatter: {exc}") from exc
    if not isinstance(frontmatter, dict):
        return SHIPPED
    metadata = frontmatter.get("metadata")
    if not isinstance(metadata, dict) or DISTRIBUTION_KEY not in metadata:
        return SHIPPED
    value = metadata[DISTRIBUTION_KEY]
    if not isinstance(value, str) or value not in ALLOWED_VALUES:
        allowed = ", ".join(sorted(ALLOWED_VALUES))
        raise SkillDistributionError(
            f"{source}: metadata.distribution is {value!r}; the only allowed value is "
            f"{allowed} (omit the field to ship the skill)"
        )
    return REPO_LOCAL


def _skill_source(repo_root: Path, name: str) -> Path | None:
    template = repo_root / "templates" / "skills" / f"{name}{_TEMPLATE_SUFFIX}"
    if template.is_file():
        return template
    installed = repo_root / ".claude" / "skills" / name / "SKILL.md"
    if installed.is_file():
        return installed
    return None


def is_repo_local(repo_root: Path, name: str) -> bool:
    """Return True when skill ``name`` is flagged ``distribution: repo-local``.

    A skill with neither a template nor an installed ``SKILL.md`` is not
    repo-local. Raises :class:`SkillDistributionError` on a bad field value.
    """
    source = _skill_source(repo_root, name)
    if source is None:
        return False
    text = source.read_text(encoding="utf-8")
    return distribution_of_text(text, str(source)) == REPO_LOCAL


def repo_local_names(repo_root: Path) -> frozenset[str]:
    """Return every repo-local skill name found under templates or ``.claude/skills``."""
    names: set[str] = set()
    templates_dir = repo_root / "templates" / "skills"
    if templates_dir.is_dir():
        templates = templates_dir.glob(f"*{_TEMPLATE_SUFFIX}")
        names.update(p.name[: -len(_TEMPLATE_SUFFIX)] for p in templates)
    skills_dir = repo_root / ".claude" / "skills"
    if skills_dir.is_dir():
        names.update(p.name for p in skills_dir.iterdir() if p.is_dir())
    return frozenset(name for name in names if is_repo_local(repo_root, name))


def render_target(repo_root: Path, name: str) -> Path:
    """Return where ``skill_templates.compile_all`` writes skill ``name``'s ``SKILL.md``.

    A shipped skill renders into the plugin tree and binplace copies it onto
    ``.claude/skills/``. A repo-local skill renders straight to
    ``.claude/skills/<name>/SKILL.md`` and appears in no plugin tree.
    """
    root = repo_root / ".claude" if is_repo_local(repo_root, name) else repo_root / "src" / "claude"
    return root / "skills" / name / "SKILL.md"


def install_target_symlink_error(repo_root: Path, name: str, tmpl_path: Path) -> str | None:
    """Return why a repo-local skill's direct render target is refused, or ``None``.

    With no plugin-tree hop, the symlink defense ``_plugin_tree_error`` gives
    ``src/claude/skills/<name>/SKILL.md`` applies to the install-tree file.
    """
    target = repo_root / ".claude" / "skills" / name / "SKILL.md"
    if target.is_symlink():
        return f"{tmpl_path}: .claude/skills/{name}/SKILL.md is a symlink, not a real file"
    return None
