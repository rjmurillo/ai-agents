"""Shared fixtures for eval-harness tests.

The eval mains now run ``verify_model_available()`` before a live run
(issue #2857), which probes ``GET /v1/models``. Keep unit and integration
tests hermetic by skipping that network probe by default. Tests that exercise
the preflight itself delenv ``EVAL_SKIP_MODEL_PREFLIGHT`` explicitly.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _skip_model_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_SKIP_MODEL_PREFLIGHT", "1")
