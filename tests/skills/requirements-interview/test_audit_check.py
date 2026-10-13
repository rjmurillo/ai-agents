"""Coverage-ledger behavior for the ambiguity-audit mode (issue #5429 fixtures)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import audit_check
import pytest
from audit_check import NO_GAPS_VERDICT, OWNER_DECISION_NOTE, ledger_problems, plan_questions
from audit_paths import FIXTURES
from ledgers import anchor, ask, ledger, option


def run(spec: str, data: dict[str, Any], root: Path = Path("."), **caps: int) -> dict[str, Any]:
    lines = (FIXTURES / spec).read_text(encoding="utf-8").splitlines()
    candidates, problems = ledger_problems(data, lines, root)
    if problems:
        return {"status": "invalid", "problems": problems}
    return plan_questions(
        candidates, data, caps.get("max_options", 4), caps.get("max_questions", 4)
    )


def problem_text(result: dict[str, Any]) -> str:
    return " | ".join(p["problem"] for p in result["problems"])


CONTRADICTION = ask(
    "Q1",
    "contradiction",
    [
        anchor("3.1 Session count", "at most 3 active sessions"),
        anchor("5.2 Concurrency", "up to 5 concurrent sessions"),
    ],
    statement="How many concurrent sessions may one account hold?",
)


def test_contradiction_yields_one_question_anchored_on_both_sides() -> None:
    result = run("contradiction_spec.md", ledger([CONTRADICTION]))
    assert result["status"] == "ask"
    (entry,) = result["batch"]
    assert entry["id"] == "Q1"
    assert [a["section"] for a in entry["anchors"]] == ["3.1 Session count", "5.2 Concurrency"]
    assert entry["page"] == ["a", "b"]


def test_contradiction_with_one_section_is_rejected() -> None:
    one_sided = ask("Q1", "contradiction", [anchor("3.1", "at most 3 active sessions")])
    result = run("contradiction_spec.md", ledger([one_sided]))
    assert result["status"] == "invalid"
    assert "two different sections" in problem_text(result)


def test_answer_elsewhere_is_recorded_and_not_asked() -> None:
    answered = {
        "id": "Q1",
        "category": "data_constraint",
        "disposition": "answered_in_document",
        "anchors": [anchor("4. Audit trail", "How long audit entries persist")],
        "evidence": anchor("2. Retention", "kept for 90 days"),
        "answer": "Audit entries are kept for 90 days.",
    }
    result = run("answered_elsewhere_spec.md", ledger([answered]))
    assert result["status"] == "no_material_gaps"
    assert "batch" not in result
    assert result["recorded"] == [
        {
            "id": "Q1",
            "disposition": "answered_in_document",
            "answer": "Audit entries are kept for 90 days.",
            "evidence": anchor("2. Retention", "kept for 90 days"),
        }
    ]


def test_answer_evidence_must_exist_in_the_document() -> None:
    answered = {
        "id": "Q1",
        "category": "data_constraint",
        "disposition": "answered_in_document",
        "anchors": [anchor("4. Audit trail", "How long audit entries persist")],
        "evidence": anchor("2. Retention", "kept for 30 days"),
        "answer": "Thirty days.",
    }
    result = run("answered_elsewhere_spec.md", ledger([answered]))
    assert result["status"] == "invalid"
    assert "evidence:" in problem_text(result)


def test_recorded_answer_needs_the_answer_text() -> None:
    answered = {
        "id": "Q1",
        "category": "data_constraint",
        "disposition": "answered_in_document",
        "anchors": [anchor("4. Audit trail", "How long audit entries persist")],
        "evidence": anchor("2. Retention", "kept for 90 days"),
    }
    assert "answer:" in problem_text(run("answered_elsewhere_spec.md", ledger([answered])))


def test_codebase_answer_is_recorded(tmp_path: Path) -> None:
    (tmp_path / "limits.py").write_text("MAX = 3\nMIN = 1\n", encoding="utf-8")
    answered = {
        "id": "Q1",
        "category": "data_constraint",
        "disposition": "answered_in_codebase",
        "anchors": [anchor("3.1", "at most 3 active sessions")],
        "evidence": {"path": "limits.py", "lines": [1, 1]},
        "answer": "The code caps sessions at 3.",
    }
    result = run("contradiction_spec.md", ledger([answered]), root=tmp_path)
    assert result["status"] == "no_material_gaps"
    assert result["recorded"][0]["disposition"] == "answered_in_codebase"


@pytest.mark.parametrize(
    "evidence",
    [
        {"path": "missing.py", "lines": [1, 1]},
        {"path": "../outside.py", "lines": [1, 1]},
        {"path": "limits.py", "lines": [1, 9]},
        {"path": "limits.py", "lines": "1-1"},
        {"path": "  ", "lines": [1, 1]},
        "limits.py",
    ],
)
def test_bad_codebase_evidence_is_rejected(tmp_path: Path, evidence: Any) -> None:
    (tmp_path / "limits.py").write_text("MAX = 3\n", encoding="utf-8")
    (tmp_path.parent / "outside.py").write_text("X = 1\n", encoding="utf-8")
    answered = {
        "id": "Q1",
        "category": "data_constraint",
        "disposition": "answered_in_codebase",
        "anchors": [anchor("3.1", "at most 3 active sessions")],
        "evidence": evidence,
        "answer": "x",
    }
    result = run("contradiction_spec.md", ledger([answered]), root=tmp_path)
    assert result["status"] == "invalid"
    assert "evidence:" in problem_text(result)


def test_undefined_term_gets_a_closed_definition_decision() -> None:
    term = ask(
        "Q1",
        "terminology",
        [
            anchor("1. Pricing", "Each active user is billed"),
            anchor("2. Reports", "every active user"),
        ],
        statement="What counts as an active user?",
        options=[
            option("login", "Signed in during the period", "Only users who signed in are billed."),
            option("seat", "Holds a paid seat", "Billing follows seats, signed in or not."),
            option("event", "Triggered any event", "Any API event makes the user billable."),
        ],
    )
    result = run("terminology_spec.md", ledger([term]))
    assert result["status"] == "ask"
    (entry,) = result["batch"]
    assert entry["page"] == ["login", "seat", "event"]
    assert entry["category"] == "terminology"


def test_other_is_never_listed_as_an_option() -> None:
    term = ask(
        "Q1",
        "terminology",
        [anchor("1. Pricing", "Each active user")],
        options=[option("a", "Seat"), option("b", "Login"), option("o", "Other: specify")],
    )
    result = run("terminology_spec.md", ledger([term]))
    assert result["status"] == "invalid"
    assert "'Other'" in problem_text(result)


def test_cosmetic_duplicate_options_are_incomplete() -> None:
    term = ask(
        "Q1",
        "terminology",
        [anchor("1. Pricing", "Each active user")],
        options=[option("a", "Seat"), option("b", "seat")],
    )
    result = run("terminology_spec.md", ledger([term]))
    assert result["status"] == "incomplete"
    assert "options_not_distinct" in result["incomplete"]["Q1"]


def test_missing_statement_is_incomplete() -> None:
    term = ask("Q1", "terminology", [anchor("1. Pricing", "Each active user")], statement="")
    result = run("terminology_spec.md", ledger([term]))
    assert result["incomplete"] == {"Q1": ["statement"]}


def test_owner_decision_carries_the_no_recommendation_note() -> None:
    result = run("contradiction_spec.md", ledger([CONTRADICTION]))
    assert result["batch"][0]["recommendation_note"] == OWNER_DECISION_NOTE


def test_evidence_backed_recommendation_is_accepted() -> None:
    backed = {
        **CONTRADICTION,
        "recommendation": "a",
        "recommendation_reason": "The code enforces 3.",
        "recommendation_evidence": "src/limits.py:1",
    }
    result = run("contradiction_spec.md", ledger([backed]))
    assert result["status"] == "ask"
    assert "recommendation_note" not in result["batch"][0]


def test_recommendation_without_evidence_is_rejected() -> None:
    unbacked = {**CONTRADICTION, "recommendation": "a", "recommendation_reason": "Feels right."}
    result = run("contradiction_spec.md", ledger([unbacked]))
    assert result["status"] == "invalid"
    assert "recommendation_evidence" in problem_text(result)


def dependent_ledger(**extra: Any) -> dict[str, Any]:
    first = ask(
        "Q1",
        "permissions",
        [anchor("3.1", "at most 3 active sessions")],
        statement="Share sessions?",
    )
    first["options"] = [option("share", "Shared"), option("solo", "Per user")]
    second = ask(
        "Q2", "concurrency", [anchor("5.2", "up to 5 concurrent sessions")], statement="Pool size?"
    )
    second["requires"] = {"Q1": "share"}
    second["options"] = [
        option("small", "Small pool"),
        option("large", "Large pool", "Large pool becomes the rule."),
    ]
    return ledger([first, second], **extra)


def test_prerequisite_is_asked_first_and_dependent_is_deferred() -> None:
    result = run("contradiction_spec.md", dependent_ledger())
    assert [e["id"] for e in result["batch"]] == ["Q1"]
    assert result["deferred"] == ["Q2"]


def test_answer_that_keeps_the_dependent_alive_releases_it() -> None:
    result = run("contradiction_spec.md", dependent_ledger(answers={"Q1": "share"}))
    assert [e["id"] for e in result["batch"]] == ["Q2"]
    assert result["deferred"] == []


def test_answer_that_voids_the_dependent_prunes_it() -> None:
    result = run("contradiction_spec.md", dependent_ledger(answers={"Q1": "solo"}))
    assert result["status"] == "resolved"
    assert result["pruned"] == ["Q2"]


def test_option_level_requirement_filters_options_and_keeps_ids() -> None:
    data = dependent_ledger(answers={"Q1": "share"})
    data["candidates"][1].pop("requires")
    data["candidates"][1]["options"] = [
        option("small", "Small pool"),
        option("large", "Large pool"),
        {**option("solo_only", "One slot"), "requires": {"Q1": "solo"}},
    ]
    result = run("contradiction_spec.md", data)
    assert result["batch"][0]["id"] == "Q2"
    assert result["batch"][0]["page"] == ["small", "large"]


def test_recommendation_removed_by_an_answer_must_be_revised() -> None:
    data = dependent_ledger(answers={"Q1": "share"})
    data["candidates"][1].pop("requires")
    data["candidates"][1]["options"] = [
        option("small", "Small pool"),
        option("large", "Large pool"),
        {**option("solo_only", "One slot"), "requires": {"Q1": "solo"}},
    ]
    data["candidates"][1].update(
        recommendation="solo_only",
        recommendation_reason="Matches the code.",
        recommendation_evidence="src/pool.py:3",
    )
    result = run("contradiction_spec.md", data)
    assert result["status"] == "revise_recommendation"
    assert result["stale_recommendations"] == {"Q2": "solo_only"}


def six_independent(count: int = 6, **extra: Any) -> dict[str, Any]:
    candidates = [
        ask(f"Q{n}", "edge_case", [anchor("3.2", "idle session expires")])
        for n in range(1, count + 1)
    ]
    return ledger(candidates, **extra)


def test_batch_respects_the_observed_question_limit() -> None:
    result = run("contradiction_spec.md", six_independent())
    assert [e["id"] for e in result["batch"]] == ["Q1", "Q2", "Q3", "Q4"]
    assert result["max_questions_per_call"] == 4
    assert result["harness_limit_observed"] is True


def test_next_batch_resumes_after_answers_without_renumbering() -> None:
    answers = {f"Q{n}": "a" for n in (1, 2, 3, 4)}
    result = run("contradiction_spec.md", six_independent(answers=answers))
    assert [e["id"] for e in result["batch"]] == ["Q5", "Q6"]


def test_a_lower_harness_limit_shrinks_the_batch() -> None:
    result = run("contradiction_spec.md", six_independent(), max_questions=2)
    assert [e["id"] for e in result["batch"]] == ["Q1", "Q2"]


def test_batching_is_deterministic() -> None:
    first = run("contradiction_spec.md", six_independent())
    second = run("contradiction_spec.md", six_independent())
    assert first == second


def test_many_options_split_into_pages_with_a_continuation() -> None:
    many = ask("Q1", "edge_case", [anchor("3.2", "idle session expires")])
    many["options"] = [option(f"o{n}", f"Choice {n}") for n in range(1, 7)]
    result = run("contradiction_spec.md", ledger([many]))
    entry = result["batch"][0]
    assert entry["pages"] == [["o1", "o2", "o3", "_more"], ["o4", "o5", "o6"]]
    assert entry["split"] is True
    paged = run("contradiction_spec.md", ledger([many], paging={"Q1": 1}))
    assert paged["batch"][0]["page"] == ["o4", "o5", "o6"]


def test_paging_past_the_last_page_raises() -> None:
    many = ask("Q1", "edge_case", [anchor("3.2", "idle session expires")])
    with pytest.raises(ValueError, match="page"):
        run("contradiction_spec.md", ledger([many], paging={"Q1": 3}))


def test_a_lower_option_cap_changes_the_pages() -> None:
    many = ask("Q1", "edge_case", [anchor("3.2", "idle session expires")])
    many["options"] = [option(f"o{n}", f"Choice {n}") for n in range(1, 5)]
    result = run("contradiction_spec.md", ledger([many]), max_options=3)
    assert result["batch"][0]["pages"] == [["o1", "o2", "_more"], ["o3", "o4"]]


def test_a_held_decision_is_reported_and_blocks_its_dependents() -> None:
    data = dependent_ledger(answers={"Q1": "_hold"})
    data["candidates"][0].update(
        allow_hold=True, hold_reopen_condition="Reopen when sharing is decided."
    )
    result = run("contradiction_spec.md", data)
    assert result["status"] == "held"
    assert result["held"] == [{"id": "Q1", "reopen_condition": "Reopen when sharing is decided."}]


def test_clean_spec_returns_no_material_gaps() -> None:
    result = run("clean_spec.md", ledger([]))
    assert result["status"] == "no_material_gaps"
    assert result["verdict"] == NO_GAPS_VERDICT == "NO MATERIAL GAPS"
    assert result["recorded"] == []


def test_all_answered_ledger_resolves() -> None:
    result = run("contradiction_spec.md", ledger([CONTRADICTION], answers={"Q1": "a"}))
    assert result["status"] == "resolved"


def test_unreviewed_category_blocks_the_verdict() -> None:
    data = ledger([])
    data["coverage_reviewed"] = ["edge_case"]
    result = run("clean_spec.md", data)
    assert result["status"] == "invalid"
    assert "coverage_reviewed" in problem_text(result)


def test_duplicate_and_blank_ids_are_rejected() -> None:
    one = ask("Q1", "edge_case", [anchor("3.2", "idle session expires")])
    blank = ask("", "edge_case", [anchor("3.2", "idle session expires")])
    result = run("contradiction_spec.md", ledger([one, dict(one), blank]))
    assert problem_text(result).count("id: required and unique") == 2


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"category": "vibes"}, "category:"),
        ({"disposition": "maybe"}, "disposition:"),
        ({"anchors": []}, "at least one source anchor"),
        ({"anchors": [anchor("3.2", "no such text")]}, "not found verbatim"),
    ],
)
def test_candidate_fields_are_validated(patch: dict[str, Any], message: str) -> None:
    candidate = {**ask("Q1", "edge_case", [anchor("3.2", "idle session expires")]), **patch}
    assert message in problem_text(run("contradiction_spec.md", ledger([candidate])))


def test_paging_past_a_later_batch_members_last_page_raises() -> None:
    first = ask("Q1", "edge_case", [anchor("3.2", "idle session expires")])
    second = ask("Q2", "edge_case", [anchor("3.2", "idle session expires")])
    with pytest.raises(ValueError, match="Q2 is 5"):
        run("contradiction_spec.md", ledger([first, second], paging={"Q2": 5}))


def test_missing_decision_question_engine_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit_check, "_DQ_RELATIVE", Path("nowhere", "engine.py"))
    with pytest.raises(FileNotFoundError, match="engine not found"):
        audit_check.load_decision_question()
