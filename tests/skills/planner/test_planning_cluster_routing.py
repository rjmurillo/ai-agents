"""The planning skills must redirect to the skill that owns each job.

Issue #5945: execution-plans sent milestone work to planner, though plan owns
it and is execution-plans' own invoker. Autoplan never routed to planner at
all. Every check runs on each rendered copy, so a template or mirror
regression fails here. The plan and planner trigger split is pinned in
test_plan_planner_trigger_ownership.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]

CLUSTER = ("execution-plans", "plan", "planner", "spec")
COPY_ROOTS = (".claude/skills", "src/claude/skills", "src/copilot-cli/skills")
USE_TARGET_RE = re.compile(r"\(use ([a-z0-9-]+)")


def _copies(name: str) -> list[str]:
    """Return every committed copy of one skill: template plus mirrors."""
    return [f"templates/skills/{name}.SKILL.md.tmpl"] + [
        f"{root}/{name}/SKILL.md" for root in COPY_ROOTS
    ]


def _redirects(relative_path: str) -> str:
    """Return the Do NOT use part of a skill's description, or an empty string."""
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    description = yaml.safe_load(text.split("---", 2)[1])["description"]
    parts = description.split("Do NOT use", 1)
    return parts[1] if len(parts) == 2 else ""


@pytest.mark.parametrize("path", _copies("execution-plans"))
def test_execution_plans_sends_milestone_work_to_plan(path: str) -> None:
    """AC1: milestone breakdown redirects to plan, the skill that invokes it."""
    redirects = _redirects(path)

    assert "milestones (use plan)" in redirects, path
    assert "milestones (use planner)" not in redirects, path


@pytest.mark.parametrize("path", _copies("autoplan"))
def test_autoplan_routes_plan_file_execution_to_planner(path: str) -> None:
    """AC6: the routing table sends approved-plan execution to planner."""
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| ")]

    assert any("Skill: planner" in row and "plan file" in row for row in rows), path


@pytest.mark.parametrize("name", CLUSTER)
def test_every_cluster_redirect_names_a_real_skill(name: str) -> None:
    """AC8: every (use X) in the cluster names a skill directory that exists."""
    for path in _copies(name):
        targets = USE_TARGET_RE.findall(_redirects(path))
        assert targets, f"{path} has no (use X) redirect"
        missing = [t for t in targets if not (REPO_ROOT / ".claude/skills" / t).is_dir()]
        assert not missing, f"{path} redirects to missing skills {missing}"
