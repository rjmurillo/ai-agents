"""Plan and planner must not claim the same planning requests.

Issue #5945: planner listed "plan this feature" while plan listed "plan this
work", so the router picked either skill for the same request, and neither
description named the other. Plan now owns milestone decomposition, planner
owns its script-driven review and plan-file execution, and each Do NOT use
clause names the other. Every check runs on each rendered copy, so a template
or mirror regression fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]

COPY_ROOTS = (".claude/skills", "src/claude/skills", "src/copilot-cli/skills")
RETIRED_PLANNER_TRIGGERS = ("plan this feature", "create implementation plan")
TRIGGER_PHRASE_RE = re.compile(r'"([^"]+)"|`([^`]+)`')
TRIGGER_ROW_RE = re.compile(r"^\| `([^`]+)` \|", re.MULTILINE)
TRIGGERS_SECTION_RE = re.compile(r"^## Triggers\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)


def _copies(name: str) -> list[str]:
    """Return every committed copy of one skill: template plus mirrors."""
    return [f"templates/skills/{name}.SKILL.md.tmpl"] + [
        f"{root}/{name}/SKILL.md" for root in COPY_ROOTS
    ]


PLAN_PAIRS = list(zip(_copies("plan"), _copies("planner"), strict=True))


def _read(relative_path: str) -> tuple[str, str]:
    """Return a skill file's text and its frontmatter ``description``."""
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    return text, yaml.safe_load(text.split("---", 2)[1])["description"]


def _trigger_phrases(relative_path: str) -> set[str]:
    """Return quoted phrases before Do NOT use, plus Triggers section rows."""
    text, description = _read(relative_path)
    quoted = TRIGGER_PHRASE_RE.findall(description.split("Do NOT use", 1)[0])
    section = TRIGGERS_SECTION_RE.search(text)
    rows = TRIGGER_ROW_RE.findall(section.group(1)) if section else []
    return {a or b for a, b in quoted} | set(rows)


@pytest.mark.parametrize("path", _copies("planner"))
def test_planner_drops_the_triggers_plan_owns(path: str) -> None:
    """AC2: planner no longer claims generic plan-authoring requests."""
    text = _read(path)[0].lower()

    for trigger in RETIRED_PLANNER_TRIGGERS:
        assert trigger not in text, f"{path} still claims {trigger!r}"


@pytest.mark.parametrize(("plan_path", "planner_path"), PLAN_PAIRS)
def test_plan_and_planner_redirect_to_each_other(plan_path: str, planner_path: str) -> None:
    """AC3, AC4: each Do NOT use clause names the other skill."""
    plan_redirects = _read(plan_path)[1].split("Do NOT use", 1)[-1]
    planner_redirects = _read(planner_path)[1].split("Do NOT use", 1)[-1]

    assert "(use plan)" in planner_redirects, planner_path
    assert "(use planner)" in plan_redirects, plan_path


@pytest.mark.parametrize(("plan_path", "planner_path"), PLAN_PAIRS)
def test_plan_and_planner_share_no_trigger_phrase(plan_path: str, planner_path: str) -> None:
    """AC5: no trigger phrase, and no trigger lead verb, has two owners."""
    plan_triggers = _trigger_phrases(plan_path)
    planner_triggers = _trigger_phrases(planner_path)

    assert plan_triggers, f"{plan_path} lists no triggers"
    assert planner_triggers, f"{planner_path} lists no triggers"
    shared = plan_triggers & planner_triggers
    assert not shared, f"{plan_path} and {planner_path} share {sorted(shared)}"
    # The old overlap was "plan this feature" against "plan this work": same
    # verb, different object. A shared lead verb is how that collision shows.
    plan_verbs = {phrase.split()[0].lower() for phrase in plan_triggers}
    planner_verbs = {phrase.split()[0].lower() for phrase in planner_triggers}
    assert not plan_verbs & planner_verbs, f"{plan_path} and {planner_path} share a lead verb"
