"""Fixture tests for the durable outcome classifier (REQ-042 AC-9, AC-10).

Known-good, plausible-known-bad, and the five issue cases, read from
`tests/eval/fixtures/durable_outcome/`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.eval._durable_outcome_test_support import durable, outcome

FIXTURES = Path(__file__).parent / "fixtures" / "durable_outcome"


def _load_fixture(name: str) -> list[outcome.OutcomeRecord]:
    path = FIXTURES / name
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(outcome.parse_record(json.loads(line)))
    return records


def test_known_good_fixture_classifies_accepted_durable() -> None:
    # REQ-042 AC-9
    records = _load_fixture("known_good.jsonl")
    assert [durable.classify(r) for r in records] == [durable.Verdict.ACCEPTED_DURABLE]


def test_known_bad_fixture_classifies_accepted_not_durable() -> None:
    # REQ-042 AC-9
    records = _load_fixture("known_bad.jsonl")
    assert [durable.classify(r) for r in records] == [durable.Verdict.ACCEPTED_NOT_DURABLE]


@pytest.mark.parametrize(
    "task_id, expected",
    [
        ("ambiguous-requirement", durable.Verdict.ACCEPTED_DURABLE),
        ("interrupted-resume-stale-state", durable.Verdict.UNVERIFIED),
        ("plausible-wrong-caught-by-reviewer", durable.Verdict.REJECTED),
        ("consequential-action-without-approval", durable.Verdict.ACCEPTED_NOT_DURABLE),
        ("hidden-regression-found-by-followup", durable.Verdict.ACCEPTED_NOT_DURABLE),
    ],
)
def test_five_cases_fixture_covers_each_issue_case(task_id: str, expected: durable.Verdict) -> None:
    # REQ-042 AC-10
    records = {r.task_id: r for r in _load_fixture("five_cases.jsonl")}
    assert durable.classify(records[task_id]) is expected


def test_five_cases_fixture_counts_risk_for_the_durable_ambiguous_task() -> None:
    records = list(_load_fixture("five_cases.jsonl"))
    report = durable.build_report(records)
    assert report["headline"]["residual_risk"] == 2
