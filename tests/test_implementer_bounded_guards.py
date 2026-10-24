"""Implementer prompts must not stop on an authorized, bounded guard (issue #6881).

The implementer stopped twice before a caller-authorized exclusion guard.
It demanded a plan file when the brief carried acceptance criteria, and it
demanded security approval before a change that only narrows what runs.
These tests pin the corrected stop conditions in every rendered copy.
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARTIALS = PROJECT_ROOT / "templates/agents/partials"
PLAN_PARTIAL = PARTIALS / "implementer-blocking-read-project-documentation.mustache"
SECURITY_PARTIAL = PARTIALS / "implementer-code-quality-standards.mustache"
HANDOFF_PARTIAL = PARTIALS / "implementer-degraded-mode-protocol.mustache"
RENDERED_PATHS = (
    PROJECT_ROOT / "src/claude/agents/implementer.md",
    PROJECT_ROOT / ".claude/agents/implementer.md",
    PROJECT_ROOT / ".github/agents/implementer.agent.md",
    PROJECT_ROOT / "src/copilot-cli/agents/implementer.agent.md",
    PROJECT_ROOT / "src/cursor/agents/implementer.md",
    PROJECT_ROOT / "src/vs-code-agents/implementer.agent.md",
)
# Partials own the text; rendered copies must carry it. Each partial is checked
# for its own phrases below, and every rendered copy for all of them.
ALL_PATHS = (PLAN_PARTIAL, SECURITY_PARTIAL, HANDOFF_PARTIAL, *RENDERED_PATHS)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _rendered_id(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


@pytest.mark.parametrize("path", RENDERED_PATHS, ids=_rendered_id)
class TestRenderedPrompt:
    def test_brief_with_acceptance_criteria_counts_as_a_plan(self, path: Path) -> None:
        text = _text(path)

        assert "from the plan file or the caller's brief" in text
        assert "A brief that lists them counts as a plan." in text
        assert "A caller brief with acceptance criteria is a plan." in text

    def test_plan_block_fires_only_when_plan_and_brief_lack_criteria(self, path: Path) -> None:
        text = _text(path)

        assert "<plan file path or brief>` only when neither states any." in text
        assert "If the plan has no acceptance criteria, stop and return" not in text

    def test_brief_counts_in_every_plan_reference(self, path: Path) -> None:
        text = _text(path)

        assert "Read the plan from `.project-toolkit/planning/` or the caller's brief" in text
        assert "per approved plan or brief" in text
        assert "outside the plan or brief" in text
        assert "Read complete plans from `.project-toolkit/planning/`" not in text

    def test_restrictive_authorized_guard_is_implement_then_flag(self, path: Path) -> None:
        text = _text(path)

        assert "- **Implement, then flag.**" in text
        assert "A caller-authorized, bounded change that only narrows what runs" in text
        assert "Do not ask for security approval first." in text
        assert "Escalate only for a Stop condition above." in text

    def test_weakening_or_adding_a_mechanism_still_stops_for_review(self, path: Path) -> None:
        text = _text(path)

        assert "- **Stop before proceeding.**" in text
        assert "weaken, remove, or bypass a safeguard, widen a trust boundary" in text
        assert "handle credential values" in text
        assert "add a path-construction, command-construction, auth, or secret-handling" in text
        assert 'Return to orchestrator with "SECURITY_FLAG: [what, where, risk]"' in text
        assert "adds no new mechanism and alters no safeguard" in text
        assert "- **Implement, then flag.** Every other case." not in text

    def test_security_checks_stay_mandatory(self, path: Path) -> None:
        text = _text(path)

        assert "**Security pattern checks are NOT optional.**" in text
        assert "are mandatory checks. Run them before coding and before handoff." in text

    def test_unconditional_stop_wording_is_gone(self, path: Path) -> None:
        text = _text(path)

        assert "are mandatory blocking preconditions" not in text
        assert "When you touch sensitive surfaces, stop and flag." not in text
        assert "flag immediately:" not in text
        assert (
            'Return to orchestrator with "SECURITY_FLAG: [what, where, risk]" and let'
            " security agent review before proceeding.\n\nDo not"
        ) not in text

    def test_flagging_process_applies_only_when_not_stopped(self, path: Path) -> None:
        text = _text(path)

        assert "When ANY trigger matches and you did not stop:" in text

    def test_handoff_codes_match_the_stop_conditions(self, path: Path) -> None:
        text = _text(path)

        assert "No acceptance criteria in the plan or brief" in text
        assert "meets a Stop condition in Security Flagging" in text
        assert "A surface you only touch is flagged in a `[COMPLETE]` handoff." in text


@pytest.mark.parametrize(
    "path",
    [p for p in RENDERED_PATHS if "cursor" not in p.parts],
    ids=_rendered_id,
)
def test_argument_hint_accepts_inline_acceptance_criteria(path: Path) -> None:
    text = _text(path)

    assert "argument-hint: Specify the plan file path or acceptance criteria, and the task" in text
    assert "argument-hint: Specify the plan file path and task to implement" not in text


def test_partials_hold_the_text_that_rendered_copies_carry() -> None:
    assert "caller's brief" in _text(PLAN_PARTIAL)
    assert "- **Implement, then flag.**" in _text(SECURITY_PARTIAL)
    assert "`[COMPLETE]` handoff" in _text(HANDOFF_PARTIAL)
