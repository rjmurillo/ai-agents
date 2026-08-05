"""Shared fixtures for CI tests."""

from collections.abc import Iterator
from unittest.mock import patch

import pytest


@pytest.fixture
def _zero_memory_index_count() -> Iterator[None]:
    """Return zero from the memory counter only for tests that opt in."""
    with patch("scripts.ci.memory_index_count_ratchet.current_count", return_value=0):
        yield
