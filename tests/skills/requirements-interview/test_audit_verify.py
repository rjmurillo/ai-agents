"""Rebuild verification for the ambiguity-audit mode."""

from __future__ import annotations

from typing import Any

import pytest
from audit_check import ledger_problems
from audit_paths import FIXTURES
from audit_verify import verify_rebuild
from ledgers import anchor, ask, ledger

SOURCE = (FIXTURES / "rebuild_source.md").read_text(encoding="utf-8")
REBUILT = (FIXTURES / "rebuild_ok.md").read_text(encoding="utf-8")
Q1_TEXT = "The concurrent session limit is 3 per account."
Q1_OLD = "Each account supports up to 5 concurrent sessions."

LEDGER = ledger(
    [
        ask(
            "Q1",
            "contradiction",
            [
                anchor("3. Limits", "at most 3 active sessions"),
                anchor("5. Account policy", "up to 5 concurrent sessions"),
            ],
        ),
        ask("Q2", "edge_case", [anchor("6. Terms", "An active user is anyone with a session.")]),
    ]
)
LOG: list[dict[str, Any]] = [
    {"id": "Q1", "outcome": "accepted", "text": Q1_TEXT, "replaces": [Q1_OLD]},
    {"id": "Q2", "outcome": "open"},
]


def verify(rebuilt: str = REBUILT, log: list[dict[str, Any]] | None = None, source: str = SOURCE):
    candidates, problems = ledger_problems(LEDGER, source.splitlines(), FIXTURES)
    assert not problems
    return verify_rebuild(candidates, LOG if log is None else log, source, rebuilt)


def messages(result: dict[str, Any]) -> str:
    return " | ".join(p["problem"] for p in result["problems"])


def test_good_rebuild_verifies() -> None:
    result = verify()
    assert result["status"] == "verified"
    assert result["problems"] == []


def test_decision_log_is_keyed_by_id_and_source_anchor() -> None:
    log = verify()["decision_log"]
    assert [(e["id"], e["outcome"]) for e in log] == [("Q1", "accepted"), ("Q2", "open")]
    assert log[0]["anchors"][1]["section"] == "5. Account policy"


def test_growth_is_an_observation_and_never_fails_the_run() -> None:
    padded = REBUILT + "\n" + "Extra context line.\n" * 200
    result = verify(rebuilt=padded)
    assert result["status"] == "verified"
    assert result["growth"]["delta_chars"] == len(padded) - len(SOURCE)
    assert "observation only" in result["growth"]["note"]


def test_accepted_decision_duplicated_in_the_rebuild_fails() -> None:
    result = verify(rebuilt=REBUILT + "\n" + Q1_TEXT + "\n")
    assert result["status"] == "failed"
    assert "appears 2 times" in messages(result)


def test_accepted_decision_missing_from_the_rebuild_fails() -> None:
    result = verify(rebuilt=REBUILT.replace(Q1_TEXT, "Sessions are limited."))
    assert "appears 0 times" in messages(result)


def test_text_already_in_the_source_proves_nothing() -> None:
    log = [{**LOG[0], "text": "Sessions are listed on the account page."}, LOG[1]]
    assert "already exists in the source" in messages(verify(log=log))


def test_superseded_text_left_in_place_fails() -> None:
    result = verify(rebuilt=REBUILT + "\n" + Q1_OLD + "\n")
    assert "still in the rebuilt document" in messages(result)


def test_replaced_quote_must_come_from_the_source() -> None:
    log = [{**LOG[0], "replaces": ["Not in the source."]}, LOG[1]]
    assert "is not in the source" in messages(verify(log=log))


def test_accepted_contradiction_must_supersede_a_side() -> None:
    log = [{"id": "Q1", "outcome": "accepted", "text": Q1_TEXT}, LOG[1]]
    assert "must supersede one side" in messages(verify(log=log))


def test_accepted_decision_needs_its_text() -> None:
    log = [{"id": "Q1", "outcome": "accepted", "replaces": [Q1_OLD]}, LOG[1]]
    assert "needs the exact text" in messages(verify(log=log))


def test_open_decision_needs_an_open_decisions_section() -> None:
    result = verify(rebuilt=REBUILT.split("## Open decisions")[0])
    assert "no 'Open decisions' section" in messages(result)


def test_open_decision_must_be_listed_exactly_once() -> None:
    twice = REBUILT + "- Q2: restated.\n"
    unlisted = REBUILT.replace("Q2", "Q7")
    assert "appears 2 times under" in messages(verify(rebuilt=twice))
    assert "appears 0 times under" in messages(verify(rebuilt=unlisted))


def test_open_decision_may_not_silently_drop_its_source_text() -> None:
    result = verify(
        rebuilt=REBUILT.replace("An active user is anyone with a session.", "Users exist.")
    )
    assert "removed without a decision" in messages(result)


def test_unaffected_source_line_deleted_fails() -> None:
    result = verify(rebuilt=REBUILT.replace("Sessions are listed on the account page.\n", ""))
    assert "unaffected source line deleted" in messages(result)


def test_unlogged_ask_candidate_fails() -> None:
    assert "no decision log entry" in messages(verify(log=[LOG[0]]))


def test_log_entry_for_unknown_id_fails() -> None:
    assert "matches no ask candidate" in messages(
        verify(log=[*LOG, {"id": "Q9", "outcome": "open"}])
    )


def test_unknown_outcome_fails() -> None:
    assert "outcome:" in messages(verify(log=[LOG[0], {"id": "Q2", "outcome": "skipped"}]))


def test_recorded_candidates_need_no_log_entry() -> None:
    answered = {
        "id": "Q3",
        "category": "edge_case",
        "disposition": "answered_in_document",
        "anchors": [anchor("6. Terms", "An active user")],
        "evidence": anchor("3. Limits", "idle session expires"),
        "answer": "Thirty minutes.",
    }
    data = ledger([*LEDGER["candidates"], answered])
    candidates, problems = ledger_problems(data, SOURCE.splitlines(), FIXTURES)
    assert not problems
    assert verify_rebuild(candidates, LOG, SOURCE, REBUILT)["status"] == "verified"


@pytest.mark.parametrize("heading", ["## Open decisions", "# Open Decisions", "### OPEN DECISIONS"])
def test_open_decisions_heading_matches_any_level_and_case(heading: str) -> None:
    assert verify(rebuilt=REBUILT.replace("## Open decisions", heading))["status"] == "verified"
