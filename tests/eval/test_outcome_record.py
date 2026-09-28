"""Tests for scripts/eval/_outcome_record.py (REQ-042 AC-1, DESIGN-040).

Behavior under test: strict OutcomeRecord parsing. Pure functions, no mocks.
"""

from __future__ import annotations

import pytest

from tests.eval._durable_outcome_test_support import make_record, outcome

# ---------------------------------------------------------------------------
# parse_record (REQ-042 AC-1)
# ---------------------------------------------------------------------------


def test_parses_a_valid_record() -> None:
    record = outcome.parse_record(make_record())
    assert record.task_id == "t1"
    assert record.config.model == "claude-sonnet-5"
    assert record.execution.judge is outcome.Evidence.PASS


def test_parses_record_with_judge_omitted() -> None:
    data = make_record()
    data["execution"] = {k: v for k, v in data["execution"].items() if k != "judge"}
    record = outcome.parse_record(data)
    assert record.execution.judge is None


def test_parses_record_with_judge_explicit_null() -> None:
    data = make_record()
    data["execution"] = {**data["execution"], "judge": None}
    record = outcome.parse_record(data)
    assert record.execution.judge is None


def test_refuses_non_dict_record() -> None:
    with pytest.raises(outcome.DurableOutcomeError, match="expected an object"):
        outcome.parse_record(["not", "a", "dict"])


def test_refuses_unknown_top_level_key() -> None:
    data = make_record()
    data["extra"] = 1
    with pytest.raises(outcome.DurableOutcomeError, match="unknown key"):
        outcome.parse_record(data)


def test_refuses_missing_top_level_key() -> None:
    data = make_record()
    del data["risk"]
    with pytest.raises(outcome.DurableOutcomeError, match="missing required key"):
        outcome.parse_record(data)


def test_refuses_config_not_a_dict() -> None:
    data = make_record()
    data["config"] = "not-a-dict"
    with pytest.raises(outcome.DurableOutcomeError, match="expected an object"):
        outcome.parse_record(data)


def test_refuses_unknown_nested_key_in_config() -> None:
    data = make_record()
    data["config"] = {**data["config"], "extra_field": "x"}
    with pytest.raises(outcome.DurableOutcomeError, match="unknown key"):
        outcome.parse_record(data)


def test_refuses_missing_nested_key_in_config() -> None:
    data = make_record()
    config = dict(data["config"])
    del config["reviewer"]
    data["config"] = config
    with pytest.raises(outcome.DurableOutcomeError, match="missing required key"):
        outcome.parse_record(data)


def test_refuses_missing_key_in_execution_section() -> None:
    data = make_record()
    execution = dict(data["execution"])
    del execution["first_pass"]
    data["execution"] = execution
    with pytest.raises(outcome.DurableOutcomeError, match="missing required key"):
        outcome.parse_record(data)


def test_refuses_unknown_key_in_execution_section() -> None:
    data = make_record()
    data["execution"] = {**data["execution"], "extra": 1}
    with pytest.raises(outcome.DurableOutcomeError, match="unknown key"):
        outcome.parse_record(data)


def test_refuses_bad_evidence_enum() -> None:
    data = make_record()
    data["execution"] = {**data["execution"], "deterministic_acceptance": "MAYBE"}
    with pytest.raises(outcome.DurableOutcomeError):
        outcome.parse_record(data)


def test_refuses_non_string_evidence() -> None:
    data = make_record()
    data["execution"] = {**data["execution"], "deterministic_acceptance": 1}
    with pytest.raises(outcome.DurableOutcomeError):
        outcome.parse_record(data)


def test_refuses_negative_count() -> None:
    data = make_record()
    data["durable"] = {**data["durable"], "residual_defects": -1}
    with pytest.raises(outcome.DurableOutcomeError):
        outcome.parse_record(data)


def test_refuses_negative_money() -> None:
    data = make_record()
    data["economics"] = {**data["economics"], "model_cost_usd": -0.1}
    with pytest.raises(outcome.DurableOutcomeError):
        outcome.parse_record(data)


def test_refuses_bool_as_int_repeat() -> None:
    data = make_record()
    data["repeat"] = True
    with pytest.raises(outcome.DurableOutcomeError):
        outcome.parse_record(data)


def test_refuses_bool_as_int_count() -> None:
    data = make_record()
    data["durable"] = {**data["durable"], "residual_defects": False}
    with pytest.raises(outcome.DurableOutcomeError):
        outcome.parse_record(data)


def test_refuses_bool_as_number() -> None:
    data = make_record()
    data["economics"] = {**data["economics"], "wall_seconds": True}
    with pytest.raises(outcome.DurableOutcomeError):
        outcome.parse_record(data)


def test_refuses_non_number_economics_field() -> None:
    data = make_record()
    data["economics"] = {**data["economics"], "model_cost_usd": "free"}
    with pytest.raises(outcome.DurableOutcomeError):
        outcome.parse_record(data)


def test_refuses_non_int_count() -> None:
    data = make_record()
    data["execution"] = {**data["execution"], "retries": "3"}
    with pytest.raises(outcome.DurableOutcomeError):
        outcome.parse_record(data)


def test_refuses_wrong_type_for_string_field() -> None:
    data = make_record()
    data["task_id"] = 123
    with pytest.raises(outcome.DurableOutcomeError):
        outcome.parse_record(data)


def test_refuses_wrong_type_for_bool_field() -> None:
    data = make_record()
    data["capability"] = {**data["capability"], "attempted": "yes"}
    with pytest.raises(outcome.DurableOutcomeError):
        outcome.parse_record(data)


def test_refuses_empty_task_id() -> None:
    data = make_record()
    data["task_id"] = ""
    with pytest.raises(outcome.DurableOutcomeError):
        outcome.parse_record(data)


def test_refuses_empty_config_string_field() -> None:
    data = make_record()
    data["config"] = {**data["config"], "harness": ""}
    with pytest.raises(outcome.DurableOutcomeError):
        outcome.parse_record(data)


def test_allows_null_durable_count() -> None:
    data = make_record()
    data["durable"] = {**data["durable"], "residual_defects": None}
    record = outcome.parse_record(data)
    assert record.durable.residual_defects is None


def test_allows_null_rework_minutes() -> None:
    data = make_record()
    data["durable"] = {**data["durable"], "rework_minutes": None}
    record = outcome.parse_record(data)
    assert record.durable.rework_minutes is None


def test_refuses_negative_rework_minutes() -> None:
    data = make_record()
    data["durable"] = {**data["durable"], "rework_minutes": -5}
    with pytest.raises(outcome.DurableOutcomeError):
        outcome.parse_record(data)


def test_allows_null_risk_count() -> None:
    data = make_record()
    data["risk"] = {**data["risk"], "security_findings": None}
    record = outcome.parse_record(data)
    assert record.risk.security_findings is None


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
@pytest.mark.parametrize(
    ("section", "field"),
    [("economics", "model_cost_usd"), ("durable", "rework_minutes")],
)
def test_refuses_nonfinite_number(section: str, field: str, value: float) -> None:
    """REQ-042 data-model invariant 1: NaN and Infinity from JSONL are refused."""
    data = make_record()
    data[section] = {**data[section], field: value}
    with pytest.raises(outcome.DurableOutcomeError, match="finite"):
        outcome.parse_record(data)
