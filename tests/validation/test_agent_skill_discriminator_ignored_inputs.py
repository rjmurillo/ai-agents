"""Gitignored inputs of the discriminator baseline dirty-state guard.

``git ls-files --others --exclude-standard`` hides ignored files, but the
scorer walks pipeline trees on disk and reads them anyway. The guard must
refuse on ignored files the scorer reads and ignore the rest.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.validation.agent_skill_discriminator_baseline as bmod
from tests.validation.test_agent_skill_discriminator_baseline import seed_repo
from tests.validation.test_check_agent_skill_discriminator import (
    _prose_body,
    _scaffold,
    _write_agent,
)


def _ignore(repo: Path, *patterns: str) -> None:
    """Commit a .gitignore so the listed patterns are ignored, not untracked."""
    (repo / ".gitignore").write_text("\n".join(patterns) + "\n", encoding="utf-8")


class TestIgnoredPipelineFiles:
    """Ignored files the scorer reads must refuse; ignored noise must not."""

    def test_ignored_skill_file_is_refused(self, tmp_path: Path) -> None:
        repo = _scaffold(tmp_path)
        _write_agent(repo, "alpha", _prose_body())
        _ignore(repo, ".claude/skills/hidden/")
        seed_repo(repo)
        hidden = repo / ".claude" / "skills" / "hidden" / "SKILL.md"
        hidden.parent.mkdir(parents=True)
        hidden.write_text('Task(subagent_type="alpha")\n', encoding="utf-8")

        assert bmod.refuse_dirty_scoring_inputs(repo) is True

    def test_ignored_skill_template_is_refused(self, tmp_path: Path) -> None:
        repo = _scaffold(tmp_path)
        _write_agent(repo, "alpha", _prose_body())
        _ignore(repo, "*.tmpl")
        seed_repo(repo)
        tmpl = repo / "templates" / "skills" / "ghost.SKILL.md.tmpl"
        tmpl.parent.mkdir(parents=True)
        tmpl.write_text("ghost\n", encoding="utf-8")

        assert bmod.refuse_dirty_scoring_inputs(repo) is True

    def test_ignored_bytecode_and_non_matching_files_are_accepted(
        self, tmp_path: Path
    ) -> None:
        repo = _scaffold(tmp_path)
        _write_agent(repo, "alpha", _prose_body())
        _ignore(repo, "__pycache__/", "*.pyc", "notes.txt")
        seed_repo(repo)
        skill_dir = repo / ".claude" / "skills" / "build"
        (skill_dir / "__pycache__").mkdir(parents=True)
        (skill_dir / "__pycache__" / "x.pyc").write_bytes(b"\0")
        (skill_dir / "notes.txt").write_text("scratch\n", encoding="utf-8")

        assert bmod.refuse_dirty_scoring_inputs(repo) is False

    def test_ignored_pattern_listing_failure_fails_closed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _scaffold(tmp_path)
        _write_agent(repo, "alpha", _prose_body())
        seed_repo(repo)
        real = bmod.run_git

        def failing(root: Path, *args: str) -> object:
            if "--ignored" in args:
                return None
            return real(root, *args)

        monkeypatch.setattr(bmod, "run_git", failing)

        assert bmod.refuse_dirty_scoring_inputs(repo) is True
