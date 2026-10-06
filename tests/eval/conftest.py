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


@pytest.fixture(autouse=True)
def _hermetic_credential_sources(monkeypatch: pytest.MonkeyPatch):
    """Keep the subscription transports off the operator's real logins.

    The shared credential order reads dotenv files, the CLIs' on-disk logins,
    and runs `claude auth status`, `codex login status`, and `gh auth token`.
    A unit test must reach none of that. Each transport's spec is replaced
    with one that has no disk credential and reports an existing login, which
    is the state every pre-existing transport test already assumed. A test
    about credential order replaces the spec again with `set_sources`.
    """
    from tests.eval._credential_test_support import install_inert_sources

    install_inert_sources(monkeypatch)
    yield
    from tests.eval._credential_test_support import reset_cache

    reset_cache()
