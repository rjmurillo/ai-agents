#!/usr/bin/env python3
"""Tests for search_memory.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ..scripts.search_memory import (
    estimate_tokens,
    get_memory_router_status,
    main,
    search_episodes,
    search_serena,
    validate_query,
)


def _write_episode(
    directory: Path, name: str, task: str, lessons: list[str] | None = None,
) -> Path:
    """Write a minimal episode record for search tests."""
    payload = {"id": name, "task": task, "lessons": lessons or []}
    path = directory / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


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

    def test_search_finds_nested_memories(self, tmp_path: Path) -> None:
        """Nested memories must be searchable.

        Regression: search used a non-recursive glob, so it saw only the
        123 top-level memories and none of the 845 under a subdirectory.
        Two memories were duplicated because the search that would have
        found them could not reach them.
        """
        (tmp_path / "ci").mkdir()
        (tmp_path / "ci" / "github-rate-limit-payload.md").write_text("# Rate limit")

        results = search_serena("rate limit payload", tmp_path, 10)

        assert [r["Name"] for r in results] == ["ci/github-rate-limit-payload"]

    def test_nested_name_is_addressable(self, tmp_path: Path) -> None:
        """Name carries the directory, so read_memory can resolve it.

        Returning the bare stem would send a caller to a path that does
        not exist, which is worse than not finding the memory at all.
        """
        (tmp_path / "process").mkdir()
        (tmp_path / "process" / "gh-graphql-budgets.md").write_text("# Budgets")

        results = search_serena("graphql budgets", tmp_path, 10)

        assert (tmp_path / f"{results[0]['Name']}.md").is_file()

    def test_top_level_name_has_no_directory_prefix(self, tmp_path: Path) -> None:
        """Recursion must not rename the top-level memories it already found."""
        (tmp_path / "git-hooks-patterns.md").write_text("# Git Hooks")

        results = search_serena("git hooks", tmp_path, 10)

        assert results[0]["Name"] == "git-hooks-patterns"

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


class TestGetMemoryRouterStatus:
    """Tests for memory router status."""

    def test_with_serena_path(self, tmp_path: Path) -> None:
        serena = tmp_path / "memories"
        serena.mkdir()
        (serena / "test.md").write_text("content")

        status = get_memory_router_status(serena)
        assert status["Serena"]["Available"] is True
        assert status["Serena"]["MemoryCount"] == 1
        assert set(status) == {"Serena", "Episodes"}

    def test_with_missing_path(self, tmp_path: Path) -> None:
        status = get_memory_router_status(tmp_path / "missing")
        assert status["Serena"]["Available"] is False

    def test_reports_episode_store(self, tmp_path: Path) -> None:
        serena = tmp_path / "memories"
        serena.mkdir()
        episodes = tmp_path / "episodes"
        episodes.mkdir()
        _write_episode(episodes, "episode-2026-01-02-alpha", "alpha task")

        status = get_memory_router_status(serena, episodes)
        assert status["Episodes"]["Available"] is True
        assert status["Episodes"]["MemoryCount"] == 1

    def test_episode_store_absent(self, tmp_path: Path) -> None:
        serena = tmp_path / "memories"
        serena.mkdir()
        status = get_memory_router_status(serena, tmp_path / "missing")
        assert status["Episodes"]["Available"] is False
        assert status["Episodes"]["MemoryCount"] == 0


class TestSearchEpisodes:
    """Tests for the Tier 2 episode reader (Issue #3630)."""

    def test_matches_name_slug(self, tmp_path: Path) -> None:
        _write_episode(tmp_path, "episode-2026-01-02-session-9-ruff-ratchet", "")
        _write_episode(tmp_path, "episode-2026-01-02-session-8-unrelated", "")

        results = search_episodes("ruff", tmp_path, 10)
        assert len(results) == 1
        assert results[0]["Source"] == "Episodes"
        assert results[0]["Name"] == "episode-2026-01-02-session-9-ruff-ratchet"

    def test_matches_task_when_name_has_no_slug(self, tmp_path: Path) -> None:
        _write_episode(tmp_path, "episode-2026-01-02-session-9", "Repair the ruff ratchet")

        results = search_episodes("ratchet", tmp_path, 10)
        assert len(results) == 1
        assert results[0]["Content"] == "Repair the ruff ratchet"

    def test_matches_lessons(self, tmp_path: Path) -> None:
        _write_episode(
            tmp_path, "episode-2026-01-02-session-9", "unrelated task",
            lessons=["Always measure the corpus before narrowing a guard"],
        )

        results = search_episodes("corpus", tmp_path, 10)
        assert len(results) == 1

    def test_structural_filename_tokens_do_not_match(self, tmp_path: Path) -> None:
        # Every filename carries "episode", the date, and usually "session".
        # Matching those would return the whole store for a generic query.
        for index in range(5):
            _write_episode(
                tmp_path, f"episode-2026-01-02-session-{index}-topic-{index}", "",
            )

        assert search_episodes("episode", tmp_path, 10) == []
        assert search_episodes("session", tmp_path, 10) == []
        assert len(search_episodes("topic", tmp_path, 10)) == 5

    def test_scores_by_fraction_of_keywords_matched(self, tmp_path: Path) -> None:
        _write_episode(tmp_path, "episode-2026-01-02-session-1-alpha-beta", "")
        _write_episode(tmp_path, "episode-2026-01-02-session-2-alpha", "")

        results = search_episodes("alpha beta", tmp_path, 10)
        assert results[0]["Score"] == 1.0
        assert results[1]["Score"] == 0.5

    def test_newest_episode_wins_a_score_tie(self, tmp_path: Path) -> None:
        _write_episode(tmp_path, "episode-2026-01-02-session-1-alpha", "")
        _write_episode(tmp_path, "episode-2026-06-30-session-2-alpha", "")
        _write_episode(tmp_path, "episode-2026-03-15-session-3-alpha", "")

        results = search_episodes("alpha", tmp_path, 10)
        assert [r["Score"] for r in results] == [1.0, 1.0, 1.0]
        assert results[0]["Name"].startswith("episode-2026-06-30")

    def test_no_match_returns_empty(self, tmp_path: Path) -> None:
        _write_episode(tmp_path, "episode-2026-01-02-session-1-alpha", "some task")
        assert search_episodes("zzzznomatch", tmp_path, 10) == []

    def test_missing_directory(self, tmp_path: Path) -> None:
        assert search_episodes("alpha", tmp_path / "missing", 10) == []

    def test_malformed_json_is_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "episode-2026-01-02-session-1-alpha.json").write_text("{ not json")
        _write_episode(tmp_path, "episode-2026-01-02-session-2-alpha", "")

        results = search_episodes("alpha", tmp_path, 10)
        assert len(results) == 1
        assert results[0]["Name"] == "episode-2026-01-02-session-2-alpha"

    def test_non_object_json_is_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "episode-2026-01-02-session-1-alpha.json").write_text("[1, 2, 3]")
        assert search_episodes("alpha", tmp_path, 10) == []

    def test_respects_max_results(self, tmp_path: Path) -> None:
        for index in range(10):
            _write_episode(tmp_path, f"episode-2026-01-02-session-{index}-alpha", "")
        assert len(search_episodes("alpha", tmp_path, 3)) == 3

    def test_ignores_non_episode_files(self, tmp_path: Path) -> None:
        (tmp_path / "notes-alpha.json").write_text('{"task": "alpha"}')
        assert search_episodes("alpha", tmp_path, 10) == []


class TestMainFunction:
    """Tests for the main CLI entry point."""

    def test_valid_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        serena = tmp_path / "memories"
        serena.mkdir()
        (serena / "git-hooks.md").write_text("# Git Hooks\nTest content")
        episodes = tmp_path / "episodes"
        episodes.mkdir()

        result = main([
            "git hooks",
            "--serena-path", str(serena),
            "--episodes-path", str(episodes),
        ])
        assert result == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["Query"] == "git hooks"
        assert output["Source"] == "Unified"
        assert isinstance(output["Results"], list)

    def test_searches_episodes_alongside_serena(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        serena = tmp_path / "memories"
        serena.mkdir()
        (serena / "ratchet-notes.md").write_text("# Notes")
        episodes = tmp_path / "episodes"
        episodes.mkdir()
        _write_episode(episodes, "episode-2026-01-02-session-9-ratchet-fix", "")

        result = main([
            "ratchet",
            "--serena-path", str(serena),
            "--episodes-path", str(episodes),
        ])
        assert result == 0

        output = json.loads(capsys.readouterr().out)
        sources = {r["Source"] for r in output["Results"]}
        assert sources == {"Serena", "Episodes"}
        assert output["SearchStatus"]["EpisodesQueried"] is True
        assert output["SearchStatus"]["EpisodesSucceeded"] is True
        assert output["Diagnostic"]["Episodes"]["MemoryCount"] == 1

    def test_episode_path_traversal_rejected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        result = main([
            "alpha",
            "--episodes-path", "../../etc",
        ])
        assert result == 2
        assert "traversal" in json.loads(capsys.readouterr().out)["Error"]

    def test_table_format(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        serena = tmp_path / "memories"
        serena.mkdir()
        episodes = tmp_path / "episodes"
        episodes.mkdir()

        result = main([
            "test query",
            "--serena-path", str(serena),
            "--episodes-path", str(episodes),
            "--format", "table",
        ])
        assert result == 0
        captured = capsys.readouterr()
        assert "No results found" in captured.out

    def test_invalid_query_returns_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = main(["test<invalid>"])
        assert result == 1

    @pytest.mark.parametrize(
        "removed_flag", ["--lexical-only", "--semantic-only"]
    )
    def test_removed_backend_flags_are_rejected(
        self, removed_flag: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Both flags named a backend choice; one backend remains.

        argparse exits 2 on an unrecognised argument rather than raising, so
        this asserts SystemExit. Without it a doc or agent prompt still
        passing the old flag would look like a silent no-op instead of the
        hard failure it actually is.
        """
        with pytest.raises(SystemExit) as excinfo:
            main(["test", removed_flag])
        assert excinfo.value.code == 2
        assert removed_flag in capsys.readouterr().err

    def test_search_status_omits_retired_backend(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No status key for a store that is no longer queried.

        A `<backend>Succeeded: false` key would read as a store that is down,
        which is the wrong signal now that nothing tries to reach one.
        """
        serena = tmp_path / "memories"
        serena.mkdir()
        episodes = tmp_path / "episodes"
        episodes.mkdir()

        assert main([
            "alpha",
            "--serena-path", str(serena),
            "--episodes-path", str(episodes),
        ]) == 0

        output = json.loads(capsys.readouterr().out)
        assert set(output["SearchStatus"]) == {
            "SerenaQueried",
            "EpisodesQueried",
            "SerenaSucceeded",
            "EpisodesSucceeded",
        }
        assert set(output["Diagnostic"]) == {"Serena", "Episodes"}

    def test_empty_results(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        serena = tmp_path / "memories"
        serena.mkdir()
        episodes = tmp_path / "episodes"
        episodes.mkdir()

        result = main([
            "nonexistent",
            "--serena-path", str(serena),
            "--episodes-path", str(episodes),
        ])
        assert result == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["Count"] == 0
