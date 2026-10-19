"""Render a Cursor ``.mdc`` rule frontmatter from a remapped rule (ADR-115 Decision 2).

``generate_rules.py`` calls this when ``artifacts.rules.outputFormat`` is
``cursor-mdc``. It runs after the stanza's ``frontmatterRemap`` and
``frontmatterDrop`` and after the internal-glob filter, so the scope it sees is
the same ``applyTo`` string the Copilot instruction tree gets. That keeps the
internal-only glob rule one implementation.

Cursor's rule frontmatter, from https://cursor.com/docs/context/rules:

* ``alwaysApply: true`` includes the rule in every session and ignores
  ``globs`` and ``description``.
* ``alwaysApply: false`` with ``globs`` attaches the rule when a matching file
  is in context. Several patterns are one comma-separated string.
* ``description`` is kept: it is how the agent picks a rule it may apply.

``priority`` has no Cursor equivalent and the stanza drops it.

Only the exact entry ``**`` means "every file". A glob such as ``**/*.py`` is a
scoped rule.
"""

from __future__ import annotations

import json

_ALWAYS_APPLY_GLOB = "**"
_SCOPE_KEY = "applyTo"
_FRONTMATTER_ORDER = ("description", "globs", "alwaysApply")


def build_mdc_frontmatter(remapped: dict[str, str | None]) -> dict[str, str | bool]:
    """Return the ``.mdc`` frontmatter for a remapped rule.

    ``remapped`` is the output of ``generate_rules._remap_frontmatter``: it
    carries ``applyTo`` as a comma-separated string. Keys other than
    ``applyTo`` and ``description`` are dropped, because Cursor documents no
    others and treats unknown keys as unspecified behaviour.
    """
    scope = remapped.get(_SCOPE_KEY) or _ALWAYS_APPLY_GLOB
    patterns = [part.strip() for part in scope.split(",") if part.strip()]
    result: dict[str, str | bool] = {}
    description = remapped.get("description")
    if description:
        result["description"] = description
    if _ALWAYS_APPLY_GLOB in patterns:
        result["alwaysApply"] = True
        return result
    result["globs"] = ", ".join(patterns)
    result["alwaysApply"] = False
    return result


def format_mdc_frontmatter(frontmatter: dict[str, str | bool]) -> str:
    """Serialize ``.mdc`` frontmatter as YAML lines with a trailing newline.

    Strings are JSON-quoted, which is valid YAML double-quoted scalars, so a
    glob such as ``*.env*`` or a description containing a colon cannot be
    misread. Booleans are bare.
    """
    lines: list[str] = []
    for key in _FRONTMATTER_ORDER:
        if key not in frontmatter:
            continue
        value = frontmatter[key]
        rendered = ("true" if value else "false") if isinstance(value, bool) else _quote(value)
        lines.append(f"{key}: {rendered}")
    return "\n".join(lines) + "\n"


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)
