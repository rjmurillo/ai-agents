#!/usr/bin/env python3
"""
Review round 5 regression tests for skillforge triage scoring (issue #6647).

Covers one shared inflection rule for the matcher, the coverage count, and the
domain classifier, and improve requests that carry a determiner or open with an
improve verb before a creation-verb skill name.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.skills.skillforge.triage_support import (
    discover_skills,
    make_skill,
    run_triage,
    triage,
)

# ---------------------------------------------------------------------------
# stem_forms undoes a doubled final consonant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("token", "expected_form"),
    [
        ("shipped", "ship"),
        ("shipping", "ship"),
        ("planning", "plan"),
        ("debugging", "debug"),
        ("debugged", "debug"),
        ("testing", "test"),
        ("releases", "release"),
    ],
)
def test_stem_forms_recovers_the_base_form(token: str, expected_form: str) -> None:
    assert expected_form in triage.stem_forms(token)


@pytest.mark.parametrize(
    ("token", "absent_form"),
    [
        # A vowel never doubles, so the doubled form is a real stem.
        ("feeding", "fed"),
        ("deployed", "deploye"),
        # The stem must keep three letters.
        ("tipped", "ti"),
        ("sing", "s"),
        # A letter outside the doubling set keeps its pair.
        ("passing", "pas"),
        ("buzzing", "buz"),
        # Only ing and ed collapse a double, a plural does not.
        ("balls", "bal"),
    ],
)
def test_stem_forms_does_not_overreach(token: str, absent_form: str) -> None:
    assert absent_form not in triage.stem_forms(token)


def test_stem_forms_keeps_the_token_itself() -> None:
    assert "shipped" in triage.stem_forms("shipped")
    assert triage.stem_forms("go") == {"go"}
    assert triage.stem_forms("") == {""}


# ---------------------------------------------------------------------------
# The matcher and the coverage count agree
# ---------------------------------------------------------------------------

_PAIRS = [
    ("ship", "shipped"),
    ("ship", "shipping"),
    ("plan", "planning"),
    ("plan", "planned"),
    ("debug", "debugging"),
    ("debug", "debugged"),
    ("test", "testing"),
    ("test", "tests"),
    ("release", "releases"),
    ("deploy", "deployed"),
]


@pytest.mark.parametrize(("base", "inflected"), _PAIRS)
def test_matcher_and_coverage_accept_the_same_inflections(base: str, inflected: str) -> None:
    skill = make_skill("alpha", f"Handles {base} work for a team.")

    assert triage.contains_term(inflected, base)
    assert triage.count_explained_terms([inflected], skill) == 1
    assert triage.count_explained_terms([base], skill) == 1


@pytest.mark.parametrize(("base", "inflected"), _PAIRS)
def test_coverage_matches_an_inflected_skill_word_to_a_base_query(
    base: str, inflected: str
) -> None:
    skill = make_skill("alpha", f"Handles {inflected} work for a team.")

    assert triage.count_explained_terms([base], skill) == 1


def test_issue_example_counts_all_three_inflected_terms() -> None:
    skill = make_skill("alpha", "debug flaky ship pipelines")

    assert triage.count_explained_terms(["debugging", "shipped", "pipeline"], skill) == 3
    assert triage.count_explained_terms(["debug", "ship", "pipeline"], skill) == 3


@pytest.mark.parametrize(
    ("term", "text"),
    [
        ("test", "attest the claim"),
        ("ship", "shippers"),
        ("debug", "debugger"),
        ("plan", "planet"),
    ],
)
def test_neither_path_matches_a_different_word(term: str, text: str) -> None:
    skill = make_skill("alpha", text)

    assert not triage.contains_term(text, term)
    assert triage.count_explained_terms([term], skill) == 0


def test_discovery_and_triage_share_one_matcher() -> None:
    assert discover_skills._has_term is triage.has_term


# ---------------------------------------------------------------------------
# An inflected query gets the same answer as its base-form query
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("base_query", "inflected_query", "top"),
    [
        ("plan ship release checklist", "planning shipped releases checklist", "ship"),
        (
            "ship the release and plan the checklist",
            "shipping the releases and planning the checklists",
            "ship",
        ),
    ],
)
def test_inflected_query_routes_like_its_base_form_on_the_real_index(
    base_query: str,
    inflected_query: str,
    top: str,
    real_index: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(triage, "load_skill_index", lambda: real_index)

    base = run_triage(base_query)
    inflected = run_triage(inflected_query)

    assert inflected["action"] == base["action"], (base["top_matches"], inflected["top_matches"])
    assert base["top_matches"][0]["name"] == top
    assert inflected["top_matches"][0]["name"] == top
    assert inflected["top_matches"][0]["coverage"] == base["top_matches"][0]["coverage"]


def test_inflected_query_is_not_capped_below_its_base_form() -> None:
    skill = make_skill("ship", "Ship a release: run checks, plan the release, and open the PR.")
    base = triage.score_skill("plan ship release checklist", skill)
    inflected = triage.score_skill("planning shipped releases checklist", skill)

    assert inflected[2] == base[2]


# ---------------------------------------------------------------------------
# Improve requests with a determiner, or a creation verb as the skill name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "name"),
    [
        ("improve my build skill", "build"),
        ("fix our build skill", "build"),
        ("improve build skill", "build"),
        ("update make skill", "make"),
        ("improve the build skill", "build"),
        ("enhance this design skill", "design"),
        ("please upgrade the develop skill", "develop"),
    ],
)
def test_improve_request_for_a_creation_verb_skill_is_an_improve(query: str, name: str) -> None:
    category, signals = triage.classify_input(query)

    assert category == triage.InputCategory.EXPLICIT_IMPROVE
    assert signals["mentioned_skill_name"] == name


@pytest.mark.parametrize(
    "query",
    [
        "build a skill for hook loops",
        "build skill for hook loops",
        "make a new skill to rotate time slots",
        "create a skill for docs",
        # An improve verb that does not open the request keeps the create reading.
        "I want to create a new skill for logging and fix the report",
    ],
)
def test_create_requests_stay_create_requests(query: str) -> None:
    category, _ = triage.classify_input(query)

    assert category == triage.InputCategory.EXPLICIT_CREATE


@pytest.mark.parametrize("query", ["improve a skill", "improve the skill", "fix this skill"])
def test_improve_request_without_a_name_reports_no_skill_name(query: str) -> None:
    category, signals = triage.classify_input(query)

    assert category == triage.InputCategory.EXPLICIT_IMPROVE
    assert signals["mentioned_skill_name"] is None


def test_update_without_skill_word_is_not_an_improve() -> None:
    category, _ = triage.classify_input("update docs and create a new skill for logging")

    assert category == triage.InputCategory.EXPLICIT_CREATE


@pytest.mark.parametrize(
    "query", ["improve my build skill", "fix our build skill", "improve build skill"]
)
def test_improve_request_lists_the_build_skill_in_the_real_index(
    query: str, real_index: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(triage, "load_skill_index", lambda: real_index)

    data = run_triage(query)

    assert data["action"] == triage.Action.IMPROVE_EXISTING
    assert "build" in [m["name"] for m in data["top_matches"]]
