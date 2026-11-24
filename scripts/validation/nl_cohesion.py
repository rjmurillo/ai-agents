"""Measure cohesion of an authored rule: how many unrelated roots it claims.

A rule's `paths:` frontmatter is the scope key. One rule that activates under many
unrelated top-level roots is the prompt equivalent of a class that owns unrelated
responsibilities: low cohesion. This module counts the distinct top-level roots a
rule claims. It is deterministic and reads only frontmatter, so no model judgment
is involved.

Frontmatter that is present but cannot be parsed raises :class:`FrontmatterError`.
Returning a spread of 0 for it would let a broken rule slip under the cohesion
ratchet without a word (issue #6506). A file with no frontmatter block at all has
no `paths:` and a spread of 0.

A glob that starts with a wildcard (`**/Auth/**`, `*.env*`) has no stable root. All
such globs share one root, `*`, so a rule is not penalized for many wildcard forms of
one idea.

Known limits, by design for a deterministic proxy: the root is the first path segment, so
five subsystems under one `src/` count once, and `**/Auth/**` and `**/Billing/**` count
once. The measure under-reports; it never flags a rule that is cohesive by this test.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.hook_utilities.frontmatter_block import (
    FrontmatterStatus,
    parse_frontmatter,
)

WILDCARD_ROOT = "*"
# A rule claiming this many distinct roots or more is reported as low cohesion.
MIN_SPREAD = 5


class FrontmatterError(ValueError):
    """Frontmatter is present but unterminated, invalid YAML, or not a mapping."""


def _frontmatter(text: str) -> dict[str, Any]:
    """Return the parsed frontmatter mapping, or an empty mapping when there is none.

    Uses ``scripts/hook_utilities/frontmatter_block.py`` for the fence and the YAML load.

    Raises:
        FrontmatterError: a `---` block opens but never closes, is not valid YAML,
            or parses to something other than a mapping.
    """
    result = parse_frontmatter(text, yaml, allow_duplicate_keys=True)
    if result.status is FrontmatterStatus.UNTERMINATED:
        raise FrontmatterError("frontmatter opens with `---` but never closes")
    if result.status is FrontmatterStatus.MALFORMED:
        detail = (result.error or "").removeprefix("invalid YAML frontmatter: ")
        raise FrontmatterError(f"frontmatter is not valid YAML: {detail}")
    if result.status is FrontmatterStatus.NOT_A_MAPPING:
        # The core words it "(got <type>)"; keep this module's own wording.
        got = (result.error or "").rsplit("got ", 1)[-1].rstrip(")")
        raise FrontmatterError(f"frontmatter must be a mapping, got {got}")
    return result.metadata or {}


def _root(glob: str) -> str:
    """Return the top-level root a glob names, or the shared wildcard root."""
    first = glob.strip().removeprefix("./").split("/", 1)[0]
    if not first or "*" in first or "?" in first or "[" in first:
        return WILDCARD_ROOT
    return first


def path_spread(text: str) -> int:
    """Return the count of distinct top-level roots in the `paths:` frontmatter.

    Raises:
        FrontmatterError: the frontmatter is present but unparseable.
    """
    paths = _frontmatter(text).get("paths")
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, list):
        return 0
    return len({_root(p) for p in paths if isinstance(p, str)})
