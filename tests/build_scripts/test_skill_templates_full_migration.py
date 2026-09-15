"""Pins ``discover()`` to the full, post-migration skill set (TASK-033).

Replaces ``test_skill_templates_pilot_scope.py``, deleted once
``skill_templates.discover(repo_root)`` on the real tree returned every one
of the 111 skills under ``.claude/skills/`` (ADR-108 section 1's pilot
boundary, and its batched widening through TASK-033, both retired). Without
this test, nothing else in the repository asserts that every on-disk skill
is template-owned: a skill with no ``templates/skills/<name>.SKILL.md.tmpl``
could land silently, and ``discover()`` would just exclude it with no gate
saying so.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import skill_templates  # noqa: E402


def _on_disk_skill_names() -> set[str]:
    """Return every name under ``.claude/skills/<name>/SKILL.md``."""
    skills_dir = REPO_ROOT / ".claude" / "skills"
    return {
        child.name
        for child in skills_dir.iterdir()
        if child.is_dir() and (child / "SKILL.md").is_file()
    }


def test_discover_equals_the_full_on_disk_skill_set() -> None:
    """Every ``.claude/skills/<name>/SKILL.md`` has a template, and vice versa.

    A skill missing here means either a template was never written for an
    existing skill (silent scope loss) or a name is discovered with no
    matching on-disk skill directory, which :func:`skill_templates.discover`
    already refuses (see ``discover_errors``) but is worth re-asserting at
    the full-tree level.
    """
    assert set(skill_templates.discover(REPO_ROOT)) == _on_disk_skill_names()
    assert skill_templates.discover_errors(REPO_ROOT) == []
