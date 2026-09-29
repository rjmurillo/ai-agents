"""Stdlib-only split of a leading YAML frontmatter block from a Markdown file.

Callers: ``build/scripts/generate_pr_quality_prompts.py`` and
``scripts/validation/validate_seed_parity.py``. Both run under bare ``python3``
and must stay stdlib-only, because ``check_doc_interpreter_portability.py``
fails any bare-``python3`` script whose import closure reaches a third-party
module. This module therefore never imports ``yaml`` or ``frontmatter``, and it
does no YAML parsing: it only finds the fences.

``scripts/validation/yaml_utils.py`` and ``frontmatter_contract.py`` own the
parsing contract for callers that may depend on PyYAML and python-frontmatter.

The name is ``split_leading_frontmatter`` on purpose. ``split_frontmatter`` is
already public in ``check_agent_skill_discriminator.py`` and in
``build/sync_slim_agents_reconcile.py`` with two different contracts.
"""

from __future__ import annotations

_OPEN_FENCE = "---\n"
_CLOSE_FENCE = "\n---\n"


def split_leading_frontmatter(text: str) -> tuple[str, str]:
    """Split a Markdown file into ``(frontmatter, body)``.

    The frontmatter excludes both ``---`` fences. Returns ``("", text)`` when
    the file does not open with a fence line or the block never closes.
    """
    if not text.startswith(_OPEN_FENCE):
        return "", text
    end_idx = text.find(_CLOSE_FENCE, len(_OPEN_FENCE))
    if end_idx == -1:
        return "", text
    return text[len(_OPEN_FENCE) : end_idx], text[end_idx + len(_CLOSE_FENCE) :]
