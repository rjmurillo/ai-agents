"""The planning skills must redirect to the skill that owns each job.

Issue #5945: execution-plans sent milestone work to planner, though plan owns
it and is execution-plans' own invoker. Plan and planner also claimed the same
"plan this ..." requests and never named each other. Plan now owns milestone
decomposition, planner owns review and delegated execution of an approved plan
file, and autoplan routes that execution to planner. Every check runs on each
rendered copy, so a template or mirror regression fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]

CLUSTER = ("execution-plans", "plan", "planner", "spec")
COPY_ROOTS = (".claude/skills", "src/claude/skills", "src/copilot-cli/skills")
RETIRED_PLANNER_TRIGGERS = ("plan this feature", "create implementation plan")
TRIGGER_PHRASE_RE = re.compile(r'"([^"]+)"|`([^`]+)`')
USE_TARGET_RE = re.compile(r"\(use ([a-z0-9-]+)")
TRIGGER_ROW_RE = re.compile(r"^\| `([^`]+)` \|", re.MULTILINE)


def _copies(name: str) -> list[str]:
    """Return every committed copy of one skill: template plus mirrors."""
    return [f"templates/skills/{name}.SKILL.md.tmpl"] + [
        f"{root}/{name}/SKILL.md" for root in COPY_ROOTS
    ]


def _text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _description(relative_path: str) -> str:
    """Return the parsed frontmatter ``description`` of a skill file."""
    return yaml.safe_load(_text(relative_path).split("---", 2)[1])["description"]


def _redirects(description: str) -> str:
    """Return the Do NOT use part of a description, or an empty string."""
    parts = description.split("Do NOT use", 1)
    return parts[1] if len(parts) == 2 else ""


def _trigger_phrases(relative_path: str) -> set[str]:
    """Return quoted phrases before Do NOT use, plus Triggers table rows."""
    description = _description(relative_path).split("Do NOT use", 1)[0]
    quoted = {a or b for a, b in TRIGGER_PHRASE_RE.findall(description)}
    return quoted | set(TRIGGER_ROW_RE.findall(_text(relative_path)))


def _pairs(first: str, second: str) -> list[tuple[str, str]]:
    return list(zip(_copies(first), _copies(second), strict=True))


@pytest.mark.parametrize("path", _copies("execution-plans"))
def test_execution_plans_sends_milestone_work_to_plan(path: str) -> None:
    """AC1: milestone breakdown redirects to plan, the skill that invokes it."""
    redirects = _redirects(_description(path))

    assert "milestones (use plan)" in redirects, path
    assert "milestones (use planner)" not in redirects, path


@pytest.mark.parametrize("path", _copies("planner"))
def test_planner_drops_the_triggers_plan_owns(path: str) -> None:
    """AC2: planner no longer claims generic plan-authoring requests."""
    text = _text(path).lower()

    for trigger in RETIRED_PLANNER_TRIGGERS:
        assert trigger not in text, f"{path} still claims {trigger!r}"


@pytest.mark.parametrize(("plan_path", "planner_path"), _pairs("plan", "planner"))
def test_plan_and_planner_redirect_to_each_other(plan_path: str, planner_path: str) -> None:
    """AC3, AC4: each Do NOT use clause names the other skill."""
    assert "(use plan)" in _redirects(_description(planner_path)), planner_path
    assert "(use planner)" in _redirects(_description(plan_path)), plan_path


@pytest.mark.parametrize(("plan_path", "planner_path"), _pairs("plan", "planner"))
def test_plan_and_planner_share_no_trigger_phrase(plan_path: str, planner_path: str) -> None:
    """AC5: no trigger phrase has two owners."""
    plan_triggers = _trigger_phrases(plan_path)
    planner_triggers = _trigger_phrases(planner_path)

    assert plan_triggers, f"{plan_path} lists no triggers"
    assert planner_triggers, f"{planner_path} lists no triggers"
    shared = plan_triggers & planner_triggers
    assert not shared, f"{plan_path} and {planner_path} share {sorted(shared)}"


@pytest.mark.parametrize("path", _copies("autoplan"))
def test_autoplan_routes_plan_file_execution_to_planner(path: str) -> None:
    """AC6: the routing table sends approved-plan execution to planner."""
    rows = [line for line in _text(path).splitlines() if line.startswith("| ")]

    assert any("Skill: planner" in row and "plan file" in row for row in rows), path


@pytest.mark.parametrize("name", CLUSTER)
def test_every_cluster_redirect_names_a_real_skill(name: str) -> None:
    """AC8: every (use X) in the cluster names a skill directory that exists."""
    for path in _copies(name):
        targets = USE_TARGET_RE.findall(_redirects(_description(path)))
        assert targets, f"{path} has no (use X) redirect"
        missing = [t for t in targets if not (REPO_ROOT / ".claude/skills" / t).is_dir()]
        assert not missing, f"{path} redirects to missing skills {missing}"
