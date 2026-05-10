#!/usr/bin/env python3
"""orphan-ref-validator working-tree count enumeration.

Mirrors the project-toolkit count strategies in
``build/scripts/validate_marketplace_counts.py`` and the per-plugin
rules in ``templates/marketplace-counters.yaml``. Per
``.claude/rules/canonical-source-mirror.md``, the canonical
``project-toolkit`` stanza for ``.claude-plugin/marketplace.json`` is,
byte-for-byte:

    project-toolkit:
      marketplaces:
        .claude-plugin/marketplace.json:
          agent:
            strategy: "md_agents"
            sourceDir: ".claude/agents"
            exclude: ["AGENTS.md", "CLAUDE.md"]
          slash command:
            strategy: "commands"
            sourceDir: ".claude/commands"
          lifecycle hook:
            strategy: "hooks"
            sourceDir: ".claude/hooks"
          reusable skill:
            strategy: "skill_dirs"
            sourceDir: ".claude/skills"

The YAML stanza for ``slash command`` does not include an ``exclude``
key. The canonical strategy ``_count_commands`` defaults that argument
to ``{"CLAUDE.md"}`` when the YAML does not override it (a
path-scoped ``CLAUDE.md`` is not a slash command, it is documentation).
This module passes ``exclude={"CLAUDE.md"}`` explicitly to
``_count_md_recursive`` for the same effect.

The corresponding strategy implementations from the canonical Python
source are referenced inline by ``_count_md_agents``, ``_count_md_recursive``,
``_count_py_recursive``, and ``enumerate_skills`` below. This module
re-implements the same algorithms rather than importing from
``build/scripts/validate_marketplace_counts.py`` because the canonical
script depends on a YAML loader and its own CLI scaffolding.

Stricter/looser/different than canonical:

- Pruning: canonical uses ``os.walk`` with ``_EXCLUDED_DIRS`` removed
  from ``dirs`` in-place; this module uses ``os.walk(followlinks=False)``
  with the same in-place pruning idiom for the recursive counters
  (``_count_md_recursive`` / ``_count_py_recursive``) and ``Path.iterdir``
  for the non-recursive ``md_agents`` strategy. The pruned set is
  ``_EXCLUDED_DIR_NAMES`` (same five names as canonical ``_EXCLUDED_DIRS``).
- Per-plugin overrides: canonical reads
  ``templates/marketplace-counters.yaml`` for plugin-specific
  ``exclude`` lists; this hard-codes the project-toolkit excludes.
  Other plugins are not supported here; orphan-ref-validator scans
  manifests for general count drift, not per-plugin enforcement.
- ``--fix``: canonical supports auto-fix; this is detection only.
- Caching: canonical re-walks per call; this caches per
  ``(repo_root, kind)`` so a single manifest scan does one walk per kind.
- Skill enumeration: canonical ``_count_skill_dirs`` counts every
  immediate subdirectory under ``.claude/skills/``; this requires each
  subdirectory to contain a ``SKILL.md`` (see ``enumerate_skills``).
  The intent here is different: the canonical reports the marketplace's
  declared inventory, while orphan-ref-validator needs to know which
  *valid* skills exist so it can decide whether a backticked kebab
  reference resolves to a real skill catalog entry. A directory without
  a ``SKILL.md`` is a partial or in-progress skill that cannot legally
  be referenced. The two functions disagree intentionally.
"""

from __future__ import annotations

import os
from pathlib import Path

# Mirror the upstream prune set so counts under .claude/<dir>/ never
# inflate if a vendor directory ever lands inside (defense in depth; the
# names below should not appear under .claude/ in practice).
_EXCLUDED_DIR_NAMES: frozenset[str] = frozenset({
    "node_modules", ".git", "worktrees", "cache", "__pycache__",
})

_COUNT_CACHE: dict[tuple[str, str], int | None] = {}


def enumerate_skills(repo_root: Path) -> set[str] | None:
    """Return the set of skill names found at ``.claude/skills/<name>/SKILL.md``.

    Returns ``None`` when ``.claude/skills/`` is absent or is not a
    directory so callers can distinguish "no directory" (undeterminable)
    from "directory with zero skills" (deterministic count of zero).
    """
    skills_dir = repo_root / ".claude" / "skills"
    if not skills_dir.exists() or not skills_dir.is_dir():
        return None
    return {
        d.name
        for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    }


def enumerate_count(repo_root: Path, kind: str) -> int | None:
    """Return count for the given canonical label, or ``None`` when absent.

    ``kind`` is one of the canonical labels (``"agent"``,
    ``"slash command"``, ``"lifecycle hook"``, ``"reusable skill"``).
    The legacy short forms (``"skills"``, ``"agents"``, ``"commands"``,
    ``"hooks"``) are accepted as aliases.
    """
    canonical = {
        "agents": "agent",
        "commands": "slash command",
        "hooks": "lifecycle hook",
        "skills": "reusable skill",
    }.get(kind, kind)
    cache_key = (str(repo_root), canonical)
    if cache_key in _COUNT_CACHE:
        return _COUNT_CACHE[cache_key]
    result: int | None
    if canonical == "reusable skill":
        skills = enumerate_skills(repo_root)
        result = None if skills is None else len(skills)
    elif canonical == "agent":
        result = _count_md_agents(
            repo_root / ".claude" / "agents",
            exclude={"AGENTS.md", "CLAUDE.md"},
        )
    elif canonical == "slash command":
        result = _count_md_recursive(
            repo_root / ".claude" / "commands", exclude={"CLAUDE.md"}
        )
    elif canonical == "lifecycle hook":
        result = _count_py_recursive(repo_root / ".claude" / "hooks")
    else:
        result = None
    _COUNT_CACHE[cache_key] = result
    return result


def reset_count_cache() -> None:
    """Clear the per-repo count cache.

    ``scan()`` calls this at entry so a CLI run never observes stale
    counts. Programmatic callers that invoke ``enumerate_count`` /
    ``enumerate_skills`` directly (without going through ``scan``) and
    that mutate the filesystem between calls must call this themselves
    to avoid stale cached values; the cache is keyed by
    ``(str(repo_root), canonical_kind)`` and lives for the process
    lifetime otherwise.
    """
    _COUNT_CACHE.clear()


def _count_md_agents(directory: Path, exclude: set[str]) -> int | None:
    """Mirrors canonical ``_count_md_agents``: count ``.md`` files,
    exclude ``AGENTS.md``/``CLAUDE.md`` and any ``*template*`` filenames."""
    if not directory.exists() or not directory.is_dir():
        return None
    return sum(
        1
        for f in directory.iterdir()
        if f.is_file()
        and f.suffix == ".md"
        and f.name not in exclude
        and "template" not in f.name
    )


def _count_md_recursive(directory: Path, exclude: set[str]) -> int | None:
    """Recursive count of ``.md`` files, excluding given filenames and
    pruning ``_EXCLUDED_DIR_NAMES`` subtrees.

    Uses ``os.walk(followlinks=False)`` rather than ``Path.rglob`` so the
    behavior matches canonical ``validate_marketplace_counts.py`` on
    Python 3.10-3.12 (where ``Path.rglob`` follows symlinks; ``os.walk``
    does not by default). A symlinked directory pointing back into the
    repo would otherwise inflate the count.
    """
    return _count_with_suffix(directory, ".md", exclude)


def _count_py_recursive(directory: Path) -> int | None:
    """Recursive count of ``.py`` files, pruning ``_EXCLUDED_DIR_NAMES``."""
    return _count_with_suffix(directory, ".py", exclude=set())


def _count_with_suffix(
    directory: Path, suffix: str, exclude: set[str]
) -> int | None:
    if not directory.exists() or not directory.is_dir():
        return None
    total = 0
    for root, dirnames, filenames in os.walk(directory, followlinks=False):
        # Prune excluded subtrees in place.
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIR_NAMES]
        for name in filenames:
            if not name.endswith(suffix):
                continue
            if name in exclude:
                continue
            total += 1
    return total


def is_manifest_file(path: Path) -> bool:
    """Return True if a path's basename matches the plugin/marketplace shapes."""
    return path.name in {"plugin.json", "marketplace.json"}
