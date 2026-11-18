"""Planner delegations must name an agent or skill that exists.

Issue #7421: planner told its caller to delegate to `@agent-technical-writer`,
which commit 782e492b1 removed, and to modes (`plan-scrub`, `plan-annotation`)
the removed agent never had. Every check here reads the planner scripts, the
template, and the hand-maintained references, so a regression in any of them
fails.

`KNOWN_MISSING_AGENTS` lists delegation targets that planner still names and
that do not exist today. They predate #7421 and stay in the set until a separate
decision maps or removes each one.
`test_known_missing_agents_are_still_missing` fails when one of them starts to
exist, so the exemption cannot go stale.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_TEMPLATES = REPO_ROOT / "templates" / "agents"
SHIPPED_SKILLS = REPO_ROOT / "src" / "claude" / "skills"
PLANNER_ROOTS = (
    "src/claude/skills/planner",
    ".claude/skills/planner",
    "src/copilot-cli/skills/planner",
)
PLANNER_TEMPLATE = REPO_ROOT / "templates" / "skills" / "planner.SKILL.md.tmpl"
PLANNER_DOCS_PAGE = REPO_ROOT / "docs" / "skills" / "planner.md"
COMMENT_ANALYZER = AGENT_TEMPLATES / "comment-analyzer.shared.md"
SRC_PLANNER = REPO_ROOT / "src" / "claude" / "skills" / "planner"
SCRIPTS = SRC_PLANNER / "scripts"

# Names planner still delegates to that no template or skill defines. Out of
# scope for #7421; each needs its own mapping decision.
KNOWN_MISSING_AGENTS = frozenset({"developer", "debugger", "quality-reviewer"})

# A removed agent name, its abbreviation, and the modes it never had.
REMOVED_WRITER_RE = re.compile(
    r"technical[-_ ]?writer|\bTW\b|plan-scrub|plan-annotation|tw_delegation|delegate_tw",
    re.IGNORECASE,
)
# One wording for who runs a skill, used in every executor site that names one.
SKILL_RUNNER_PHRASE = (
    "the coordinator, or a general-purpose subagent it starts, loads the skill and follows it"
)
AGENT_REF_RE = re.compile(r"@agent-([a-z][a-z0-9]*(?:-[a-z0-9]+)*)")
SKILL_TAG_RE = re.compile(r"<skill>([a-z][a-z0-9-]*)</skill>")
SKILL_PROSE_RE = re.compile(r"\b([a-z][a-z0-9]*(?:-[a-z0-9]+)+) skill\b")
LOAD_SKILL_RE = re.compile(r"\bload ([a-z][a-z0-9]*(?:-[a-z0-9]+)+)\b")


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader, name
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
    outputs = {}
    for step in range(1, 8):
        outputs[f"planning step {step}"] = _flatten(planner.get_planning_step_guidance(step, 6))
    for step in (1, 2, 3):
        outputs[f"review step {step}"] = _flatten(planner.get_review_step_guidance(step, 2))
    return outputs


def _executor_outputs() -> dict[str, str]:
    plan = "plans/example.md"
    outputs = {}
    for step in range(1, 8):
        outputs[f"execution step {step}"] = _flatten(executor.get_step_guidance(step, plan, "go"))
    outputs["execution step 1 reconciliation"] = _flatten(
        executor.get_step_guidance(1, plan, "existing code already implemented, reconciliation")
    )
    return outputs


def _planner_files() -> dict[str, str]:
    files = {
        str(path.relative_to(REPO_ROOT)): path.read_text(encoding="utf-8")
        for path in (PLANNER_TEMPLATE, PLANNER_DOCS_PAGE)
    }
    for root in PLANNER_ROOTS:
        base = REPO_ROOT / root
        for path in sorted(base.rglob("*")):
            if path.suffix in {".md", ".py"} and "__pycache__" not in path.parts:
                files[str(path.relative_to(REPO_ROOT))] = path.read_text(encoding="utf-8")
    return files


def _corpus() -> dict[str, str]:
    return {**_planner_outputs(), **_executor_outputs(), **_planner_files()}


def squash(text: str) -> str:
    """Collapse line breaks and runs of spaces so a phrase can span emitted lines."""
    return " ".join(text.split())


def find_removed_writer(text: str) -> list[str]:
    """Return every reference to the removed technical-writer agent or its modes."""
    return [match.group(0) for match in REMOVED_WRITER_RE.finditer(text)]


def agent_targets(text: str) -> set[str]:
    return set(AGENT_REF_RE.findall(text))


def skill_targets(text: str) -> set[str]:
    return (
        set(SKILL_TAG_RE.findall(text))
        | set(SKILL_PROSE_RE.findall(text))
        | set(LOAD_SKILL_RE.findall(text))
    )


def missing_agents(text: str) -> set[str]:
    """Agents named in text that have no `templates/agents/<name>.shared.md`."""
    return {
        name
        for name in agent_targets(text)
        if not (AGENT_TEMPLATES / f"{name}.shared.md").is_file()
    }


def missing_skills(text: str) -> set[str]:
    """Skills named in text that have no `src/claude/skills/<name>/SKILL.md`."""
    return {
        name for name in skill_targets(text) if not (SHIPPED_SKILLS / name / "SKILL.md").is_file()
    }


CORPUS = _corpus()


@pytest.mark.parametrize("label", sorted(CORPUS))
def test_no_removed_technical_writer_reference(label: str) -> None:
    assert find_removed_writer(CORPUS[label]) == [], label


@pytest.mark.parametrize("label", sorted(CORPUS))
def test_every_named_agent_exists_or_is_known_missing(label: str) -> None:
    unknown = missing_agents(CORPUS[label]) - KNOWN_MISSING_AGENTS
    assert not unknown, f"{label} names agents with no template: {sorted(unknown)}"


@pytest.mark.parametrize("label", sorted(CORPUS))
def test_every_named_skill_exists(label: str) -> None:
    unknown = missing_skills(CORPUS[label])
    assert not unknown, f"{label} names skills that do not ship: {sorted(unknown)}"


def test_known_missing_agents_are_still_missing() -> None:
    now_present = {
        n for n in KNOWN_MISSING_AGENTS if (AGENT_TEMPLATES / f"{n}.shared.md").is_file()
    }
    assert not now_present, f"remove from KNOWN_MISSING_AGENTS: {sorted(now_present)}"


def test_review_step_1_delegates_to_comment_analyzer_and_applies_findings() -> None:
    text = _planner_outputs()["review step 1"]
    assert agent_targets(text) == {"comment-analyzer"}
    assert "read-only" in text
    assert "apply the findings to the plan file yourself" in text.lower()


def test_review_step_1_names_the_plan_file_as_the_artifact_under_review() -> None:
    text = squash(_planner_outputs()["review step 1"])
    assert "The plan file is the artifact under review" in text
    assert "proposed code that does not exist in the repository yet" in text
    assert "cite the plan file path and line in each finding" in text
    assert "do not flag a symbol the plan introduces as missing from the repository" in text


def test_review_step_1_does_not_forbid_reading_the_cited_location() -> None:
    # comment-analyzer's Tool Use Directive requires reading the code at the cited
    # location. The brief makes the plan file that location instead of banning reads.
    text = squash(_planner_outputs()["review step 1"])
    assert "do not read code at a file location" not in text


def test_review_step_1_second_pass_targets_findings_past_the_top_10() -> None:
    text = squash(_planner_outputs()["review step 1"])
    assert (
        "NEEDS_DECOMPOSITION, apply the top 10 findings, then delegate again for the "
        "findings past the top 10."
    ) in text
    assert "remaining snippets" not in text


def test_comment_analyzer_still_returns_the_top_10_the_planner_brief_assumes() -> None:
    source = squash(COMMENT_ANALYZER.read_text(encoding="utf-8"))
    assert (
        "[NEEDS_DECOMPOSITION]**: more than 10 findings apply. Return the top 10 by impact"
        in source
    )


def test_documentation_milestone_loads_technical_writing_skill() -> None:
    text = _executor_outputs()["execution step 1"]
    assert "technical-writing" in skill_targets(text)
    assert "<skill>technical-writing</skill>" in text


def test_step_1_splits_docs_skills_and_keeps_prompts_with_implementer() -> None:
    text = squash(_executor_outputs()["execution step 1"])
    assert skill_targets(text) == {"technical-writing", "codebase-documenter"}
    assert "New README or ARCHITECTURE scaffold: codebase-documenter skill" in text
    assert "Edits to existing docs pages, including an existing README: technical-writing" in text
    assert (
        "Agent prompts and SKILL.md files: out of scope for both skills; @agent-implementer" in text
    )


def test_step_1_scopes_the_skill_form_to_docs_page_milestones() -> None:
    text = squash(_executor_outputs()["execution step 1"])
    assert "A docs-page milestone (new scaffold or existing page) names a skill" in text
    assert "A milestone for agent prompts or SKILL.md files uses the <agent> form" in text


def test_docs_page_scopes_the_skill_route_to_docs_pages() -> None:
    text = squash(PLANNER_DOCS_PAGE.read_text(encoding="utf-8"))
    assert "holds docs pages goes to a docs skill" in text
    assert "agent prompts or `SKILL.md` files goes to the implementer agent" in text


def test_technical_writing_owner_row_covers_only_new_scaffolds() -> None:
    row = (REPO_ROOT / "templates/skills/technical-writing.SKILL.md.tmpl").read_text(
        encoding="utf-8"
    )
    assert "| New repository README and architecture doc scaffolds | `codebase-documenter` |" in row
    assert "Edits to an existing README are a docs page edit this skill owns." in row


def test_step_6_splits_docs_docstrings_and_comment_checks_by_owner() -> None:
    text = _executor_outputs()["execution step 6"]
    assert skill_targets(text) == {"technical-writing", "codebase-documenter"}
    assert agent_targets(text) == {"implementer", "comment-analyzer"}


def test_step_6_coordinator_edits_claude_md_index_without_doc_accuracy() -> None:
    text = squash(_executor_outputs()["execution step 6"])
    assert "CLAUDE.md index entries: the coordinator edits them directly" in text
    assert "doc-accuracy" not in skill_targets(text)


@pytest.mark.parametrize("label", ["execution step 1", "execution step 6"])
def test_skill_runner_wording_is_the_same_everywhere(label: str) -> None:
    assert SKILL_RUNNER_PHRASE in squash(_executor_outputs()[label])


def test_step_1_names_the_runner_for_the_delegation_form_and_the_parallel_limit() -> None:
    assert squash(_executor_outputs()["execution step 1"]).count(SKILL_RUNNER_PHRASE) == 2


def test_docs_page_states_the_current_delegation_targets() -> None:
    text = PLANNER_DOCS_PAGE.read_text(encoding="utf-8")
    assert "comment-analyzer" in text
    assert "`technical-writing`" in text
    assert "`codebase-documenter`" in text
    assert find_removed_writer(text) == []


def test_executor_mode_line_lists_only_quality_reviewer_modes() -> None:
    text = _executor_outputs()["execution step 1"]
    assert "<mode>[For QR: plan-review|post-implementation|reconciliation]</mode>" in text


def test_temporal_contamination_doc_names_only_the_real_consumers() -> None:
    text = squash(
        (SRC_PLANNER / "resources" / "temporal-contamination.md").read_text(encoding="utf-8")
    )
    assert (
        "@agent-quality-reviewer embeds this specification, and planner review step 1 "
        "points @agent-comment-analyzer to it."
    ) in text
    assert "Both @agent-comment-analyzer and @agent-quality-reviewer reference" not in text


def test_comment_analyzer_does_not_embed_temporal_contamination() -> None:
    # The planner doc may say only that review step 1 points the agent at the file.
    assert "temporal" not in COMMENT_ANALYZER.read_text(encoding="utf-8").lower()


# Negative controls: each helper must catch the defect it guards against.


@pytest.mark.parametrize(
    "stale",
    [
        "Delegate to @agent-technical-writer with mode: `plan-annotation`",
        "Technical Writer sources ALL code comments",
        "After TW completes, invoke step 2",
        "<mode>plan-scrub</mode>",
        "<tw_delegation>",
    ],
)
def test_negative_control_removed_writer_is_detected(stale: str) -> None:
    assert find_removed_writer(stale)


@pytest.mark.parametrize(
    "current",
    [
        "load the technical-writing skill",
        "<skill>technical-writing</skill>",
        "@agent-comment-analyzer returns findings",
    ],
)
def test_negative_control_current_targets_are_not_flagged(current: str) -> None:
    assert find_removed_writer(current) == []


def test_negative_control_stale_docs_page_is_detected() -> None:
    stale = "Step 1 delegates to the technical-writer agent in `plan-annotation` mode."
    assert find_removed_writer(stale)


def test_negative_control_old_agent_is_reported_missing() -> None:
    assert missing_agents("DELEGATE to @agent-technical-writer") == {"technical-writer"}


def test_negative_control_invented_skill_is_reported_missing() -> None:
    assert missing_skills("<skill>no-such-skill</skill>") == {"no-such-skill"}
    assert missing_skills("load the technical-writing skill") == set()
