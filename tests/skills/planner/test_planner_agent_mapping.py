"""Planner delegations map to real agents and fall back when one is missing.

Planner once named `developer`, `debugger` and `quality-reviewer`, which no
template defines. They map to `implementer`, `debug`, `critic` (plan review),
and `code-reviewer` (reconciliation and post-implementation review). Codex and
Muse Code do not install read-only agents such as `comment-analyzer` and
`code-reviewer`, so every planner SKILL.md carries the host-delegation
paragraph that runs a missing agent's step in the current session.
`test_planner_delegation_targets.py` checks that every named agent exists.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_TEMPLATES = REPO_ROOT / "templates" / "agents"
SCRIPTS = REPO_ROOT / "src" / "claude" / "skills" / "planner" / "scripts"
PLANNER_TEMPLATE = REPO_ROOT / "templates" / "skills" / "planner.SKILL.md.tmpl"
PLANNER_DOCS_PAGE = REPO_ROOT / "docs" / "skills" / "planner.md"
# Every on-disk planner tree, found by glob so a new mirror cannot go unchecked.
PLANNER_ROOTS = tuple(
    sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in (
            *REPO_ROOT.glob("src/*/skills/planner"),
            *REPO_ROOT.glob("src/*/*/skills/planner"),
            REPO_ROOT / ".claude" / "skills" / "planner",
        )
        if path.is_dir()
    )
)
DELEGATION_MARKER = "**Delegation on each host.**"
NOT_INSTALLED_FALLBACK = "no `X` agent is installed, run the step yourself in this session"
AGENT_REF_RE = re.compile(r"@agent-([a-z][a-z0-9]*(?:-[a-z0-9]+)*)")
CRITIC_VERDICT_ROW_RE = re.compile(r"^\| \*\*([A-Z_]+)\*\* \|", re.MULTILINE)


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"mapping_{name}", SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


planner = _load("planner")
executor = _load("executor")


def _flatten(guidance: dict) -> str:
    parts: list[str] = []
    for value in guidance.values():
        parts.extend(value if isinstance(value, list) else [str(value)])
    return "\n".join(parts)


def _planner_outputs() -> dict[str, str]:
    return {f"review step {s}": _flatten(planner.get_review_step_guidance(s, 2)) for s in (1, 2)}


def _executor_outputs() -> dict[str, str]:
    plan = "plans/example.md"
    return {
        f"execution step {s}": _flatten(executor.get_step_guidance(s, plan, "go"))
        for s in range(1, 8)
    }


def squash(text: str) -> str:
    """Collapse line breaks and runs of spaces so a phrase can span emitted lines."""
    return " ".join(text.split())


def agent_targets(text: str) -> set[str]:
    return set(AGENT_REF_RE.findall(text))


def test_review_step_2_delegates_plan_review_to_critic() -> None:
    text = _planner_outputs()["review step 2"]
    assert agent_targets(text) == {"critic"}
    assert "APPROVED | APPROVED_WITH_CONCERNS | NEEDS_REVISION" in text
    assert "<mode>" not in text


def critic_verdicts() -> set[str]:
    """Every verdict token in the critic agent's verdict table."""
    critic = (AGENT_TEMPLATES / "critic.shared.md").read_text(encoding="utf-8")
    return set(CRITIC_VERDICT_ROW_RE.findall(critic))


def test_planner_roots_are_found_on_disk() -> None:
    assert "src/claude/skills/planner" in PLANNER_ROOTS
    assert len(PLANNER_ROOTS) >= 6


def test_critic_verdict_table_is_found() -> None:
    assert {"APPROVED", "NEEDS_REVISION"} <= critic_verdicts()


def test_review_step_2_routes_every_critic_verdict() -> None:
    text = squash(_planner_outputs()["review step 2"])
    routing = text.split("After the critic returns its verdict:", 1)[1]
    missing = {v for v in critic_verdicts() if not re.search(rf"\b{v}\b", routing)}
    assert not missing, f"review step 2 has no next step for: {sorted(missing)}"


def test_reconciliation_names_files_and_maps_findings_to_a_result() -> None:
    text = squash(_executor_outputs()["execution step 2"])
    assert "Files: [the milestone's file paths" in text
    assert "No blocking finding: SATISFIED" in text
    assert "Return: SATISFIED" not in text


def test_review_step_2_brief_carries_its_criteria_and_resource() -> None:
    text = squash(_planner_outputs()["review step 2"])
    assert "production reliability" in text
    assert "resources/default-conventions.md" in text


@pytest.mark.parametrize("step", ["execution step 2", "execution step 4"])
def test_code_review_steps_delegate_to_code_reviewer(step: str) -> None:
    text = _executor_outputs()[step]
    assert agent_targets(text) == {"code-reviewer"}
    assert "read-only" in text


def test_post_implementation_review_names_both_resources() -> None:
    text = squash(_executor_outputs()["execution step 4"])
    assert "resources/default-conventions.md" in text
    assert "resources/temporal-contamination.md" in text


def test_post_implementation_review_routes_on_blocking_findings() -> None:
    text = _executor_outputs()["execution step 4"]
    assert "If any finding is blocking -> invoke step 5" in text
    assert "If no finding is blocking -> invoke step 6" in text


@pytest.mark.parametrize(
    "path",
    [PLANNER_TEMPLATE, *(REPO_ROOT / root / "SKILL.md" for root in PLANNER_ROOTS)],
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_skill_body_falls_back_to_this_session_when_an_agent_is_not_installed(
    path: Path,
) -> None:
    text = path.read_text(encoding="utf-8")
    if path == PLANNER_TEMPLATE:
        assert "{{> host-delegation}}" in text
        return
    assert DELEGATION_MARKER in text
    assert NOT_INSTALLED_FALLBACK in text
    assert "`@agent-X` in the scripts' output means the\n`X` agent" in text


def test_docs_page_says_a_missing_agent_runs_in_this_session() -> None:
    text = squash(PLANNER_DOCS_PAGE.read_text(encoding="utf-8"))
    assert "When a named agent isn't installed, the coordinator runs that step" in text


def test_delegation_form_has_no_mode_line() -> None:
    text = _executor_outputs()["execution step 1"]
    assert "<mode>" not in text


def test_delegation_form_lists_only_real_agents() -> None:
    text = _executor_outputs()["execution step 1"]
    assert "<agent>@agent-[implementer|debug|code-reviewer]</agent>" in text
