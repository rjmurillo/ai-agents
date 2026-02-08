"""Tests for context-retrieval auto-invocation decision logic (Step 3.5).

Validates that extract_context_retrieval_data() and collect_metrics()
from measure_context_retrieval_metrics.py correctly parse session logs
with known classification data.

See: src/copilot-cli/orchestrator.agent.md Step 3.5
See: tests/eval_scenarios/step35_scenarios.json
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.measure_context_retrieval_metrics import (
    collect_metrics,
    extract_context_retrieval_data,
)

SCENARIOS_PATH = Path(__file__).parent / "eval_scenarios" / "step35_scenarios.json"


def _load_unit_scenarios() -> list[dict]:
    """Load unit test scenarios from shared JSON file."""
    data = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    return data["unit_scenarios"]


def _build_session_log(scenario: dict) -> dict:
    """Build a synthetic session log JSON from a scenario definition.

    The session log mirrors the structure parsed by
    extract_context_retrieval_data(): a dict with optional
    "classification", "outcomes", and "decisions" keys.
    """
    classification = scenario.get("classification")
    if classification is None:
        # S08: no classification data, but include outcomes so the
        # function sees *some* orchestration evidence (or not).
        return {
            "outcomes": ["Task completed"],
            "decisions": ["Proceeded with default"],
        }

    return {
        "classification": classification,
        "outcomes": [f"Scenario {scenario['id']} executed"],
        "decisions": [f"context-retrieval {classification.get('context_retrieval', 'N/A')}"],
    }


# Build parametrize IDs and argument tuples from the shared JSON.
_UNIT_SCENARIOS = _load_unit_scenarios()
_SCENARIO_IDS = [s["id"] for s in _UNIT_SCENARIOS]


@pytest.mark.parametrize("scenario", _UNIT_SCENARIOS, ids=_SCENARIO_IDS)
class TestExtractContextRetrievalData:
    """Verify extract_context_retrieval_data against each scenario."""

    def test_invocation_status(self, scenario: dict, tmp_path: Path) -> None:
        """The invoked field matches the expected decision."""
        session_log = _build_session_log(scenario)
        session_file = tmp_path / f"{scenario['id']}.json"
        session_file.write_text(json.dumps(session_log), encoding="utf-8")

        record = extract_context_retrieval_data(session_file)

        if scenario["expected_invoked"] is None:
            # S08: no classification data, no orchestration keyword
            # The function should return None when there is no evidence.
            assert record is None, (
                f"Expected None for scenario {scenario['id']}, got {record}"
            )
            return

        assert record is not None, (
            f"Expected InvocationRecord for {scenario['id']}, got None"
        )
        assert record.invoked is scenario["expected_invoked"], (
            f"{scenario['id']}: expected invoked={scenario['expected_invoked']}, "
            f"got {record.invoked}"
        )

    def test_classification_fields(self, scenario: dict, tmp_path: Path) -> None:
        """Classification fields are correctly extracted."""
        if scenario.get("classification") is None:
            pytest.skip("No classification data in this scenario")

        session_log = _build_session_log(scenario)
        session_file = tmp_path / f"{scenario['id']}.json"
        session_file.write_text(json.dumps(session_log), encoding="utf-8")

        record = extract_context_retrieval_data(session_file)
        assert record is not None

        cls = scenario["classification"]
        assert record.complexity == cls["complexity"]
        assert record.domain_count == cls["domain_count"]
        assert record.confidence == cls["classification_confidence"]
        assert record.user_requested is cls["user_requested_context"]

    def test_session_id_from_filename(self, scenario: dict, tmp_path: Path) -> None:
        """Session ID is derived from the filename stem."""
        if scenario.get("classification") is None:
            pytest.skip("No classification data in this scenario")

        session_log = _build_session_log(scenario)
        session_file = tmp_path / f"2026-01-15-session-{scenario['id']}.json"
        session_file.write_text(json.dumps(session_log), encoding="utf-8")

        record = extract_context_retrieval_data(session_file)
        assert record is not None
        assert record.session_id == f"2026-01-15-session-{scenario['id']}"


class TestCollectMetrics:
    """Verify collect_metrics aggregation over multiple session logs."""

    def test_counts_match_expectations(self, tmp_path: Path) -> None:
        """Invoked/skipped/eligible counts are correct."""
        scenarios = _load_unit_scenarios()

        for scenario in scenarios:
            session_log = _build_session_log(scenario)
            session_file = tmp_path / f"{scenario['id']}.json"
            session_file.write_text(json.dumps(session_log), encoding="utf-8")

        metrics = collect_metrics(tmp_path, limit=100)

        # Count expected values from scenarios (exclude S08 which returns None)
        expected_invoked = sum(
            1 for s in scenarios
            if s["expected_invoked"] is True
        )
        expected_skipped = sum(
            1 for s in scenarios
            if s["expected_invoked"] is False
        )
        expected_eligible = expected_invoked + expected_skipped

        assert metrics.total_eligible == expected_eligible
        assert metrics.total_invoked == expected_invoked
        assert metrics.total_skipped == expected_skipped

    def test_invocation_rate_calculation(self, tmp_path: Path) -> None:
        """Invocation rate percentage is computed correctly."""
        scenarios = _load_unit_scenarios()

        for scenario in scenarios:
            session_log = _build_session_log(scenario)
            session_file = tmp_path / f"{scenario['id']}.json"
            session_file.write_text(json.dumps(session_log), encoding="utf-8")

        metrics = collect_metrics(tmp_path, limit=100)

        if metrics.total_eligible > 0:
            expected_rate = (metrics.total_invoked / metrics.total_eligible) * 100
            assert abs(metrics.invocation_rate - expected_rate) < 0.01

    def test_empty_directory_returns_zero_metrics(self, tmp_path: Path) -> None:
        """An empty sessions directory produces zero-value metrics."""
        metrics = collect_metrics(tmp_path)
        assert metrics.total_eligible == 0
        assert metrics.total_invoked == 0
        assert metrics.total_skipped == 0
        assert metrics.invocation_rate == 0.0

    def test_limit_parameter_respected(self, tmp_path: Path) -> None:
        """The limit parameter caps how many logs are processed."""
        scenarios = _load_unit_scenarios()

        for scenario in scenarios:
            session_log = _build_session_log(scenario)
            session_file = tmp_path / f"{scenario['id']}.json"
            session_file.write_text(json.dumps(session_log), encoding="utf-8")

        metrics = collect_metrics(tmp_path, limit=2)
        assert len(metrics.invocations) <= 2

    def test_to_dict_serializable(self, tmp_path: Path) -> None:
        """Metrics.to_dict() produces JSON-serializable output."""
        scenarios = _load_unit_scenarios()

        for scenario in scenarios:
            session_log = _build_session_log(scenario)
            session_file = tmp_path / f"{scenario['id']}.json"
            session_file.write_text(json.dumps(session_log), encoding="utf-8")

        metrics = collect_metrics(tmp_path, limit=100)
        result = metrics.to_dict()

        # Should not raise
        serialized = json.dumps(result)
        assert isinstance(serialized, str)
        assert "total_eligible" in result
        assert "invocations" in result


class TestEdgeCases:
    """Edge cases for extract_context_retrieval_data."""

    def test_invalid_json_returns_none(self, tmp_path: Path) -> None:
        """Malformed JSON files return None."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{{", encoding="utf-8")
        assert extract_context_retrieval_data(bad_file) is None

    def test_json_array_returns_none(self, tmp_path: Path) -> None:
        """A JSON array (not object) returns None."""
        arr_file = tmp_path / "array.json"
        arr_file.write_text("[1, 2, 3]", encoding="utf-8")
        assert extract_context_retrieval_data(arr_file) is None

    def test_empty_object_returns_none(self, tmp_path: Path) -> None:
        """An empty JSON object with no orchestration evidence returns None."""
        empty_file = tmp_path / "empty.json"
        empty_file.write_text("{}", encoding="utf-8")
        assert extract_context_retrieval_data(empty_file) is None

    def test_nonexistent_file_returns_none(self, tmp_path: Path) -> None:
        """A path to a nonexistent file returns None."""
        missing = tmp_path / "does_not_exist.json"
        assert extract_context_retrieval_data(missing) is None

    def test_fallback_text_detection(self, tmp_path: Path) -> None:
        """Fallback text detection finds 'context-retrieval invoked' in outcomes."""
        session_log = {
            "outcomes": ["orchestrator routed task", "context-retrieval invoked for security"],
            "decisions": [],
        }
        session_file = tmp_path / "fallback.json"
        session_file.write_text(json.dumps(session_log), encoding="utf-8")

        record = extract_context_retrieval_data(session_file)
        assert record is not None
        assert record.invoked is True
        assert record.reason == "inferred from session text"

    def test_fallback_no_context_retrieval_mention(self, tmp_path: Path) -> None:
        """Fallback returns record with invoked=False when no CR mention."""
        session_log = {
            "outcomes": ["orchestrator completed task"],
            "decisions": ["used implementer agent"],
        }
        session_file = tmp_path / "no_cr.json"
        session_file.write_text(json.dumps(session_log), encoding="utf-8")

        record = extract_context_retrieval_data(session_file)
        # Has "orchestrat" in text, so should return a record
        assert record is not None
        assert record.invoked is False
