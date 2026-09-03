"""Structural tests for the completion-tail-audit runtime fixtures (issue #5404).

These fixtures are a regex-based regression backstop for the completion-tail
audit (`.claude/rules/voice.md`) and the task-completion terminal predicate
(`.claude/rules/builder-ethos.md`). They are not the semantic authority: a
model-graded assertion kind that judges whether a response reopens an
interaction is not implemented here or in `scripts/eval/_runtime_parity.py`
today (see the fixture file's own `_scope_note`). These tests prove the
fixture corpus is well-formed and that its positive/negative controls
discriminate offline; running the fixtures against the real Claude and
Copilot CLIs is exercised manually via `eval_runtime_parity.py`, not in CI,
since it requires both CLIs installed and authenticated.
"""

from __future__ import annotations

from pathlib import Path

from tests.eval._runtime_parity_test_support import runtime_parity

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_PATH = REPO_ROOT / "tests" / "evals" / "completion-terminal-runtime-fixtures.json"

EXPECTED_FIXTURE_IDS = {
    "completion-no-continuation-offer",
    "optional-finding-declarative-not-solicited",
    "blocking-decision-question-allowed",
}


def test_fixture_corpus_loads_and_controls_discriminate() -> None:
    """load_fixtures validates every positive control passes and every negative fails at least one assertion."""
    fixtures = runtime_parity.load_fixtures(FIXTURES_PATH)

    assert {f.fixture_id for f in fixtures} == EXPECTED_FIXTURE_IDS


def test_positive_controls_carry_no_banned_continuation_phrase() -> None:
    """The clean, terminal response in each positive control must not itself need a fix."""
    fixtures = runtime_parity.load_fixtures(FIXTURES_PATH)
    banned = ("want me to", "would you like me to", "happy to", "let me know if you want")

    for fixture in fixtures:
        lowered = fixture.positive.response.lower()
        for phrase in banned:
            assert phrase not in lowered, (
                f"fixture {fixture.fixture_id!r} positive control contains "
                f"{phrase!r}, which defeats its purpose as the clean example"
            )


def test_negative_controls_are_the_documented_defect() -> None:
    """Each negative control must fail because it reopens the interaction, not for an unrelated reason."""
    fixtures = runtime_parity.load_fixtures(FIXTURES_PATH)
    banned = ("want me to", "would you like me to", "happy to", "let me know if you want")

    for fixture in fixtures:
        lowered = fixture.negative.response.lower()
        assert any(phrase in lowered for phrase in banned), (
            f"fixture {fixture.fixture_id!r} negative control does not carry "
            f"a banned continuation phrase; its failure would not demonstrate "
            f"the completion-tail defect this fixture exists to catch"
        )


def test_scope_note_names_the_deferred_semantic_grader() -> None:
    """The fixture file must not be read as the semantic authority the issue also asks for."""
    import json

    payload = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))

    assert "_scope_note" in payload
    assert "semantic" in payload["_scope_note"].lower()
    assert "deferred" in payload["_scope_note"].lower()
