"""Tests for http_timeout_seconds in scripts/eval/_eval_api_adapter_constants.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _eval_api_adapter_constants as http  # noqa: E402

ENV = "EVAL_HTTP_TIMEOUT_SECONDS"


@pytest.mark.parametrize("value", [None, "", "  "])
def test_unset_or_blank_uses_the_default(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, value)

    assert http.http_timeout_seconds() == 120.0


@pytest.mark.parametrize(("value", "expected"), [("900", 900.0), ("1800", 1800.0), ("0.5", 0.5)])
def test_valid_override_is_used(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: float
) -> None:
    monkeypatch.setenv(ENV, value)

    assert http.http_timeout_seconds() == expected


@pytest.mark.parametrize("value", ["soon", "0", "-5", "1800.1", "inf", "nan"])
def test_invalid_override_raises(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(ENV, value)

    with pytest.raises(RuntimeError, match=ENV):
        http.http_timeout_seconds()
