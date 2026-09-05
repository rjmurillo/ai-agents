#!/usr/bin/env python3
"""Tests for memory_router module.

Coverage target: all public and key private functions.

Exit codes (ADR-035):
    0 - Success: all tests passed
    1 - Error: one or more tests failed
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from memory_core.memory_router import (
    get_content_hash,
    get_memory_router_status,
    invoke_serena_search,
    reset_caches,
    search_memory,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_module_caches() -> None:
    """Reset module caches before each test."""
    reset_caches()


@pytest.fixture()
def memory_dir(tmp_path: Path) -> Path:
    """Create a temporary memory directory with test files."""
    mem_dir = tmp_path / "memories"
    mem_dir.mkdir()

    (mem_dir / "schema-validation.md").write_text(
        "# Schema Validation\nValidation content.", encoding="utf-8"
    )
    (mem_dir / "memory-router.md").write_text(
        "# Memory Router\nRouter content.", encoding="utf-8"
    )
    (mem_dir / "reflexion-memory.md").write_text(
        "# Reflexion Memory\nReflexion content.", encoding="utf-8"
    )
    (mem_dir / "yagni-principle.md").write_text(
        "# YAGNI\nYou ain't gonna need it.", encoding="utf-8"
    )
    (mem_dir / "boy-scout-rule.md").write_text(
        "# Boy Scout Rule\nLeave code cleaner.", encoding="utf-8"
    )

    return mem_dir


# ---------------------------------------------------------------------------
# get_content_hash tests
# ---------------------------------------------------------------------------


class TestGetContentHash:
    """Tests for get_content_hash function."""

    def test_returns_64_char_hex_string(self) -> None:
        result = get_content_hash("hello")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic_for_same_input(self) -> None:
        assert get_content_hash("test") == get_content_hash("test")

    def test_different_for_different_input(self) -> None:
        assert get_content_hash("hello") != get_content_hash("world")

    def test_handles_empty_string(self) -> None:
        result = get_content_hash("")
        assert len(result) == 64


# ---------------------------------------------------------------------------
# invoke_serena_search tests
# ---------------------------------------------------------------------------


class TestInvokeSerenaSearch:
    """Tests for invoke_serena_search function."""

    def test_returns_empty_for_nonexistent_path(self) -> None:
        result = invoke_serena_search("test", memory_path="/nonexistent")
        assert result == []

    def test_returns_empty_for_short_keywords(
        self, memory_dir: Path
    ) -> None:
        result = invoke_serena_search("ab", memory_path=str(memory_dir))
        assert result == []

    def test_finds_matching_files(self, memory_dir: Path) -> None:
        results = invoke_serena_search(
            "memory router", memory_path=str(memory_dir)
        )
        assert len(results) > 0
        names = [r.name for r in results]
        assert "memory-router" in names

    def test_scores_by_keyword_match_percentage(
        self, memory_dir: Path
    ) -> None:
        results = invoke_serena_search(
            "memory router", memory_path=str(memory_dir)
        )
        # "memory-router" matches both keywords (100%)
        # "reflexion-memory" matches "memory" only (50%)
        router_result = next(r for r in results if r.name == "memory-router")
        assert router_result.score == 100.0

    def test_limits_results_to_max(self, memory_dir: Path) -> None:
        results = invoke_serena_search(
            "memory", memory_path=str(memory_dir), max_results=2
        )
        assert len(results) <= 2

    def test_skip_content_returns_null_content(
        self, memory_dir: Path
    ) -> None:
        results = invoke_serena_search(
            "memory", memory_path=str(memory_dir), skip_content=True
        )
        assert len(results) > 0
        for r in results:
            assert r.content is None
            assert r.hash is None

    def test_includes_content_and_hash_by_default(
        self, memory_dir: Path
    ) -> None:
        results = invoke_serena_search(
            "memory", memory_path=str(memory_dir)
        )
        assert len(results) > 0
        for r in results:
            assert r.content is not None
            assert r.hash is not None
            assert len(r.hash) == 64

    def test_source_is_serena(self, memory_dir: Path) -> None:
        results = invoke_serena_search(
            "memory", memory_path=str(memory_dir)
        )
        for r in results:
            assert r.source == "Serena"


# ---------------------------------------------------------------------------
# search_memory tests
# ---------------------------------------------------------------------------


class TestSearchMemory:
    """Tests for search_memory function."""

    def test_raises_for_empty_query(self) -> None:
        with pytest.raises(ValueError, match="1-500 characters"):
            search_memory("")

    def test_raises_for_invalid_characters(self) -> None:
        with pytest.raises(ValueError, match="invalid characters"):
            search_memory("test; rm -rf /")

    def test_raises_for_long_query(self) -> None:
        with pytest.raises(ValueError, match="1-500 characters"):
            search_memory("x" * 501)

    def test_raises_for_invalid_max_results(self) -> None:
        with pytest.raises(ValueError, match="between 1 and 100"):
            search_memory("test", max_results=0)

    @pytest.mark.parametrize(
        "removed_parameter", ["semantic_only", "lexical_only"]
    )
    def test_rejects_removed_backend_selection_parameters(
        self, removed_parameter: str
    ) -> None:
        """Both parameters chose between backends; one backend remains.

        Negative control for the contract change. Without this a caller
        passing the old parameter would fail somewhere downstream instead of
        at the call site, and a later reader could not tell the removal was
        deliberate.
        """
        with pytest.raises(TypeError, match=removed_parameter):
            search_memory("test", **{removed_parameter: True})

    def test_returns_results_carrying_content(self, memory_dir: Path) -> None:
        """The single path reads content, as the two-backend default did.

        Content was skipped only under the lexical-only parameter. Dropping
        that parameter must not silently promote its cheaper behaviour to the
        default, because callers read `content` off the result.
        """
        with patch(
            "memory_core.memory_router._config",
            {"serena_path": str(memory_dir), "max_results": 10},
        ), patch(
            "memory_core.memory_router.invoke_serena_search",
            wraps=invoke_serena_search,
        ) as mock_serena:
            results = search_memory("memory")

        mock_serena.assert_called_once()
        _, kwargs = mock_serena.call_args
        assert "skip_content" not in kwargs
        assert results
        assert all(r.content is not None for r in results)
        assert all(r.source == "Serena" for r in results)


# ---------------------------------------------------------------------------
# get_memory_router_status tests
# ---------------------------------------------------------------------------


class TestGetMemoryRouterStatus:
    """Tests for get_memory_router_status function."""

    def test_returns_diagnostic_info(self) -> None:
        status = get_memory_router_status()
        assert "Serena" in status
        assert "Configuration" in status

    def test_serena_section_has_available_and_path(self) -> None:
        status = get_memory_router_status()
        assert "Available" in status["Serena"]
        assert "Path" in status["Serena"]

    def test_omits_retired_backend_and_its_probe_cache(self) -> None:
        """Negative control: no status block for a backend that is gone.

        The `Cache` block reported the age of the availability probe's
        30-second result cache. With no probe there is nothing to report, and
        leaving an always-empty block would read as a backend that is merely
        down.
        """
        status = get_memory_router_status()
        assert "Cache" not in status
        assert set(status) == {"Serena", "Configuration"}
        assert not any("port" in key for key in status["Configuration"])


@pytest.fixture()
def nested_memory_dir(tmp_path: Path) -> Path:
    """Memory directory using the topic-subdirectory layout."""
    mem_dir = tmp_path / "nested-memories"
    (mem_dir / "ci").mkdir(parents=True)
    (mem_dir / "toplevel-router.md").write_text(
        "# Top Level\nContent.", encoding="utf-8"
    )
    (mem_dir / "ci" / "nested-router.md").write_text(
        "# Nested\nContent.", encoding="utf-8"
    )
    return mem_dir


class TestNestedMemoryDiscovery:
    """The corpus keeps 851 of 974 memories in topic subdirectories."""

    def test_finds_nested_memories(self, nested_memory_dir: Path) -> None:
        results = invoke_serena_search(
            "nested router", memory_path=str(nested_memory_dir)
        )
        assert [r.name for r in results if "nested" in r.name] == [
            "ci/nested-router"
        ]

    def test_nested_name_is_addressable(
        self, nested_memory_dir: Path
    ) -> None:
        """read_memory() takes 'subdir/name'; a bare stem does not resolve."""
        results = invoke_serena_search(
            "nested router", memory_path=str(nested_memory_dir)
        )
        nested = next(r for r in results if "nested" in r.name)
        assert nested.name == "ci/nested-router"
        assert "\\" not in nested.name

    def test_top_level_name_has_no_directory_prefix(
        self, nested_memory_dir: Path
    ) -> None:
        """Guards the 123 existing top-level names against a rename."""
        results = invoke_serena_search(
            "toplevel router", memory_path=str(nested_memory_dir)
        )
        assert "toplevel-router" in [r.name for r in results]

    def test_directory_only_match_scores_below_stem_match(
        self, nested_memory_dir: Path
    ) -> None:
        """A topic directory must not outrank the file the query named.

        Matching on the relative path let every file under a topic directory
        collect a perfect score for that topic keyword, which buried the
        top-level file the query actually named.

        The directory is `agents`, not the fixture's `ci`, because
        `invoke_serena_search` drops query tokens of two characters or fewer.
        """
        (nested_memory_dir / "agents").mkdir()
        (nested_memory_dir / "agents" / "buried.md").write_text(
            "# Buried\nContent.", encoding="utf-8"
        )
        (nested_memory_dir / "agents-toplevel.md").write_text(
            "# Top\nContent.", encoding="utf-8"
        )
        by_name = {
            r.name: r.score
            for r in invoke_serena_search(
                "agents", memory_path=str(nested_memory_dir)
            )
        }
        assert by_name["agents-toplevel"] == 100.0
        assert by_name["agents/buried"] == 50.0

    def test_top_level_score_matches_pre_subdirectory_behaviour(
        self, nested_memory_dir: Path
    ) -> None:
        """A top-level stem is its whole relative path, so weighting is a no-op."""
        results = invoke_serena_search(
            "toplevel router", memory_path=str(nested_memory_dir)
        )
        scores = {r.name: r.score for r in results}
        assert scores["toplevel-router"] == 100.0
