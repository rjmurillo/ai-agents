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

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = REPO_ROOT / "src" / "claude" / "skills" / "autoplan" / "references"
LOADING_HEADING = "## Reference Loading"
PATH_FORM = "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/autoplan/references/"
UNRESOLVED_RULE = "apply the rules in this file and state that the reference was unavailable"

ORCHESTRATOR_PATHS = (
    Path("templates/agents/orchestrator.shared.md"),
    Path("src/claude/agents/orchestrator.md"),
    Path(".claude/agents/orchestrator.md"),
    Path(".github/agents/orchestrator.agent.md"),
    Path("src/copilot-cli/agents/orchestrator.agent.md"),
    Path("src/vs-code-agents/orchestrator.agent.md"),
)

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


def _text(path: Path) -> str:
    return " ".join((REPO_ROOT / path).read_text(encoding="utf-8").split())


def _loading_section(path: Path) -> str:
    text = _text(path)
    assert text.count(LOADING_HEADING) == 1, f"{path} must carry {LOADING_HEADING!r} once"
    rest = text[text.index(LOADING_HEADING) + len(LOADING_HEADING) :]
    boundary = rest.find(" ## ")
    return rest if boundary == -1 else rest[:boundary]


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_reference_loading_names_every_reference_with_a_condition(path: Path) -> None:
    section = _loading_section(path)

    assert PATH_FORM in section, f"{path} Reference Loading lacks the plugin-root path form"
    for name, (_, condition) in REFERENCES.items():
        assert name in section, f"{path} Reference Loading does not list {name}"
        assert condition in section, f"{path} has no load condition {condition!r} for {name}"


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_harness_without_a_skill_tree_has_a_fallback_rule(path: Path) -> None:
    assert UNRESOLVED_RULE in _loading_section(path), f"{path} has no unresolved-path rule"


@pytest.mark.parametrize("name", sorted(REFERENCES))
def test_reference_exists_and_is_not_empty(name: str) -> None:
    ref = REFERENCE_DIR / name

    assert ref.is_file(), f"missing reference {ref}"
    assert len(ref.read_text(encoding="utf-8").split()) > 40, f"{name} is a stub, not a reference"


@pytest.mark.parametrize("name", sorted(REFERENCES))
@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_body_keeps_the_stub_heading_that_points_at_its_reference(path: Path, name: str) -> None:
    heading, _ = REFERENCES[name]
    text = _text(path)

    assert heading in text, f"{path} lost {heading!r}"
    assert name in text[text.index(heading) :], f"{path} stub for {heading!r} never names {name}"


def test_drift_stub_points_at_the_same_reference() -> None:
    for path in ORCHESTRATOR_PATHS:
        text = _text(path)
        stub = text[text.index("### 7-Step Recovery") :]
        assert "orchestrator-resume-and-drift.md" in stub, f"{path} drift stub lost its pointer"


def test_negative_control_unrelated_file_has_no_reference_loading() -> None:
    assert LOADING_HEADING not in (REPO_ROOT / "README.md").read_text(encoding="utf-8")
