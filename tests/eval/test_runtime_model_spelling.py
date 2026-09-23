"""Per-harness Claude model spelling and optional grader temperature (#5404)."""

from __future__ import annotations

import json
import sys
from types import ModuleType, SimpleNamespace

import _anthropic_api
import _providers
import _runtime_grader
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


class _FakeMessages:
    def __init__(self, recorder: list[dict[str, object]]) -> None:
        self._recorder = recorder

    def create(self, **kwargs: object) -> SimpleNamespace:
        self._recorder.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")])


def _sdk_request(monkeypatch: pytest.MonkeyPatch, temperature: float | None) -> dict[str, object]:
    recorder: list[dict[str, object]] = []
    module = ModuleType("anthropic")
    module.__dict__["Anthropic"] = lambda **_: SimpleNamespace(messages=_FakeMessages(recorder))
    monkeypatch.setitem(sys.modules, "anthropic", module)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = _providers.resolve_provider("anthropic-sdk")

    provider.complete(
        messages=[{"role": "user", "content": "x"}],
        model="claude-sonnet-5",
        temperature=temperature,
    )

    return recorder[0]


def test_sdk_provider_omits_temperature_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _sdk_request(monkeypatch, None)
    assert "temperature" not in request
    assert "extra_body" not in request


def test_sdk_provider_keeps_explicit_temperature(monkeypatch: pytest.MonkeyPatch) -> None:
    # anthropic SDK 1.6.0 removed the `temperature` keyword; it rides in `extra_body`.
    request = _sdk_request(monkeypatch, 0.0)
    assert "temperature" not in request
    assert request["extra_body"] == {"temperature": 0.0}


def test_grade_asks_registry_providers_for_no_temperature() -> None:
    seen: dict[str, object] = {}

    class _Recorder:
        name = "recorder"
        system_fingerprint = None

        def complete(self, **kwargs: object) -> str:
            seen.update(kwargs)
            return '{"verdict": "PASS", "reason": "ok"}'

    result = _runtime_grader.grade(_Recorder(), "claude-sonnet-5", "rubric", "prompt", "response")

    assert result.verdict == "PASS"
    assert seen["temperature"] is None
