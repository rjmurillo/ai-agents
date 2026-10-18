#!/usr/bin/env python3
"""
Review round 4 regression tests for skillforge triage scoring (issue #6647).

Covers the CREATE_NEW gate (a skill that covers the topic blocks it), the
single-term cap for exact one-word names outside create requests, the
in-domain coverage discount, and recall gaps in name lookups.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.skills.skillforge.triage_support import (
    discover_skills,
    make_skill,
    run_triage,
    triage,
)

# ---------------------------------------------------------------------------
# Real-index controls: a covered request must never become CREATE_NEW
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected_tops"),
    [
        ("resolve merge conflicts on my branch", {"merge-resolver"}),
        ("search memory for prior decisions", {"memory", "memory-search"}),
        ("grade quality across domains", {"quality-grades"}),
        ("assess the maintainability of this module", {"code-qualities-assessment"}),
        ("debug this flaky test", {"test"}),
        ("threat model the auth service", {"threat-modeling"}),
    ],
)
def test_covered_requests_never_route_to_create_new_on_the_real_index(
    query: str,
    expected_tops: set[str],
    real_index: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(triage, "load_skill_index", lambda: real_index)

    data = run_triage(query)

    assert data["action"] != triage.Action.CREATE_NEW, data["top_matches"]
    assert data["top_matches"][0]["name"] in expected_tops, data["top_matches"]


@pytest.mark.parametrize(
    ("query", "skill_name"),
    [
        ("debug this flaky test", "test"),
        ("threat model the auth service", "threat-modeling"),
    ],
)
def test_named_skill_requests_reach_use_existing_on_the_real_index(
    query: str, skill_name: str, real_index: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(triage, "load_skill_index", lambda: real_index)

    data = run_triage(query)

    assert data["action"] == triage.Action.USE_EXISTING
    assert data["top_matches"][0]["name"] == skill_name
    assert data["top_matches"][0]["score"] >= 70


# ---------------------------------------------------------------------------
# topic_is_covered and the GENERAL CREATE_NEW gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("matches", "expected"),
    [
        ([], False),
        ([{"names_skill": False, "coverage": 0.33}], False),
        ([{"names_skill": False, "coverage": 0.5}], True),
        ([{"names_skill": True, "coverage": 0.2}], True),
        ([{"names_skill": False, "coverage": 0.2}, {"names_skill": False, "coverage": 1.0}], True),
        ([{}], False),
    ],
)
def test_topic_is_covered(matches: list[dict[str, Any]], expected: bool) -> None:
    assert triage.topic_is_covered(matches) is expected


def _landing_index() -> dict[str, Any]:
    return {
        "skills": [
            make_skill(
                "landing-page",
                "Design and build marketing pages.",
                keywords=["landing", "page"],
                domains=["frontend"],
            ),
            make_skill("xlsx", "Edit spreadsheets.", domains=["spreadsheet"]),
        ]
    }


def test_general_request_naming_a_multi_word_skill_does_not_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _landing_index()
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)

    data = run_triage("design a landing page")

    assert data["details"]["category"] == triage.InputCategory.GENERAL
    assert data["top_matches"][0]["name"] == "landing-page"
    assert any("name match" in r for r in data["top_matches"][0]["reasons"])
    assert data["action"] != triage.Action.CREATE_NEW


def test_general_topic_no_skill_explains_still_routes_to_create_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _landing_index()
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)

    data = run_triage("track beehive humidity through winter")

    assert data["action"] == triage.Action.CREATE_NEW


def test_general_topic_a_low_scoring_skill_explains_does_not_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # phase0-triage.md documents this exemption: a match that explains at least
    # half the content terms covers the topic, even when it scores under 50.
    index = {
        "skills": [
            make_skill("merge-resolver", "Resolve merge conflicts by reading git history."),
        ]
    }
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)

    data = run_triage("resolve merge conflicts")

    top = data["top_matches"][0]
    assert data["details"]["category"] == triage.InputCategory.GENERAL
    assert top["name"] == "merge-resolver"
    assert top["score"] < 50
    assert top["names_skill"] is False
    assert top["coverage"] >= triage.TOPIC_COVERAGE_MIN
    assert data["action"] == triage.Action.CLARIFY


def test_match_dicts_report_coverage_and_name_evidence() -> None:
    skills = _landing_index()["skills"]

    matches = triage.find_matching_skills("design a landing page", skills)

    top = matches[0]
    assert top["names_skill"] is True
    assert 0.0 < top["coverage"] <= 1.0


# ---------------------------------------------------------------------------
# One-word skill names outside create requests are not capped
# ---------------------------------------------------------------------------


# Only "pdf" is explained by the skill, so this request is capped unless the name exempts it.
PDF_ONE_TERM_QUERY = "make a pdf for quarterly payroll numbers"


def _pdf_skill() -> dict[str, Any]:
    return make_skill(
        "pdf",
        "Read, merge, split, and create PDF files.",
        keywords=["pdf", "merge", "split"],
        domains=["pdf", "document"],
    )


@pytest.mark.parametrize(
    "category",
    [
        triage.InputCategory.GENERAL,
        triage.InputCategory.TASK_REQUEST,
        triage.InputCategory.CODE_SNIPPET,
        triage.InputCategory.ERROR_MESSAGE,
    ],
)
def test_exact_one_word_name_is_not_capped_outside_create_requests(category: str) -> None:
    _, reasons, ceiling = triage.score_skill(PDF_ONE_TERM_QUERY, _pdf_skill(), category)

    assert "name match: pdf" in reasons
    assert ceiling is None


@pytest.mark.parametrize("category", [triage.InputCategory.EXPLICIT_CREATE, None])
def test_exact_one_word_name_keeps_the_cap_for_create_requests(category: str | None) -> None:
    _, _, ceiling = triage.score_skill(PDF_ONE_TERM_QUERY, _pdf_skill(), category)

    assert ceiling == triage.SINGLE_TERM_SCORE_CAP


def test_pdf_request_ranks_the_pdf_skill_above_a_spreadsheet_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = {
        "skills": [
            _pdf_skill(),
            make_skill(
                "xlsx",
                "Open, edit, and create spreadsheet, csv, and tsv files with formulas.",
                keywords=["spreadsheet", "csv", "formulas", "data"],
                domains=["spreadsheet", "document"],
            ),
        ]
    }
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)

    data = run_triage("write a pdf report from csv data")

    assert data["top_matches"][0]["name"] == "pdf"
    assert data["action"] == triage.Action.USE_EXISTING


def test_create_request_for_a_test_topic_still_routes_to_create_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = {
        "skills": [
            make_skill(
                "test",
                "Prove a change works across quality gates.",
                keywords=["test", "gates"],
                domains=["testing"],
            )
        ]
    }
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)

    data = run_triage("create a skill for test payment gateways")

    assert data["details"]["category"] == triage.InputCategory.EXPLICIT_CREATE
    assert data["action"] == triage.Action.CREATE_NEW


# ---------------------------------------------------------------------------
# The coverage discount is gentler for a skill in the query's leading domain
# ---------------------------------------------------------------------------


PPTX_DESCRIPTION = (
    "Use this skill any time a .pptx or .potx file is involved in any way, as input, "
    "output, or both. This includes: creating slide decks, pitch decks, or presentations; "
    "reading, parsing, or extracting text from any .pptx or .potx file; editing, "
    "modifying, or updating existing presentations; combining or splitting slide files; "
    "working with templates (.potx), layouts, speaker notes, or comments. Trigger "
    'whenever the user mentions "deck," "slides," "presentation," or references a .pptx '
    "or .potx filename, regardless of what they plan to do with the content afterward."
)
XLSX_DESCRIPTION = (
    "Use this skill any time a spreadsheet file is the primary input or output. This "
    "means any task where the user wants to: open, read, edit, or fix an existing .xlsx, "
    ".xlsm, .xltx, .csv, or .tsv file (e.g., adding columns, computing formulas, "
    "formatting, charting, cleaning messy data); create a new spreadsheet from scratch "
    "or from other data sources; or convert between tabular file formats. Trigger "
    "especially when the user references a spreadsheet file by name or path, and wants "
    "something done to it or produced from it. The deliverable must be a spreadsheet file."
)


def _parsed_skill(tmp_path: Path, name: str, description: str) -> dict[str, Any]:
    """Build a skill record the way discover_skills.py does, from a SKILL.md file."""
    skill_dir = tmp_path / name
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    skill = discover_skills.parse_skill_file(skill_file, "fixture", 1)
    assert skill is not None
    return skill


@pytest.mark.parametrize(
    ("query", "skill_name"),
    [
        ("make a powerpoint deck about quarterly results", "pptx"),
        ("excel workbook formulas pivot tables", "xlsx"),
    ],
)
def test_natural_requests_for_a_document_skill_reach_use_existing(
    query: str, skill_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = {
        "skills": [
            _parsed_skill(tmp_path, "pptx", PPTX_DESCRIPTION),
            _parsed_skill(tmp_path, "xlsx", XLSX_DESCRIPTION),
        ]
    }
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)

    data = run_triage(query)

    assert data["top_matches"][0]["name"] == skill_name
    assert data["top_matches"][0]["score"] >= 70, data["top_matches"]
    assert data["action"] == triage.Action.USE_EXISTING


def test_in_domain_skill_keeps_more_score_than_an_out_of_domain_skill(tmp_path: Path) -> None:
    query = "make a powerpoint deck about quarterly results"
    in_domain = _parsed_skill(tmp_path, "pptx", PPTX_DESCRIPTION)
    assert "presentation" in in_domain["domains"]
    out_of_domain = {**in_domain, "domains": ["document"]}

    in_score, _, _ = triage.score_skill(query, in_domain)
    out_score, _, _ = triage.score_skill(query, out_of_domain)

    assert in_score > out_score


def test_in_domain_skill_still_loses_score_for_unexplained_terms(tmp_path: Path) -> None:
    skill = _parsed_skill(tmp_path, "pptx", PPTX_DESCRIPTION)

    full, _, _ = triage.score_skill("powerpoint deck", skill)
    diluted, reasons, _ = triage.score_skill("powerpoint deck zebra quartz walrus", skill)

    assert diluted < full
    assert any(r.startswith("coverage:") for r in reasons)


# ---------------------------------------------------------------------------
# Recall gaps in name lookups
# ---------------------------------------------------------------------------


def _adr_index() -> dict[str, Any]:
    return {
        "skills": [
            make_skill("adr-generator", "Generate architecture decision records."),
            make_skill("adr-review", "Review architecture decision records."),
            make_skill("xlsx", "Edit spreadsheets.", domains=["spreadsheet"]),
        ]
    }


def test_name_lookup_for_a_short_name_word_lists_the_matching_skills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _adr_index()
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)

    data = run_triage("do I have a skill for adr")

    assert data["details"]["category"] == triage.InputCategory.SKILL_QUESTION
    assert {m["name"] for m in data["top_matches"]} == {"adr-generator", "adr-review"}
    assert data["action"] == triage.Action.CLARIFY
    assert set(data["details"]["recommended_skills"]) == {"adr-generator", "adr-review"}


def test_name_lookup_for_a_short_word_no_skill_name_has_still_creates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = {"skills": [make_skill("xlsx", "Edit spreadsheets.", domains=["spreadsheet"])]}
    monkeypatch.setattr(triage, "load_skill_index", lambda: index)

    data = run_triage("do I have a skill for adr")

    assert data["action"] == triage.Action.CREATE_NEW


def test_short_word_earns_partial_name_credit_only_in_a_name_lookup() -> None:
    skill = make_skill("adr-generator", "Generate architecture decision records.")

    lookup, lookup_reasons, _ = triage.score_skill(
        "adr", skill, triage.InputCategory.SKILL_QUESTION
    )
    general, _, _ = triage.score_skill("adr", skill, triage.InputCategory.GENERAL)

    assert lookup > 0
    assert any(r.startswith("partial name: adr") for r in lookup_reasons)
    assert general == 0


@pytest.mark.parametrize(
    ("query", "words", "expected"),
    [
        ("do I have a skill for adr", frozenset({"adr", "generator"}), True),
        ("do I have a skill for adr", frozenset({"xlsx"}), False),
        ("write an adr for billing", frozenset({"adr"}), True),
        ("write documentation for billing", frozenset({"documentation"}), False),
        ("", frozenset({"adr"}), False),
    ],
)
def test_has_recall_gap(query: str, words: frozenset[str], expected: bool) -> None:
    assert triage.has_recall_gap(query, words) is expected
