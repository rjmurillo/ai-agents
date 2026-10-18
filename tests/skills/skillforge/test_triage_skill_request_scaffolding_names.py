#!/usr/bin/env python3
"""
Review round 3 regression tests for skillforge triage scoring (issue #6647).

Covers skills named after a scaffolding verb ("build", "make"), GENERAL input
that describes a topic no skill covers, and the issue repros run against an
index built by discover_skills.py over this repo's real skills.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.skills.skillforge.triage_support import (
    BARE_QUERY,
    BUILD_QUERY,
    CREATE_QUERY,
    REPO_SKILLS_DIR,
    discover_skills,
    make_skill,
    run_triage,
    triage,
)

# ---------------------------------------------------------------------------
# Skills named after a scaffolding word must not match request framing
# ---------------------------------------------------------------------------


def _verb_named_skills() -> list[dict[str, Any]]:
    """Skills whose names are creation verbs, plus one that really tests."""
    return [
        make_skill(
            "build",
            "Implement a planned change in thin vertical slices with tests.",
            keywords=["build", "implement", "slices", "tests"],
            domains=["testing"],
            triggers=["build this", "build"],
        ),
        make_skill(
            "make",
            "Run make targets for the project.",
            keywords=["make", "targets"],
            domains=["testing"],
            triggers=["make"],
        ),
        make_skill(
            "webapp-testing",
            "Toolkit for testing local web applications using Playwright.",
            keywords=["webapp-testing", "webapp", "testing", "playwright"],
            domains=["testing", "frontend"],
        ),
    ]


@pytest.fixture
def verb_index(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    index = {"skills": _verb_named_skills()}
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)
    return index


@pytest.mark.parametrize("verb", ["build", "make"])
def test_creation_verb_naming_a_skill_is_not_a_name_match(
    verb: str, verb_index: dict[str, Any]
) -> None:
    data = run_triage(CREATE_QUERY.replace("create a skill", f"{verb} a skill", 1))

    reasons = " ".join(r for m in data["top_matches"] for r in m["reasons"])
    assert f"name match: {verb}" not in reasons
    assert data["action"] == triage.Action.CREATE_NEW
    assert data["details"]["top_score"] < 50


def test_build_a_skill_request_does_not_trigger_the_build_skill(
    verb_index: dict[str, Any],
) -> None:
    data = run_triage(BUILD_QUERY)

    reasons = " ".join(r for m in data["top_matches"] for r in m["reasons"])
    assert "trigger: build" not in reasons
    assert data["action"] == triage.Action.CREATE_NEW
    assert data["details"]["top_score"] < 50


def test_task_request_using_a_creation_verb_does_not_improve_the_verb_skill(
    verb_index: dict[str, Any],
) -> None:
    data = run_triage("I need to build a social media hook testing loop")

    assert data["action"] == triage.Action.CREATE_NEW
    assert data["details"]["top_score"] < 50


def test_scaffolding_named_skill_scores_zero_for_framing_only() -> None:
    skill = make_skill("build", "Implement a change.", triggers=["build this"])

    score, reasons = triage.calculate_match_score("build a skill", skill)

    assert score == 0
    assert reasons == []


def test_content_named_skill_still_gets_its_name_match(verb_index: dict[str, Any]) -> None:
    skill = make_skill("webapp-testing", "Toolkit for testing web apps.", triggers=["webapp"])

    score, reasons = triage.calculate_match_score("webapp-testing for the checkout page", skill)

    assert score > 0
    assert "name match: webapp-testing" in reasons


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("build", True),
        ("make", True),
        ("build a", True),
        ("create-new", True),
        ("build pipeline", False),
        ("code review", False),
        ("", False),
        ("   ", False),
    ],
)
def test_is_scaffolding_phrase(phrase: str, expected: bool) -> None:
    assert triage.is_scaffolding_phrase(phrase) is expected


# ---------------------------------------------------------------------------
# GENERAL input that describes an uncovered topic routes to CREATE_NEW
# ---------------------------------------------------------------------------


def test_general_topic_with_no_strong_match_routes_to_create_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = {"skills": [make_skill("xlsx", "Edit spreadsheets.", domains=["spreadsheet"])]}
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)

    data = run_triage(BARE_QUERY)

    assert data["details"]["category"] == triage.InputCategory.GENERAL
    assert data["action"] == triage.Action.CREATE_NEW
    assert data["details"]["top_score"] < 50


def test_general_topic_with_a_partial_match_below_fifty_routes_to_create_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = {
        "skills": [
            make_skill(
                "webapp-testing",
                "Toolkit for testing local web applications.",
                keywords=["testing", "webapp"],
                domains=["testing"],
            )
        ]
    }
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)

    data = run_triage(BARE_QUERY)

    assert 0 < data["details"]["top_score"] < 50
    assert data["action"] == triage.Action.CREATE_NEW


def test_short_general_input_still_asks_for_clarification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(triage, "load_skill_index", lambda: {"skills": []})

    data = run_triage("hello there")

    assert data["details"]["category"] == triage.InputCategory.GENERAL
    assert data["action"] == triage.Action.CLARIFY


def test_general_input_with_a_strong_match_still_uses_the_existing_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = {
        "skills": [
            make_skill(
                "xlsx",
                "Edit xlsx spreadsheet files with formulas.",
                keywords=["xlsx", "spreadsheet", "formulas"],
                domains=["spreadsheet"],
            )
        ]
    }
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)

    data = run_triage("xlsx spreadsheet formulas")

    assert data["action"] == triage.Action.USE_EXISTING


# ---------------------------------------------------------------------------
# Issue repros against an index built from this repo's real skills
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_index(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Index built by discover_skills.py over .claude/skills, with HOME isolated."""
    if not REPO_SKILLS_DIR.is_dir():
        pytest.skip("repo .claude/skills tree not present")
    home = tmp_path_factory.mktemp("home")
    patch = pytest.MonkeyPatch()
    try:
        patch.setenv("HOME", str(home))
        patch.setattr(
            discover_skills,
            "SKILL_SOURCES",
            [
                {
                    "name": "custom",
                    "path": REPO_SKILLS_DIR,
                    "pattern": "*/[Ss][Kk][Ii][Ll][Ll].[Mm][Dd]",
                    "priority": 1,
                }
            ],
        )
        result = discover_skills.discover_skills()
    finally:
        patch.undo()
    assert result.success
    assert result.data["total_count"] > 10
    return result.data


@pytest.mark.parametrize(
    "query",
    [
        CREATE_QUERY,
        BUILD_QUERY,
        BARE_QUERY,
        "I need to build a social media hook testing loop",
        "make a skill for running a social media hook testing loop",
        "create a skill for docs social hook",
        "create a skill for test payment gateways",
    ],
)
def test_issue_repros_route_to_create_new_on_the_real_index(
    query: str, real_index: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(triage, "load_skill_index", lambda: real_index)

    data = run_triage(query)

    assert data["action"] == triage.Action.CREATE_NEW
    # Every listed match, not only the top one, stays under the 50 point boundary.
    assert all(m["score"] < 50 for m in data["top_matches"]), data["top_matches"]
