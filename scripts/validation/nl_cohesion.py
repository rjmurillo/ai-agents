"""Measure cohesion of an authored rule: how many unrelated roots it claims.

A rule's `paths:` frontmatter is the scope key. One rule that activates under many
unrelated top-level roots is the prompt equivalent of a class that owns unrelated
responsibilities: low cohesion. This module counts the distinct top-level roots a
rule claims. It is deterministic and reads only frontmatter, so no model judgment
is involved.

A glob that starts with a wildcard (`**/Auth/**`, `*.env*`) has no stable root. All
such globs share one root, `*`, so a rule is not penalized for many wildcard forms of
one idea.

Known limits, by design for a deterministic proxy: the root is the first path segment, so
five subsystems under one `src/` count once, and `**/Auth/**` and `**/Billing/**` count
once. The measure under-reports; it never flags a rule that is cohesive by this test.
"""

from __future__ import annotations

from typing import Any

import yaml

WILDCARD_ROOT = "*"
# A rule claiming this many distinct roots or more is reported as low cohesion.
MIN_SPREAD = 5


def _frontmatter(text: str) -> dict[str, Any]:
    """Return the parsed frontmatter mapping, or an empty mapping when absent or invalid."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}
    try:
        data = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _root(glob: str) -> str:
    """Return the top-level root a glob names, or the shared wildcard root."""
    first = glob.strip().removeprefix("./").split("/", 1)[0]
    if not first or "*" in first or "?" in first or "[" in first:
        return WILDCARD_ROOT
    return first


def path_spread(text: str) -> int:
    """Return the count of distinct top-level roots in the `paths:` frontmatter."""
    paths = _frontmatter(text).get("paths")
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, list):
        return 0
    return len({_root(p) for p in paths if isinstance(p, str)})
