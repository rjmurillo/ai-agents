"""Shared pytest fixtures for Semgrep scanner tests."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest


@pytest.fixture
def stub_pinned_semgrep_executable() -> Iterator[None]:
    """Stub executable resolution without a ``semgrep --version`` subprocess.

    The resolver verifies the binary against the ``pyproject.toml`` pin. Tests
    that mock ``subprocess.run`` to script the scan need this separate probe
    stubbed, or it consumes their scan mock. Resolver behavior has its own
    coverage in ``tests/test_run_semgrep_pinning.py``.
    """
    with patch(
        "scripts.security.run_semgrep._resolve_semgrep_executable",
        return_value="/pinned/semgrep",
    ):
        yield
