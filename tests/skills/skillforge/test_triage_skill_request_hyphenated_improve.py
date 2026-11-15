#!/usr/bin/env python3
"""
Regression tests for improve requests that name a hyphenated skill (issue #7358).

"improve the context-mode skill" must classify as explicit_improve and keep the
whole skill name, the same as "improve the build skill" always did.
"""

from __future__ import annotations

import pytest

from tests.skills.skillforge.triage_support import make_skill, run_triage, triage

EXPLICIT_IMPROVE = triage.InputCategory.EXPLICIT_IMPROVE


@pytest.mark.parametrize(
    ("query", "name"),
    [
        ("improve the build skill", "build"),
        ("improve the context-mode skill", "context-mode"),
        ("improve the agent-harness-reference skill", "agent-harness-reference"),
        ("improve my context-mode skill", "context-mode"),
        ("improve our context-mode skill", "context-mode"),
        ("improve this context-mode skill", "context-mode"),
        ("improve a context-mode skill", "context-mode"),
        ("improve context-mode skill", "context-mode"),
        ("please improve the context-mode skill", "context-mode"),
        ("Improve The Context-Mode Skill", "context-mode"),
        ("fix the agent-harness-reference skill", "agent-harness-reference"),
        ("extend the a-b-c-d skill", "a-b-c-d"),
    ],
)
def test_leading_improve_keeps_the_whole_hyphenated_name(query: str, name: str) -> None:
    category, signals = triage.classify_input(query)

    assert category == EXPLICIT_IMPROVE
    assert signals["mentioned_skill_name"] == name


@pytest.mark.parametrize(
    ("query", "name"),
    [
        ("can you improve the context-mode skill", "context-mode"),
        ("we should update the agent-harness-reference skill soon", "agent-harness-reference"),
    ],
)
def test_non_leading_improve_matches_a_hyphenated_name(query: str, name: str) -> None:
    category, signals = triage.classify_input(query)

    assert category == EXPLICIT_IMPROVE
    assert signals["mentioned_skill_name"] == name


@pytest.mark.parametrize(
    "query",
    [
        "improve the skill",
        "improve my skill",
    ],
)
def test_determiner_only_request_names_no_skill(query: str) -> None:
    category, signals = triage.classify_input(query)

    assert category == EXPLICIT_IMPROVE
    assert signals["mentioned_skill_name"] is None


@pytest.mark.parametrize(
    "query",
    [
        "improve the context- skill",
        "improve the -mode skill",
        "improve the context--mode skill",
    ],
)
def test_malformed_hyphenation_is_not_an_improve_request(query: str) -> None:
    category, _ = triage.classify_input(query)

    assert category != EXPLICIT_IMPROVE


@pytest.mark.parametrize(
    ("query", "category"),
    [
        ("create a skill for context-mode handling", "explicit_create"),
        ("build a skill for agent-harness-reference", "explicit_create"),
        ("create a skill to improve the context-mode skill", "explicit_create"),
        ("improve build skill", "explicit_improve"),
        ("do I have a skill for context-mode?", "skill_question"),
        ("I need to review context-mode output", "task_request"),
        ("context-mode skill", "general"),
    ],
)
def test_unrelated_categories_are_unchanged(query: str, category: str) -> None:
    got, _ = triage.classify_input(query)

    assert got == category


def test_catalog_backed_hyphenated_improve_targets_the_existing_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skill = make_skill(
        "context-mode",
        "Keep large tool output out of the conversation context.",
        keywords=["context", "mode"],
    )
    monkeypatch.setattr(triage, "load_skill_index", lambda: {"skills": [skill]})

    data = run_triage("improve the context-mode skill")

    assert data["input_category"] == EXPLICIT_IMPROVE
    assert data["action"] == triage.Action.IMPROVE_EXISTING
    assert data["details"]["target_skill"] == "context-mode"


def _overlap(name: str, score: int) -> dict[str, object]:
    return {"name": name, "score": score, "domains": [], "reasons": []}


def _improve(query: str, matches: list[dict[str, object]], names: frozenset[str]) -> tuple:
    category, signals = triage.classify_input(query)
    return triage.make_triage_decision(category, signals, matches, query, frozenset(), names)


def test_exact_name_wins_over_a_higher_ranked_longer_name() -> None:
    matches = [_overlap("context-mode-plus", 90), _overlap("context-mode", 60)]
    names = frozenset({"context-mode-plus", "context-mode"})

    action, details = _improve("improve the context-mode skill", matches, names)

    assert action == triage.Action.IMPROVE_EXISTING
    assert details["target_skill"] == "context-mode"


def test_exact_name_outside_the_ranked_matches_still_wins() -> None:
    matches = [_overlap("context-mode-plus", 90)]
    names = frozenset({"context-mode-plus", "context-mode"})

    action, details = _improve("improve the context-mode skill", matches, names)

    assert action == triage.Action.IMPROVE_EXISTING
    assert details["target_skill"] == "context-mode"


def test_two_longer_names_without_an_exact_name_ask_instead_of_guessing() -> None:
    matches = [_overlap("context-mode-plus", 90), _overlap("context-mode-lite", 80)]
    names = frozenset({"context-mode-plus", "context-mode-lite"})

    action, details = _improve("improve the context-mode skill", matches, names)

    assert action == triage.Action.CLARIFY
    assert "target_skill" not in details


def test_single_longer_name_without_an_exact_name_is_still_the_target() -> None:
    matches = [_overlap("adr-generator", 70)]

    action, details = _improve("improve the adr skill", matches, frozenset({"adr-generator"}))

    assert action == triage.Action.IMPROVE_EXISTING
    assert details["target_skill"] == "adr-generator"


def test_catalog_with_overlapping_names_targets_the_exact_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plus = make_skill(
        "context-mode-plus",
        "Context mode plus: improve context mode output for context mode users.",
        keywords=["context", "mode", "plus"],
    )
    exact = make_skill("context-mode", "Keep tool output small.", keywords=["context"])
    monkeypatch.setattr(triage, "load_skill_index", lambda: {"skills": [plus, exact]})

    data = run_triage("improve the context-mode skill")

    assert data["action"] == triage.Action.IMPROVE_EXISTING
    assert data["details"]["target_skill"] == "context-mode"
