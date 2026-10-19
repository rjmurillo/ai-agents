"""Content-checked skip rule for Hermes pack mirrors (ADR-115 Decision 6).

A file under ``src/hermes/project-toolkit-<key>/`` is a generated copy of a file
under ``src/claude/``: ``skills/<rest>`` from ``src/claude/skills/<rest>`` and
``lib/<pkg>/<rest>`` from ``src/claude/lib/<pkg>/<rest>``. The count ratchets skip
such a copy so one suppression is not counted once per pack.

Stricter than the ``src/claude`` and ``src/copilot-cli`` mirror skips in the
ratchets, which key on the path and on the canonical source being tracked. A
Hermes row is skipped only when its bytes equal the canonical file's bytes. A
planted line in a Hermes copy makes the bytes differ, so the file is counted.

Stdlib only: the ratchets run by path in CI.
"""

from __future__ import annotations

import re
from pathlib import Path

LIB_MIRROR_PACKAGES: tuple[str, ...] = ("hook_utilities", "github_core", "ai_review_common")

_HERMES_MIRROR_RE = re.compile(
    r"^src/hermes/project-toolkit-[a-z0-9-]+/"
    r"(?:(?P<skill>skills/.+)|(?P<lib>lib/(?:" + "|".join(LIB_MIRROR_PACKAGES) + r")/.+))$"
)


def hermes_canonical_source(path_str: str) -> str | None:
    """Return the ``src/claude/`` path a Hermes pack file is generated from, if any."""
    match = _HERMES_MIRROR_RE.match(path_str)
    if match is None:
        return None
    rel = match.group("skill") or match.group("lib")
    return f"src/claude/{rel}"


def is_verbatim_hermes_mirror(repo_root: Path, path_str: str, tracked: frozenset[str]) -> bool:
    """Return True when ``path_str`` is a Hermes copy whose bytes equal its tracked source."""
    source = hermes_canonical_source(path_str)
    if source is None or source not in tracked:
        return False
    try:
        return bool((repo_root / path_str).read_bytes() == (repo_root / source).read_bytes())
    except OSError:
        return False
