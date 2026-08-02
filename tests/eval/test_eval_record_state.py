"""Tests for issues #4121 and #4123: eval-record state modeling.

#4121: max_retries <= 0 silently calls nothing and returns an 'unknown' error.
       Fix: raise ValueError at the start of call_model.

#4123: malformed (non-str, non-None) system_fingerprint is silently coerced to
       None instead of surfacing as a bug. Fix: raise RuntimeError on malformed
       fingerprints in all three transport sites.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"
_ORIGINAL_SYS_PATH = sys.path.copy()
sys.path.insert(0, str(_EVAL_DIR))
try:
    import _eval_api_adapter
    import _providers
finally:
    sys.path[:] = _ORIGINAL_SYS_PATH


# ---------------------------------------------------------------------------
# Helpers: minimal fakes so the tests never reach the network.
# ---------------------------------------------------------------------------


class _FakeTransport:
    """Callable transport that records calls and returns a canned response."""

    def __init__(self, response: str = "ok") -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.system_fingerprint: str | None = None
        self._response = response

    def __call__(self, prompt: str, model_id: str, system: str) -> str:
        self.calls.append((prompt, model_id, system))
        return self._response


def _make_adapter(transport: _FakeTransport) -> _eval_api_adapter.AnthropicAPIAdapter:
    """Build an AnthropicAPIAdapter backed by a fake transport."""
    return _eval_api_adapter.AnthropicAPIAdapter(transport=transport)


# ---------------------------------------------------------------------------
# Issue #4121: max_retries <= 0 must raise, not silently do nothing.
# ---------------------------------------------------------------------------


class TestMaxRetriesGuard:
    """AnthropicAPIAdapter.call_model raises ValueError when max_retries < 1."""

    @pytest.mark.parametrize("bad_value", [0, -1, -100])
    def test_raises_value_error_for_non_positive_max_retries(self, bad_value: int) -> None:
        transport = _FakeTransport()
        adapter = _make_adapter(transport)

        with pytest.raises(ValueError, match="max_retries must be at least 1"):
            adapter.call_model(
                "prompt",
                "model",
                "fix",
                "v1",
                0,
                max_retries=bad_value,
            )

    @pytest.mark.parametrize("bad_value", [0, -1, -100])
    def test_transport_is_never_called_before_the_raise(self, bad_value: int) -> None:
        transport = _FakeTransport()
        adapter = _make_adapter(transport)

        with pytest.raises(ValueError):
            adapter.call_model(
                "prompt",
                "model",
                "fix",
                "v1",
                0,
                max_retries=bad_value,
            )

        assert transport.calls == [], "transport must not be called when max_retries < 1"

    def test_positive_max_retries_does_not_raise(self) -> None:
        transport = _FakeTransport()
        adapter = _make_adapter(transport)

        result = adapter.call_model(
            "prompt",
            "model",
            "fix",
            "v1",
            0,
            max_retries=1,
        )

        assert result.outcome == "success"
        assert len(transport.calls) == 1

    # Inverted control: proves max_retries=1 path diverges from max_retries=0.
    # If the guard were removed this test would PASS (no ValueError raised) and
    # call_model would return an error result instead of raising.
    def test_inverted_control_max_retries_one_differs_from_zero(self) -> None:
        transport = _FakeTransport()
        adapter = _make_adapter(transport)

        # max_retries=1 succeeds; max_retries=0 must raise.
        result = adapter.call_model("p", "m", "f", "v", 0, max_retries=1)
        assert result.outcome == "success"

        with pytest.raises(ValueError):
            adapter.call_model("p", "m", "f", "v", 0, max_retries=0)


# ---------------------------------------------------------------------------
# Issue #4123: malformed system_fingerprint must raise, not silently vanish.
# ---------------------------------------------------------------------------


class TestFingerprintGuardOpenAITransport:
    """_OpenAIProviderTransport raises RuntimeError on non-str, non-None fingerprint."""

    def _make_transport(
        self, fingerprint: Any
    ) -> _eval_api_adapter._OpenAIProviderTransport:
        class _FakeProvider:
            system_fingerprint: Any

            def complete(self, **_: object) -> str:
                return "answer"

        provider = _FakeProvider()
        provider.system_fingerprint = fingerprint
        return _eval_api_adapter._OpenAIProviderTransport(provider, seed=None)

    @pytest.mark.parametrize("fingerprint", ["fp-abc", ""])
    def test_str_fingerprint_stored_as_is(self, fingerprint: str) -> None:
        transport = self._make_transport(fingerprint)
        transport("prompt", "model", "system")
        assert transport.system_fingerprint == fingerprint

    def test_none_fingerprint_stored_as_none(self) -> None:
        transport = self._make_transport(None)
        transport("prompt", "model", "system")
        assert transport.system_fingerprint is None

    @pytest.mark.parametrize("bad_value", [42, 3.14, [], {}])
    def test_raises_on_non_str_non_none(self, bad_value: Any) -> None:
        transport = self._make_transport(bad_value)
        with pytest.raises(RuntimeError, match="system_fingerprint must be str or None"):
            transport("prompt", "model", "system")

    # Inverted control: coerce-to-None was the old behavior; this test shows
    # the new code diverges. Remove the guard and transport.system_fingerprint
    # would be None for bad_value=42; with the guard it raises.
    def test_inverted_control_malformed_raises_not_silenced(self) -> None:
        transport = self._make_transport(42)
        with pytest.raises(RuntimeError):
            transport("prompt", "model", "system")


class TestFingerprintGuardAnthropicTransport:
    """_AnthropicTransport raises RuntimeError on non-str, non-None fingerprint."""

    def _call_with_fake_api(
        self, fingerprint: Any, monkeypatch: pytest.MonkeyPatch
    ) -> _eval_api_adapter._AnthropicTransport:
        t = _eval_api_adapter._AnthropicTransport(api_key="fake", seed=None)

        def _fake_call_api(**kwargs: object) -> str:
            md = kwargs.get("metadata")
            if isinstance(md, dict):
                md["system_fingerprint"] = fingerprint
            return "answer"

        monkeypatch.setattr(_eval_api_adapter, "call_api", _fake_call_api)
        return t

    def test_str_fingerprint_stored_as_is(self, monkeypatch: pytest.MonkeyPatch) -> None:
        t = self._call_with_fake_api("fp-abc", monkeypatch)
        t("prompt", "model", "system")
        assert t.system_fingerprint == "fp-abc"

    def test_none_fingerprint_stored_as_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        t = self._call_with_fake_api(None, monkeypatch)
        t("prompt", "model", "system")
        assert t.system_fingerprint is None

    @pytest.mark.parametrize("bad_value", [42, [], {}])
    def test_raises_on_non_str_non_none(
        self, bad_value: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        t = self._call_with_fake_api(bad_value, monkeypatch)
        with pytest.raises(RuntimeError, match="system_fingerprint must be str or None"):
            t("prompt", "model", "system")


class TestFingerprintGuardProvidersOpenAI:
    """_providers._OpenAICompatibleProvider raises RuntimeError on malformed fingerprint."""

    def _setup_fake_openai(
        self, fingerprint: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Inject a minimal fake openai module so no real SDK is needed."""
        import types

        fake_openai = types.ModuleType("openai")

        class _FakeMessage:
            def __init__(self) -> None:
                self.content = "answer"
                self.type = "text"

        class _FakeChoice:
            def __init__(self) -> None:
                self.message = _FakeMessage()

        class _FakeResponse:
            def __init__(self) -> None:
                self.choices = [_FakeChoice()]
                self.system_fingerprint = fingerprint
                self.usage = None

        class _FakeCompletions:
            def create(self, **_: object) -> _FakeResponse:
                return _FakeResponse()

        class _FakeChat:
            completions = _FakeCompletions()

        class _FakeOpenAI:
            def __init__(self, **_: object) -> None:
                self.chat = _FakeChat()

        fake_openai.OpenAI = _FakeOpenAI
        monkeypatch.setitem(sys.modules, "openai", fake_openai)
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def _get_provider(
        self, fingerprint: Any, monkeypatch: pytest.MonkeyPatch
    ) -> Any:
        self._setup_fake_openai(fingerprint, monkeypatch)
        sys.path.insert(0, str(_EVAL_DIR))
        try:
            return _providers.resolve_provider("openai")
        finally:
            sys.path[:] = [p for p in sys.path if p != str(_EVAL_DIR)]

    @pytest.mark.parametrize("fingerprint", ["fp-abc", ""])
    def test_str_fingerprint_stored_as_is(
        self, fingerprint: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = self._get_provider(fingerprint, monkeypatch)
        provider.complete(messages=[{"role": "user", "content": "hi"}], model="gpt-4o")
        assert provider.system_fingerprint == fingerprint

    def test_none_fingerprint_stored_as_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = self._get_provider(None, monkeypatch)
        provider.complete(messages=[{"role": "user", "content": "hi"}], model="gpt-4o")
        assert provider.system_fingerprint is None

    @pytest.mark.parametrize("bad_value", [42, []])
    def test_raises_on_non_str_non_none(
        self, bad_value: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = self._get_provider(bad_value, monkeypatch)
        with pytest.raises(RuntimeError, match="system_fingerprint must be str or None"):
            provider.complete(messages=[{"role": "user", "content": "hi"}], model="gpt-4o")
