"""Issue #7328: the mypy changed-files gate must not fail on binplace symlinks."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.validation import checks_mypy
from scripts.validation.checks_mypy import _resolve_symlinked_sources
from scripts.validation.evidence import EvidenceState

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="creating symlinks needs POSIX or a privileged Windows user"
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src" / "lib").mkdir(parents=True)
    (tmp_path / ".claude" / "lib").mkdir(parents=True)
    (tmp_path / "src" / "lib" / "mod.py").write_text("X: int = 1\n", encoding="utf-8")
    (tmp_path / ".claude" / "lib" / "mod.py").symlink_to("../../src/lib/mod.py")
    return tmp_path


class TestResolveSymlinkedSources:
    def test_a_link_to_an_in_repo_file_becomes_its_source(self, repo: Path) -> None:
        assert _resolve_symlinked_sources(repo, [".claude/lib/mod.py"]) == ["src/lib/mod.py"]

    def test_the_link_and_its_source_collapse_to_one_entry(self, repo: Path) -> None:
        paths = [".claude/lib/mod.py", "src/lib/mod.py"]
        assert _resolve_symlinked_sources(repo, paths) == ["src/lib/mod.py"]

    def test_a_regular_file_is_unchanged(self, repo: Path) -> None:
        assert _resolve_symlinked_sources(repo, ["src/lib/mod.py"]) == ["src/lib/mod.py"]

    def test_a_link_that_leaves_the_repo_stays_so_run_mypy_refuses_it(
        self, repo: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        outside = tmp_path_factory.mktemp("outside") / "evil.py"
        outside.write_text("Y = 2\n", encoding="utf-8")
        (repo / ".claude" / "lib" / "evil.py").symlink_to(outside)
        assert _resolve_symlinked_sources(repo, [".claude/lib/evil.py"]) == [".claude/lib/evil.py"]

    def test_a_link_to_a_directory_stays(self, repo: Path) -> None:
        (repo / ".claude" / "lib" / "dirlink.py").symlink_to("../../src/lib")
        assert _resolve_symlinked_sources(repo, [".claude/lib/dirlink.py"]) == [
            ".claude/lib/dirlink.py"
        ]


class TestGateOnASymlinkedChange:
    def test_run_mypy_receives_the_source_not_the_link(self, repo: Path) -> None:
        diff = ".claude/lib/mod.py\nsrc/lib/mod.py\n"
        with (
            patch.object(checks_mypy, "_resolve_branch_base_ref", return_value="main"),
            patch.object(checks_mypy, "_run_subprocess", return_value=(0, diff, "")),
            patch("git_hook_policy.run_mypy", return_value=0) as run_mypy,
        ):
            outcome = checks_mypy.validate_mypy_changed_files(repo)
        assert outcome.state is EvidenceState.PASS
        run_mypy.assert_called_once_with(["src/lib/mod.py"], repo)

    def test_negative_control_the_unresolved_list_would_pass_the_link(self, repo: Path) -> None:
        """Without the swap, the link reaches run_mypy, which refuses it with exit 2."""
        from git_hook_policy import run_mypy

        assert run_mypy([".claude/lib/mod.py"], repo) == 2
