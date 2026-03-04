"""Tests for search_memory.py."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import search_memory


class TestValidateQuery:
    """Tests for validate_query function."""

    def test_valid_query(self):
        # validate_query returns None on success (no error)
        assert search_memory.validate_query("git hooks") is None

    def test_empty_query(self):
        assert search_memory.validate_query("") is not None

    def test_too_long(self):
        assert search_memory.validate_query("x" * 501) is not None

    def test_special_chars_rejected(self):
        assert search_memory.validate_query("query; rm -rf /") is not None

    def test_allowed_punctuation(self):
        assert search_memory.validate_query("test-query, another (one)") is None


class TestSearchSerena:
    """Tests for search_serena function."""

    def test_finds_matching_files(self, tmp_path):
        (tmp_path / "security-scan.md").write_text("# Security scanning details")
        (tmp_path / "git-hooks.md").write_text("# Git hook patterns")

        results = search_memory.search_serena("security", tmp_path, 10)
        assert len(results) >= 1
        assert results[0]["Name"] == "security-scan"
        assert results[0]["Source"] == "Serena"

    def test_no_matches(self, tmp_path):
        (tmp_path / "unrelated.md").write_text("# Something else")
        results = search_memory.search_serena("security", tmp_path, 10)
        assert len(results) == 0

    def test_respects_max_results(self, tmp_path):
        for i in range(10):
            (tmp_path / f"test-item-{i}.md").write_text(f"# Test {i}")
        results = search_memory.search_serena("test", tmp_path, 3)
        assert len(results) <= 3

    def test_sorts_by_score(self, tmp_path):
        (tmp_path / "security-patterns.md").write_text("# Patterns")
        (tmp_path / "security.md").write_text("# Security")
        results = search_memory.search_serena("security patterns", tmp_path, 10)
        if len(results) >= 2:
            assert results[0]["Score"] >= results[1]["Score"]

    def test_missing_directory(self, tmp_path):
        results = search_memory.search_serena("test", tmp_path / "missing", 10)
        assert results == []


class TestGetMemoryRouterStatus:
    """Tests for get_memory_router_status function."""

    def test_serena_available(self, tmp_path):
        (tmp_path / "test.md").write_text("# Test")
        status = search_memory.get_memory_router_status(tmp_path)
        assert status["Serena"]["Available"] is True
        assert status["Serena"]["MemoryCount"] >= 1

    def test_serena_unavailable(self, tmp_path):
        status = search_memory.get_memory_router_status(tmp_path / "missing")
        assert status["Serena"]["Available"] is False

    def test_forgetful_unavailable(self, tmp_path):
        status = search_memory.get_memory_router_status(tmp_path)
        assert status["Forgetful"]["Available"] is False
