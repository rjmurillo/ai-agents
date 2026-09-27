"""Drop named top-level keys from a SKILL.md frontmatter block (ADR-111).

`copilot_body_translation.translate_skill_file` calls this for the Copilot CLI
skill mirror. The platform config lists the keys under
`artifacts.skills.frontmatterDrop`; Copilot lists `model` and
`model-rationale`, because its skills have no per-skill model field (issue
#5606).

The cut is line-based so every other byte of the frontmatter survives. A YAML
round-trip would reorder keys and rewrite quoting in a customer-facing file.
The parse-and-compare guard below is what makes a line-based cut safe.
"""

from __future__ import annotations

import re

import yaml

_FRONTMATTER_FENCE_RE = re.compile(r"\A---\r?\n|^---\r?\n\Z", re.MULTILINE)
# A top-level frontmatter key line, bare or quoted, with optional space before
# the colon. Group 2 is the key name. Its value lines are found by
# `_drop_key_lines`, not by this pattern.
_TOP_LEVEL_KEY_RE = re.compile(r"""^(["']?)([^\s"':#][^"':]*?)\1[ \t]*:(?:[ \t]|$)""")


def drop_frontmatter_keys(frontmatter: str, keys: frozenset[str]) -> str:
    """Remove the named top-level keys from fenced frontmatter (transform 5).

    Claude Code switches to a skill's `model:` while the skill is active.
    Copilot CLI skills have no per-skill model field: skill content is
    injected into the running session. So the Copilot config drops the pin,
    and it is never resolved to a versioned id (ADR-111, issue #5606).

    Raises ValueError when the result does not parse to the input mapping
    minus the named keys, so a bad cut fails the build instead of shipping.
    """
    if not keys:
        return frontmatter
    result = _drop_key_lines(frontmatter, keys)
    _check_only_keys_dropped(frontmatter, result, keys)
    return result


def _is_dropped_key(text: str, keys: frozenset[str]) -> bool:
    match = _TOP_LEVEL_KEY_RE.match(text)
    return match is not None and match.group(2) in keys


def _drop_key_lines(frontmatter: str, keys: frozenset[str]) -> str:
    """Drop each named key line plus its value lines.

    A value line is indented or an un-indented `- ` list item. Blank lines
    inside a block scalar go with the value; blank lines before the next
    top-level key are kept.
    """
    kept: list[str] = []
    blanks: list[str] = []
    dropping = False
    for line in frontmatter.splitlines(keepends=True):
        text = line.rstrip("\r\n")
        if dropping and not text.strip():
            blanks.append(line)
            continue
        if dropping and (text[:1] in (" ", "\t") or text.startswith("- ")):
            blanks.clear()
            continue
        kept.extend(blanks)
        blanks.clear()
        dropping = _is_dropped_key(text, keys)
        if not dropping:
            kept.append(line)
    kept.extend(blanks)
    return "".join(kept)


def _frontmatter_mapping(frontmatter: str) -> object:
    return yaml.safe_load(_FRONTMATTER_FENCE_RE.sub("", frontmatter))


def _check_only_keys_dropped(before: str, after: str, keys: frozenset[str]) -> None:
    try:
        original = _frontmatter_mapping(before)
    except yaml.YAMLError:
        return  # Source frontmatter is not YAML; the skill validators own that.
    if not isinstance(original, dict):
        return
    expected = {k: v for k, v in original.items() if k not in keys}
    try:
        actual = _frontmatter_mapping(after)
    except yaml.YAMLError as exc:
        raise ValueError(f"dropping {sorted(keys)} broke SKILL.md frontmatter: {exc}") from exc
    if (actual or {}) != expected:
        raise ValueError(f"dropping {sorted(keys)} changed other SKILL.md frontmatter keys")
