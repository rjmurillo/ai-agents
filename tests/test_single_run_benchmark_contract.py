"""Contract tests for the single-run clause in benchmark-models Step 4 (issue #5410 fixture 9).

Every rendered benchmark-models skill must carry the clause, the skill must not order a
best-overall call beside it, and the underpowered-eval fixture must discriminate.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests.eval._runtime_parity_test_support import runtime_parity
from tests.structural_recurrence_support import REPO_ROOT, flat, missing

BENCHMARK_SURFACES = (
    Path("templates/skills/benchmark-models.SKILL.md.tmpl"),
    Path(".claude/skills/benchmark-models/SKILL.md"),
    Path("src/claude/skills/benchmark-models/SKILL.md"),
    Path("src/codex/skills/benchmark-models/SKILL.md"),
    Path("src/copilot-cli/skills/benchmark-models/SKILL.md"),
    Path("src/cursor/skills/benchmark-models/SKILL.md"),
    Path("src/hermes/project-toolkit-delivery/skills/benchmark-models/SKILL.md"),
)

BENCHMARK_CLAUSES: dict[str, str] = {
    "single-run-inconclusive": "One run per provider is inconclusive, not a preference",
    "report-n": "report n",
    "interval-or-margin": "an interval or margin (or say none can be estimated at n=1)",
    "no-winner-from-direction": "call no winner from a directional delta",
    "rerun-to-confirm": "rerun to confirm",
}

UNDERPOWERED_FIXTURES_PATH = (
    REPO_ROOT / "tests" / "evals" / "underpowered-eval-runtime-fixtures.json"
)


# --- benchmark-models Step 4 single-run clause (fixture 9) -----------------


@pytest.mark.parametrize("path", BENCHMARK_SURFACES, ids=str)
def test_benchmark_surface_carries_every_single_run_clause(path: Path) -> None:
    assert missing(flat(path), BENCHMARK_CLAUSES) == []


@pytest.mark.parametrize("clause_id", sorted(BENCHMARK_CLAUSES))
def test_removing_a_benchmark_clause_is_detected(clause_id: str) -> None:
    """Negative control: the checker fails once the clause is gone."""
    source = flat(BENCHMARK_SURFACES[0])
    mutated = source.replace(" ".join(BENCHMARK_CLAUSES[clause_id].split()), "")
    assert missing(mutated, BENCHMARK_CLAUSES) == [clause_id]


BEST_MODEL_PROMISES = ("best-overall call", "actually best for this skill")


def promises_a_best_model(text: str) -> list[str]:
    """Return the removed best-model phrases still present in ``text``."""
    flat = " ".join(text.lower().split())
    return [phrase for phrase in BEST_MODEL_PROMISES if phrase in flat]


@pytest.mark.parametrize("path", BENCHMARK_SURFACES, ids=str)
def test_benchmark_surface_has_no_best_overall_instruction(path: Path) -> None:
    """Step 4 must not order a best-overall call beside the no-winner clause.

    model_benchmark.py has no repeat flag, so every invocation is one run per
    provider and the single-run clause always applies. The description and
    the Step 4 text must also stop promising a "best" model from that run.
    """
    assert promises_a_best_model(flat(path)) == []


def test_benchmark_script_docstring_does_not_promise_a_best_model() -> None:
    script = REPO_ROOT / ".claude/skills/benchmark-models/scripts/model_benchmark.py"
    assert promises_a_best_model(script.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("phrase", BEST_MODEL_PROMISES)
def test_best_model_check_detects_each_reintroduced_phrase(phrase: str) -> None:
    """Negative control: the check fires when a removed phrase returns."""
    mutated = flat(BENCHMARK_SURFACES[0]) + " " + phrase.upper()
    assert promises_a_best_model(mutated) == [phrase]


def _underpowered_fixture() -> Any:
    fixtures = runtime_parity.load_fixtures(UNDERPOWERED_FIXTURES_PATH)
    assert [f.fixture_id for f in fixtures] == ["single-run-benchmark-names-no-winner"]
    return fixtures[0]


def test_underpowered_fixture_quotes_the_shipped_step_4_sentence() -> None:
    """The harness installs no skills, so the prompt carries the clause.

    The quote must stay a substring of every rendered skill, or the fixture
    grades a sentence the skill no longer says.
    """
    prompt = " ".join(_underpowered_fixture().prompt.split())
    quoted = prompt.split("Step 4 of the skill says: '", 1)[1].split("' Write", 1)[0]
    assert quoted.startswith("One run per provider is inconclusive")
    for path in BENCHMARK_SURFACES:
        assert quoted in flat(path), path


RESEARCH_METHODOLOGY_TEMPLATE = Path(
    "templates/skills/ai-agents-research-methodology.SKILL.md.tmpl"
)


def test_both_model_preference_owners_require_an_interval_or_margin() -> None:
    """Research-methodology step 4 and benchmark-models Step 4 must not disagree."""
    for path in (RESEARCH_METHODOLOGY_TEMPLATE, BENCHMARK_SURFACES[0]):
        assert "interval or margin" in flat(path), path


def _required_regexes() -> list[re.Pattern[str]]:
    return [
        re.compile(spec.pattern)
        for spec in _underpowered_fixture().assertions
        if spec.kind == "regex"
    ]


def test_underpowered_fixture_requires_an_interval_or_a_stated_absence() -> None:
    """A reply that grades n=1 but never mentions an interval or margin fails."""
    fixture = _underpowered_fixture()
    required = _required_regexes()
    assert all(p.search(fixture.positive.response) for p in required)
    no_interval = (
        "Fastest: gpt at 6.9s. Cheapest: gemini at $0.018. n=1 per provider, so the "
        "comparison is inconclusive. Rerun to confirm."
    )
    assert not all(p.search(no_interval) for p in required)


def test_underpowered_fixture_has_a_semantic_assertion_and_a_scope_note() -> None:
    fixture = _underpowered_fixture()
    assert "semantic" in {spec.kind for spec in fixture.assertions}
    note = json.loads(UNDERPOWERED_FIXTURES_PATH.read_text(encoding="utf-8"))["_scope_note"]
    assert "does not test that the skill loads" in note
    assert "NOT the semantic authority" in note


def _winner_pattern() -> re.Pattern[str]:
    patterns = [
        spec.pattern for spec in _underpowered_fixture().assertions if spec.kind == "not_regex"
    ]
    assert len(patterns) == 1
    return re.compile(patterns[0])


def test_underpowered_negative_control_names_a_winner_and_positive_does_not() -> None:
    """Negative control: a reply that crowns a winner from one run is rejected."""
    fixture = _underpowered_fixture()
    winner = _winner_pattern()
    assert winner.search(fixture.negative.response)
    assert not winner.search(fixture.positive.response)
    assert "inconclusive" in fixture.positive.response
    assert "inconclusive" not in fixture.negative.response


@pytest.mark.parametrize(
    "reply",
    [
        "GPT is the best overall on this run.",
        "Best overall: Claude, given the judge score.",
        "Winner: Gemini.",
        "I would pick Gemini.",
    ],
)
def test_winner_pattern_rejects_single_run_winner_claims(reply: str) -> None:
    assert _winner_pattern().search(reply), reply


@pytest.mark.parametrize(
    "reply",
    [
        "n=1 per provider, so the result is inconclusive. No winner can be called.",
        "Step 4 applies: inconclusive. No winner is called.",
        'This does not support "gpt is best" or "gemini is the cheapest good option."',
        "We never call a winner from one run.",
        "Fastest: gpt at 6.9s. Cheapest: gemini at $0.018. Rerun to confirm.",
        "",
    ],
)
def test_winner_pattern_allows_the_per_metric_summary_and_no_winner(reply: str) -> None:
    assert not _winner_pattern().search(reply), reply


def test_winner_pattern_still_rejects_a_bare_winner_after_a_negation_elsewhere() -> None:
    """Negation guards are local: 'No winner is called' must not excuse a later pick."""
    assert _winner_pattern().search("No winner is called yet. The winner is gpt.")
