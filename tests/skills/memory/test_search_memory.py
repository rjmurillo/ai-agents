"""Tests for search_memory.py."""

import sys
from pathlib import Path

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


class TestSearchEpisodes:
    """Tests for the Tier 2 episode reader (Issue #3630)."""

    @staticmethod
    def _episode(directory, name, task="", lessons=None):
        import json as _json
        (directory / f"{name}.json").write_text(
            _json.dumps({"id": name, "task": task, "lessons": lessons or []}),
        )

    def test_finds_episode_by_slug(self, tmp_path):
        self._episode(tmp_path, "episode-2026-01-02-session-9-ruff-ratchet")
        self._episode(tmp_path, "episode-2026-01-02-session-8-unrelated")

        results = search_memory.search_episodes("ruff", tmp_path, 10)
        assert len(results) == 1
        assert results[0]["Source"] == "Episodes"

    def test_finds_episode_by_task(self, tmp_path):
        self._episode(tmp_path, "episode-2026-01-02-session-9", task="repair the ratchet")
        assert len(search_memory.search_episodes("ratchet", tmp_path, 10)) == 1

    def test_structural_tokens_do_not_match_everything(self, tmp_path):
        for index in range(4):
            self._episode(tmp_path, f"episode-2026-01-02-session-{index}-topic-{index}")

        assert search_memory.search_episodes("episode", tmp_path, 10) == []
        assert search_memory.search_episodes("session", tmp_path, 10) == []
        assert len(search_memory.search_episodes("topic", tmp_path, 10)) == 4

    def test_missing_directory(self, tmp_path):
        assert search_memory.search_episodes("alpha", tmp_path / "missing", 10) == []

    def test_malformed_json_skipped(self, tmp_path):
        (tmp_path / "episode-2026-01-02-session-1-alpha.json").write_text("{ bad")
        assert search_memory.search_episodes("alpha", tmp_path, 10) == []

    def test_newest_wins_a_tie(self, tmp_path):
        self._episode(tmp_path, "episode-2026-01-02-session-1-alpha")
        self._episode(tmp_path, "episode-2026-06-30-session-2-alpha")
        results = search_memory.search_episodes("alpha", tmp_path, 10)
        assert results[0]["Name"].startswith("episode-2026-06-30")

    def test_higher_session_number_wins_a_same_date_tie(self, tmp_path):
        """A digit-width change must not invert recency within one date.

        A reverse string sort compares "9" against "1" at the first differing
        position, so session-9 outranks session-10 even though session-10 is
        newer. Measured across the 302-episode corpus in
        `.agents/memory/episodes`, no date currently spans a digit-width
        boundary, so this has never fired in production. It is a latent trap,
        not an observed regression.
        """
        self._episode(tmp_path, "episode-2026-01-02-session-9-alpha")
        self._episode(tmp_path, "episode-2026-01-02-session-10-alpha")
        results = search_memory.search_episodes("alpha", tmp_path, 10)
        assert results[0]["Name"] == "episode-2026-01-02-session-10-alpha"

    def test_session_ordering_holds_across_the_hundreds_boundary(self, tmp_path):
        """The same inversion recurs at every power of ten, not just at ten."""
        self._episode(tmp_path, "episode-2026-01-02-session-99-alpha")
        self._episode(tmp_path, "episode-2026-01-02-session-100-alpha")
        results = search_memory.search_episodes("alpha", tmp_path, 10)
        assert results[0]["Name"] == "episode-2026-01-02-session-100-alpha"

    def test_date_outranks_the_session_number(self, tmp_path):
        """Negative control: the session number must not override the date.

        Session numbers are globally increasing, so a naive numeric sort that
        dropped the date would still pass the two tests above. This one fails
        if the date stops being the primary key.
        """
        self._episode(tmp_path, "episode-2026-01-02-session-500-alpha")
        self._episode(tmp_path, "episode-2026-06-30-session-9-alpha")
        results = search_memory.search_episodes("alpha", tmp_path, 10)
        assert results[0]["Name"] == "episode-2026-06-30-session-9-alpha"

    def test_an_unnumbered_episode_sorts_below_a_numbered_one(self, tmp_path):
        """Edge: four of the 302 real episodes carry no session number.

        They must still sort deterministically rather than raise. A numbered
        session is the more specific record, so it wins the date tie.
        """
        self._episode(tmp_path, "episode-2026-01-02-plain-alpha")
        self._episode(tmp_path, "episode-2026-01-02-session-1-alpha")
        results = search_memory.search_episodes("alpha", tmp_path, 10)
        assert results[0]["Name"] == "episode-2026-01-02-session-1-alpha"
        assert results[1]["Name"] == "episode-2026-01-02-plain-alpha"

    def test_a_name_matching_no_pattern_still_sorts(self, tmp_path):
        """Edge: a filename with no parseable date must not crash the sort."""
        self._episode(tmp_path, "episode-nodate-alpha")
        self._episode(tmp_path, "episode-2026-01-02-session-1-alpha")
        results = search_memory.search_episodes("alpha", tmp_path, 10)
        assert len(results) == 2
        assert results[0]["Name"] == "episode-2026-01-02-session-1-alpha"


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

    def test_reports_only_the_two_file_stores(self, tmp_path):
        """Negative control: the retired backend has no status block.

        It reported a TCP probe. Nothing probes now, so a block claiming a
        store is unavailable would misdescribe a store that does not exist.
        """
        status = search_memory.get_memory_router_status(tmp_path)
        assert set(status) == {"Serena", "Episodes"}

    def test_reports_episode_store(self, tmp_path):
        episodes = tmp_path / "episodes"
        episodes.mkdir()
        (episodes / "episode-2026-01-02-session-1-alpha.json").write_text('{"task": "a"}')
        status = search_memory.get_memory_router_status(tmp_path, episodes)
        assert status["Episodes"]["Available"] is True
        assert status["Episodes"]["MemoryCount"] == 1
