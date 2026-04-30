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
    MemoryResult,
    get_content_hash,
    get_memory_router_status,
    invoke_serena_search,
    merge_memory_results,
    reset_caches,
    search_memory,
    test_forgetful_available,
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
# merge_memory_results tests
# ---------------------------------------------------------------------------


class TestMergeMemoryResults:
    """Tests for merge_memory_results function."""

    def test_serena_results_come_first(self) -> None:
        serena = [
            MemoryResult(
                name="s1", content="a", source="Serena", score=80, hash="aaa"
            )
        ]
        forgetful = [
            MemoryResult(
                name="f1", content="b", source="Forgetful", score=90, hash="bbb"
            )
        ]
        merged = merge_memory_results(serena, forgetful)
        assert merged[0].source == "Serena"

    def test_deduplicates_by_hash(self) -> None:
        same_hash = get_content_hash("same content")
        serena = [
            MemoryResult(
                name="s1",
                content="same content",
                source="Serena",
                score=80,
                hash=same_hash,
            )
        ]
        forgetful = [
            MemoryResult(
                name="f1",
                content="same content",
                source="Forgetful",
                score=90,
                hash=same_hash,
            )
        ]
        merged = merge_memory_results(serena, forgetful)
        assert len(merged) == 1
        assert merged[0].source == "Serena"

    def test_includes_null_hash_results(self) -> None:
        serena = [
            MemoryResult(
                name="s1", content=None, source="Serena", score=80, hash=None
            )
        ]
        forgetful = [
            MemoryResult(
                name="f1", content=None, source="Forgetful", score=90, hash=None
            )
        ]
        merged = merge_memory_results(serena, forgetful)
        assert len(merged) == 2

    def test_limits_total_results(self) -> None:
        serena = [
            MemoryResult(
                name=f"s{i}",
                content=f"c{i}",
                source="Serena",
                score=80,
                hash=f"h{i}",
            )
            for i in range(10)
        ]
        merged = merge_memory_results(serena, max_results=5)
        assert len(merged) == 5

    def test_handles_empty_inputs(self) -> None:
        merged = merge_memory_results()
        assert merged == []


# ---------------------------------------------------------------------------
# test_forgetful_available tests
# ---------------------------------------------------------------------------


class TestTestForgetfulAvailable:
    """Tests for test_forgetful_available function."""

    def test_returns_false_when_port_not_listening(self) -> None:
        # Use a high port that's very unlikely to be in use
        result = test_forgetful_available(port=59999, force=True)
        assert result is False

    def test_caches_result(self) -> None:
        test_forgetful_available(port=59999, force=True)
        # Second call should use cache (no TCP connection)
        result = test_forgetful_available(port=59999)
        assert result is False

    def test_force_bypasses_cache(self) -> None:
        test_forgetful_available(port=59999, force=True)
        # Force should bypass cache
        result = test_forgetful_available(port=59999, force=True)
        assert result is False


# ---------------------------------------------------------------------------
# search_memory tests
# ---------------------------------------------------------------------------


class TestSearchMemory:
    """Tests for search_memory function."""

    def test_raises_for_both_flags(self) -> None:
        with pytest.raises(
            ValueError, match="Cannot specify both"
        ):
            search_memory("test", semantic_only=True, lexical_only=True)

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

    def test_semantic_only_raises_when_unavailable(self) -> None:
        with patch(
            "memory_core.memory_router.test_forgetful_available",
            return_value=False,
        ):
            with pytest.raises(RuntimeError, match="Forgetful is not available"):
                search_memory("test", semantic_only=True)

    def test_lexical_only_skips_content(self, memory_dir: Path) -> None:
        with patch(
            "memory_core.memory_router._config",
            {
                **{
                    "serena_path": str(memory_dir),
                    "forgetful_port": 8020,
                    "forgetful_timeout": 0.5,
                    "max_results": 10,
                },
            },
        ), patch(
            "memory_core.memory_router.invoke_serena_search",
            wraps=invoke_serena_search,
        ) as mock_serena:
            search_memory("memory", lexical_only=True)
            # Should have called invoke_serena_search with skip_content=True
            mock_serena.assert_called_once()
            _, kwargs = mock_serena.call_args
            assert kwargs.get("skip_content") is True


# ---------------------------------------------------------------------------
# get_memory_router_status tests
# ---------------------------------------------------------------------------


class TestGetMemoryRouterStatus:
    """Tests for get_memory_router_status function."""

    def test_returns_diagnostic_info(self) -> None:
        status = get_memory_router_status()
        assert "Serena" in status
        assert "Forgetful" in status
        assert "Cache" in status
        assert "Configuration" in status

    def test_serena_section_has_available_and_path(self) -> None:
        status = get_memory_router_status()
        assert "Available" in status["Serena"]
        assert "Path" in status["Serena"]

    def test_forgetful_section_has_available_and_endpoint(self) -> None:
        status = get_memory_router_status()
        assert "Available" in status["Forgetful"]
        assert "Endpoint" in status["Forgetful"]
