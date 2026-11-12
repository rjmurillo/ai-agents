"""Issue #7328: run_mypy type-checks the source of a binplace symlink, not the link."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.validation import git_hook_policy
from scripts.validation.git_hook_policy import _in_repo_symlink_source, run_mypy

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="creating symlinks needs POSIX or a privileged Windows user"
)

CLEAN = "def greet(name: str) -> str:\n    return name\n"
BROKEN = CLEAN + "\nx: int = 'not an int'\n"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo whose `.claude/lib/mod.py` links to `src/lib/mod.py`."""
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@test.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "src" / "lib").mkdir(parents=True)
    (tmp_path / ".claude" / "lib").mkdir(parents=True)
    (tmp_path / "src" / "lib" / "mod.py").write_text(CLEAN, encoding="utf-8")
    (tmp_path / ".claude" / "lib" / "mod.py").symlink_to("../../src/lib/mod.py")
    _commit(tmp_path, "base")
    return tmp_path


class TestInRepoSymlinkSource:
    def test_a_link_to_an_in_repo_file_gives_its_source(self, repo: Path) -> None:
        assert _in_repo_symlink_source(repo, ".claude/lib/mod.py") == "src/lib/mod.py"

    def test_a_link_that_leaves_the_repo_gives_none(
        self, repo: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        outside = tmp_path_factory.mktemp("outside") / "evil.py"
        outside.write_text("Y = 2\n", encoding="utf-8")
        (repo / ".claude" / "lib" / "evil.py").symlink_to(outside)
        assert _in_repo_symlink_source(repo, ".claude/lib/evil.py") is None

    def test_a_chain_of_links_gives_the_final_source(self, repo: Path) -> None:
        (repo / ".claude" / "lib" / "hop.py").symlink_to("mod.py")
        assert _in_repo_symlink_source(repo, ".claude/lib/hop.py") == "src/lib/mod.py"

    def test_a_link_to_a_file_that_is_not_python_gives_none(self, repo: Path) -> None:
        (repo / "src" / "lib" / "notes.txt").write_text("x\n", encoding="utf-8")
        (repo / ".claude" / "lib" / "notes.py").symlink_to("../../src/lib/notes.txt")
        assert _in_repo_symlink_source(repo, ".claude/lib/notes.py") is None

    def test_a_link_to_a_directory_gives_none(self, repo: Path) -> None:
        (repo / ".claude" / "lib" / "dirlink.py").symlink_to("../../src/lib")
        assert _in_repo_symlink_source(repo, ".claude/lib/dirlink.py") is None


class TestRunMypyOnALink:
    def test_a_type_error_in_the_source_is_found_through_the_link(self, repo: Path) -> None:
        (repo / "src" / "lib" / "mod.py").write_text(BROKEN, encoding="utf-8")
        _commit(repo, "add error")
        with patch.object(git_hook_policy, "_mypy_ratchet_base_ref", return_value="HEAD~1"):
            assert run_mypy([".claude/lib/mod.py"], repo) == 1

    def test_a_clean_source_passes_through_the_link(self, repo: Path) -> None:
        (repo / "src" / "lib" / "mod.py").write_text(CLEAN + "\nY = 1\n", encoding="utf-8")
        _commit(repo, "touch")
        with patch.object(git_hook_policy, "_mypy_ratchet_base_ref", return_value="HEAD~1"):
            assert run_mypy([".claude/lib/mod.py"], repo) == 0

    def test_the_link_and_its_source_are_checked_once(self, repo: Path) -> None:
        (repo / "src" / "lib" / "mod.py").write_text(CLEAN + "\nY = 1\n", encoding="utf-8")
        _commit(repo, "touch")
        with (
            patch.object(git_hook_policy, "_mypy_ratchet_base_ref", return_value="HEAD~1"),
            patch.object(git_hook_policy, "_mypy_invocations", return_value=[]) as invocations,
        ):
            run_mypy([".claude/lib/mod.py", "src/lib/mod.py"], repo)
        assert invocations.call_args.args[0] == ["src/lib/mod.py"]

    def test_a_link_that_ends_at_no_file_is_skipped_as_before(self, repo: Path) -> None:
        (repo / ".claude" / "lib" / "gone.py").symlink_to("../../src/lib/missing.py")
        assert run_mypy([".claude/lib/gone.py"], repo) == 0

    def test_negative_control_a_link_that_leaves_the_repo_is_refused(
        self, repo: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        outside = tmp_path_factory.mktemp("outside") / "evil.py"
        outside.write_text("Y = 2\n", encoding="utf-8")
        (repo / ".claude" / "lib" / "evil.py").symlink_to(outside)
        assert run_mypy([".claude/lib/evil.py"], repo) == 2
