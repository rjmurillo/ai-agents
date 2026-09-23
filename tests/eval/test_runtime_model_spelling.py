"""Per-harness Claude model spelling and optional grader temperature (#5404)."""

from __future__ import annotations

import json

import _anthropic_api
import pytest
from _runtime_output import comparison_verdict, harness_model_id, same_model


@pytest.mark.parametrize(
    ("harness", "model", "expected"),
    [
        ("copilot", "claude-opus-5-5", "claude-opus-5.5"),
        ("copilot", "claude-opus-5.5", "claude-opus-5.5"),
        ("claude", "claude-opus-5.5", "claude-opus-5-5"),
        ("claude", "claude-opus-5-5", "claude-opus-5-5"),
        ("claude", "claude-sonnet-5", "claude-sonnet-5"),
        ("copilot", "claude-opus-4-8", "claude-opus-4.8"),
        ("claude", "claude-3-5-sonnet-20241022", "claude-3-5-sonnet-20241022"),
        ("copilot", "claude-haiku-4-5-20251001", "claude-haiku-4-5-20251001"),
        ("claude", "gpt-5.6", "gpt-5.6"),
        ("copilot", "gpt-5-6", "gpt-5-6"),
    ],
)
def test_harness_model_id_spells_claude_ids_per_harness(
    harness: str, model: str, expected: str
) -> None:
    assert harness_model_id(harness, model) == expected


def test_same_model_accepts_either_spelling_and_rejects_others() -> None:
    assert same_model("claude-opus-5.5", "claude-opus-5-5")
    assert not same_model("claude-opus-5-5", "claude-opus-4-6")
    assert not same_model(None, "claude-opus-5-5")


def _pair(claude_model: str, copilot_model: str) -> tuple[dict[str, object], dict[str, object]]:
    base = {"question_mechanism": "none", "passed": True}
    return (
        {**base, "resolved_model": claude_model},
        {**base, "resolved_model": copilot_model},
    )


def test_comparison_verdict_passes_same_model_in_harness_spellings() -> None:
    claude, copilot = _pair("claude-opus-5-5", "claude-opus-5.5")

    assert comparison_verdict(claude, copilot, "claude-opus-5-5") is None


def test_comparison_verdict_still_flags_a_different_model() -> None:
    claude, copilot = _pair("claude-opus-5-5", "claude-sonnet-5")

    assert comparison_verdict(claude, copilot, "claude-opus-5-5") == "FAIL_MODEL_MISMATCH"


def _body(temperature: float | None) -> dict[str, object]:
    request = _anthropic_api._build_messages_request(
        "test-key", [{"role": "user", "content": "x"}], "", "claude-sonnet-5", 8, temperature
    )
    data = request.data
    assert isinstance(data, bytes)
    body: dict[str, object] = json.loads(data)
    return body


def test_messages_request_omits_temperature_when_none() -> None:
    assert "temperature" not in _body(None)


def test_messages_request_keeps_explicit_temperature() -> None:
    assert _body(0.0)["temperature"] == 0.0
