"""Shared pytest fixtures for hook tests."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable


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
