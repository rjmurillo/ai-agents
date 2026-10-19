"""Rewrite a skill's top-level ``SKILL.md`` for a host mirror (split from skill_support_mirror.py).

Two rewrites exist. ``skills_output_dir`` selects the Copilot translation
(ADR-111). ``frontmatter_drop`` alone selects the drop-only cut Codex needs
(ADR-115 Decision 7). ``frontmatter_keep`` selects the allow-list cut Cursor needs
(ADR-115 Decision 2). Every other file in a skill is a byte copy.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from copilot_body_translation import render_skill_file  # noqa: E402
from frontmatter_key_drop import keep_skill_frontmatter  # noqa: E402

_SKILL_MD = Path("SKILL.md")


class GenerateSkillsError(Exception):
    """Domain error for skill generation. Wraps copy/load issues.

    Defined here so the rewrite can raise it; ``skill_support_mirror`` and
    ``generate_skills`` re-export it under the same name.
    """


def rewrite_skill_md(
    src_path: Path,
    rel: Path,
    *,
    skills_output_dir: Path | None,
    plugin_skill_md: Path | None,
    frontmatter_drop: frozenset[str],
    frontmatter_keep: frozenset[str] | None,
) -> str | None:
    """Return the rewritten ``SKILL.md`` text, or ``None`` for a byte copy.

    Only the top-level ``SKILL.md`` is ever rewritten, and only when the
    platform asks for a Copilot translation, a key drop, or a frontmatter allow-list.
    Raises :class:`GenerateSkillsError` naming the source file when a rewrite refuses a skill.
    """
    if rel != _SKILL_MD or (
        skills_output_dir is None and frontmatter_keep is None and not frontmatter_drop
    ):
        return None
    content_source = src_path
    if plugin_skill_md is not None and plugin_skill_md.is_file():
        content_source = plugin_skill_md
    content = content_source.read_text(encoding="utf-8")
    try:
        if skills_output_dir is not None or frontmatter_keep is None:
            return str(render_skill_file(content, skills_output_dir, frontmatter_drop))
        return str(keep_skill_frontmatter(content, frontmatter_keep or frozenset()))
    except ValueError as exc:
        raise GenerateSkillsError(f"{content_source}: {exc}") from exc
