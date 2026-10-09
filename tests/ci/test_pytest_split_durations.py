"""The committed durations file names most of the pool (issue #6239, AC2).

pytest-split balances by recorded duration, so a stale file skews the groups.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ci import run_pytest_partition as runner
from tests.ci.pytest_split_collect_helpers import (
    REPO,
    collect,
    load_durations,
    missing_fraction,
    pool_args,
)

_DURATIONS = REPO / runner.DURATIONS_PATH

# The share of the pool allowed to be missing from the durations file before a
# split group stops being balanced. pytest-split assigns an unknown test the
# average known duration, so a small gap is harmless; a large one skews groups.
MAX_MISSING_FRACTION = 0.20


class TestMissingFraction:
    def test_all_known_is_zero(self) -> None:
        assert missing_fraction(["a::t", "b::t"], {"a::t": 1.0, "b::t": 2.0}) == 0.0

    def test_counts_only_ids_absent_from_the_file(self) -> None:
        assert missing_fraction(["a::t", "b::t", "c::t", "d::t"], {"a::t": 1.0}) == 0.75

    def test_extra_entries_for_deleted_tests_do_not_count(self) -> None:
        assert missing_fraction(["a::t"], {"a::t": 1.0, "gone::t": 5.0}) == 0.0

    def test_an_empty_pool_is_an_error_not_a_pass(self) -> None:
        with pytest.raises(ValueError, match="collected no tests"):
            missing_fraction([], {"a::t": 1.0})

    def test_whitespace_in_an_id_is_not_trimmed(self) -> None:
        assert missing_fraction(["a::t "], {"a::t": 1.0}) == 1.0


class TestLoadDurations:
    def test_reads_node_ids_and_seconds(self, tmp_path: Path) -> None:
        path = tmp_path / "d"
        path.write_text('{"a::t": 1.5}', encoding="utf-8")
        assert load_durations(path) == {"a::t": 1.5}

    def test_a_non_object_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "d"
        path.write_text("[1, 2]", encoding="utf-8")
        with pytest.raises(ValueError, match="not a JSON object"):
            load_durations(path)

    def test_malformed_json_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "d"
        path.write_text("{", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_durations(path)

    def test_a_non_numeric_duration_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "d"
        path.write_text('{"a::t": "soon"}', encoding="utf-8")
        with pytest.raises(ValueError):
            load_durations(path)


@pytest.mark.timeout(300)
def test_the_durations_file_names_most_of_the_pool() -> None:
    """Refresh it with the command in tests/AGENTS.md when this fails.

    Fails when the file is absent: the file is committed, and a missing one
    means the splits silently fall back to an even count split.
    """
    assert _DURATIONS.is_file(), f"{runner.DURATIONS_PATH} is not committed; see tests/AGENTS.md"
    pool_ids = collect(pool_args())
    fraction = missing_fraction(pool_ids, load_durations(_DURATIONS))
    assert fraction <= MAX_MISSING_FRACTION, (
        f"{fraction:.1%} of the pool is missing from {runner.DURATIONS_PATH} "
        f"(limit {MAX_MISSING_FRACTION:.0%}); refresh it, see tests/AGENTS.md"
    )
