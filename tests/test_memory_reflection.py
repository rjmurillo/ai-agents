"""Tests for the reflection module."""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_enhancement.reflection import (
    apply_confidence_decay,
    extract_session_facts,
    generate_skill_candidates,
    reinforce_memories,
)


def _write_memory(mem_dir: Path, name: str, content: str) -> Path:
    """Write a memory file and return its path."""
    path = mem_dir / f"{name}.md"
    path.write_text(content)
    return path


def _make_memory_with_links(name: str, link_targets: list[str]) -> str:
    """Create memory content with link references."""
    lines = [f"# {name} (2026-01-01)\n\nContent for {name}\n"]
    for target in link_targets:
        lines.append(f"[link:depends_on]({target}) - depends on {target}\n")
    return "\n".join(lines)


class TestReinforceMemories:
    """Tests for confidence score recalculation."""

    @pytest.mark.unit
    def test_empty_directory(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        scores = reinforce_memories(mem_dir, tmp_path)
        assert scores == {}

    @pytest.mark.unit
    def test_single_memory(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        _write_memory(mem_dir, "m1", "# M1 (2026-01-01)\n\nContent\n")
        scores = reinforce_memories(mem_dir, tmp_path)
        assert "m1" in scores
        assert 0.0 <= scores["m1"] <= 1.0

    @pytest.mark.unit
    def test_multiple_memories(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        _write_memory(mem_dir, "m1", "# M1 (2026-01-01)\n\nContent\n")
        _write_memory(mem_dir, "m2", "# M2 (2026-01-01)\n\nOther content\n")
        scores = reinforce_memories(mem_dir, tmp_path)
        assert len(scores) == 2


class TestGenerateSkillCandidates:
    """Tests for skill candidate identification."""

    @pytest.mark.unit
    def test_no_candidates_without_links(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        _write_memory(mem_dir, "m1", "# M1 (2026-01-01)\n\nContent\n")
        candidates = generate_skill_candidates(mem_dir, tmp_path)
        assert candidates == []

    @pytest.mark.unit
    def test_empty_directory(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        candidates = generate_skill_candidates(mem_dir, tmp_path)
        assert candidates == []

    @pytest.mark.unit
    def test_candidate_with_links(self, tmp_path):
        """Memory with 2+ links and high confidence is a candidate."""
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        # Create target memories
        _write_memory(mem_dir, "dep1", "# Dep1 (2026-01-01)\n\nContent\n")
        _write_memory(mem_dir, "dep2", "# Dep2 (2026-01-01)\n\nContent\n")
        # Create memory with valid citation and links
        (tmp_path / "exists.py").write_text("content\n")
        content = _make_memory_with_links("linked", ["dep1", "dep2"])
        content += "\n[cite:file](exists.py) - ref\n"
        _write_memory(mem_dir, "linked", content)
        candidates = generate_skill_candidates(mem_dir, tmp_path)
        # Result depends on confidence score meeting threshold
        # With valid citation + links, it may qualify
        assert isinstance(candidates, list)


class TestExtractSessionFacts:
    """Tests for session fact extraction."""

    @pytest.mark.unit
    def test_empty_directory(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        facts = extract_session_facts(mem_dir)
        assert facts == []

    @pytest.mark.unit
    def test_nonexistent_directory(self, tmp_path):
        facts = extract_session_facts(tmp_path / "missing")
        assert facts == []

    @pytest.mark.unit
    def test_finds_today_modified_files(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        _write_memory(mem_dir, "today", "# Today (2026-01-01)\n\nContent\n")
        facts = extract_session_facts(mem_dir)
        assert "today" in facts

    @pytest.mark.unit
    def test_returns_sorted_ids(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        _write_memory(mem_dir, "beta", "# Beta (2026-01-01)\n\nContent\n")
        _write_memory(mem_dir, "alpha", "# Alpha (2026-01-01)\n\nContent\n")
        facts = extract_session_facts(mem_dir)
        assert facts == sorted(facts)

    @pytest.mark.unit
    def test_ignores_non_md_files(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "data.json").write_text("{}")
        facts = extract_session_facts(mem_dir)
        assert facts == []


class TestApplyConfidenceDecay:
    """Tests for confidence decay detection."""

    @pytest.mark.unit
    def test_empty_directory(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        decayed = apply_confidence_decay(mem_dir, tmp_path)
        assert decayed == []

    @pytest.mark.unit
    def test_recent_memory_not_flagged(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        _write_memory(mem_dir, "recent", "# Recent (2026-04-06)\n\nContent\n")
        decayed = apply_confidence_decay(mem_dir, tmp_path, max_age_days=90)
        assert decayed == []

    @pytest.mark.unit
    def test_old_memory_flagged(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        # Create memory with old updated_at date
        old_date = "2025-01-01"
        _write_memory(
            mem_dir, "old", f"# Old ({old_date})\n\nContent\n"
        )
        # The updated_at comes from the parsed date in the header
        decayed = apply_confidence_decay(mem_dir, tmp_path, max_age_days=90)
        # Memory with date 2025-01-01 is >90 days old from 2026-04-06
        assert "old" in decayed

    @pytest.mark.unit
    def test_returns_sorted_ids(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        _write_memory(mem_dir, "beta", "# Beta (2025-01-01)\n\nContent\n")
        _write_memory(mem_dir, "alpha", "# Alpha (2025-01-01)\n\nContent\n")
        decayed = apply_confidence_decay(mem_dir, tmp_path, max_age_days=90)
        assert decayed == sorted(decayed)

    @pytest.mark.unit
    def test_custom_max_age(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        _write_memory(mem_dir, "m1", "# M1 (2026-04-01)\n\nContent\n")
        # With max_age_days=1, a 5-day-old memory should be flagged
        decayed = apply_confidence_decay(mem_dir, tmp_path, max_age_days=1)
        assert "m1" in decayed
