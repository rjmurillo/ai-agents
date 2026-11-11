"""Codex TOML rendering helpers for ``agent_tree_copy.py`` (ADR-115 Decision 7).

A Codex custom agent is one TOML file with ``name``, ``description`` and
``developer_instructions``. This module owns the TOML basic-string escaper, the
file renderer, and the paragraph appended to each body when agents are left out.
"""

from __future__ import annotations

CODEX_KEEP = ["name", "description"]
_TOML_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}


class CodexTomlError(Exception):
    """An agent's frontmatter cannot become a Codex TOML file."""


def toml_basic_string(value: str) -> str:
    """Return ``value`` as a single-line TOML 1.0 basic string, quotes included.

    Escapes ``\\``, ``"`` and the control characters U+0000-U+001F and U+007F
    (``\\b \\t \\n \\f \\r`` or ``\\uXXXX``). Every other character, including
    non-BMP ones such as emoji, stays raw UTF-8. ``json.dumps`` is not a
    substitute: it emits surrogate pairs (invalid TOML) and leaves U+007F raw.
    """
    out: list[str] = []
    for char in value:
        if char in _TOML_ESCAPES:
            out.append(_TOML_ESCAPES[char])
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


def render_codex_toml(kept: dict[str, object], body: str, source: str) -> str:
    for key in CODEX_KEEP:
        if not isinstance(kept.get(key), str):
            raise CodexTomlError(f"{source}: frontmatter `{key}` must be a string for codex-toml")
    return (
        f"name = {toml_basic_string(str(kept['name']))}\n"
        f"description = {toml_basic_string(str(kept['description']))}\n"
        f"developer_instructions = {toml_basic_string(body)}\n"
    )


def not_installed_paragraph(skipped_stems: list[str]) -> str:
    """Return the paragraph appended to each body when agents were left out.

    The list is the sorted skip list passed in, never a fixed set of names.
    """
    names = ", ".join(f"`{stem}`" for stem in sorted(skipped_stems))
    return (
        "\n\n## Agents not installed on this host\n\n"
        f"These agents are not installed on this host: {names}. "
        "When a step above hands work to one of them, do that step yourself "
        "in this session and say that you did.\n"
    )
