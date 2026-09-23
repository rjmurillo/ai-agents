"""Grader resolution and malformed-verdict handling for `_runtime_grader` (#5404).

Split from `test_eval_runtime_parity_semantic.py` to keep each test file
under the 500-line taste limit.
"""

from __future__ import annotations

import pytest

from tests.eval._runtime_parity_test_support import runtime_grader

# --- Grader resolution --------------------------------------------------------


@pytest.mark.parametrize("name", ["anthropic", "claude-api", ""])
def test_resolve_grader_maps_default_anthropic_names_to_http_adapter(name: str) -> None:
    grader = runtime_grader.resolve_grader(name)

    assert grader.name == "anthropic"
    assert grader.system_fingerprint is None


def test_resolve_grader_delegates_registry_names() -> None:
    grader = runtime_grader.resolve_grader("anthropic-sdk")

    assert grader.name == "anthropic-sdk"


def test_resolve_grader_rejects_unknown_names() -> None:
    with pytest.raises(RuntimeError, match="Unknown EVAL_PROVIDER"):
        runtime_grader.resolve_grader("no-such-provider")


def test_http_grader_forwards_arguments_to_call_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import _anthropic_api

    seen: dict[str, object] = {}

    def fake_call_api(api_key: str, messages: list[dict[str, str]], **kwargs: object) -> str:
        seen.update(api_key=api_key, messages=messages, **kwargs)
        return '{"verdict": "PASS", "reason": "ok"}'

    monkeypatch.setattr(_anthropic_api, "load_api_key", lambda: "test-key")
    monkeypatch.setattr(_anthropic_api, "call_api", fake_call_api)
    grader = runtime_grader.resolve_grader("anthropic")

    text = grader.complete(
        messages=[{"role": "user", "content": "x"}], system="s", model="m", max_tokens=7
    )

    assert text == '{"verdict": "PASS", "reason": "ok"}'
    assert seen["api_key"] == "test-key"
    assert seen["model"] == "m"
    assert seen["system"] == "s"
    assert seen["max_tokens"] == 7
    assert seen["provider"] == "anthropic"
    assert seen["temperature"] is None


def test_http_grader_missing_key_grades_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import _anthropic_api

    def no_key() -> str:
        raise RuntimeError("ANTHROPIC_API_KEY not found")

    monkeypatch.setattr(_anthropic_api, "load_api_key", no_key)
    grader = runtime_grader.resolve_grader("anthropic")

    result = runtime_grader.grade(grader, "m", "rubric", "prompt", "response")

    assert result.verdict == "UNAVAILABLE"
    assert result.provider == "anthropic"


class _FixedTextGrader:
    name = "fixed"
    system_fingerprint: str | None = None

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, **_: object) -> str:
        return self.text


def test_grade_salvages_verdict_from_malformed_json() -> None:
    raw = '{"verdict": "FAIL", "reason": "appends an offer.""}'

    result = runtime_grader.grade(_FixedTextGrader(raw), "m", "r", "p", "x")

    assert result.verdict == "FAIL"
    assert result.reason == ""


def test_grade_conflicting_salvaged_verdicts_are_unavailable() -> None:
    raw = '"verdict": "PASS" then "verdict": "FAIL" {'

    result = runtime_grader.grade(_FixedTextGrader(raw), "m", "r", "p", "x")

    assert result.verdict == "UNAVAILABLE"


def test_grade_prose_without_verdict_field_is_unavailable() -> None:
    result = runtime_grader.grade(_FixedTextGrader("I think it FAILs."), "m", "r", "p", "x")

    assert result.verdict == "UNAVAILABLE"


@pytest.mark.parametrize("raw", ['{"verdict": ["PASS"]}', '{"verdict": {}}', '{"verdict": 1}'])
def test_grade_non_string_verdict_is_unavailable(raw: str) -> None:
    result = runtime_grader.grade(_FixedTextGrader(raw), "m", "r", "p", "x")

    assert result.verdict == "UNAVAILABLE"
