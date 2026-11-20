"""Read YAML frontmatter with or without python-frontmatter and PyYAML.

The recall path ships in the Claude plugin's ``lib/`` tree and runs under a
consumer's bare ``python3``, which carries neither ``python-frontmatter`` nor
PyYAML (plugin-self-containment.md MUST 4; ADR-109 amendment 2026-11-20). Both
imports are guarded. With python-frontmatter, ``read_frontmatter`` behaves as
``frontmatter.loads`` always did. Without it, ``read_frontmatter_stdlib``
splits the block with the same boundary rule and parses it with PyYAML when
that is present. No YAML parser is hand-rolled: with neither package the
metadata is empty and the block is still stripped from the content.
"""

from __future__ import annotations

import importlib
import re
import sys
from types import ModuleType
from typing import Any


def _optional_module(name: str) -> ModuleType | None:
    """Import *name*, or return None when it is not installed.

    ``importlib`` keeps the guard type-checkable without a ``type: ignore``.
    """
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


frontmatter = _optional_module("frontmatter")
yaml = _optional_module("yaml")

# Exceptions a YAML parse can raise. Empty when PyYAML is missing, so an
# ``except YAML_ERRORS`` clause then catches nothing.
YAML_ERRORS: tuple[type[Exception], ...] = (yaml.YAMLError,) if yaml is not None else ()

# python-frontmatter's YAML boundary: YAMLHandler.FM_BOUNDARY in
# frontmatter/default_handlers.py (python-frontmatter, read from the project
# venv). ``split_frontmatter`` below applies it the way
# ``frontmatter.parse`` does. tests/test_memory_frontmatter_reader.py
# compares the two readers over this repository's memories.
_FM_BOUNDARY = re.compile(r"^-{3,}\s*$", re.MULTILINE)


def warn_malformed_frontmatter() -> None:
    print(
        "Warning: malformed YAML frontmatter, treating as plain markdown",
        file=sys.stderr,
    )


def read_frontmatter(raw_text: str) -> tuple[dict[str, Any], str, str]:
    """Split a memory file into frontmatter metadata and body.

    Returns:
        (metadata, body, fallback_content). ``body`` is the text after the
        frontmatter block. ``fallback_content`` is the content to use when
        ``metadata`` is empty: the raw text, except when PyYAML is missing and
        the block was stripped but could not be parsed.
    """
    if frontmatter is not None:
        try:
            post = frontmatter.loads(raw_text)
        except YAML_ERRORS:
            # Malformed YAML frontmatter; treat as plain markdown
            warn_malformed_frontmatter()
            return {}, raw_text, raw_text
        return dict(post.metadata), post.content, raw_text
    return read_frontmatter_stdlib(raw_text)


def split_frontmatter(raw_text: str) -> tuple[str, str] | None:
    """Split a leading YAML block from *raw_text* like ``frontmatter.parse``.

    Mirrors ``frontmatter.parse`` with its default YAMLHandler: strip the text,
    require ``_FM_BOUNDARY`` to match at the start (``BaseHandler.detect``),
    then ``_FM_BOUNDARY.split(text, 2)`` (``BaseHandler.split``). Fewer than
    two boundaries means no frontmatter, as in ``parse``.

    Different than canonical: python-frontmatter also tries JSON and TOML
    handlers. Memories use YAML only, so this reader does not.
    """
    text = raw_text.strip()
    if not _FM_BOUNDARY.match(text):
        return None
    try:
        _, block, content = _FM_BOUNDARY.split(text, 2)
    except ValueError:
        return None
    return block, content.strip()


def read_frontmatter_stdlib(raw_text: str) -> tuple[dict[str, Any], str, str]:
    """Read frontmatter without python-frontmatter (stdlib plus optional PyYAML)."""
    parts = split_frontmatter(raw_text)
    if parts is None:
        return {}, raw_text.strip(), raw_text
    block, content = parts
    if yaml is None:
        # No YAML parser: metadata is unreadable, but the block must not
        # leak into the memory body.
        return {}, content, content
    try:
        data = yaml.safe_load(block)
    except YAML_ERRORS:
        warn_malformed_frontmatter()
        return {}, raw_text, raw_text
    metadata = dict(data) if isinstance(data, dict) else {}
    return metadata, content, raw_text
