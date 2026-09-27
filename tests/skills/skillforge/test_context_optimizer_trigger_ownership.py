"""SkillForge and context-optimizer must not claim the same trigger phrases.

Issue #5944: both descriptions listed the same five phrases, so the router
picked either skill for the same request. Context-optimizer owns them now, and
each skill's Do NOT use clause names the other. The checks run on every
rendered copy so a template or mirror regression fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]

CONTEXT_OPTIMIZER_TRIGGERS = (
    "analyze skill placement",
    "compress markdown",
    "optimize context",
    "extract and index",
    "audit always-on rules",
)
SKILL_PAIR_COPIES = (
    (
        "templates/skills/skillforge.SKILL.md.tmpl",
        "templates/skills/context-optimizer.SKILL.md.tmpl",
    ),
    (".claude/skills/skillforge/SKILL.md", ".claude/skills/context-optimizer/SKILL.md"),
    ("src/claude/skills/skillforge/SKILL.md", "src/claude/skills/context-optimizer/SKILL.md"),
    (
        "src/copilot-cli/skills/skillforge/SKILL.md",
        "src/copilot-cli/skills/context-optimizer/SKILL.md",
    ),
)
QUOTED_PHRASE_RE = re.compile(r'"([^"]+)"')


def _description(relative_path: str) -> str:
    """Return the parsed frontmatter ``description`` of a skill file."""
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---", 2)[1])["description"]


@pytest.mark.parametrize(("skillforge_path", "optimizer_path"), SKILL_PAIR_COPIES)
def test_context_optimizer_alone_owns_its_trigger_phrases(
    skillforge_path: str, optimizer_path: str
) -> None:
    """AC1, AC4: each trigger phrase has one owner in every copy."""
    skillforge = _description(skillforge_path)
    optimizer = _description(optimizer_path)

    shared = set(QUOTED_PHRASE_RE.findall(skillforge)) & set(QUOTED_PHRASE_RE.findall(optimizer))
    assert not shared, f"{skillforge_path} and {optimizer_path} share triggers: {sorted(shared)}"
    for trigger in CONTEXT_OPTIMIZER_TRIGGERS:
        assert f'"{trigger}"' in optimizer, f"{optimizer_path} lost trigger {trigger!r}"
        assert trigger not in skillforge.lower(), f"{skillforge_path} still claims {trigger!r}"


@pytest.mark.parametrize(("skillforge_path", "optimizer_path"), SKILL_PAIR_COPIES)
def test_skillforge_and_context_optimizer_redirect_to_each_other(
    skillforge_path: str, optimizer_path: str
) -> None:
    """AC2, AC3: each Do NOT use clause names the other skill."""
    skillforge = _description(skillforge_path)
    optimizer = _description(optimizer_path)

    assert "(use context-optimizer)" in skillforge.split("Do NOT use", 1)[-1], skillforge_path
    assert "(use skillforge)" in optimizer.split("Do NOT use", 1)[-1], optimizer_path
