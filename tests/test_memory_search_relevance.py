"""Tests for memory search relevance scoring and the relevance floor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from memory_enhancement.search import query_relevance, rank_results, search_memories


def _write_memory(tmp_path: Path, name: str, content: str = "Test content") -> Path:
    """Write a minimal memory file and return its path."""
    file_path = tmp_path / f"{name}.md"
    file_path.write_text(f"# {name} (2026-01-01)\n\n{content}\n", encoding="utf-8")
    return file_path


class TestQueryRelevance:
    """Tests for the fraction-of-terms-naming-the-memory score."""

    @pytest.mark.unit
    def test_all_terms_in_label(self):
        label = "decision-lefthook-no-finally-cleanup"
        assert query_relevance("lefthook cleanup", label) == 1.0

    @pytest.mark.unit
    def test_partial_match_is_fraction(self):
        label = "decision-lefthook-no-finally-cleanup"
        assert query_relevance("lefthook cleanup removed unrelated", label) == 0.5

    @pytest.mark.unit
    def test_no_match_is_zero(self):
        assert query_relevance("hindsight mental", "skills-design-index") == 0.0

    @pytest.mark.unit
    def test_case_insensitive(self):
        assert query_relevance("LeftHook", "decision-lefthook") == 1.0

    @pytest.mark.unit
    def test_stem_prefix_matches_plural(self):
        assert query_relevance("guards", "worktree-identity-guard-scope") == 1.0

    @pytest.mark.unit
    def test_short_terms_need_exact_match(self):
        assert query_relevance("hooks", "pre-hook-design") == 0.0
        assert query_relevance("hook", "pre-hook-design") == 1.0

    @pytest.mark.unit
    @pytest.mark.parametrize("query", ["", "   ", "$$ ;;"])
    def test_empty_or_unusable_query_is_zero(self, query: str):
        assert query_relevance(query, "anything-here") == 0.0

    @pytest.mark.unit
    def test_duplicate_terms_counted_once(self):
        assert query_relevance("alpha alpha beta", "alpha-only") == 0.5

    @pytest.mark.unit
    def test_hyphenated_term_matches_its_own_memory(self):
        assert query_relevance("pr-autofix rounds", "pr-autofix-round-cap") == 1.0

    @pytest.mark.unit
    def test_compound_term_needs_every_word(self):
        assert query_relevance("decision-foo", "decision-lefthook") == 0.0
        assert query_relevance("decision-lefthook", "decision-lefthook") == 1.0

    @pytest.mark.unit
    @pytest.mark.parametrize("term", ["skills_index", "skills.index"])
    def test_underscore_and_dot_terms_split_like_labels(self, term: str):
        assert query_relevance(term, "skills-index") == 1.0

    @pytest.mark.unit
    def test_terms_with_same_words_counted_once(self):
        assert query_relevance("pr-autofix pr_autofix other", "pr-autofix") == 0.5

    @pytest.mark.unit
    def test_punctuation_only_term_is_ignored(self):
        assert query_relevance("lefthook --", "decision-lefthook") == 1.0


class TestMinRelevance:
    """The relevance floor drops weak matches before the result cap."""

    @pytest.mark.unit
    def test_rank_drops_results_below_floor(self, tmp_path: Path):
        hit = _write_memory(tmp_path, "worktree-identity-guard")
        miss = _write_memory(tmp_path, "skills-design-index")

        results = rank_results([hit, miss], tmp_path, query="worktree identity", min_relevance=0.5)

        assert [r.memory_id for r in results] == ["worktree-identity-guard"]
        assert results[0].relevance == 1.0

    @pytest.mark.unit
    def test_rank_keeps_result_exactly_at_floor(self, tmp_path: Path):
        path = _write_memory(tmp_path, "worktree-notes")

        results = rank_results([path], tmp_path, query="worktree identity", min_relevance=0.5)

        assert len(results) == 1
        assert results[0].relevance == 0.5

    @pytest.mark.unit
    def test_rank_drops_result_just_below_floor(self, tmp_path: Path):
        path = _write_memory(tmp_path, "worktree-notes")

        results = rank_results([path], tmp_path, query="worktree identity guard", min_relevance=0.5)

        assert results == []

    @pytest.mark.unit
    def test_floor_applies_before_result_cap(self, tmp_path: Path):
        noise = [_write_memory(tmp_path, f"noise-{i}") for i in range(5)]
        hit = _write_memory(tmp_path, "worktree-identity-guard")

        results = rank_results(
            [*noise, hit], tmp_path, max_results=1, query="worktree identity", min_relevance=0.5
        )

        assert [r.memory_id for r in results] == ["worktree-identity-guard"]

    @pytest.mark.unit
    def test_rank_orders_by_relevance_before_confidence(self, tmp_path: Path):
        weak = _write_memory(tmp_path, "alpha-notes")
        strong = _write_memory(tmp_path, "alpha-beta-notes")

        results = rank_results([weak, strong], tmp_path, query="alpha beta")

        assert [r.memory_id for r in results] == ["alpha-beta-notes", "alpha-notes"]

    @pytest.mark.unit
    def test_default_floor_keeps_everything(self, tmp_path: Path):
        path = _write_memory(tmp_path, "unrelated")

        assert len(rank_results([path], tmp_path, query="zzz")) == 1

    @pytest.mark.unit
    @patch("memory_enhancement.search._search_with_ripgrep")
    def test_search_memories_passes_floor(self, mock_rg, tmp_path: Path):
        hit = _write_memory(tmp_path, "worktree-identity-guard")
        miss = _write_memory(tmp_path, "skills-design-index")
        mock_rg.return_value = [hit, miss]

        results = search_memories(
            "worktree identity", tmp_path, repo_root=tmp_path, min_relevance=0.5
        )

        assert [r.memory_id for r in results] == ["worktree-identity-guard"]


class TestRelevanceLabel:
    """Relevance scores the file stem and title, never the folder."""

    @pytest.mark.unit
    @patch("memory_enhancement.search._search_with_ripgrep")
    def test_folder_name_does_not_count_toward_relevance(self, mock_rg, tmp_path: Path):
        sub = tmp_path / "github"
        sub.mkdir()
        md = sub / "unrelated-entry.md"
        md.write_text("# Unrelated Entry (2026-01-01)\n\ngithub tokens\n", encoding="utf-8")
        mock_rg.return_value = [md]

        results = search_memories("github tokens", tmp_path, repo_root=tmp_path)
        assert len(results) == 1
        assert results[0].memory_id == "github/unrelated-entry"
        assert results[0].relevance == 0.0
        assert (
            search_memories("github tokens", tmp_path, repo_root=tmp_path, min_relevance=0.5) == []
        )

    @pytest.mark.unit
    @patch("memory_enhancement.search._search_with_ripgrep")
    def test_folder_name_ignored_with_windows_separator(self, mock_rg, tmp_path: Path):
        from dataclasses import replace

        from memory_enhancement import search as search_module
        from memory_enhancement.serena_integration import load_memory

        sub = tmp_path / "github"
        sub.mkdir()
        md = sub / "unrelated-entry.md"
        md.write_text("# Unrelated Entry (2026-01-01)\n\ngithub tokens\n", encoding="utf-8")
        mock_rg.return_value = [md]

        def windows_ids(path, root=None):
            memory = load_memory(path, root)
            return replace(memory, memory_id=memory.memory_id.replace("/", "\\"))

        with patch.object(search_module, "load_memory", windows_ids):
            results = search_memories("github tokens", tmp_path, repo_root=tmp_path)
        assert results[0].memory_id == "github\\unrelated-entry"
        assert results[0].relevance == 0.0

    @pytest.mark.unit
    @patch("memory_enhancement.search._search_with_ripgrep")
    def test_basename_still_counts_toward_relevance(self, mock_rg, tmp_path: Path):
        sub = tmp_path / "github"
        sub.mkdir()
        md = sub / "token-rotation.md"
        md.write_text("# Notes (2026-01-01)\n\nbody\n", encoding="utf-8")
        mock_rg.return_value = [md]

        results = search_memories("token rotation", tmp_path, repo_root=tmp_path)
        assert results[0].relevance == 1.0
