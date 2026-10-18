#!/usr/bin/env python3
"""
Review round 1 regression tests for skillforge triage scoring (issue #6647).

Covers synonym-matched skills, natural phrasing that must still reach an
existing skill, whole-word name and trigger matching, the single-term cap,
zero-score cleanup, and create/improve classification order.
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

# ---------------------------------------------------------------------------
# Review round 1: synonym matches, natural phrasing, whole-word names, zero scores
# ---------------------------------------------------------------------------


def _sheets_skill() -> dict[str, Any]:
    """Declares the spreadsheet domain but lists none of its synonyms."""
    return make_skill(
        "sheets",
        "Create and edit spreadsheet files with formulas and charts",
        keywords=["spreadsheet", "formulas"],
        domains=["spreadsheet"],
    )


def test_synonym_only_match_keeps_its_score(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(triage, "load_skill_index", lambda: {"skills": [_sheets_skill()]})

    data = run_triage("excel workbook")

    assert data["top_matches"][0]["name"] == "sheets"
    assert data["top_matches"][0]["score"] >= 50
    assert not any(r.startswith("coverage:") for r in data["top_matches"][0]["reasons"])


def test_creation_request_for_synonym_matched_skill_never_creates_a_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(triage, "load_skill_index", lambda: {"skills": [_sheets_skill()]})

    data = run_triage("create a skill for excel workbooks")

    assert data["action"] == triage.Action.CLARIFY
    assert data["top_matches"][0]["name"] == "sheets"


def test_calculate_coverage_counts_declared_domain_synonyms() -> None:
    skill = _sheets_skill()

    assert triage.calculate_coverage(["excel", "workbook"], skill) == 0.0
    assert triage.calculate_coverage(["excel", "workbook"], skill, frozenset({"excel"})) == 0.5
    assert (
        triage.calculate_coverage(["excel", "workbook"], skill, frozenset({"excel", "workbook"}))
        == 1.0
    )


def test_domain_synonym_terms_only_use_domains_the_skill_declares() -> None:
    query_domains = [("spreadsheet", ["excel", "rows columns"]), ("testing", ["test"])]

    terms = triage.domain_synonym_terms(query_domains, {"spreadsheet"})

    assert terms == frozenset({"excel", "rows", "columns"})
    assert triage.domain_synonym_terms(query_domains, set()) == frozenset()


@pytest.fixture
def realistic_index() -> dict[str, Any]:
    """Skills shaped like discover_skills.py output for this repo's real skills."""
    return {
        "skills": [
            make_skill(
                "test",
                "Prove a change works across six gates covering functional, security, "
                "DevOps, and observability quality. Use when you say `run the test gates` "
                "or `validate this change`.",
                keywords=["test", "tests", "gates", "prove", "validate", "quality", "change"],
                domains=["testing"],
            ),
            make_skill(
                "threat-modeling",
                "Structured security analysis using OWASP and STRIDE methodology. "
                "Generates threat matrices with risk ratings and mitigations.",
                keywords=["threat", "stride", "owasp", "matrices", "security", "framework"],
                domains=["security", "ai_ml"],
            ),
            make_skill(
                "adr-generator",
                "Create Architectural Decision Records (ADRs). Use when you say "
                '"write an ADR" or "document this decision".',
                keywords=["adr", "adrs", "decision", "documenting", "write", "chose", "record"],
                domains=["document"],
            ),
            make_skill(
                "analyze",
                "Systematic codebase analysis covering architecture reviews, security "
                "assessments, and code quality evaluations.",
                keywords=["analysis", "security", "review", "code", "quality", "findings"],
                domains=["security", "code_quality", "architecture"],
            ),
            make_skill(
                "skillforge",
                "Intelligent skill router and creator. Recommends existing skills, improves "
                "them, or creates new ones.",
                keywords=["skillforge", "router", "creator", "improve"],
                domains=["general"],
            ),
        ]
    }


@pytest.mark.parametrize(
    ("query", "expected_skill"),
    [
        ("I need to run a threat model on the new auth service", "threat-modeling"),
        ("fix the failing pytest tests in my repo", "test"),
        ("review my pull request for security issues before merging", "analyze"),
        ("write an ADR documenting why we chose postgres", "adr-generator"),
    ],
)
def test_natural_requests_for_existing_skills_never_route_to_create_new(
    monkeypatch: pytest.MonkeyPatch,
    realistic_index: dict[str, Any],
    query: str,
    expected_skill: str,
) -> None:
    monkeypatch.setattr(triage, "load_skill_index", lambda: realistic_index)

    data = run_triage(query)

    assert data["action"] != triage.Action.CREATE_NEW
    # The existing skill must lead, and its score must stay out of the CREATE_NEW
    # band. "!= CREATE_NEW" alone passes when the score collapses to a GENERAL
    # CLARIFY, which hid the "documenting" regression.
    assert data["top_matches"][0]["name"] == expected_skill
    assert data["top_matches"][0]["score"] >= 50


@pytest.mark.parametrize(
    ("query", "domain"),
    [
        ("documenting the release process", "document"),
        ("documented decisions", "document"),
        ("how do I authorize a user", "authentication"),
        ("authorization for the admin api", "authentication"),
        ("authenticate the webhook caller", "authentication"),
        ("debugging a flaky build", "debugging"),
    ],
)
def test_inflected_and_long_forms_of_short_synonyms_still_match_their_domain(
    query: str, domain: str
) -> None:
    detected = [name for name, _ in triage.detect_query_domains(query)]

    assert domain in detected


def test_short_synonym_does_not_match_inside_an_unrelated_word() -> None:
    detected = [name for name, _ in triage.detect_query_domains("authority over the doctor")]

    assert "authentication" not in detected
    assert "document" not in detected


def test_hyphenated_trigger_matches_a_spaced_query() -> None:
    skill = make_skill("reviewer", "Checks changes.", triggers=["code-review"])

    _, spaced = triage.calculate_match_score("please do a code review now", skill)
    _, hyphenated = triage.calculate_match_score("please do a code-review now", skill)

    assert "trigger: code-review" in spaced
    assert "trigger: code-review" in hyphenated


def test_hyphenated_trigger_does_not_match_a_partial_phrase() -> None:
    skill = make_skill("reviewer", "Checks changes.", triggers=["code-review"])

    _, reasons = triage.calculate_match_score("please do a code check now", skill)

    assert "trigger: code-review" not in reasons


def test_trigger_explained_terms_count_toward_coverage() -> None:
    skill = make_skill("reviewer", "Checks changes.", triggers=["code-review"])

    assert triage.calculate_coverage(["code", "review"], skill) == 1.0
    assert triage.calculate_coverage(["code", "zebra"], skill) == 0.5

    # The trigger alone explains both query terms, so the 25 point trigger score
    # is not halved by an unexplained-terms discount (it was 12 before).
    score, reasons = triage.calculate_match_score("do a code-review", skill)

    assert reasons == ["trigger: code-review"]
    assert score == 25


def test_coverage_discount_is_half_strength() -> None:
    skill = make_skill("webapp-testing", "Toolkit for testing web applications.", ["testing"])
    full, _ = triage.calculate_match_score("testing", skill)
    # "testing" plus one unexplained word: coverage 50%, so the factor is 0.75.
    diluted, _ = triage.calculate_match_score("testing zebra", skill)

    assert diluted == round(full * 0.75)


def test_long_request_on_one_shared_term_is_capped_below_create_boundary(
    realistic_index: dict[str, Any],
) -> None:
    skills = realistic_index["skills"]

    matches = triage.find_matching_skills(BARE_QUERY, skills)

    assert matches, "the testing skill still matches on its one shared term"
    assert all(m["score"] <= triage.SINGLE_TERM_SCORE_CAP for m in matches)
    assert any("capped:" in r for m in matches for r in m["reasons"])


def test_cap_is_not_lifted_by_context_boosts(realistic_index: dict[str, Any]) -> None:
    skills = realistic_index["skills"]
    signals = {"has_error": True, "has_code": True, "has_url": True}

    matches = triage.find_matching_skills(BARE_QUERY, skills, signals=signals)

    assert all(m["score"] <= triage.SINGLE_TERM_SCORE_CAP for m in matches)


def test_short_query_on_one_shared_term_is_not_capped() -> None:
    skill = make_skill("webapp-testing", "Toolkit for testing web applications.", ["testing"])

    score, reasons, ceiling = triage.score_skill("testing loop", skill)

    assert ceiling is None
    assert score > 0
    assert not any("capped:" in r for r in reasons)


def test_lookup_naming_the_skill_exactly_is_not_capped() -> None:
    skill = make_skill("skillforge", "Skill router.", ["router"])
    query = "do I have a skill named skillforge for my repo please now"

    _, reasons, ceiling = triage.score_skill(query, skill, triage.InputCategory.SKILL_QUESTION)

    assert ceiling is None
    assert "name match: skillforge" in reasons


def test_inflected_name_match_on_a_long_query_is_still_capped() -> None:
    skill = make_skill("test", "Prove a change works.", ["test"], domains=["testing"])

    _, reasons, ceiling = triage.score_skill(BARE_QUERY, skill)

    assert ceiling == triage.SINGLE_TERM_SCORE_CAP
    assert "name match: test" in reasons


def test_name_match_is_whole_word() -> None:
    skill = make_skill("test", "Prove a change works.", ["prove"])

    _, attest_reasons = triage.calculate_match_score("attest builds", skill)
    _, testing_reasons = triage.calculate_match_score("testing builds", skill)

    assert "name match: test" not in attest_reasons
    assert "name match: test" in testing_reasons


def test_hyphenated_skill_name_matches_spaced_and_hyphenated_queries() -> None:
    skill = make_skill("webapp-testing", "Toolkit.", [])

    _, spaced = triage.calculate_match_score("webapp testing", skill)
    _, hyphenated = triage.calculate_match_score("use webapp-testing", skill)

    assert "name match: webapp-testing" in spaced
    assert "name match: webapp-testing" in hyphenated


def test_nameless_skill_does_not_match_every_query() -> None:
    skill = make_skill("", "Does something.", [])

    score, reasons = triage.calculate_match_score("anything at all", skill)

    assert score == 0
    assert reasons == []


def test_trigger_match_is_whole_word() -> None:
    skill = make_skill("sec", "Security helper.", triggers=["ci"])

    _, social = triage.calculate_match_score("social media hook", skill)
    _, ci = triage.calculate_match_score("fix the ci pipeline", skill)

    assert "trigger: ci" not in social
    assert "trigger: ci" in ci


def test_empty_trigger_is_ignored() -> None:
    skill = make_skill("sec", "Security helper.", triggers=[""])

    _, reasons = triage.calculate_match_score("fix the pipeline", skill)

    assert not any(r.startswith("trigger:") for r in reasons)


def test_zero_score_drops_reasons_and_is_not_listed() -> None:
    skill = make_skill("sheets", "Spreadsheet helper.", ["spreadsheet"], domains=["spreadsheet"])

    score, reasons = triage.calculate_match_score("zebra stripes", skill)

    assert (score, reasons) == (0, [])
    assert triage.find_matching_skills("zebra stripes", [skill]) == []


def test_every_listed_match_has_a_positive_score(realistic_index: dict[str, Any]) -> None:
    for query in (CREATE_QUERY, BARE_QUERY, "fix the failing pytest tests in my repo"):
        matches = triage.find_matching_skills(query, realistic_index["skills"], limit=50)

        assert all(m["score"] > 0 and m["reasons"] for m in matches)


# ---------------------------------------------------------------------------
# Review round 1: improving a skill named "skillforge" is not a create request
# ---------------------------------------------------------------------------


def test_improve_the_skillforge_skill_is_an_improve_request(
    monkeypatch: pytest.MonkeyPatch, realistic_index: dict[str, Any]
) -> None:
    monkeypatch.setattr(triage, "load_skill_index", lambda: realistic_index)

    data = run_triage("improve the skillforge skill")

    assert data["input_category"] == triage.InputCategory.EXPLICIT_IMPROVE
    assert data["action"] == triage.Action.IMPROVE_EXISTING
    assert data["details"]["target_skill"] == "skillforge"


@pytest.mark.parametrize(
    ("query", "category"),
    [
        ("SkillForge: improve the test skill", "explicit_improve"),
        ("SkillForge: create a skill for database migrations", "explicit_create"),
        ("skillforge: database migrations", "explicit_create"),
        ("skillforge handle this request", "explicit_create"),
        ("create a skill to update the config skill", "explicit_create"),
    ],
)
def test_classify_input_orders_create_and_improve_patterns(query: str, category: str) -> None:
    got, _ = triage.classify_input(query)

    assert got == category


def test_skillforge_prefix_create_still_extracts_the_purpose() -> None:
    _, signals = triage.classify_input("SkillForge: create a skill for database migrations")

    assert signals["extracted_purpose"] == "database migrations"
