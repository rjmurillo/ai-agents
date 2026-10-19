#!/usr/bin/env python3
"""
Regression tests for skillforge triage scoring (issue #6647).

Request scaffolding words ("create", "skill", "with") and substring matches
("test" inside "testing", "ci" inside "social") must not lift unrelated skills
over the 50 point CREATE_NEW boundary.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.skills.skillforge.triage_support import (
    BARE_QUERY,
    CREATE_QUERY,
    make_skill,
    run_triage,
    triage,
)


@pytest.fixture
def index() -> dict[str, Any]:
    """A small index shaped like a real one, with no social media skill."""
    return {
        "skills": [
            make_skill(
                "skill-creator",
                "Create new skills, improve existing skills, and run evals to test a skill.",
                keywords=["skill-creator", "skill", "creator", "create", "with", "test", "evals"],
                domains=["testing", "meta", "document"],
            ),
            make_skill(
                "skillify",
                "Turn a completed workflow into a reusable skill with a test plan.",
                keywords=["skillify", "skill", "create", "with", "workflow"],
                domains=["testing", "meta"],
            ),
            make_skill(
                "webapp-testing",
                "Toolkit for testing local web applications using Playwright.",
                keywords=["webapp-testing", "webapp", "testing", "playwright", "browser"],
                domains=["testing", "frontend"],
            ),
            make_skill(
                "xlsx",
                "Edit and create xlsx spreadsheet files, including formulas and charts.",
                keywords=["xlsx", "spreadsheet", "excel", "formulas"],
                domains=["spreadsheet"],
            ),
        ]
    }


@pytest.fixture(autouse=True)
def _fixture_index(monkeypatch: pytest.MonkeyPatch, index: dict[str, Any]) -> None:
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)


# ---------------------------------------------------------------------------
# Positive: the two repros from the issue
# ---------------------------------------------------------------------------


def test_creation_request_with_no_matching_skill_routes_to_create_new() -> None:
    data = run_triage(CREATE_QUERY)

    assert data["action"] == triage.Action.CREATE_NEW
    assert data["details"]["top_score"] < 50


def test_bare_noun_phrase_has_no_match_at_or_above_the_improve_boundary() -> None:
    data = run_triage(BARE_QUERY)

    assert data["details"]["top_score"] < 50
    assert data["action"] == triage.Action.CREATE_NEW


def test_scaffolding_words_are_not_reported_as_match_reasons() -> None:
    data = run_triage(CREATE_QUERY)

    reasons = " ".join(r for m in data["top_matches"] for r in m["reasons"])
    assert "partial name: skill" not in reasons
    assert "keywords: skill" not in reasons
    assert "create" not in reasons


# ---------------------------------------------------------------------------
# Negative: real matches must survive the fix
# ---------------------------------------------------------------------------


def test_spreadsheet_request_still_uses_existing_skill() -> None:
    data = run_triage("edit an xlsx spreadsheet")

    assert data["action"] == triage.Action.USE_EXISTING
    assert data["top_matches"][0]["name"] == "xlsx"


def test_web_app_testing_request_still_matches_the_testing_skill() -> None:
    data = run_triage("playwright web app testing")

    assert data["top_matches"][0]["name"] == "webapp-testing"
    assert data["details"]["top_score"] >= 50


def test_explicit_improve_request_still_targets_the_named_skill() -> None:
    data = run_triage("improve the skillify skill")

    assert data["action"] == triage.Action.IMPROVE_EXISTING
    assert data["details"]["target_skill"] == "skillify"


def test_creation_request_for_an_existing_domain_still_warns_about_duplicates() -> None:
    data = run_triage("create a skill for editing xlsx spreadsheet files")

    assert data["action"] == triage.Action.CLARIFY
    assert data["top_matches"][0]["name"] == "xlsx"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_scaffolding_only_query_creates_new() -> None:
    data = run_triage("create a skill")

    assert data["action"] == triage.Action.CREATE_NEW
    assert data["details"]["top_score"] == 0


def test_empty_query_does_not_crash_and_matches_nothing() -> None:
    data = run_triage("")

    assert data["details"]["top_score"] == 0
    assert data["action"] == triage.Action.CLARIFY


def test_single_content_word_is_fully_covered() -> None:
    skill = make_skill("webapp-testing", "Toolkit for testing web applications.")

    assert triage.calculate_coverage(["testing"], skill) == 1.0


def test_one_shared_term_in_a_long_query_scores_low() -> None:
    skill = make_skill("webapp-testing", "Toolkit for testing web applications.", ["testing"])
    full, _ = triage.calculate_match_score("testing", skill)
    diluted, reasons = triage.calculate_match_score(BARE_QUERY, skill)

    assert diluted < full
    assert any(r.startswith("coverage:") for r in reasons)


def test_unanchored_result_is_unchanged_when_every_term_is_covered() -> None:
    skill = make_skill("webapp-testing", "Toolkit for testing web applications.", ["testing"])
    _, reasons = triage.calculate_match_score("testing", skill)

    assert not any(r.startswith("coverage:") for r in reasons)


# ---------------------------------------------------------------------------
# Tokenizer, boundary matching, and domain detection
# ---------------------------------------------------------------------------


def test_tokenize_for_scoring_drops_scaffolding_and_dedupes() -> None:
    tokens = triage.tokenize_for_scoring("Create a skill for the testing, testing and e2e loop")

    assert tokens == ["testing", "e2e", "loop"]


def test_tokenize_for_scoring_splits_hyphenated_terms() -> None:
    assert triage.tokenize_for_scoring("time-slot rotation") == ["time", "slot", "rotation"]


def test_tokenize_for_scoring_of_empty_input_is_empty() -> None:
    assert triage.tokenize_for_scoring("") == []
    assert triage.tokenize_for_scoring("   !!! ") == []


@pytest.mark.parametrize(
    ("text", "term", "expected"),
    [
        ("run the tests", "test", True),
        ("testing loop", "test", True),
        ("tested", "test", True),
        ("attest the claim", "test", False),
        ("testimony", "test", False),
        ("social media", "ci", False),
        ("set up ci pipeline", "ci", True),
        ("stack trace", "stack trace", True),
        ("c++ (cpp)", "c++", True),
        ("debugging a flaky failure", "debug", True),
        ("shipped it", "ship", True),
        ("shipping soon", "ship", True),
        ("debugger", "debug", False),
        ("shippers", "ship", False),
        ("", "debug", False),
    ],
)
def test_contains_term_respects_word_boundaries(text: str, term: str, expected: bool) -> None:
    assert triage.contains_term(text, term) is expected


def test_detect_query_domains_ignores_terms_inside_other_words() -> None:
    names = [d for d, _ in triage.detect_query_domains("attest the social media campaign")]

    assert "testing" not in names
    assert "deployment" not in names


def test_detect_query_domains_matches_inflected_forms() -> None:
    names = [d for d, _ in triage.detect_query_domains("social media hook testing loop")]

    assert "testing" in names


@pytest.mark.parametrize(
    ("a", "b"),
    [("testing", "test"), ("tests", "test"), ("files", "file"), ("processes", "process")],
)
def test_stems_link_inflected_forms(a: str, b: str) -> None:
    assert triage.stem_forms(a) & triage.stem_forms(b)


def test_stems_keep_short_words_intact() -> None:
    assert triage.stem_forms("is") == {"is"}
    assert "ne" not in triage.stem_forms("need")


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------


def test_missing_index_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(triage, "load_skill_index", lambda: None)

    result = triage.triage_request(CREATE_QUERY)

    assert not result.success
    assert "index" in result.message.lower()
