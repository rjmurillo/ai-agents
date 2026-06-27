"""Shared pytest fixtures for hook tests."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable


# Operator escape hatches for the LSP-first guards (ADR-062). LSP_DOWN
# (issue #2622) flips read/grep/pre-delegation guards from BLOCK to ALLOW for a
# dead language server; SKIP_LSP_GATE disables the gate; LSP_GATE_MODE=warn
# downgrades it to advisory. When any of these is exported in the operator
# environment it leaks into the test process and silently turns the guards'
# would-block assertions into allow (issue #2759). Neutralize all three so each
# test exercises gate logic against the env it sets explicitly. Tests that
# assert the escape-hatch behavior re-set the var inside the test body, which
# wins over this fixture.
_LSP_GUARD_OVERRIDE_ENV = ("LSP_DOWN", "SKIP_LSP_GATE", "LSP_GATE_MODE")


@pytest.fixture(autouse=True)
def _neutralize_lsp_guard_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear ambient LSP-guard override env vars before every hook test."""
    for name in _LSP_GUARD_OVERRIDE_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def mock_stdin(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    """Create a factory fixture for mocking stdin with content.

    Returns a function that sets sys.stdin to a StringIO with the given content.
    Use io.StringIO for cleaner stdin mocking since it has real read() and isatty()
    methods.

    Example:
        def test_something(mock_stdin):
            mock_stdin('{"tool_input": {"command": "test"}}')
            assert main() == 0
    """

    def _mock_stdin(content: str) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(content))

    return _mock_stdin
