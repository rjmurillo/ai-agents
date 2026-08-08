"""Shared fixtures for CI tests."""

from collections.abc import Iterator
from unittest.mock import patch

import pytest


@pytest.fixture
def _zero_non_target_aggregate_counts() -> Iterator[None]:
    """Return zero from auxiliary counters only for tests that opt in."""
    with (
        patch("scripts.ci.memory_index_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.cli_exit_contract_ratchet.current_count", return_value=0),
    ):
        yield
