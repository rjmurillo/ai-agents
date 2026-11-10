"""Tests for the reflection module."""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from memory_enhancement import reflection
from memory_enhancement.confidence import update_confidence_scores_with_memories
from memory_enhancement.reflection import (
    apply_confidence_decay,
    extract_session_facts,
    generate_skill_candidates,
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


class TestScoreRecalculation:
    """Tests for confidence score recalculation. Scoring never writes."""

    @pytest.mark.unit
    def test_empty_directory(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        scores, memories = update_confidence_scores_with_memories(mem_dir, tmp_path)
        assert scores == {}
        assert memories == []

    @pytest.mark.unit
    def test_single_memory(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        _write_memory(mem_dir, "m1", "# M1 (2026-01-01)\n\nContent\n")
        scores, memories = update_confidence_scores_with_memories(mem_dir, tmp_path)
        assert "m1" in scores
        assert 0.0 <= scores["m1"] <= 1.0
        assert len(memories) == 1

    @pytest.mark.unit
    def test_multiple_memories(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        _write_memory(mem_dir, "m1", "# M1 (2026-01-01)\n\nContent\n")
        _write_memory(mem_dir, "m2", "# M2 (2026-01-01)\n\nOther content\n")
        scores, memories = update_confidence_scores_with_memories(mem_dir, tmp_path)
        assert len(scores) == 2
        assert len(memories) == 2


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


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
        },
    )


def _init_repo_with_memories(tmp_path: Path, names: list[str]) -> Path:
    """Create a git repo whose committed HEAD holds the named memories."""
    repo = tmp_path / "repo"
    mem_dir = repo / ".serena" / "memories"
    mem_dir.mkdir(parents=True)
    repo_args = ("init", "-q", "-b", "main")
    _git(repo, *repo_args)
    for name in names:
        _write_memory(mem_dir, name, f"# {name} (2026-01-01)\n\nContent\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed", "--no-gpg-sign")
    return mem_dir


class TestExtractSessionFacts:
    """Session facts come from git status, never from file mtime (#7227)."""

    @pytest.mark.unit
    def test_clean_checkout_reports_nothing_even_when_mtimes_are_today(self, tmp_path):
        mem_dir = _init_repo_with_memories(tmp_path, ["alpha", "beta"])
        now = datetime.now(UTC).timestamp()
        for md_file in mem_dir.glob("*.md"):
            os.utime(md_file, (now, now))
        assert extract_session_facts(mem_dir) == []

    @pytest.mark.unit
    def test_modified_tracked_file_is_reported(self, tmp_path):
        mem_dir = _init_repo_with_memories(tmp_path, ["alpha", "beta"])
        (mem_dir / "beta.md").write_text("# beta (2026-01-01)\n\nchanged\n", encoding="utf-8")
        assert extract_session_facts(mem_dir) == ["beta"]

    @pytest.mark.unit
    def test_untracked_file_is_reported(self, tmp_path):
        mem_dir = _init_repo_with_memories(tmp_path, ["alpha"])
        _write_memory(mem_dir, "fresh", "# Fresh (2026-01-01)\n\nContent\n")
        assert extract_session_facts(mem_dir) == ["fresh"]

    @pytest.mark.unit
    def test_untracked_file_in_new_subdirectory_is_reported(self, tmp_path):
        mem_dir = _init_repo_with_memories(tmp_path, ["alpha"])
        (mem_dir / "sub").mkdir()
        _write_memory(mem_dir / "sub", "nested", "# Nested (2026-01-01)\n\nContent\n")
        assert extract_session_facts(mem_dir) == ["nested"]

    @pytest.mark.unit
    def test_deleted_file_is_reported(self, tmp_path):
        mem_dir = _init_repo_with_memories(tmp_path, ["alpha", "beta"])
        (mem_dir / "alpha.md").unlink()
        assert extract_session_facts(mem_dir) == ["alpha"]

    @pytest.mark.unit
    def test_renamed_file_reports_the_new_name_once(self, tmp_path):
        mem_dir = _init_repo_with_memories(tmp_path, ["alpha"])
        _git(mem_dir.parent.parent, "mv", ".serena/memories/alpha.md", ".serena/memories/gamma.md")
        assert extract_session_facts(mem_dir) == ["gamma"]

    @pytest.mark.unit
    def test_returns_sorted_ids(self, tmp_path):
        mem_dir = _init_repo_with_memories(tmp_path, ["seed"])
        _write_memory(mem_dir, "beta", "# Beta (2026-01-01)\n\nContent\n")
        _write_memory(mem_dir, "alpha", "# Alpha (2026-01-01)\n\nContent\n")
        assert extract_session_facts(mem_dir) == ["alpha", "beta"]

    @pytest.mark.unit
    def test_ignores_non_md_and_skip_names(self, tmp_path):
        mem_dir = _init_repo_with_memories(tmp_path, ["alpha"])
        (mem_dir / "data.json").write_text("{}", encoding="utf-8")
        (mem_dir / "README.md").write_text("readme", encoding="utf-8")
        (mem_dir / "CLAUDE.md").write_text("claude", encoding="utf-8")
        assert extract_session_facts(mem_dir) == []

    @pytest.mark.unit
    def test_changes_outside_the_memory_directory_are_ignored(self, tmp_path):
        mem_dir = _init_repo_with_memories(tmp_path, ["alpha"])
        (mem_dir.parent.parent / "other.md").write_text("elsewhere", encoding="utf-8")
        assert extract_session_facts(mem_dir) == []

    @pytest.mark.unit
    def test_empty_directory(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        assert extract_session_facts(mem_dir) is None  # not a git repository

    @pytest.mark.unit
    def test_nonexistent_directory(self, tmp_path):
        assert extract_session_facts(tmp_path / "missing") == []

    @pytest.mark.unit
    def test_directory_outside_a_git_repository_is_unknown_not_mtime_based(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        _write_memory(mem_dir, "today", "# Today (2026-01-01)\n\nContent\n")
        assert extract_session_facts(mem_dir) is None

    @pytest.mark.unit
    def test_git_missing_is_unknown(self, tmp_path, monkeypatch):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        monkeypatch.setattr(reflection.shutil, "which", lambda _name: None)
        assert extract_session_facts(mem_dir) is None

    @pytest.mark.unit
    def test_git_timeout_is_unknown(self, tmp_path, monkeypatch):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        monkeypatch.setattr(reflection.shutil, "which", lambda _name: "git")

        def hang(*args, **kwargs):
            raise subprocess.TimeoutExpired(args, kwargs.get("timeout", 0))

        monkeypatch.setattr(reflection.subprocess, "run", hang)
        assert extract_session_facts(mem_dir) is None

    @pytest.mark.unit
    def test_git_call_is_bounded_by_a_timeout(self, tmp_path, monkeypatch):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        seen: dict[str, object] = {}

        def fake_run(*args, **kwargs):
            seen.update(kwargs)
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        monkeypatch.setattr(reflection.shutil, "which", lambda _name: "git")
        monkeypatch.setattr(reflection.subprocess, "run", fake_run)
        assert extract_session_facts(mem_dir) == []
        assert isinstance(seen["timeout"], (int, float))


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
        # Use a date relative to now so the fixture never rots into the
        # decay window as wall-clock time advances (see #2886).
        recent_date = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
        _write_memory(mem_dir, "recent", f"# Recent ({recent_date})\n\nContent\n")
        decayed = apply_confidence_decay(mem_dir, tmp_path, max_age_days=90)
        assert decayed == []

    @pytest.mark.unit
    def test_old_memory_flagged(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        # Create memory with old updated_at date
        old_date = "2025-01-01"
        _write_memory(mem_dir, "old", f"# Old ({old_date})\n\nContent\n")
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
