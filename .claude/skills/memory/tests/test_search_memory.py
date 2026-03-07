#!/usr/bin/env python3
"""Tests for search_memory.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ..scripts.search_memory import (
    estimate_tokens,
    get_memory_router_status,
    main,
    search_serena,
    validate_query,
)
from ..scripts.search_memory import (
    test_forgetful_available as check_forgetful,
)


class TestValidateQuery:
    """Tests for query validation."""

    def test_valid_query(self) -> None:
        assert validate_query("git hooks") is None

    def test_empty_query(self) -> None:
        result = validate_query("")
        assert result is not None
        assert "1-500" in result

    def test_too_long_query(self) -> None:
        result = validate_query("a" * 501)
        assert result is not None
        assert "1-500" in result

    def test_invalid_characters(self) -> None:
        result = validate_query("test<script>alert(1)</script>")
        assert result is not None
        assert "invalid characters" in result

    def test_valid_with_punctuation(self) -> None:
        assert validate_query("git hooks, patterns & more") is None


class TestEstimateTokens:
    """Tests for token estimation."""

    def test_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("a" * 400)
        assert estimate_tokens(f) == 100

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        f = tmp_path / "missing.md"
        assert estimate_tokens(f) == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.md"
        f.write_text("")
        assert estimate_tokens(f) == 0


class TestSearchSerena:
    """Tests for Serena lexical search."""

    def test_search_finds_matching_files(self, tmp_path: Path) -> None:
        (tmp_path / "git-hooks-patterns.md").write_text("# Git Hooks\nContent about hooks")
        (tmp_path / "unrelated.md").write_text("# Unrelated\nNo match")

        results = search_serena("git hooks", tmp_path, 10)
        assert len(results) >= 1
        assert results[0]["Name"] == "git-hooks-patterns"
        assert results[0]["Source"] == "Serena"

    def test_search_empty_directory(self, tmp_path: Path) -> None:
        results = search_serena("anything", tmp_path, 10)
        assert results == []

    def test_search_nonexistent_directory(self, tmp_path: Path) -> None:
        results = search_serena("test", tmp_path / "missing", 10)
        assert results == []

    def test_search_respects_max_results(self, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"test-file-{i}.md").write_text(f"# Test {i}")

        results = search_serena("test file", tmp_path, 2)
        assert len(results) <= 2

    def test_search_scores_by_keyword_match(self, tmp_path: Path) -> None:
        (tmp_path / "git-hooks.md").write_text("both keywords")
        (tmp_path / "git-only.md").write_text("partial")

        results = search_serena("git hooks", tmp_path, 10)
        if len(results) >= 2:
            assert results[0]["Score"] >= results[1]["Score"]


class TestForgetfulAvailable:
    """Tests for Forgetful availability check."""

    def test_unavailable(self) -> None:
        with patch("socket.create_connection", side_effect=OSError("refused")):
            assert check_forgetful() is False

    def test_available(self) -> None:
        mock_conn = type("MockConn", (), {"__enter__": lambda s: s, "__exit__": lambda *a: None})()
        with patch("socket.create_connection", return_value=mock_conn):
            assert check_forgetful() is True


class TestGetMemoryRouterStatus:
    """Tests for memory router status."""

    def test_with_serena_path(self, tmp_path: Path) -> None:
        serena = tmp_path / "memories"
        serena.mkdir()
        (serena / "test.md").write_text("content")

        with patch("socket.create_connection", side_effect=OSError("refused")):
            status = get_memory_router_status(serena)
            assert status["Serena"]["Available"] is True
            assert status["Serena"]["MemoryCount"] == 1

    def test_with_missing_path(self, tmp_path: Path) -> None:
        status = get_memory_router_status(tmp_path / "missing")
        assert status["Serena"]["Available"] is False


class TestMainFunction:
    """Tests for the main CLI entry point."""

    def test_valid_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        serena = tmp_path / "memories"
        serena.mkdir()
        (serena / "git-hooks.md").write_text("# Git Hooks\nTest content")

        result = main([
            "git hooks",
            "--serena-path", str(serena),
            "--lexical-only",
        ])
        assert result == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["Query"] == "git hooks"
        assert output["Source"] == "Serena"
        assert isinstance(output["Results"], list)

    def test_table_format(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        serena = tmp_path / "memories"
        serena.mkdir()

        result = main([
            "test query",
            "--serena-path", str(serena),
            "--lexical-only",
            "--format", "table",
        ])
        assert result == 0
        captured = capsys.readouterr()
        assert "No results found" in captured.out

    def test_invalid_query_returns_1(self, capsys: pytest.CaptureFixture) -> None:
        result = main(["test<invalid>"])
        assert result == 1

    def test_empty_results(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        serena = tmp_path / "memories"
        serena.mkdir()

        result = main([
            "nonexistent",
            "--serena-path", str(serena),
            "--lexical-only",
        ])
        assert result == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["Count"] == 0
