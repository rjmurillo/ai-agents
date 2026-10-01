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

_FENCE = "---"


def _line_body(line: str) -> str:
    """Return a line without its terminator (LF, CRLF, or none)."""
    return line.rstrip("\r\n")


def split_leading_frontmatter(text: str) -> tuple[str, str]:
    """Split a Markdown file into ``(frontmatter, body)``.

    The frontmatter excludes both fences and the newline before the closing
    fence. A fence is a line holding ``---`` plus optional surrounding
    whitespace, so CRLF files, a padded fence, and a closing fence at end of
    file all split. Returns ``("", text)`` when the file does not open with a
    fence line or the block never closes.
    """
    lines = text.splitlines(keepends=True)
    if not lines or _line_body(lines[0]).strip() != _FENCE:
        return "", text
    for index in range(1, len(lines)):
        if _line_body(lines[index]).strip() == _FENCE:
            frontmatter = "".join(lines[1:index])
            return _line_body(frontmatter) if frontmatter else "", "".join(lines[index + 1 :])
    return "", text
