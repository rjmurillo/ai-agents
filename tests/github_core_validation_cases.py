"""Focused GitHub Core contract cases."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core import (
    REPO_ROOT_GIT_FAILED,
    REPO_ROOT_NOT_A_REPO,
    REPO_ROOT_OK,
    error_and_exit,
    is_github_name_valid,
    is_safe_file_path,
)
from tests.github_core_test_helpers import _REPO_ROOT, _thread
from tests.mock_fidelity import assert_mock_keys_match


def test_thread_mock_keys_subset_of_fixture():
    """The minimal _thread mock should be a subset of the review_thread fixture."""
    thread = _thread("T1", False, 1)
    assert_mock_keys_match(thread, "review_thread", allow_missing=True)


class TestIsGitHubNameValid:
    def test_valid_owner(self):
        assert is_github_name_valid("rjmurillo", "Owner") is True

    def test_valid_owner_with_hyphens(self):
        assert is_github_name_valid("my-org", "Owner") is True

    def test_owner_cannot_start_with_hyphen(self):
        assert is_github_name_valid("-badname", "Owner") is False

    def test_owner_cannot_end_with_hyphen(self):
        assert is_github_name_valid("badname-", "Owner") is False

    def test_owner_max_39_chars(self):
        assert is_github_name_valid("a" * 39, "Owner") is True
        # Pattern: start(1) + middle(0-37) + end(1) = max 39 chars
        assert is_github_name_valid("a" * 40, "Owner") is False

    def test_valid_repo(self):
        assert is_github_name_valid("ai-agents", "Repo") is True

    @pytest.mark.parametrize("name_type", ["repo", "Repo", "REPO"])
    def test_repo_name_type_is_case_insensitive(self, name_type: str):
        assert is_github_name_valid("ai-agents", name_type) is True
        assert is_github_name_valid("..", name_type) is False

    def test_repo_allows_dots(self):
        assert is_github_name_valid("my.repo.name", "Repo") is True

    def test_repo_allows_underscores(self):
        assert is_github_name_valid("my_repo", "Repo") is True

    def test_repo_max_100_chars(self):
        assert is_github_name_valid("a" * 100, "Repo") is True
        assert is_github_name_valid("a" * 101, "Repo") is False

    def test_empty_name_is_invalid(self):
        assert is_github_name_valid("", "Owner") is False
        assert is_github_name_valid("", "Repo") is False

    def test_whitespace_only_is_invalid(self):
        assert is_github_name_valid("   ", "Owner") is False

    def test_invalid_type_returns_false(self):
        assert is_github_name_valid("foo", "Invalid") is False

    @pytest.mark.parametrize("name", [".", ".."])
    @pytest.mark.parametrize("name_type", ["repo", "Repo", "REPO"])
    def test_repo_rejects_the_two_directory_aliases(self, name: str, name_type: str):
        """`.` and `..` are the only names GitHub refuses outright.

        They are also the two that carry traversal meaning once a caller
        interpolates them into a URL path, which several callers do.

        `name_type` is documented case-insensitive, so the rejection has to
        hold for every spelling a caller may pass. Testing one spelling would
        let a guard that keys off a single literal survive.
        """
        assert is_github_name_valid(name, name_type) is False

    @pytest.mark.parametrize("name", [".", ".."])
    @pytest.mark.parametrize("name_type", ["owner", "Owner", "OWNER"])
    def test_owner_rejects_the_two_directory_aliases(self, name: str, name_type: str):
        assert is_github_name_valid(name, name_type) is False

    def test_longer_dot_runs_stay_valid(self):
        """Only the two aliases are reserved. `...` is a legal repository name.

        Rejecting every all-dot name would be a wider rule than GitHub's and
        would fail a name a user can really create.
        """
        assert is_github_name_valid("...", "Repo") is True
        assert is_github_name_valid("....", "Repo") is True

    def test_dots_elsewhere_in_a_name_stay_valid(self):
        """The guard matches whole names, not substrings."""
        assert is_github_name_valid("..leading", "Repo") is True
        assert is_github_name_valid("trailing..", "Repo") is True
        assert is_github_name_valid("mid..dle", "Repo") is True


class TestIsSafeFilePath:
    def test_safe_path_within_base(self, tmp_path: Path):
        child = tmp_path / "child.txt"
        child.touch()
        assert is_safe_file_path(str(child), str(tmp_path)) is True

    def test_traversal_blocked(self, tmp_path: Path):
        bad_path = str(tmp_path / ".." / "escape.txt")
        assert is_safe_file_path(bad_path, str(tmp_path)) is False

    def test_default_base_is_repo_root(self, tmp_path: Path):
        child = tmp_path / "file.txt"
        child.touch()
        with patch(
            "scripts.github_core.repo.resolve_repo_root",
            return_value=(tmp_path, REPO_ROOT_OK),
        ):
            assert is_safe_file_path(str(child)) is True

    def test_default_base_falls_back_to_cwd_when_there_is_no_repository(self, tmp_path: Path):
        """Git answered. "No repository" is a fact, so cwd is a real boundary."""
        child = tmp_path / "file.txt"
        child.touch()
        with patch(
            "scripts.github_core.repo.resolve_repo_root",
            return_value=(None, REPO_ROOT_NOT_A_REPO),
        ):
            with patch("os.getcwd", return_value=str(tmp_path)):
                assert is_safe_file_path(str(child)) is True

    def test_git_failure_does_not_silently_become_a_cwd_check(self, tmp_path: Path):
        """The false accept. Git failed, so containment cannot be answered.

        Before this fix the base silently became the working directory, so a
        path nowhere near the repository passed the repository containment
        check purely because the process happened to be sitting next to it.
        """
        child = tmp_path / "file.txt"
        child.touch()
        with patch(
            "scripts.github_core.repo.resolve_repo_root",
            return_value=(None, REPO_ROOT_GIT_FAILED),
        ):
            with patch("os.getcwd", return_value=str(tmp_path)):
                assert is_safe_file_path(str(child)) is False

    def test_explicit_base_never_consults_git(self, tmp_path: Path):
        """A caller-supplied base is authoritative; git must not be run at all."""
        child = tmp_path / "file.txt"
        child.touch()
        with patch("scripts.github_core.repo.resolve_repo_root") as resolver:
            assert is_safe_file_path(str(child), str(tmp_path)) is True
        resolver.assert_not_called()

    def test_rejects_backslash_traversal(self):
        assert is_safe_file_path("foo\\..\\bar") is False

    def test_rejects_sibling_directory_prefix(self, tmp_path: Path):
        base = tmp_path / "safe"
        base.mkdir()
        sibling = tmp_path / "safe_evil"
        sibling.mkdir()
        evil_file = sibling / "secret.txt"
        evil_file.touch()
        assert is_safe_file_path(str(evil_file), str(base)) is False

    def test_allows_exact_base_path(self, tmp_path: Path):
        target = tmp_path / "file.txt"
        target.touch()
        assert is_safe_file_path(str(target), str(target)) is True


class TestErrorAndExit:
    def test_raises_system_exit_with_code(self):
        with pytest.raises(SystemExit) as exc:
            error_and_exit("boom", 3)
        assert exc.value.code == 3

    def test_writes_to_stderr(self, capsys):
        with pytest.raises(SystemExit):
            error_and_exit("error message", 1)
        assert "error message" in capsys.readouterr().err


class TestMirrorParity:
    """The install mirrors must equal the canonical loader's sync transform.

    build/scripts/lib_mirror.py (_transform_file) converts intra-package
    absolute imports to relative ones (ADR-109 B5 absorbed this from
    scripts/sync_plugin_lib.py, unchanged). The mirrors must equal that
    output exactly so they cannot drift from the real sync contract.
    """

    def test_mirrors_match_sync_transform(self) -> None:
        import sys

        build_scripts = _REPO_ROOT / "build" / "scripts"
        if str(build_scripts) not in sys.path:
            sys.path.insert(0, str(build_scripts))
        import lib_mirror

        src = _REPO_ROOT / "scripts/github_core/bot_config.py"
        expected = lib_mirror._transform_file(src).decode("utf-8")
        for mirror in (
            ".claude/lib/github_core/bot_config.py",
            "src/copilot-cli/lib/github_core/bot_config.py",
            "src/claude/lib/github_core/bot_config.py",
        ):
            assert (_REPO_ROOT / mirror).read_text(encoding="utf-8") == expected, mirror
