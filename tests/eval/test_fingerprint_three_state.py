"""Tests for the three-state system_fingerprint contract (issue #4123).

Three states:
- present-and-valid: str -> recorded verbatim
- present-but-malformed: non-str, non-None -> recorded as "<malformed:TYPENAME>"
- absent: None -> recorded as None

Each test class tests normalize_fingerprint directly so the upstream invariants
in the real transports cannot make the malformed branch unreachable. The
integration tests further verify the sentinel flows through the actual transport
stubs used in production.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_EVAL_DIR = Path(__file__).parent.parent.parent / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

import _eval_api_adapter_constants as _constants


class TestNormalizeFingerprintContract:
    """Unit tests for normalize_fingerprint (all three states)."""

    def test_none_returns_none(self) -> None:
        assert _constants.normalize_fingerprint(None) is None

    def test_string_returned_verbatim(self) -> None:
        assert _constants.normalize_fingerprint("fp-abc123") == "fp-abc123"

    def test_empty_string_returned_verbatim(self) -> None:
        """Empty string is a valid (if unusual) str, not malformed."""
        assert _constants.normalize_fingerprint("") == ""

    def test_integer_returns_sentinel(self) -> None:
        result = _constants.normalize_fingerprint(42)
        assert result == "<malformed:int>"

    def test_list_returns_sentinel(self) -> None:
        result = _constants.normalize_fingerprint(["fp"])
        assert result == "<malformed:list>"

    def test_dict_returns_sentinel(self) -> None:
        result = _constants.normalize_fingerprint({"fp": "x"})
        assert result == "<malformed:dict>"

    def test_bool_returns_sentinel(self) -> None:
        """bool subclasses int; ensure it gets its own typename."""
        result = _constants.normalize_fingerprint(True)
        assert result == "<malformed:bool>"

    def test_float_returns_sentinel(self) -> None:
        result = _constants.normalize_fingerprint(3.14)
        assert result == "<malformed:float>"

    # Inverted control: sentinel strings are themselves valid str, not malformed
    def test_sentinel_string_is_not_re_encoded(self) -> None:
        sentinel = "<malformed:int>"
        assert _constants.normalize_fingerprint(sentinel) == sentinel


class TestNormalizeFingerprintDistinguishesStates:
    """Malformed is not the same as absent."""

    def test_malformed_differs_from_absent(self) -> None:
        malformed = _constants.normalize_fingerprint(99)
        absent = _constants.normalize_fingerprint(None)
        assert malformed != absent
        assert malformed is not None
        assert absent is None

    def test_malformed_differs_from_valid(self) -> None:
        malformed = _constants.normalize_fingerprint(99)
        valid = _constants.normalize_fingerprint("fp-real")
        assert malformed != valid

    def test_typename_in_sentinel(self) -> None:
        """The sentinel carries the unexpected type for diagnosis."""
        result = _constants.normalize_fingerprint(42)
        assert "int" in result


class TestOpenAITransportFingerprintIntegration:
    """_OpenAIProviderTransport records the sentinel when the provider returns non-str."""

    def _make_transport(self, fingerprint: Any) -> Any:
        import _eval_api_adapter as adapter

        class _FakeProvider:
            system_fingerprint: Any = fingerprint

            def complete(self, **_: object) -> str:
                return "answer"

        t = adapter._OpenAIProviderTransport.__new__(adapter._OpenAIProviderTransport)
        t._provider = _FakeProvider()
        t._seed = None
        t.system_fingerprint = None
        return t

    def test_valid_fingerprint_recorded(self) -> None:
        t = self._make_transport("fp-valid")
        t("prompt", "model", "system")
        assert t.system_fingerprint == "fp-valid"

    def test_none_fingerprint_recorded_as_none(self) -> None:
        t = self._make_transport(None)
        t("prompt", "model", "system")
        assert t.system_fingerprint is None

    def test_int_fingerprint_recorded_as_sentinel(self) -> None:
        t = self._make_transport(42)
        t("prompt", "model", "system")
        assert t.system_fingerprint == "<malformed:int>"

    def test_list_fingerprint_recorded_as_sentinel(self) -> None:
        t = self._make_transport(["fp"])
        t("prompt", "model", "system")
        assert t.system_fingerprint == "<malformed:list>"

    # Inverted control: valid string must NOT become a sentinel
    def test_valid_string_not_sentinel(self) -> None:
        t = self._make_transport("fp-real")
        t("prompt", "model", "system")
        assert not t.system_fingerprint.startswith("<malformed:")


class TestAnthropicTransportFingerprintIntegration:
    """_AnthropicTransport records the sentinel when metadata holds non-str."""

    def _make_transport_with_metadata(
        self, fingerprint: Any
    ) -> tuple[Any, dict[str, Any]]:
        import _eval_api_adapter as adapter

        captured_metadata: dict[str, Any] = {}

        def _fake_call_api(**kwargs: Any) -> str:
            md = kwargs.get("metadata")
            if isinstance(md, dict):
                md["system_fingerprint"] = fingerprint
            return "answer"

        t = adapter._AnthropicTransport.__new__(adapter._AnthropicTransport)
        t._api_key = "key"
        t._seed = None
        t.system_fingerprint = None

        original_call_api = adapter.call_api

        class _Ctx:
            def __enter__(self) -> _Ctx:
                adapter.call_api = _fake_call_api  # type: ignore[assignment]
                return self

            def __exit__(self, *_: object) -> None:
                adapter.call_api = original_call_api

        return t, _Ctx()

    def test_int_fingerprint_recorded_as_sentinel(self) -> None:
        import _eval_api_adapter as adapter

        def _fake_call_api(**kwargs: Any) -> str:
            md = kwargs.get("metadata")
            if isinstance(md, dict):
                md["system_fingerprint"] = 99
            return "answer"

        original = adapter.call_api
        adapter.call_api = _fake_call_api  # type: ignore[assignment]
        try:
            t = adapter._AnthropicTransport.__new__(adapter._AnthropicTransport)
            t._api_key = "key"
            t._seed = None
            t.system_fingerprint = None
            t("prompt", "model", "system")
            assert t.system_fingerprint == "<malformed:int>"
        finally:
            adapter.call_api = original

    def test_none_fingerprint_recorded_as_none(self) -> None:
        import _eval_api_adapter as adapter

        def _fake_call_api(**kwargs: Any) -> str:
            return "answer"

        original = adapter.call_api
        adapter.call_api = _fake_call_api  # type: ignore[assignment]
        try:
            t = adapter._AnthropicTransport.__new__(adapter._AnthropicTransport)
            t._api_key = "key"
            t._seed = None
            t.system_fingerprint = None
            t("prompt", "model", "system")
            assert t.system_fingerprint is None
        finally:
            adapter.call_api = original
