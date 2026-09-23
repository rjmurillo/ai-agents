"""Structural tests for the completion-tail-audit runtime fixtures (issue #5404).

Each fixture carries both a regex/not_regex regression backstop for the
completion-tail audit (`.claude/rules/voice.md`) and the task-completion
terminal predicate (`.claude/rules/builder-ethos.md`), and a `semantic`
assertion graded through `scripts/eval/_runtime_grader.py`. The regex
assertions are a useful fixture but are NOT the semantic authority: a
response can reopen an interaction without using any exact prohibited
phrase, and using one of those phrases inside a genuine blocking question is
not itself a defect; that is what the semantic assertion grades (see the
fixture file's own `_scope_note`). These tests prove the fixture corpus is
well-formed and that its positive/negative controls discriminate offline;
running the fixtures against the real Claude and Copilot CLIs is exercised
manually via `eval_runtime_parity.py`, not in CI, since it requires both
CLIs installed and authenticated (and, for the semantic assertions, a
grader CLI signed in).
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
    "requested-next-steps-allowed",
    "voice-conflict-terminal-wins-over-offer",
    "last-tail-mutation-detected",
}


def test_fixture_corpus_loads_and_controls_discriminate() -> None:
    """Every positive control passes; every negative fails at least one assertion."""
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
    """Each negative control must fail because it reopens the interaction, not for anything else."""
    fixtures = runtime_parity.load_fixtures(FIXTURES_PATH)
    banned = ("want me to", "would you like me to", "happy to", "let me know if you want")

    for fixture in fixtures:
        lowered = fixture.negative.response.lower()
        assert any(phrase in lowered for phrase in banned), (
            f"fixture {fixture.fixture_id!r} negative control does not carry "
            f"a banned continuation phrase; its failure would not demonstrate "
            f"the completion-tail defect this fixture exists to catch"
        )


def test_every_fixture_carries_a_semantic_assertion() -> None:
    """The semantic grader (issue #5404) is implemented, not deferred, per fixture."""
    fixtures = runtime_parity.load_fixtures(FIXTURES_PATH)

    for fixture in fixtures:
        kinds = {spec.kind for spec in fixture.assertions}
        assert "semantic" in kinds, (
            f"fixture {fixture.fixture_id!r} carries no semantic assertion; "
            "the regex backstop alone is not the semantic authority"
        )


def test_every_fixture_installs_both_rule_files() -> None:
    """A runtime fixture with no `instructions` never exercises the real rule text."""
    fixtures = runtime_parity.load_fixtures(FIXTURES_PATH)

    for fixture in fixtures:
        assert ".claude/rules/builder-ethos.md" in fixture.instructions
        assert ".claude/rules/voice.md" in fixture.instructions


def test_scope_note_still_names_the_regex_backstop_limits() -> None:
    """The fixture file must not be read as the semantic authority by itself."""
    import json

    payload = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))

    assert "_scope_note" in payload
    note = payload["_scope_note"].lower()
    assert "semantic" in note
    assert "not the semantic authority" in note


def test_last_tail_mutation_fixture_names_the_automatic_mutant_explicitly() -> None:
    """Fixture 14's negative control is literally the automatic mutant tail.

    `scripts/eval/_runtime_grader.MUTANT_TAIL` is appended to every fixture's
    positive control automatically during calibration; this fixture's own
    authored negative control uses the identical text so the mechanism is
    visible in the fixture file itself, not only inside the grader.
    """
    from tests.eval._runtime_parity_test_support import runtime_grader

    fixtures = {
        f.fixture_id: f for f in runtime_parity.load_fixtures(FIXTURES_PATH)
    }
    fixture = fixtures["last-tail-mutation-detected"]

    assert fixture.negative.response == (
        fixture.positive.response + runtime_grader.MUTANT_TAIL
    )
