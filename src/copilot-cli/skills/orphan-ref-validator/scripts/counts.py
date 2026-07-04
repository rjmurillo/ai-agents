#!/usr/bin/env python3
"""orphan-ref-validator skill catalog enumeration.

Enumerates the live skill catalog at ``.claude/skills/<name>/SKILL.md`` so
``scan`` can decide whether a backticked kebab reference resolves to a real
skill. A subdirectory without a ``SKILL.md`` is a partial or in-progress
skill that cannot legally be referenced, so it is excluded.
"""

from __future__ import annotations

from pathlib import Path


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
