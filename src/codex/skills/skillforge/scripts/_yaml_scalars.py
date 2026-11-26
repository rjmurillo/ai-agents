#!/usr/bin/env python3
"""
_yaml_scalars.py - Shared inline YAML scalar reading for the PyYAML-less fallback

These helpers are used by:
- quick_validate.py (packaging validation)
- validate-skill.py (full structural validation)

Both validators parse frontmatter without PyYAML when it is not installed.
Keeping the scalar typing here means the two fallbacks read values the same way.
"""

from __future__ import annotations

from typing import Any


def unquote_scalar(value: str) -> str:
    """Strip matching YAML quotes from a plain one-line scalar.

    The agentskills.io guidance asks authors to quote values that contain a
    colon, so the fallback parser must read ``name: "x"`` as ``x``.
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        return inner.replace('\\"', '"') if value[0] == '"' else inner.replace("''", "'")
    return value


YAML_NULL = {"", "~", "null", "Null", "NULL"}
YAML_BOOL = {
    "true": True,
    "True": True,
    "TRUE": True,
    "false": False,
    "False": False,
    "FALSE": False,
}


def typed_scalar(value: str) -> Any:
    """Read an inline value with the YAML types a type check needs.

    Without PyYAML, the fallback parser would read ``compatibility: null`` or
    ``compatibility: [git, docker]`` as text and pass a string check. Return
    None, a bool, or a list or dict for those unquoted forms, and a string
    otherwise, so the type checks reject what PyYAML would.
    """
    if value in YAML_NULL:
        return None
    if value in YAML_BOOL:
        return YAML_BOOL[value]
    if value.startswith("[") and value.endswith("]"):
        return [unquote_scalar(item.strip()) for item in value[1:-1].split(",") if item.strip()]
    if value.startswith("{") and value.endswith("}"):
        pairs = [item.split(":", 1) for item in value[1:-1].split(",") if ":" in item]
        return {k.strip(): unquote_scalar(v.strip()) for k, v in pairs}
    return unquote_scalar(value)
