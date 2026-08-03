"""Tests for the system_fingerprint boundary contract (issue #4123)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_EVAL_DIR = Path(__file__).parent.parent.parent / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

import _eval_api_adapter_constants as _constants  # noqa: E402  # sys.path must be set first
from _eval_common import MalformedProviderMetadataError  # noqa: E402


class TestNormalizeFingerprintContract:
    """Valid values pass through and malformed values fail fast."""

    def test_none_returns_none(self) -> None:
        assert _constants.normalize_fingerprint(None) is None

    def test_string_returned_verbatim(self) -> None:
        assert _constants.normalize_fingerprint("fp-abc123") == "fp-abc123"

    def test_empty_string_returned_verbatim(self) -> None:
        """Empty string is a valid (if unusual) str, not malformed."""
        assert _constants.normalize_fingerprint("") == ""

    @pytest.mark.parametrize("malformed", [42, ["fp"], {"fp": "x"}, True, 3.14])
    def test_malformed_value_raises(self, malformed: object) -> None:
        with pytest.raises(
            MalformedProviderMetadataError,
            match=f"non-string system_fingerprint \\({type(malformed).__name__}\\)",
        ):
            _constants.normalize_fingerprint(malformed)

    def test_sentinel_shaped_string_remains_a_valid_string(self) -> None:
        sentinel = "<malformed:int>"
        assert _constants.normalize_fingerprint(sentinel) == sentinel


class TestOpenAITransportFingerprintIntegration:
    """The OpenAI transport applies the shared boundary policy."""

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

    def test_int_fingerprint_raises(self) -> None:
        t = self._make_transport(42)
        with pytest.raises(MalformedProviderMetadataError):
            t("prompt", "model", "system")
        assert t.system_fingerprint is None

    def test_list_fingerprint_raises(self) -> None:
        t = self._make_transport(["fp"])
        with pytest.raises(MalformedProviderMetadataError):
            t("prompt", "model", "system")
        assert t.system_fingerprint is None

    # Inverted control: valid string must NOT become a sentinel
    def test_valid_string_not_sentinel(self) -> None:
        t = self._make_transport("fp-real")
        t("prompt", "model", "system")
        assert not t.system_fingerprint.startswith("<malformed:")


class TestAnthropicTransportFingerprintIntegration:
    """The Anthropic transport applies the shared boundary policy."""

    def test_int_fingerprint_raises(self) -> None:
        import _eval_api_adapter as adapter

        def _fake_call_api(**kwargs: Any) -> str:
            md = kwargs.get("metadata")
            if isinstance(md, dict):
                md["system_fingerprint"] = 99
            return "answer"

        with patch("_eval_api_adapter.call_api", side_effect=_fake_call_api):
            t = adapter._AnthropicTransport.__new__(adapter._AnthropicTransport)
            t._api_key = "key"
            t._seed = None
            t.system_fingerprint = None
            with pytest.raises(MalformedProviderMetadataError):
                t("prompt", "model", "system")
            assert t.system_fingerprint is None

    def test_none_fingerprint_recorded_as_none(self) -> None:
        import _eval_api_adapter as adapter

        def _fake_call_api(**kwargs: Any) -> str:
            return "answer"

        with patch("_eval_api_adapter.call_api", side_effect=_fake_call_api):
            t = adapter._AnthropicTransport.__new__(adapter._AnthropicTransport)
            t._api_key = "key"
            t._seed = None
            t.system_fingerprint = None
            t("prompt", "model", "system")
            assert t.system_fingerprint is None
