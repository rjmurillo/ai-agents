"""Matched-comparison refusal around `context_bytes` (REQ-042 AC-7, REQ-046 AC-10)."""

from __future__ import annotations

import pytest

from tests.eval._durable_outcome_test_support import (
    durable,
    durable_record,
    outcome,
)


def test_compare_allows_control_and_context_bytes_to_differ_together() -> None:
    # REQ-046 AC-10/DESIGN-044 "Comparison change": a reduced control differs
    # in context_bytes by construction, so the comparison must not refuse on
    # that field when it is the only other difference from `control`.
    baseline_data = durable_record("t1", "reduced")
    baseline_data["config"] = {**baseline_data["config"], "context_bytes": 0}
    candidate_data = durable_record("t1", "full")
    candidate_data["config"] = {**candidate_data["config"], "context_bytes": 48210}
    baseline = [outcome.parse_record(baseline_data)]
    candidate = [outcome.parse_record(candidate_data)]
    result = durable.compare(baseline, candidate)
    assert result["result"] == "MIXED"  # identical apart from control/context_bytes: a tie


def test_compare_refuses_differing_model_even_with_matching_context_bytes() -> None:
    # A pair differing in `model` (or any non-exempt field) still refuses,
    # even when `context_bytes` also differs.
    baseline_data = durable_record("t1", "reduced")
    baseline_data["config"] = {**baseline_data["config"], "context_bytes": 0}
    candidate_data = durable_record("t1", "full")
    candidate_data["config"] = {
        **candidate_data["config"],
        "context_bytes": 48210,
        "model": "claude-opus-5-5",
    }
    baseline = [outcome.parse_record(baseline_data)]
    candidate = [outcome.parse_record(candidate_data)]
    with pytest.raises(outcome.DurableOutcomeError, match="model"):
        durable.compare(baseline, candidate)


def test_compare_refuses_same_control_with_differing_context_bytes() -> None:
    # Two runs under one control that loaded different bytes loaded different
    # instructions, so the context_bytes exemption must not apply to them.
    baseline_data = durable_record("t1", "full")
    baseline_data["config"] = {**baseline_data["config"], "context_bytes": 40324}
    candidate_data = durable_record("t1", "full")
    candidate_data["config"] = {**candidate_data["config"], "context_bytes": 48210}
    baseline = [outcome.parse_record(baseline_data)]
    candidate = [outcome.parse_record(candidate_data)]
    with pytest.raises(outcome.DurableOutcomeError, match="context_bytes"):
        durable.compare(baseline, candidate)
