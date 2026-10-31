#!/usr/bin/env python3
"""Memoized ``yaml.safe_load`` for the build pipeline's repeated frontmatter reads.

``build_all.py`` re-reads the same skill frontmatter many times in one run:
``skill_distribution.is_repo_local`` re-parses a skill's file on every
``render_target`` call, and ``frontmatter_key_drop`` parses each block before
and after every cut. The pure-Python ``SafeLoader`` costs about 3 ms per call,
so 6900 calls (533 distinct texts at c85a85f32c) were most of the
``Generated Artifact Staleness`` gate's wall time (issue #6734).

The cache key is the YAML text itself, not a path, so a file rewritten between
two calls misses the cache and is parsed again. ``yaml.safe_load`` is a pure
function of its text, so a hit returns exactly what a fresh parse returns. A
parse error is never cached: ``lru_cache`` stores only returns, so the caller
sees the same ``yaml.YAMLError`` (message, mark) on every call.

Each call returns its own deep copy of the cached parse, so a caller that
mutates the result cannot change what a later caller sees.
"""

from __future__ import annotations

import copy
from functools import lru_cache

import yaml


@lru_cache(maxsize=4096)
def _parse(text: str) -> object:
    return yaml.safe_load(text)


def load_yaml_text(text: str) -> object:
    """Return ``yaml.safe_load(text)``, parsing each distinct text once per process."""
    return copy.deepcopy(_parse(text))
