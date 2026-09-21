"""Tests for the diagnostic drift failure script."""

from __future__ import annotations

import pytest

from scripts.ci import show_drift_failure


def test_main_requires_step_conclusions(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "VALIDATE_CONCLUSION",
        "LIB_MIRROR_CONCLUSION",
        "MANIFEST_PARITY_CONCLUSION",
    ):
        monkeypatch.delenv(name, raising=False)

    assert show_drift_failure.main([]) == show_drift_failure.EXIT_USAGE
