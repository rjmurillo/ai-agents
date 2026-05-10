#!/usr/bin/env python3
"""orphan-ref-validator working-tree count enumeration.

Mirrors the project-toolkit count strategies in
``build/scripts/validate_marketplace_counts.py`` and the per-plugin
rules in ``templates/marketplace-counters.yaml``. Per
``.claude/rules/canonical-source-mirror.md``, the canonical contract
for ``.claude-plugin/marketplace.json`` is quoted here verbatim:

    agent:           md_agents(.claude/agents, exclude={AGENTS.md, CLAUDE.md})
    slash command:   commands(.claude/commands, exclude={CLAUDE.md})
    lifecycle hook:  hooks(.claude/hooks)
    reusable skill:  skill_dirs(.claude/skills)

Stricter/looser/different than canonical:

- Pruning: canonical uses ``os.walk`` with ``_EXCLUDED_DIRS`` removed
  from ``dirs``; this uses ``Path.rglob``/``iterdir`` without that
  prune set. ``.claude/`` trees do not currently contain those names,
  so counts match in practice.
- Per-plugin overrides: canonical reads
  ``templates/marketplace-counters.yaml`` for plugin-specific
  ``exclude`` lists; this hard-codes the project-toolkit excludes.
  Other plugins are not supported here; orphan-ref-validator scans
  manifests for general count drift, not per-plugin enforcement.
- ``--fix``: canonical supports auto-fix; this is detection only.
- Caching: canonical re-walks per call; this caches per
  ``(repo_root, kind)`` so a single manifest scan does one walk per kind.
"""

from __future__ import annotations

from pathlib import Path

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
    """Clear the per-repo count cache. Test helper; not part of the CLI."""
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
    """Recursive count of ``.md`` files, excluding given filenames."""
    if not directory.exists() or not directory.is_dir():
        return None
    return sum(
        1
        for f in directory.rglob("*.md")
        if f.is_file() and f.name not in exclude
    )


def _count_py_recursive(directory: Path) -> int | None:
    """Recursive count of ``.py`` files."""
    if not directory.exists() or not directory.is_dir():
        return None
    return sum(1 for f in directory.rglob("*.py") if f.is_file())


def is_manifest_file(path: Path) -> bool:
    """Return True if a path's basename matches the plugin/marketplace shapes."""
    return path.name in {"plugin.json", "marketplace.json"}
