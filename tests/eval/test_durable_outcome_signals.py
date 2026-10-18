"""Tests for the reviewer, rollback, and human-time signals in `_durable_outcome.py` (issue #5768).

A `null` signal is missing evidence and classifies `UNVERIFIED`. A measured zero is a
measurement. The report counts unmeasured signals instead of folding them into a total
of zero, and a comparison refuses two configurations that used different reviewers.
"""

from __future__ import annotations

import pytest

from tests.eval._durable_outcome_test_support import (
    classify_record,
    durable,
    durable_record,
    make_record,
    outcome,
)


def test_null_human_correction_minutes_yields_unverified() -> None:
    # An unattended run has no human timing. Missing time is not zero time.
    verdict = classify_record(economics={"human_correction_minutes": None})
    assert verdict is durable.Verdict.UNVERIFIED


def test_a_human_timed_zero_is_a_measurement_not_missing_evidence() -> None:
    verdict = classify_record(economics={"human_correction_minutes": 0.0})
    assert verdict is durable.Verdict.ACCEPTED_DURABLE


def test_a_rejected_run_stays_rejected_when_signals_are_null() -> None:
    # Classifier order: a failed deterministic check rejects before the null gate.
    verdict = classify_record(
        execution={"deterministic_acceptance": "FAIL"},
        durable={"review_findings": None, "rollback_events": None},
        economics={"human_correction_minutes": None},
    )
    assert verdict is durable.Verdict.REJECTED


def test_a_measured_rollback_demotes_an_accepted_run() -> None:
    verdict = classify_record(durable={"rollback_events": 1})
    assert verdict is durable.Verdict.ACCEPTED_NOT_DURABLE


def test_build_report_totals_reviewer_and_rollback_signals() -> None:
    records = []
    for index, (findings, rollbacks) in enumerate([(0, 0), (3, 1), (2, 0)]):
        data = make_record(task_id=f"t{index}")
        data["durable"] = {
            **data["durable"],
            "review_findings": findings,
            "rollback_events": rollbacks,
        }
        records.append(outcome.parse_record(data))
    signals = durable.build_report(records)["durable_signals"]
    assert signals == {
        "review_findings_total": 5,
        "review_findings_unmeasured": 0,
        "rollback_events_total": 1,
        "rollback_events_unmeasured": 0,
        "human_correction_unmeasured": 0,
    }


def test_build_report_counts_unmeasured_signals_instead_of_folding_them_into_zero() -> None:
    clean = make_record(task_id="t1")
    unmeasured = make_record(task_id="t2")
    unmeasured["durable"] = {
        **unmeasured["durable"],
        "review_findings": None,
        "rollback_events": None,
    }
    unmeasured["economics"] = {**unmeasured["economics"], "human_correction_minutes": None}
    report = durable.build_report([outcome.parse_record(clean), outcome.parse_record(unmeasured)])
    assert report["durable_signals"] == {
        "review_findings_total": 0,
        "review_findings_unmeasured": 1,
        "rollback_events_total": 0,
        "rollback_events_unmeasured": 1,
        "human_correction_unmeasured": 1,
    }
    assert report["status"] == "UNVERIFIED"


def test_build_report_correction_percentiles_tolerate_untimed_human_minutes() -> None:
    data = make_record()
    data["economics"] = {**data["economics"], "human_correction_minutes": None}
    report = durable.build_report([outcome.parse_record(data)])
    assert report["correction_minutes_percentiles"]["p50"] == 0.0
    assert report["verdict_counts"]["UNVERIFIED"] == 1


def test_compare_refuses_differing_reviewer_configs() -> None:
    baseline = [outcome.parse_record(durable_record("t1", "reduced"))]
    candidate_data = durable_record("t1", "full")
    candidate_data["config"] = {**candidate_data["config"], "reviewer": "claude:haiku:low"}
    with pytest.raises(outcome.DurableOutcomeError, match="reviewer"):
        durable.compare(baseline, [outcome.parse_record(candidate_data)])


def test_compare_is_unverified_when_one_side_lacks_human_timing() -> None:
    baseline = [outcome.parse_record(durable_record("t1", "reduced"))]
    candidate_data = durable_record("t1", "full")
    candidate_data["economics"] = {**candidate_data["economics"], "human_correction_minutes": None}
    result = durable.compare(baseline, [outcome.parse_record(candidate_data)])
    assert result["result"] == "UNVERIFIED"


def test_unmeasured_review_findings_count_accepted_runs_only() -> None:
    records = []
    for index in range(3):
        data = make_record(task_id=f"rejected{index}")
        data["execution"] = {**data["execution"], "deterministic_acceptance": "FAIL"}
        data["durable"] = {**data["durable"], "review_findings": None}
        records.append(outcome.parse_record(data))
    for index in range(2):
        data = make_record(task_id=f"reviewed{index}")
        data["durable"] = {**data["durable"], "review_findings": index}
        records.append(outcome.parse_record(data))
    unreviewed = make_record(task_id="unreviewed")
    unreviewed["durable"] = {**unreviewed["durable"], "review_findings": None}
    records.append(outcome.parse_record(unreviewed))
    signals = durable.build_report(records)["durable_signals"]
    assert signals["review_findings_unmeasured"] == 1
    assert signals["review_findings_total"] == 1
