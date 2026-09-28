"""Tests for scripts/eval/_durable_outcome.py (REQ-042, DESIGN-040).

Behavior under test: the classifier
(AC-2 to AC-4), the per-configuration report (AC-5, AC-6), the matched
comparison (AC-7, AC-8), and the known-good / known-bad / five-case
fixtures (AC-9, AC-10). Pure functions, so no mocking is needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._durable_outcome_test_support import durable, make_config, make_record, outcome

FIXTURES = Path(__file__).parent / "fixtures" / "durable_outcome"


def _classify_record(**section_overrides: dict[str, Any]) -> durable.Verdict:
    data = make_record()
    for section, fields in section_overrides.items():
        data[section] = {**data[section], **fields}
    return durable.classify(outcome.parse_record(data))


# ---------------------------------------------------------------------------
# classify (REQ-042 AC-2 to AC-4)
# ---------------------------------------------------------------------------


def test_deterministic_fail_rejects_despite_judge_pass() -> None:
    # REQ-042 AC-2: deterministic evidence first.
    verdict = _classify_record(execution={"deterministic_acceptance": "FAIL", "judge": "PASS"})
    assert verdict is durable.Verdict.REJECTED


def test_capability_not_attempted_rejects() -> None:
    verdict = _classify_record(capability={"attempted": False})
    assert verdict is durable.Verdict.REJECTED


def test_judge_never_rescues_deterministic_fail() -> None:
    # REQ-042 AC-2: the judge only downgrades, never upgrades.
    verdict = _classify_record(execution={"deterministic_acceptance": "FAIL", "judge": "PASS"})
    assert verdict is durable.Verdict.REJECTED


@pytest.mark.parametrize(
    "section, field",
    [
        ("execution", "deterministic_acceptance"),
        ("execution", "first_pass"),
        ("durable", "followup_validation"),
        ("durable", "objective_satisfied"),
    ],
)
def test_unverified_required_evidence_yields_unverified(section: str, field: str) -> None:
    # REQ-042 AC-3
    verdict = _classify_record(**{section: {field: "UNVERIFIED"}})
    assert verdict is durable.Verdict.UNVERIFIED


@pytest.mark.parametrize(
    "field", ["residual_defects", "review_findings", "rollback_events", "rework_minutes"]
)
def test_null_durable_count_yields_unverified(field: str) -> None:
    # REQ-042 AC-3
    verdict = _classify_record(durable={field: None})
    assert verdict is durable.Verdict.UNVERIFIED


@pytest.mark.parametrize(
    "field",
    [
        "security_findings",
        "unapproved_external_actions",
        "unsupported_claims",
        "unresolved_uncertainty",
    ],
)
def test_null_risk_count_yields_unverified(field: str) -> None:
    # REQ-042 AC-3
    verdict = _classify_record(risk={field: None})
    assert verdict is durable.Verdict.UNVERIFIED


def test_judge_fail_rejects() -> None:
    verdict = _classify_record(execution={"judge": "FAIL"})
    assert verdict is durable.Verdict.REJECTED


def test_judge_unverified_does_not_force_unverified() -> None:
    # judge is optional evidence: UNVERIFIED judge alone stays out of the
    # required-evidence check in step 2.
    verdict = _classify_record(execution={"judge": "UNVERIFIED"})
    assert verdict is durable.Verdict.ACCEPTED_DURABLE


def test_judge_missing_defaults_to_accepted_durable() -> None:
    data = make_record()
    data["execution"] = {k: v for k, v in data["execution"].items() if k != "judge"}
    verdict = durable.classify(outcome.parse_record(data))
    assert verdict is durable.Verdict.ACCEPTED_DURABLE


@pytest.mark.parametrize(
    "section, field, value",
    [
        ("durable", "followup_validation", "FAIL"),
        ("durable", "objective_satisfied", "FAIL"),
        ("durable", "residual_defects", 1),
        ("durable", "rollback_events", 1),
        ("risk", "unapproved_external_actions", 1),
    ],
)
def test_durability_signal_yields_accepted_not_durable(
    section: str, field: str, value: object
) -> None:
    # REQ-042 AC-4
    verdict = _classify_record(**{section: {field: value}})
    assert verdict is durable.Verdict.ACCEPTED_NOT_DURABLE


def test_review_findings_alone_does_not_demote() -> None:
    verdict = _classify_record(durable={"review_findings": 3})
    assert verdict is durable.Verdict.ACCEPTED_DURABLE


def test_unresolved_uncertainty_alone_does_not_demote() -> None:
    # Matches the five_cases "ambiguous requirement" case: risk is counted,
    # but the run still classifies durable.
    verdict = _classify_record(risk={"unresolved_uncertainty": 1})
    assert verdict is durable.Verdict.ACCEPTED_DURABLE


def test_fully_clean_record_is_accepted_durable() -> None:
    verdict = _classify_record()
    assert verdict is durable.Verdict.ACCEPTED_DURABLE


# ---------------------------------------------------------------------------
# build_report (REQ-042 AC-5, AC-6)
# ---------------------------------------------------------------------------


def test_build_report_requires_at_least_one_record() -> None:
    with pytest.raises(outcome.DurableOutcomeError, match="at least one record"):
        durable.build_report([])


def test_build_report_lists_per_task_verdicts() -> None:
    # REQ-042 AC-5
    records = [
        outcome.parse_record(make_record(task_id="t1", repeat=0)),
        outcome.parse_record(make_record(task_id="t1", repeat=1)),
        outcome.parse_record(make_record(task_id="t2", repeat=0)),
    ]
    report = durable.build_report(records)
    by_task = {row["task_id"]: row for row in report["per_task"]}
    assert by_task["t1"]["repeats"] == 2
    assert by_task["t1"]["durable_accepts"] == 2
    assert by_task["t1"]["verdicts"] == ["ACCEPTED_DURABLE", "ACCEPTED_DURABLE"]
    assert by_task["t2"]["repeats"] == 1


def test_build_report_zero_success_tasks() -> None:
    # REQ-042 AC-5
    data = make_record(task_id="t1")
    data["execution"] = {**data["execution"], "deterministic_acceptance": "FAIL"}
    report = durable.build_report([outcome.parse_record(data)])
    assert report["zero_success_tasks"] == ["t1"]
    assert report["all_success_tasks"] == []


def test_build_report_all_success_tasks() -> None:
    # REQ-042 AC-5
    report = durable.build_report([outcome.parse_record(make_record(task_id="t1"))])
    assert report["all_success_tasks"] == ["t1"]
    assert report["zero_success_tasks"] == []


def test_build_report_percentiles_of_cost() -> None:
    # REQ-042 AC-5: p10, p50, p90 of total cost.
    records = []
    for index, cost in enumerate([1.0, 2.0, 3.0, 4.0]):
        data = make_record(task_id=f"t{index}", repeat=0)
        data["economics"] = {**data["economics"], "model_cost_usd": cost}
        records.append(outcome.parse_record(data))
    report = durable.build_report(records)
    percentiles = report["cost_percentiles_usd"]
    assert percentiles["p50"] == 2.5
    assert percentiles["p10"] == pytest.approx(1.3)
    assert percentiles["p90"] == pytest.approx(3.7)


def test_build_report_percentiles_of_correction_time() -> None:
    # REQ-042 AC-5: p10, p50, p90 of correction time.
    records = []
    for index, minutes in enumerate([0.0, 10.0, 20.0, 30.0]):
        data = make_record(task_id=f"t{index}", repeat=0)
        data["economics"] = {**data["economics"], "human_correction_minutes": minutes}
        records.append(outcome.parse_record(data))
    report = durable.build_report(records)
    percentiles = report["correction_minutes_percentiles"]
    assert percentiles["p50"] == 15.0


def test_build_report_headline_null_when_no_accepted_durable() -> None:
    # REQ-042 AC-6
    data = make_record()
    data["execution"] = {**data["execution"], "deterministic_acceptance": "FAIL"}
    report = durable.build_report([outcome.parse_record(data)])
    assert report["headline"]["cost_per_accepted_durable_task_usd"] is None
    assert report["headline"]["correction_minutes_per_accepted_durable_task"] is None


def test_build_report_headline_values_when_accepted_durable_present() -> None:
    # REQ-042 AC-6
    report = durable.build_report([outcome.parse_record(make_record())])
    assert report["headline"]["cost_per_accepted_durable_task_usd"] == 0.5
    assert report["headline"]["correction_minutes_per_accepted_durable_task"] == 0.0


def test_build_report_status_unverified_when_any_record_unverified() -> None:
    # REQ-042 AC-3, AC-6: one UNVERIFIED record makes the whole report UNVERIFIED.
    good = make_record(task_id="t1")
    bad = make_record(task_id="t2")
    bad["durable"] = {**bad["durable"], "residual_defects": None}
    report = durable.build_report([outcome.parse_record(good), outcome.parse_record(bad)])
    assert report["status"] == "UNVERIFIED"


def test_build_report_refuses_mixed_config_within_file() -> None:
    a = make_record(task_id="t1")
    b = make_record(task_id="t2")
    b["config"] = {**b["config"], "model": "other-model"}
    with pytest.raises(outcome.DurableOutcomeError, match="different configurations"):
        durable.build_report([outcome.parse_record(a), outcome.parse_record(b)])


def test_build_report_refuses_mixed_config_reports_a_later_differing_field() -> None:
    # The first several RunConfig fields (model, harness, harness_version)
    # match; only `retry_budget` differs, so the field-finder must walk past
    # the matching ones before it reports the mismatch.
    a = make_record(task_id="t1")
    b = make_record(task_id="t2")
    b["config"] = {**b["config"], "retry_budget": 9}
    with pytest.raises(outcome.DurableOutcomeError, match="retry_budget"):
        durable.build_report([outcome.parse_record(a), outcome.parse_record(b)])


def test_build_report_refuses_duplicate_task_repeat() -> None:
    records = [
        outcome.parse_record(make_record(task_id="t1", repeat=0)),
        outcome.parse_record(make_record(task_id="t1", repeat=0)),
    ]
    with pytest.raises(outcome.DurableOutcomeError, match="duplicate"):
        durable.build_report(records)


def test_rejected_run_cost_stays_in_numerator() -> None:
    # DESIGN-040 "Report": costs of rejected runs stay in the numerator.
    accepted = make_record(task_id="t1")
    accepted["economics"] = {**accepted["economics"], "model_cost_usd": 1.0}
    rejected = make_record(task_id="t2")
    rejected["execution"] = {**rejected["execution"], "deterministic_acceptance": "FAIL"}
    rejected["economics"] = {**rejected["economics"], "model_cost_usd": 9.0}
    records = [outcome.parse_record(accepted), outcome.parse_record(rejected)]
    report = durable.build_report(records)
    assert report["headline"]["cost_per_accepted_durable_task_usd"] == 10.0


def test_build_report_residual_risk_includes_accepted_not_durable_defects() -> None:
    data = make_record()
    data["durable"] = {**data["durable"], "followup_validation": "FAIL", "residual_defects": 2}
    report = durable.build_report([outcome.parse_record(data)])
    assert report["headline"]["residual_risk"] == 2


def test_build_report_residual_risk_excludes_rejected_defects() -> None:
    # A REJECTED run's residual_defects field is not counted: the run never
    # produced an accepted result to have residual defects against.
    data = make_record()
    data["execution"] = {**data["execution"], "deterministic_acceptance": "FAIL"}
    data["durable"] = {**data["durable"], "residual_defects": 5}
    report = durable.build_report([outcome.parse_record(data)])
    assert report["headline"]["residual_risk"] == 0


# ---------------------------------------------------------------------------
# compare (REQ-042 AC-7, AC-8)
# ---------------------------------------------------------------------------


def _durable_record(task_id: str, control: str, cost: float = 1.0) -> dict[str, Any]:
    data = make_record(task_id=task_id, repeat=0, config=make_config(control=control))
    data["economics"] = {**data["economics"], "model_cost_usd": cost}
    return data


def _rejected_record(task_id: str, control: str, cost: float = 1.0) -> dict[str, Any]:
    data = _durable_record(task_id, control, cost)
    data["execution"] = {**data["execution"], "deterministic_acceptance": "FAIL"}
    return data


def test_compare_requires_nonempty_each_side() -> None:
    with pytest.raises(outcome.DurableOutcomeError, match="at least one record"):
        durable.compare([], [outcome.parse_record(_durable_record("t1", "full"))])


def test_compare_refuses_differing_config_field() -> None:
    baseline = [outcome.parse_record(_durable_record("t1", "reduced"))]
    candidate_data = _durable_record("t1", "full")
    candidate_data["config"] = {**candidate_data["config"], "harness": "codex"}
    candidate = [outcome.parse_record(candidate_data)]
    with pytest.raises(outcome.DurableOutcomeError, match="harness"):
        durable.compare(baseline, candidate)


def test_compare_allows_control_field_to_differ() -> None:
    # REQ-042 AC-7/ontology: matched when every field except `control` is equal.
    baseline = [outcome.parse_record(_durable_record("t1", "reduced"))]
    candidate = [outcome.parse_record(_durable_record("t1", "full"))]
    result = durable.compare(baseline, candidate)
    assert result["result"] == "MIXED"  # identical apart from control: a tie


def test_compare_refuses_differing_task_sets() -> None:
    # REQ-042 AC-7
    baseline = [
        outcome.parse_record(_durable_record("t1", "reduced")),
        outcome.parse_record(_durable_record("t2", "reduced")),
    ]
    candidate = [
        outcome.parse_record(_durable_record("t1", "full")),
        outcome.parse_record(_durable_record("t3", "full")),
    ]
    with pytest.raises(outcome.DurableOutcomeError, match="task sets differ"):
        durable.compare(baseline, candidate)


def test_compare_returns_better() -> None:
    # REQ-042 AC-8: same durable count, lower cost, no zero-drop.
    baseline = [
        outcome.parse_record(_durable_record("t1", "reduced", cost=1.0)),
        outcome.parse_record(_durable_record("t2", "reduced", cost=1.0)),
    ]
    candidate = [
        outcome.parse_record(_durable_record("t1", "full", cost=0.5)),
        outcome.parse_record(_durable_record("t2", "full", cost=0.5)),
    ]
    result = durable.compare(baseline, candidate)
    assert result["result"] == "BETTER"


def test_compare_returns_worse() -> None:
    baseline = [
        outcome.parse_record(_durable_record("t1", "reduced", cost=1.0)),
        outcome.parse_record(_durable_record("t2", "reduced", cost=1.0)),
    ]
    candidate = [
        outcome.parse_record(_durable_record("t1", "full", cost=2.0)),
        outcome.parse_record(_durable_record("t2", "full", cost=2.0)),
    ]
    result = durable.compare(baseline, candidate)
    assert result["result"] == "WORSE"


def test_compare_returns_mixed_on_a_tradeoff() -> None:
    # candidate: more accepted durable tasks, but a higher cost per task.
    baseline = [
        outcome.parse_record(_durable_record("t1", "reduced", cost=1.0)),
        outcome.parse_record(_rejected_record("t2", "reduced", cost=0.1)),
    ]
    candidate = [
        outcome.parse_record(_durable_record("t1", "full", cost=1.0)),
        outcome.parse_record(_durable_record("t2", "full", cost=5.0)),
    ]
    result = durable.compare(baseline, candidate)
    assert result["result"] == "MIXED"


def test_compare_treats_a_zero_durable_baseline_as_cost_free() -> None:
    # When the baseline has zero accepted durable tasks, its headline cost is
    # None, so a candidate cannot be "more expensive" than it; the candidate
    # only has to avoid a zero-drop (there is nothing to drop from).
    baseline = [outcome.parse_record(_rejected_record("t1", "reduced"))]
    candidate = [outcome.parse_record(_durable_record("t1", "full"))]
    result = durable.compare(baseline, candidate)
    assert result["result"] == "BETTER"


def test_compare_returns_unverified_when_either_side_unverified() -> None:
    baseline_data = _durable_record("t1", "reduced")
    baseline_data["durable"] = {**baseline_data["durable"], "residual_defects": None}
    baseline = [outcome.parse_record(baseline_data)]
    candidate = [outcome.parse_record(_durable_record("t1", "full"))]
    result = durable.compare(baseline, candidate)
    assert result["result"] == "UNVERIFIED"


def test_compare_better_requires_no_zero_drop_even_with_better_average() -> None:
    # REQ-042 AC-8: a lower average cost is not enough for BETTER when a task
    # that had >=1 durable accept in the baseline drops to zero.
    baseline = [
        outcome.parse_record(_durable_record("t1", "reduced", cost=1.0)),
        outcome.parse_record(_durable_record("t2", "reduced", cost=1.0)),
    ]
    candidate_t2_repeat1 = _durable_record("t2", "full", cost=0.05)
    candidate_t2_repeat1["repeat"] = 1
    candidate = [
        outcome.parse_record(_rejected_record("t1", "full", cost=0.05)),
        outcome.parse_record(_durable_record("t2", "full", cost=0.05)),
        outcome.parse_record(candidate_t2_repeat1),
    ]
    result = durable.compare(baseline, candidate)
    assert result["result"] != "BETTER"
    assert result["candidate"]["verdict_counts"]["ACCEPTED_DURABLE"] == (
        result["baseline"]["verdict_counts"]["ACCEPTED_DURABLE"]
    )


# ---------------------------------------------------------------------------
# Fixtures (REQ-042 AC-9, AC-10)
# ---------------------------------------------------------------------------


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
