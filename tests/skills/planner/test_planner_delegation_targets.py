"""Planner delegations must name an agent or skill that exists.

Issue #7421: planner told its caller to delegate to `@agent-technical-writer`,
which commit 782e492b1 removed, and to modes (`plan-scrub`, `plan-annotation`)
the removed agent never had. Every check here reads the planner scripts, the
template, and the hand-maintained references, so a regression in any of them
fails.

Planner also named three agents no template defines: `developer`, `debugger`
and `quality-reviewer`. They now map to `implementer`, `debug`, and `critic`
(plan review) or `code-reviewer` (reconciliation and post-implementation
review). No exemption remains: every `@agent-*` the planner names must exist.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import pytest

from tests.skills.planner_guidance import executor, flatten, planner

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_TEMPLATES = REPO_ROOT / "templates" / "agents"
SHIPPED_SKILLS = REPO_ROOT / "src" / "claude" / "skills"
PLANNER_ROOTS = (
    "src/claude/skills/planner",
    ".claude/skills/planner",
    "src/copilot-cli/skills/planner",
    "src/codex/skills/planner",
    "src/cursor/skills/planner",
    "src/muse/skills/planner",
)
PLANNER_TEMPLATE = REPO_ROOT / "templates" / "skills" / "planner.SKILL.md.tmpl"
PLANNER_DOCS_PAGE = REPO_ROOT / "docs" / "skills" / "planner.md"
COMMENT_ANALYZER = AGENT_TEMPLATES / "comment-analyzer.shared.md"
SRC_PLANNER = REPO_ROOT / "src" / "claude" / "skills" / "planner"
PLAN_FORMAT = SRC_PLANNER / "resources" / "plan-format.md"

# Agent names planner used before they were mapped to real agents, and the
# quality-reviewer abbreviation and sync targets that went with them.
RETIRED_AGENT_RE = re.compile(
    r"@agent-(?:developer|debugger|quality-reviewer)\b"
    r"|agents/(?:developer|quality-reviewer)\.md|\bQR\b|\bDeveloper\b|Quality Reviewer"
)
# A removed agent name, its abbreviation, and the modes it never had.
REMOVED_WRITER_RE = re.compile(
    r"technical[-_ ]?writer|\bTW\b|plan-scrub|plan-annotation|tw_delegation|delegate_tw",
    re.IGNORECASE,
)
# One wording for who runs a skill, used in every executor site that names one.
SKILL_RUNNER_PHRASE = (
    "the coordinator, or a general-purpose subagent it starts, loads the skill and follows it"
)
# A new README that must hold project content is scaffolded, then filled. Every
# site that states the docs split uses this wording (backticks stripped).
POPULATED_README_RE = re.compile(
    r"codebase-documenter scaffold, then (?:the )?technical-writing skill fills it"
)

AGENT_REF_RE = re.compile(r"@agent-([a-z][a-z0-9]*(?:-[a-z0-9]+)*)")
SKILL_TAG_RE = re.compile(r"<skill>([a-z][a-z0-9-]*)</skill>")
SKILL_PROSE_RE = re.compile(r"\b([a-z][a-z0-9]*(?:-[a-z0-9]+)+) skill\b")
LOAD_SKILL_RE = re.compile(r"\bload ([a-z][a-z0-9]*(?:-[a-z0-9]+)+)\b")


def _planner_outputs() -> dict[str, str]:
    outputs = {}
    for step in range(1, 8):
        outputs[f"planning step {step}"] = flatten(planner.get_planning_step_guidance(step, 6))
    for step in (1, 2, 3):
        outputs[f"review step {step}"] = flatten(planner.get_review_step_guidance(step, 2))
    return outputs


def _executor_outputs() -> dict[str, str]:
    plan = "plans/example.md"
    outputs = {}
    for step in range(1, 8):
        outputs[f"execution step {step}"] = flatten(executor.get_step_guidance(step, plan, "go"))
    outputs["execution step 1 reconciliation"] = flatten(
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


def discover_planner_roots() -> set[str]:
    """Every on-disk planner skill directory, as a repo-relative POSIX path.

    Covers `src/<plugin>/skills`, a pack nested one level deeper such as
    `src/hermes/<pack>/skills`, and the dogfood copy under `.claude/skills`.
    `.claude/skills/planner` is a symlink, so the check is `is_dir()`, which follows it.
    """
    candidates = [
        *REPO_ROOT.glob("src/*/skills/planner"),
        *REPO_ROOT.glob("src/*/*/skills/planner"),
        REPO_ROOT / ".claude" / "skills" / "planner",
    ]
    return {path.relative_to(REPO_ROOT).as_posix() for path in candidates if path.is_dir()}


def unconfigured_planner_roots(configured: Iterable[str]) -> set[str]:
    """On-disk planner trees that `configured` does not scan."""
    return discover_planner_roots() - set(configured)


CORPUS = _corpus()


@pytest.mark.parametrize("label", sorted(CORPUS))
def test_no_removed_technical_writer_reference(label: str) -> None:
    assert find_removed_writer(CORPUS[label]) == [], label


@pytest.mark.parametrize("label", sorted(CORPUS))
def test_every_named_agent_exists(label: str) -> None:
    unknown = missing_agents(CORPUS[label])
    assert not unknown, f"{label} names agents with no template: {sorted(unknown)}"


@pytest.mark.parametrize("label", sorted(CORPUS))
def test_no_retired_agent_name_remains(label: str) -> None:
    found = [m.group(0) for m in RETIRED_AGENT_RE.finditer(CORPUS[label])]
    assert found == [], label


@pytest.mark.parametrize("label", sorted(CORPUS))
def test_every_named_skill_exists(label: str) -> None:
    unknown = missing_skills(CORPUS[label])
    assert not unknown, f"{label} names skills that do not ship: {sorted(unknown)}"


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


def _plain(text: str) -> str:
    return squash(text.replace("`", ""))


@pytest.mark.parametrize(
    "label",
    ["execution step 1", "execution step 6", "plan-format.md", "docs page"],
)
def test_populated_new_readme_is_scaffolded_then_filled_by_technical_writing(label: str) -> None:
    sources = {
        "execution step 1": _executor_outputs()["execution step 1"],
        "execution step 6": _executor_outputs()["execution step 6"],
        "plan-format.md": PLAN_FORMAT.read_text(encoding="utf-8"),
        "docs page": PLANNER_DOCS_PAGE.read_text(encoding="utf-8"),
    }
    assert POPULATED_README_RE.search(_plain(sources[label])), label


def test_step_1_says_the_scaffold_alone_stops_at_placeholders() -> None:
    text = squash(_executor_outputs()["execution step 1"])
    assert "It stops at placeholders" in text
    assert "only when the scaffold is the deliverable" in text


def test_step_6_skip_does_not_apply_to_claude_md_skill_md_or_agent_prompts() -> None:
    text = squash(_executor_outputs()["execution step 6"])
    assert "none touched CLAUDE.md, SKILL.md, or agent prompts" in text
    assert "Do not skip when any milestone touched CLAUDE.md, SKILL.md, or agent prompts" in text
    assert "@agent-implementer edits SKILL.md and agent prompts" in text


def test_mixed_milestones_send_skill_md_and_agent_prompts_to_implementer() -> None:
    text = squash(_executor_outputs()["execution step 1"])
    assert (
        "SKILL.md files and agent prompts in a mixed milestone go to @agent-implementer, "
        "not a docs skill"
    ) in text
    assert "then the matching docs skill (docs pages) after code completes" in text


def test_step_1_split_gives_claude_md_to_the_coordinator() -> None:
    text = squash(_executor_outputs()["execution step 1"])
    assert (
        "CLAUDE.md index entries: out of scope for both skills; the coordinator edits them directly"
        in text
    )
    assert "The coordinator edits CLAUDE.md index entries in any milestone" in text


def test_temporal_contamination_doc_names_only_the_real_consumers() -> None:
    text = squash(
        (SRC_PLANNER / "resources" / "temporal-contamination.md").read_text(encoding="utf-8")
    )
    assert (
        "No agent embeds this specification. Planner review step 1 points "
        "@agent-comment-analyzer to it, and executor step 4 points @agent-code-reviewer to it."
    ) in text
    assert "Both @agent-comment-analyzer and @agent-quality-reviewer reference" not in text


def test_comment_analyzer_does_not_embed_temporal_contamination() -> None:
    # The planner doc may say only that review step 1 points the agent at the file.
    assert "temporal" not in COMMENT_ANALYZER.read_text(encoding="utf-8").lower()


# Converse guard: PLANNER_ROOTS is a configured set, so every on-disk planner tree
# must be in it, or a stale delegation in an unscanned mirror passes unseen.
def test_planner_roots_cover_every_planner_skill_on_disk() -> None:
    missing = unconfigured_planner_roots(PLANNER_ROOTS)
    assert not missing, f"PLANNER_ROOTS omits on-disk planner trees: {sorted(missing)}"


def test_every_configured_planner_root_is_a_directory() -> None:
    absent = [root for root in PLANNER_ROOTS if not (REPO_ROOT / root).is_dir()]
    assert not absent, f"PLANNER_ROOTS names missing directories: {absent}"


# Negative controls: each helper must catch the defect it guards against.
def test_negative_control_discovery_finds_every_known_planner_tree() -> None:
    assert {
        "src/claude/skills/planner",
        ".claude/skills/planner",
        "src/copilot-cli/skills/planner",
        "src/codex/skills/planner",
        "src/cursor/skills/planner",
        "src/muse/skills/planner",
    } <= discover_planner_roots()


def test_negative_control_a_dropped_root_is_reported() -> None:
    reduced = [root for root in PLANNER_ROOTS if root != "src/muse/skills/planner"]
    assert unconfigured_planner_roots(reduced) == {"src/muse/skills/planner"}


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
