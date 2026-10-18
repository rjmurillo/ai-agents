#!/usr/bin/env python3
"""
Review round 4 regression tests for skillforge triage scoring (issue #6647).

Covers the single-term ceiling under context boosts, the exact-name exemption,
name lookups for scaffolding-named skills, and the scaffolding word list.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.skills.skillforge.triage_support import make_skill, triage

# ---------------------------------------------------------------------------
# The ceiling holds when the pre-boost score is already below it
# ---------------------------------------------------------------------------


def _documenter() -> dict[str, Any]:
    return make_skill(
        "codebase-documenter",
        "Generate documentation for a codebase.",
        keywords=["documentation"],
        domains=["documentation"],
    )


def test_ceiling_is_set_when_the_score_is_already_below_it() -> None:
    score, _, ceiling = triage.score_skill("docs social hook", _documenter())

    assert score < triage.SINGLE_TERM_SCORE_CAP
    assert ceiling == triage.SINGLE_TERM_SCORE_CAP


def test_boosts_cannot_lift_a_low_single_term_score_past_the_cap() -> None:
    signals = {"has_error": True, "has_code": True, "has_url": True}

    uncapped_boost = triage.find_matching_skills("docs", [_documenter()], signals=signals)
    matches = triage.find_matching_skills("docs social hook", [_documenter()], signals=signals)

    assert uncapped_boost[0]["score"] > triage.SINGLE_TERM_SCORE_CAP, "short query is not capped"
    assert matches[0]["score"] == triage.SINGLE_TERM_SCORE_CAP
    assert any("capped:" in r for r in matches[0]["reasons"])


def test_no_cap_reason_when_the_cap_did_not_change_the_score() -> None:
    score, reasons = triage.calculate_match_score("docs social hook", _documenter())

    assert score < triage.SINGLE_TERM_SCORE_CAP
    assert not any("capped:" in r for r in reasons)


def test_apply_ceiling() -> None:
    reasons: list[str] = []

    assert triage.apply_ceiling(30, None, reasons) == 30
    assert triage.apply_ceiling(30, 49, reasons) == 30
    assert reasons == []
    assert triage.apply_ceiling(80, 49, reasons) == 49
    assert reasons == ["capped: one shared term in a long request"]


# ---------------------------------------------------------------------------
# Exact one-word names are exempt only in a name lookup
# ---------------------------------------------------------------------------


def _test_skill() -> dict[str, Any]:
    return make_skill("test", "Prove a change works.", ["test"], domains=["testing"])


@pytest.mark.parametrize(
    "query",
    [
        "create a skill for test payment gateways",
        "I need a test payment gateways workflow",
    ],
)
def test_exact_one_word_name_inside_a_long_create_request_is_capped(query: str) -> None:
    category, _ = triage.classify_input(query)
    skill = _test_skill()

    score, reasons, ceiling = triage.score_skill(query, skill, category)

    assert "name match: test" in reasons
    assert ceiling == triage.SINGLE_TERM_SCORE_CAP
    assert triage.calculate_match_score(query, skill, category)[0] <= triage.SINGLE_TERM_SCORE_CAP


@pytest.mark.parametrize(
    "category", [triage.InputCategory.SKILL_QUESTION, triage.InputCategory.EXPLICIT_IMPROVE]
)
def test_exact_one_word_name_in_a_lookup_is_not_capped(category: str) -> None:
    _, reasons, ceiling = triage.score_skill(
        "improve the test skill for payment gateways", _test_skill(), category
    )

    assert "name match: test" in reasons
    assert ceiling is None


def test_multi_word_name_in_a_long_query_is_not_capped() -> None:
    skill = make_skill("webapp-testing", "Toolkit.", [])

    _, reasons, ceiling = triage.score_skill("use webapp-testing on the checkout page flows", skill)

    assert "name match: webapp-testing" in reasons
    assert ceiling is None


# ---------------------------------------------------------------------------
# A name lookup still finds a scaffolding-named skill
# ---------------------------------------------------------------------------


def _build_skill() -> dict[str, Any]:
    return make_skill(
        "build",
        "Implement a planned change in thin vertical slices.",
        keywords=["build", "implement"],
        triggers=["build this", "build"],
    )


@pytest.mark.parametrize(
    "query",
    ["do I have a skill for build?", "improve the build skill"],
)
def test_lookup_for_a_scaffolding_named_skill_recommends_it(
    query: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(triage, "load_skill_index", lambda: {"skills": [_build_skill()]})

    result = triage.triage_request(query)

    assert result.success
    top = result.data["top_matches"][0]
    assert top["name"] == "build"
    assert "name match: build" in top["reasons"]
    assert result.data["action"] != triage.Action.CREATE_NEW


def test_lookup_does_not_match_an_inflected_scaffolding_name() -> None:
    category = triage.InputCategory.SKILL_QUESTION

    score, reasons = triage.calculate_match_score(
        "do I have a skill for building hook loops", _build_skill(), category
    )

    assert "name match: build" not in reasons
    assert score < 50


@pytest.mark.parametrize(
    "query",
    ["build a skill for hook loops", "create a skill to build pipelines"],
)
def test_create_request_still_ignores_a_scaffolding_named_skill(query: str) -> None:
    category, _ = triage.classify_input(query)

    score, reasons = triage.calculate_match_score(query, _build_skill(), category)

    assert score == 0
    assert reasons == []


def test_find_matching_skills_passes_the_category_to_scoring() -> None:
    query = "do I have a skill for build?"
    skills = [_build_skill()]

    with_category = triage.find_matching_skills(
        query, skills, category=triage.InputCategory.SKILL_QUESTION
    )
    without_category = triage.find_matching_skills(query, skills)

    assert with_category and with_category[0]["name"] == "build"
    assert without_category == []


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("improve the build skill", triage.InputCategory.EXPLICIT_IMPROVE),
        ("update the make skill", triage.InputCategory.EXPLICIT_IMPROVE),
        ("build a skill for hook loops", triage.InputCategory.EXPLICIT_CREATE),
        ("build skill for hook loops", triage.InputCategory.EXPLICIT_CREATE),
        ("make a new skill to rotate time slots", triage.InputCategory.EXPLICIT_CREATE),
        ("please create a skill for docs", triage.InputCategory.EXPLICIT_CREATE),
    ],
)
def test_a_skill_named_after_a_creation_verb_is_not_a_create_request(
    query: str, expected: str
) -> None:
    category, _ = triage.classify_input(query)

    assert category == expected
