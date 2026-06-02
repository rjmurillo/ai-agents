"""Regression tests for the front-gate cross-link contract from issue #1927."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

RESEARCH_SOURCE = REPO_ROOT / ".claude" / "skills" / "research-and-incorporate" / "SKILL.md"
RESEARCH_MIRROR = (
    REPO_ROOT / "src" / "copilot-cli" / "skills" / "research-and-incorporate" / "SKILL.md"
)
PLAN_SOURCE = REPO_ROOT / ".claude" / "commands" / "plan.md"
PLAN_MIRROR = REPO_ROOT / "src" / "copilot-cli" / "skills" / "plan" / "SKILL.md"
AVOIDING_SOURCE = REPO_ROOT / ".claude" / "skills" / "avoiding-manufactured-work" / "SKILL.md"
AVOIDING_MIRROR = (
    REPO_ROOT / "src" / "copilot-cli" / "skills" / "avoiding-manufactured-work" / "SKILL.md"
)

ALL_FILES = [
    RESEARCH_SOURCE,
    RESEARCH_MIRROR,
    PLAN_SOURCE,
    PLAN_MIRROR,
    AVOIDING_SOURCE,
    AVOIDING_MIRROR,
]

EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)


def _read(path: Path) -> str:
    assert path.is_file(), f"expected file to exist: {path}"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", [RESEARCH_SOURCE, RESEARCH_MIRROR])
def test_research_has_frontgate_callout(path: Path) -> None:
    text = _read(path)
    assert "## Front-gate first" in text, f"missing Front-gate heading in {path}"


@pytest.mark.parametrize("path", [RESEARCH_SOURCE, RESEARCH_MIRROR])
def test_research_callout_halts_on_aspirational_demand(path: Path) -> None:
    text = _read(path).lower()
    assert "front-gate-before-pipeline" in text, f"missing pattern reference in {path}"
    assert "aspirational" in text, f"missing aspirational halt language in {path}"
    assert "halt" in text, f"missing halt directive in {path}"


@pytest.mark.parametrize("path", [RESEARCH_SOURCE, RESEARCH_MIRROR])
def test_research_callout_routes_to_spec(path: Path) -> None:
    text = _read(path)
    assert "/spec" in text, f"front-gate callout must route to /spec in {path}"


def test_research_callout_precedes_phase_one() -> None:
    text = _read(RESEARCH_SOURCE)
    callout = text.index("## Front-gate first")
    phase_one = text.index("Phase 1")
    assert callout < phase_one, "Front-gate callout must appear before Phase 1 content"


@pytest.mark.parametrize("path", [PLAN_SOURCE, PLAN_MIRROR])
def test_plan_has_frontgate_guard(path: Path) -> None:
    text = _read(path)
    assert "run the front-gate first" in text, f"missing front-gate guard heading in {path}"


@pytest.mark.parametrize("path", [PLAN_SOURCE, PLAN_MIRROR])
def test_plan_guard_routes_to_spec(path: Path) -> None:
    text = _read(path)
    assert "/spec" in text, f"plan front-gate guard must route to /spec in {path}"
    assert "front-gate-before-pipeline" in text, f"missing pattern reference in {path}"


def test_plan_guard_precedes_process_section() -> None:
    text = _read(PLAN_SOURCE)
    guard = text.index("run the front-gate first")
    process = text.index("## Process")
    assert guard < process, "front-gate guard must appear before the Process section"


@pytest.mark.parametrize("path", [AVOIDING_SOURCE, AVOIDING_MIRROR])
def test_avoiding_manufactured_work_has_sibling_callout(path: Path) -> None:
    text = _read(path)
    assert "## Sibling skill" in text, f"missing Sibling skill heading in {path}"
    assert "front-gate-before-pipeline" in text, f"missing sibling skill reference in {path}"
    assert "Front-gate fires before work begins" in text, f"missing timing start in {path}"
    assert "this skill fires after work appears done" in text, f"missing timing mirror in {path}"
    assert "Same root cause" in text, f"missing shared root cause in {path}"
    assert "opposite timing" in text, f"missing opposite timing in {path}"


def test_avoiding_callout_precedes_workflow() -> None:
    text = _read(AVOIDING_SOURCE)
    callout = text.index("## Sibling skill")
    workflow = text.index("## Workflow")
    assert callout < workflow, "Sibling skill callout must appear before the Workflow section"


def test_research_source_and_mirror_agree() -> None:
    assert _read(RESEARCH_SOURCE) == _read(RESEARCH_MIRROR), (
        "research-and-incorporate source and Copilot mirror diverged; rerun "
        "build/scripts/build_all.py"
    )


def test_avoiding_source_and_mirror_agree() -> None:
    assert _read(AVOIDING_SOURCE) == _read(AVOIDING_MIRROR), (
        "avoiding-manufactured-work source and Copilot mirror diverged; rerun "
        "build/scripts/build_all.py"
    )


def test_plan_source_and_mirror_agree() -> None:
    source_parts = _read(PLAN_SOURCE).split("@CLAUDE.md", 1)
    mirror_parts = _read(PLAN_MIRROR).split("@CLAUDE.md", 1)
    assert len(source_parts) == 2, "missing @CLAUDE.md marker in plan source"
    assert len(mirror_parts) == 2, "missing @CLAUDE.md marker in plan mirror"
    assert source_parts[1] == mirror_parts[1], (
        "plan source and Copilot mirror bodies diverged; rerun "
        "build/scripts/build_all.py"
    )


@pytest.mark.parametrize("path", ALL_FILES)
def test_no_prohibited_dashes(path: Path) -> None:
    text = _read(path)
    assert EM_DASH not in text, f"em-dash found in {path}"
    assert EN_DASH not in text, f"en-dash found in {path}"
