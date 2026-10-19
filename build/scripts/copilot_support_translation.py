"""Pick the rendered text for one file in a skill directory.

Issues #2743 and #5657. The Copilot skill mirror translates the top-level
``SKILL.md`` and every Markdown file under ``references/`` from Claude Code
conventions. All other support files are byte copies. This module answers
"render or copy?" and does the rendering; ``skill_support_mirror`` owns the
write, check, and what-if handling.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from copilot_body_translation import (  # noqa: E402
    render_skill_file,
    translate_reference_file,
)
from skill_copy_compare import SKILL_MD  # noqa: E402


class SupportTranslationError(ValueError):
    """A SKILL.md render refused its input; the message names the source."""


def is_reference_markdown(rel: Path) -> bool:
    """True for a Markdown file under a skill's ``references/`` directory."""
    return rel.parts[0] == "references" and rel.suffix == ".md"


def translated_text(
    rel: Path,
    src_path: Path,
    plugin_skill_md: Path | None,
    skills_output_dir: Path | None,
    frontmatter_drop: frozenset[str],
) -> str | None:
    """Return the rendered text for ``rel``, or None when it is a byte copy.

    ``SKILL.md`` is rendered whenever the target renders it (a Copilot
    ``skills_output_dir`` or a non-empty ``frontmatter_drop``). On the Copilot
    branch every ``references/*.md`` is translated too (issue #5657); the
    Codex branch keeps references byte-for-byte. ``plugin_skill_md``, when it
    exists on disk, supplies the ``SKILL.md`` text in place of ``src_path``
    (the ADR-109 B3 render target).
    """
    if rel == SKILL_MD and (skills_output_dir is not None or frontmatter_drop):
        content_source = src_path
        if plugin_skill_md is not None and plugin_skill_md.is_file():
            content_source = plugin_skill_md
        content = content_source.read_text(encoding="utf-8")
        try:
            return str(render_skill_file(content, skills_output_dir, frontmatter_drop))
        except ValueError as exc:
            raise SupportTranslationError(f"{content_source}: {exc}") from exc
    if skills_output_dir is not None and is_reference_markdown(rel):
        # str(...): mypy types sibling sys.path imports as Any.
        return str(
            translate_reference_file(src_path.read_text(encoding="utf-8"), skills_output_dir)
        )
    return None
