"""Static guards for the orchestrator reference split.

The orchestrator body moved five references from six blocks into ``autoplan`` skill references and
kept a working rule for each. These tests pin three things for every surface:

1. ``Reference Loading`` exists once and names each reference with a load
   condition.
2. Each reference exists in the canonical skill directory and opens with the
   title the stub expects.
3. A harness with no skill tree (the VS Code agent list) is told what to do
   when the path does not resolve.

The per-contract strings for the Analyst handoff, Resume Check, and Hook
Feedback live in their own test modules.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.agent_reference_helpers import (
    REPO_ROOT,
    read_reference_text,
    reference_loading_section,
)

REFERENCE_DIR = REPO_ROOT / "src" / "claude" / "skills" / "autoplan" / "references"
LOADING_HEADING = "## Reference Loading"
SHARED_PATH_FORM = (
    "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/autoplan/references/"
)
CLAUDE_PATH_FORM = "${CLAUDE_PLUGIN_ROOT}/skills/autoplan/references/"
COPILOT_PATH_FORM = "${COPILOT_PLUGIN_ROOT}/skills/autoplan/references/"
UNRESOLVED_RULE = "apply the rules in this file and state that the reference was unavailable"

ORCHESTRATOR_PATHS = (
    "templates/agents/orchestrator.shared.md",
    "src/claude/agents/orchestrator.md",
    ".claude/agents/orchestrator.md",
    ".github/agents/orchestrator.agent.md",
    "src/copilot-cli/agents/orchestrator.agent.md",
    "src/vs-code-agents/orchestrator.agent.md",
)


def _expected_path_form(path: str) -> str:
    """Claude Code and Cursor get the bare Claude root, Copilot CLI its own, the rest both."""
    parts = Path(path).parts
    if parts[:2] in {(".claude", "agents"), ("src", "claude"), ("src", "cursor")}:
        return CLAUDE_PATH_FORM
    if ".github" in parts or "copilot-cli" in parts:
        return COPILOT_PATH_FORM
    return SHARED_PATH_FORM


# reference file -> (stub heading in the body, load condition phrase in Reference Loading)
REFERENCES = {
    "orchestrator-analyst-handoff.md": (
        "### Analyst evidence handoff",
        "delegate an investigation",
    ),
    "orchestrator-anti-patterns.md": ("## Anti-Patterns", "review a routing plan"),
    "orchestrator-resume-and-drift.md": ("### Resume Check (fail closed)", "resume from a handoff"),
    "orchestrator-hook-feedback.md": ("## Hook Feedback", "a hook blocks a tool"),
    "orchestrator-routing-evidence.md": (
        "## Model, Effort, and Cost Routing",
        "nominate a cheaper tier",
    ),
}


def _loading_section(path: str) -> str:
    return reference_loading_section(read_reference_text(path), path, LOADING_HEADING)


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_reference_loading_names_every_reference_with_a_condition(path: str) -> None:
    section = _loading_section(path)
    expected_form = _expected_path_form(path)

    assert expected_form in section, f"{path} Reference Loading lacks {expected_form!r}"
    for name, (_, condition) in REFERENCES.items():
        assert name in section, f"{path} Reference Loading does not list {name}"
        assert condition in section, f"{path} has no load condition {condition!r} for {name}"


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_harness_without_a_skill_tree_has_a_fallback_rule(path: str) -> None:
    assert UNRESOLVED_RULE in _loading_section(path), f"{path} has no unresolved-path rule"


@pytest.mark.parametrize("name", sorted(REFERENCES))
def test_reference_exists_and_is_not_empty(name: str) -> None:
    ref = REFERENCE_DIR / name

    assert ref.is_file(), f"missing reference {ref}"
    assert len(ref.read_text(encoding="utf-8").split()) > 40, f"{name} is a stub, not a reference"


@pytest.mark.parametrize("name", sorted(REFERENCES))
@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_body_keeps_the_stub_heading_that_points_at_its_reference(path: str, name: str) -> None:
    heading, _ = REFERENCES[name]
    text = read_reference_text(path)

    assert heading in text, f"{path} lost {heading!r}"
    assert name in text[text.index(heading) :], f"{path} stub for {heading!r} never names {name}"


def test_drift_stub_points_at_the_same_reference() -> None:
    for path in ORCHESTRATOR_PATHS:
        text = read_reference_text(path)
        stub = text[text.index("### 7-Step Recovery") :]
        assert "orchestrator-resume-and-drift.md" in stub, f"{path} drift stub lost its pointer"


def test_negative_control_unrelated_file_has_no_reference_loading() -> None:
    assert LOADING_HEADING not in (REPO_ROOT / "README.md").read_text(encoding="utf-8")
