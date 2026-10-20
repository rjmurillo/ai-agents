#!/usr/bin/env python3
"""
Follow-up regression tests for PR #6676 (skillforge triage scoring).

Covers CamelCase error class names in ERROR_MESSAGE routing, the covered-topic
guard on the TASK_REQUEST, SKILL_QUESTION, and EXPLICIT_CREATE branches, and the
scaffolding-named skill skip that applies to every category except a name lookup.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.skills.skillforge.triage_support import make_skill, run_triage, triage

# ---------------------------------------------------------------------------
# Finding 1: CamelCase error class names reach the debugging synonym "error"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("TypeError: Cannot read property", "Type Error: Cannot read property"),
        ("ReferenceError: foo is not defined", "Reference Error: foo is not defined"),
        ("java.lang.NullPointerException at Foo", "java.lang.NullPointer Exception at Foo"),
        # Negative: no CamelCase error name, so the text is untouched.
        ("IOError: foobar bazqux", "IO Error: foobar bazqux"),
        ("SQLException: bad", "SQL Exception: bad"),
        ("Error: something failed", "Error: something failed"),
        ("fix the TypeScript types in GitHub", "fix the TypeScript types in GitHub"),
        ("terror and exceptional", "terror and exceptional"),
    ],
)
def test_split_error_class_names(query: str, expected: str) -> None:
    assert triage.split_error_class_names(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "TypeError: Cannot read property 'map' of undefined",
        "ReferenceError: foo is not defined",
        "SyntaxError: unexpected token",
    ],
)
def test_error_class_names_route_to_a_debugging_skill_on_the_real_index(
    query: str, real_index: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(triage, "load_skill_index", lambda: real_index)

    data = run_triage(query)

    assert data["action"] == triage.Action.USE_EXISTING, data["top_matches"]
    debugging = [m for m in data["top_matches"] if "debugging" in m["domains"]]
    assert debugging, data["top_matches"]
    assert debugging[0]["score"] >= 50
    assert data["details"]["recommended_skills"] == [debugging[0]["name"]]


def _error_index(with_debugging_skill: bool) -> dict[str, Any]:
    skills = [
        make_skill(
            "pdf-tools",
            "Extract text and tables from PDF files.",
            keywords=["pdf"],
            domains=["pdf"],
        )
    ]
    if with_debugging_skill:
        skills.append(
            make_skill(
                "bug-hunter",
                "Diagnose an error or exception and find the root cause.",
                keywords=["error", "exception", "root", "cause"],
                domains=["debugging"],
            )
        )
    return {"skills": skills}


def test_syntax_error_reaches_a_debugging_skill_that_shares_one_word(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _error_index(with_debugging_skill=True)
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)

    data = run_triage("SyntaxError: unexpected token")

    assert data["action"] == triage.Action.USE_EXISTING
    assert data["details"]["recommended_skills"] == ["bug-hunter"]


def test_error_message_without_a_debugging_skill_still_routes_to_create_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _error_index(with_debugging_skill=False)
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)

    data = run_triage("SyntaxError: unexpected token")

    assert data["action"] == triage.Action.CREATE_NEW


def test_single_term_cap_still_holds_for_a_non_debugging_skill_on_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = {
        "skills": [
            make_skill(
                "token-counter",
                "Count the token usage of a prompt.",
                keywords=["token", "count"],
                domains=["tokens"],
            )
        ]
    }
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)

    data = run_triage("SyntaxError: unexpected token")

    assert data["action"] == triage.Action.CREATE_NEW
    assert all(m["score"] < 50 for m in data["top_matches"])


# ---------------------------------------------------------------------------
# Finding 2: a covered topic never becomes CREATE_NEW on any request branch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "covering_skill"),
    [
        ("help me with a retrospective", "retrospective"),
        ("plan how to build this", "plan"),
        ("which skill handles retrospectives?", "retrospective"),
        ("build a skill for pr comment responses", "pr-comment-responder"),
    ],
)
def test_covered_requests_clarify_instead_of_creating_a_duplicate_on_the_real_index(
    query: str, covering_skill: str, real_index: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(triage, "load_skill_index", lambda: real_index)

    data = run_triage(query)

    assert data["action"] == triage.Action.CLARIFY, data["top_matches"]
    assert covering_skill in data["details"]["recommended_skills"]


def test_which_skill_handles_pull_requests_reaches_use_existing(
    real_index: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(triage, "load_skill_index", lambda: real_index)

    data = run_triage("which skill handles pull requests?")

    assert data["action"] == triage.Action.USE_EXISTING
    assert data["top_matches"][0]["name"] == "pr-review"
    assert data["top_matches"][0]["score"] >= 60


@pytest.mark.parametrize(
    "query",
    [
        "I need to build a social media hook testing loop",
        "which skill handles social media hook testing?",
        "build a skill for social media hook testing",
    ],
)
def test_uncovered_requests_still_route_to_create_new(
    query: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = {
        "skills": [
            make_skill(
                "pdf-tools",
                "Extract text and tables from PDF files.",
                keywords=["pdf"],
                domains=["pdf"],
            )
        ]
    }
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)

    data = run_triage(query)

    assert data["action"] == triage.Action.CREATE_NEW


def test_covering_skills_keeps_exact_names_and_half_coverage_only() -> None:
    matches = [
        {"name": "named", "names_skill": True, "coverage": 0.1},
        {"name": "half", "names_skill": False, "coverage": 0.5},
        {"name": "shared-word", "names_skill": False, "coverage": 0.33},
    ]

    assert [m["name"] for m in triage.covering_skills(matches)] == ["named", "half"]
    assert triage.topic_is_covered(matches)
    assert not triage.topic_is_covered(matches[2:])


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("which skill handles pull requests?", ["pull", "requests"]),
        ("what skill covers retrospectives", ["retrospectives"]),
    ],
)
def test_skill_question_frame_is_not_scored_as_content(query: str, expected: list[str]) -> None:
    stripped = triage.strip_question_frame(query)

    assert triage.tokenize_for_scoring(stripped) == expected


def test_handles_is_a_content_word_outside_a_skill_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = {
        "skills": [
            make_skill(
                "file-tools", "Work with files.", keywords=["file", "files"], domains=["files"]
            )
        ]
    }
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)

    data = run_triage("I need to inspect file handles")

    assert "handles" in triage.tokenize_for_scoring("I need to inspect file handles")
    assert data["action"] == triage.Action.CREATE_NEW


def test_skill_named_after_an_error_class_still_matches_its_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = {
        "skills": [
            make_skill(
                "typeerror",
                "Explain TypeError failures.",
                keywords=["typeerror"],
                domains=["debugging"],
            )
        ]
    }
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)

    data = run_triage("do I have a skill for TypeError?")

    assert data["action"] == triage.Action.USE_EXISTING
    assert "name match: typeerror" in " ".join(data["top_matches"][0]["reasons"])


# ---------------------------------------------------------------------------
# Finding 3: a scaffolding-named skill matches only in a name lookup
# ---------------------------------------------------------------------------


@pytest.fixture
def build_index(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    index = {
        "skills": [
            make_skill(
                "build",
                "Implement a planned change in thin vertical slices with tests.",
                keywords=["build", "implement", "slices"],
                domains=["testing"],
                triggers=["build this"],
            )
        ]
    }
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)
    return index


def _reasons(data: dict[str, Any]) -> str:
    return " ".join(r for m in data["top_matches"] for r in m["reasons"])


@pytest.mark.parametrize(
    "query",
    [
        "build this feature",  # GENERAL
        "I need to build this feature",  # TASK_REQUEST
        "build a skill for this feature",  # EXPLICIT_CREATE
    ],
)
def test_scaffolding_named_skill_is_skipped_outside_a_name_lookup(
    query: str, build_index: dict[str, Any]
) -> None:
    data = run_triage(query)

    reasons = _reasons(data)
    assert "name match: build" not in reasons
    assert "trigger: build this" not in reasons


@pytest.mark.parametrize(
    "query",
    ["do I have a skill for build?", "improve the build skill"],
)
def test_scaffolding_named_skill_still_matches_in_a_name_lookup(
    query: str, build_index: dict[str, Any]
) -> None:
    data = run_triage(query)

    assert data["top_matches"], data
    assert data["top_matches"][0]["name"] == "build"
    assert "name match: build" in _reasons(data)
