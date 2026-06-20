"""Tests for the skill-shell detector (issue #2677).

scripts/validation/validate_skill_shells.py errors when a directory under a
skills root has git-tracked, non-``__pycache__`` content but no ``SKILL.md``.
These tests build real temp git repos so the ``git ls-files`` contract that
decides "tracked" is exercised end to end, not mocked. The cases cover:

  * positive: a tracked file with no SKILL.md is a shell -> reported, exit 1
  * negative: a dir with a SKILL.md is a real skill -> not reported, exit 0
  * edge: a dir whose only content is untracked ``__pycache__`` -> not reported

The third case is the issue's core nuance: the three named dirs
(session-migration, session-qa-eligibility, workflow) carry only untracked
``scripts/__pycache__/*.pyc`` in a working tree, so the validator must NOT trip
on them. Tracking status is the line between a committed shell and local cruft.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
sys.path.insert(0, str(_VALIDATION))

import validate_skill_shells as vss  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    """Run a git command in ``repo``, failing the test loudly on error."""
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal git repo with a ``.claude/skills`` root and identity set."""
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    return tmp_path


def _write(path: Path, text: str = "x\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit(repo: Path) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "fixture")


class TestIsPycache:
    def test_true_for_pycache_segment(self) -> None:
        assert vss._is_pycache("a/b/__pycache__/mod.pyc") is True

    def test_false_when_no_pycache_segment(self) -> None:
        assert vss._is_pycache("a/b/scripts/mod.py") is False

    def test_false_for_substring_not_a_segment(self) -> None:
        # "__pycache__x" is a different path segment, not the cache dir.
        assert vss._is_pycache("a/__pycache__x/mod.py") is False


class TestFindSkillShells:
    def test_reports_dir_with_tracked_content_and_no_skill_md(self, repo: Path) -> None:
        _write(repo / ".claude" / "skills" / "ghost" / "scripts" / "run.py")
        _commit(repo)

        assert vss.find_skill_shells(repo) == [".claude/skills/ghost"]

    def test_ignores_dir_with_skill_md(self, repo: Path) -> None:
        _write(repo / ".claude" / "skills" / "real" / "SKILL.md", "---\nname: real\n---\n")
        _write(repo / ".claude" / "skills" / "real" / "scripts" / "run.py")
        _commit(repo)

        assert vss.find_skill_shells(repo) == []

    def test_ignores_dir_with_only_untracked_pycache(self, repo: Path) -> None:
        # The issue's core case: a shell that exists only as untracked cache.
        _write(
            repo / ".claude" / "skills" / "stale" / "scripts" / "__pycache__" / "m.pyc",
            "bytecode",
        )
        # Nothing committed: git ls-files sees no tracked content under the dir.

        assert vss.find_skill_shells(repo) == []

    def test_ignores_dir_with_only_tracked_pycache(self, repo: Path) -> None:
        # Even if __pycache__ were tracked, it is not skill content.
        _write(
            repo / ".claude" / "skills" / "cached" / "__pycache__" / "m.pyc",
            "bytecode",
        )
        _commit(repo)

        assert vss.find_skill_shells(repo) == []

    def test_reports_shell_alongside_pycache(self, repo: Path) -> None:
        # A tracked real script plus tracked pycache, still no SKILL.md -> shell.
        base = repo / ".claude" / "skills" / "mixed"
        _write(base / "scripts" / "run.py")
        _write(base / "scripts" / "__pycache__" / "run.pyc", "bytecode")
        _commit(repo)

        assert vss.find_skill_shells(repo) == [".claude/skills/mixed"]

    def test_untracked_skill_md_does_not_save_a_tracked_shell(self, repo: Path) -> None:
        # An untracked manifest does not exist in CI or a clean clone.
        base = repo / ".claude" / "skills" / "staging"
        _write(base / "scripts" / "run.py")
        _commit(repo)
        _write(base / "SKILL.md", "---\nname: staging\n---\n")

        assert vss.find_skill_shells(repo) == [".claude/skills/staging"]

    def test_tracked_skill_md_saves_a_tracked_shell(self, repo: Path) -> None:
        base = repo / ".claude" / "skills" / "staging"
        _write(base / "scripts" / "run.py")
        _write(base / "SKILL.md", "---\nname: staging\n---\n")
        _commit(repo)

        assert vss.find_skill_shells(repo) == []

    def test_scans_copilot_skills_root(self, repo: Path) -> None:
        copilot = repo / "src" / "copilot-cli" / "skills" / "ghost"
        _write(copilot / "scripts" / "run.py")
        _commit(repo)

        assert vss.find_skill_shells(repo) == ["src/copilot-cli/skills/ghost"]

    def test_ignores_tracked_file_directly_in_skills_root(self, repo: Path) -> None:
        # A README at the skills root is not a skill directory.
        _write(repo / ".claude" / "skills" / "README.md", "# skills\n")
        _commit(repo)

        assert vss.find_skill_shells(repo) == []

    def test_reports_multiple_shells_sorted(self, repo: Path) -> None:
        _write(repo / ".claude" / "skills" / "zeta" / "a.py")
        _write(repo / ".claude" / "skills" / "alpha" / "b.py")
        _commit(repo)

        assert vss.find_skill_shells(repo) == [
            ".claude/skills/alpha",
            ".claude/skills/zeta",
        ]


class TestMain:
    def test_exit_0_when_no_shells(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _write(repo / ".claude" / "skills" / "real" / "SKILL.md", "ok\n")
        _commit(repo)

        assert vss.main(["--repo-root", str(repo)]) == 0
        assert "No skill shells" in capsys.readouterr().out

    def test_exit_1_when_shell_found(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(repo / ".claude" / "skills" / "ghost" / "run.py")
        _commit(repo)

        assert vss.main(["--repo-root", str(repo)]) == 1
        out = capsys.readouterr().out
        assert "[SHELL] .claude/skills/ghost" in out

    def test_exit_2_when_repo_root_not_found(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # A directory with no .claude/skills above it: config error.
        bare = tmp_path / "no-skills"
        bare.mkdir()

        assert vss.main(["--repo-root", str(bare)]) == 2
        assert "Could not locate repo root" in capsys.readouterr().err


class TestRealRepo:
    def test_committed_repo_has_no_skill_shells(self) -> None:
        # The committed working tree must be clean: the three dirs named in
        # issue #2677 are untracked-only and must not trip the gate.
        repo_root = Path(__file__).resolve().parents[2]
        assert vss.find_skill_shells(repo_root) == []
