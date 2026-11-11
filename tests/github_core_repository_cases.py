"""Focused GitHub Core contract cases."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core import (
    REPO_ROOT_GIT_FAILED,
    REPO_ROOT_NOT_A_REPO,
    REPO_ROOT_OK,
    RepoInfo,
    assert_gh_authenticated,
    get_repo_info,
    resolve_repo_params,
    resolve_repo_root,
)
from tests.github_core_test_helpers import _completed


class TestGetRepoInfo:
    def test_parses_https_remote(self):
        stdout = "https://github.com/rjmurillo/ai-agents.git\n"
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            info = get_repo_info()
        assert info == RepoInfo(owner="rjmurillo", repo="ai-agents")

    @pytest.mark.parametrize(
        "stdout, expected_repo",
        [
            ("https://github.com/rjmurillo/moq.analyzers.git\n", "moq.analyzers"),
            ("git@github.com:rjmurillo/repo.with.dots.git\n", "repo.with.dots"),
            ("https://github.com/rjmurillo/repo.with.dots\n", "repo.with.dots"),
            ("https://alice@github.com/rjmurillo/moq.analyzers.git\n", "moq.analyzers"),
            ("git+ssh://git@github.com/rjmurillo/repo.with.dots.git\n", "repo.with.dots"),
        ],
    )
    def test_preserves_dots_in_repository_name(self, stdout, expected_repo):
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            info = get_repo_info()
        assert info == RepoInfo(owner="rjmurillo", repo=expected_repo)

    def test_parses_ssh_remote(self):
        stdout = "git@github.com:myorg/myrepo.git\n"
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            info = get_repo_info()
        assert info == RepoInfo(owner="myorg", repo="myrepo")

    @pytest.mark.parametrize(
        "stdout",
        [
            "https://gitlab.com/rjmurillo/moq.analyzers.git\n",
            "https://notgithub.com/rjmurillo/moq.analyzers.git\n",
            "https://evil.example/github.com/rjmurillo/moq.analyzers.git\n",
        ],
    )
    def test_returns_none_for_non_github_remote(self, stdout):
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            assert get_repo_info() is None

    def test_returns_none_when_not_git_repo(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="fatal")):
            assert get_repo_info() is None

    def test_returns_none_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10)):
            assert get_repo_info() is None

    def test_strips_dot_git_suffix(self):
        stdout = "https://github.com/owner/repo.git\n"
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            info = get_repo_info()
        assert info is not None
        assert info.repo == "repo"

    def test_returns_none_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert get_repo_info() is None

    def test_returns_repo_info_type(self):
        stdout = "https://github.com/owner/repo.git\n"
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            info = get_repo_info()
        assert isinstance(info, RepoInfo)

    @pytest.mark.parametrize(
        "stdout",
        [
            "https://github.com/owner/repo/\n",
            "https://github.com/owner/repo.git/\n",
            "ssh://git@github.com/owner/repo.git\n",
            "ssh://git@github.com:22/owner/repo\n",
            "ssh://git@github.com:2222/owner/repo.git/\n",
            "git@github.com:owner/repo.git\n",
            "github.com/owner/repo\n",
        ],
    )
    def test_parses_trailing_slash_and_ssh_url_forms(self, stdout, monkeypatch):
        monkeypatch.delenv("GH_HOST", raising=False)
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            assert get_repo_info() == RepoInfo(owner="owner", repo="repo")

    @pytest.mark.parametrize(
        "stdout",
        [
            "https://github.com/owner\n",
            "https://github.com/owner/repo/extra\n",
            "ssh://git@github.com:22/owner\n",
            "\n",
        ],
    )
    def test_returns_none_for_malformed_path(self, stdout, monkeypatch):
        monkeypatch.delenv("GH_HOST", raising=False)
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            assert get_repo_info() is None

    @pytest.mark.parametrize(
        "stdout",
        [
            "https://ghe.example.com/owner/repo.git\n",
            "ssh://git@ghe.example.com:2222/owner/repo.git\n",
            "git@GHE.example.com:owner/repo\n",
        ],
    )
    def test_gh_host_enterprise_remote_matches(self, stdout, monkeypatch):
        monkeypatch.setenv("GH_HOST", "ghe.example.com")
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            assert get_repo_info() == RepoInfo(owner="owner", repo="repo")

    def test_enterprise_remote_ignored_without_gh_host(self, monkeypatch):
        monkeypatch.delenv("GH_HOST", raising=False)
        stdout = "https://ghe.example.com/owner/repo.git\n"
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            assert get_repo_info() is None

    def test_gh_host_does_not_match_other_hosts(self, monkeypatch):
        monkeypatch.setenv("GH_HOST", "ghe.example.com")
        stdout = "https://other.example.com/owner/repo.git\n"
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            assert get_repo_info() is None

    def test_gh_host_keeps_github_com_working(self, monkeypatch):
        monkeypatch.setenv("GH_HOST", "ghe.example.com")
        stdout = "https://github.com/owner/repo.git\n"
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            assert get_repo_info() == RepoInfo(owner="owner", repo="repo")

    def test_resolve_fails_loud_when_remote_unmatched(self, monkeypatch):
        monkeypatch.delenv("GH_HOST", raising=False)
        stdout = "https://ghe.example.com/owner/repo.git\n"
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            with pytest.raises(SystemExit) as exc:
                resolve_repo_params()
        assert exc.value.code == 2


class TestAssertGhAuthenticated:
    def test_passes_when_authenticated(self):
        with patch("subprocess.run", return_value=_completed(rc=0)):
            assert_gh_authenticated()

    def test_exits_4_when_not_authenticated(self):
        with patch("subprocess.run", return_value=_completed(rc=1)):
            with pytest.raises(SystemExit) as exc:
                assert_gh_authenticated()
            assert exc.value.code == 4


class TestResolveRepoRoot:
    """`None` alone cannot distinguish "no repository" from "git failed".

    `is_safe_file_path` uses the repository root as a containment base for a
    path-traversal check (CWE-22). Falling back to the working directory is
    correct only when git has confirmed there is no repository. When git could
    not answer, the root is unknown rather than absent, and substituting a
    different base answers a question nobody asked.
    """

    def test_success_returns_root_and_ok(self, tmp_path: Path):
        from scripts.github_core import repo

        with patch("subprocess.run", return_value=_completed(stdout=f"{tmp_path}\n")):
            assert repo.resolve_repo_root() == (tmp_path, REPO_ROOT_OK)

    def test_git_reporting_no_repository_is_distinguishable(self):
        from scripts.github_core import repo

        stderr = "fatal: not a git repository (or any of the parent directories): .git\n"
        with patch("subprocess.run", return_value=_completed(stderr=stderr, rc=128)):
            assert repo.resolve_repo_root() == (None, REPO_ROOT_NOT_A_REPO)

    def test_unrecognized_git_failure_fails_closed(self):
        """An exit code we cannot explain must not be read as "no repository"."""
        from scripts.github_core import repo

        stderr = "fatal: index file smaller than expected\n"
        with patch("subprocess.run", return_value=_completed(stderr=stderr, rc=128)):
            assert repo.resolve_repo_root() == (None, REPO_ROOT_GIT_FAILED)

    def test_empty_stderr_on_failure_fails_closed(self):
        from scripts.github_core import repo

        with patch("subprocess.run", return_value=_completed(rc=1)):
            assert repo.resolve_repo_root() == (None, REPO_ROOT_GIT_FAILED)

    def test_timeout_is_git_failed(self):
        from scripts.github_core import repo

        boom = subprocess.TimeoutExpired(cmd=["git"], timeout=10)
        with patch("subprocess.run", side_effect=boom):
            assert repo.resolve_repo_root() == (None, REPO_ROOT_GIT_FAILED)

    def test_missing_git_binary_is_git_failed(self):
        from scripts.github_core import repo

        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert repo.resolve_repo_root() == (None, REPO_ROOT_GIT_FAILED)

    def test_undecodable_output_is_git_failed(self):
        from scripts.github_core import repo

        boom = UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid start byte")
        with patch("subprocess.run", side_effect=boom):
            assert repo.resolve_repo_root() == (None, REPO_ROOT_GIT_FAILED)

    def test_locale_is_pinned_so_the_stderr_match_is_deterministic(self):
        """Git translates `fatal: not a git repository`. LC_ALL=C pins it.

        Without this the discriminator would silently degrade to "git failed"
        on a non-English runner, and every default-base containment check on
        that machine would start refusing.
        """
        from scripts.github_core import repo

        with patch("subprocess.run", return_value=_completed(stdout="/tmp\n")) as run:
            repo.resolve_repo_root()
        assert run.call_args.kwargs["env"]["LC_ALL"] == "C"

    def test_inherited_environment_is_preserved(self):
        """Pinning the locale must not blank PATH and friends."""
        import os

        from scripts.github_core import repo

        with patch("subprocess.run", return_value=_completed(stdout="/tmp\n")) as run:
            repo.resolve_repo_root()
        env = run.call_args.kwargs["env"]
        for key in os.environ:
            if key != "LC_ALL":
                assert env[key] == os.environ[key]

    def test_stderr_match_is_case_insensitive(self):
        from scripts.github_core import repo

        stderr = "FATAL: NOT A GIT REPOSITORY\n"
        with patch("subprocess.run", return_value=_completed(stderr=stderr, rc=128)):
            assert repo.resolve_repo_root() == (None, REPO_ROOT_NOT_A_REPO)

    def test_relative_output_is_anchored_like_before(self, tmp_path: Path):
        from scripts.github_core import repo

        with patch("subprocess.run", return_value=_completed(stdout="sub\n")):
            root, reason = repo.resolve_repo_root(start_dir=tmp_path)
        assert reason == REPO_ROOT_OK
        assert root == (tmp_path / "sub").resolve()

    def test_start_dir_is_forwarded(self, tmp_path: Path):
        from scripts.github_core import repo

        with patch("subprocess.run", return_value=_completed(stdout=f"{tmp_path}\n")) as run:
            repo.resolve_repo_root(start_dir=tmp_path)
        assert run.call_args.args[0] == [
            "git",
            "-C",
            str(tmp_path),
            "rev-parse",
            "--show-toplevel",
        ]

    def test_get_repo_root_keeps_its_none_contract(self):
        """Every existing caller reads `None`; the wrapper must not change that."""
        from scripts.github_core import repo

        stderr = "fatal: not a git repository\n"
        with patch("subprocess.run", return_value=_completed(stderr=stderr, rc=128)):
            assert repo.get_repo_root() is None
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert repo.get_repo_root() is None

    def test_public_export_matches_the_module(self):
        from scripts.github_core import repo

        assert resolve_repo_root is repo.resolve_repo_root
