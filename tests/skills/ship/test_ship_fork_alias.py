"""An origin or upstream remote that names the PR repository through another host spelling.

An ssh config alias (``git@work-gh:o/r.git``) or the port-443 ssh host
(``ssh.github.com``) differs from the PR URL host, yet names the same repository.
"""

from __future__ import annotations

import json

import pytest

from tests.skills.ship.conftest import git
from tests.skills.ship.test_ship_fork_base import (
    FORK,
    UPSTREAM_PR,
    UPSTREAM_URLS,
    _check,
    _open_pr,
    _paths_line,
    _seed_ref,
)

# The same repository, octo/repo, named through an ssh alias or the port-443 ssh host.
ALIAS_ORIGINS = [
    "git@work-gh:octo/repo.git",
    "ssh://git@ssh.github.com:443/octo/repo.git",
    "git@work-gh:OCTO/Repo.git",
]


class TestAliasOrigin:
    @pytest.mark.parametrize("origin", ALIAS_ORIGINS)
    def test_an_origin_on_an_alias_host_still_runs_the_paths_check_on_origin(
        self, make_repo, fakes, scripts, capsys, body_file, tmp_path, monkeypatch, origin
    ):
        repo = make_repo(origin)
        _seed_ref(repo, "refs/remotes/origin/main")
        _open_pr(fakes, "https://github.com/octo/repo/pull/42")
        probe = tmp_path / "probe.json"
        monkeypatch.setenv("SHIP_VALIDATOR_PROBE", str(probe))
        code, lines = _check(scripts, capsys, repo, body_file)
        assert code == 0, lines
        assert _paths_line(lines) == "paths=PASS"
        argv = json.loads(probe.read_text(encoding="utf-8"))["argv"]
        assert argv[-2:] == ["--base", "refs/remotes/origin/main"]

    def test_a_fork_with_a_port_443_upstream_remote_uses_that_remote(
        self, make_repo, fakes, scripts, capsys, body_file, tmp_path, monkeypatch
    ):
        repo = make_repo(FORK)
        git(repo, "remote", "add", "upstream", "ssh://git@ssh.github.com:443/upstream/project.git")
        _seed_ref(repo, "refs/remotes/upstream/main")
        _open_pr(fakes, UPSTREAM_PR)
        probe = tmp_path / "probe.json"
        monkeypatch.setenv("SHIP_VALIDATOR_PROBE", str(probe))
        code, lines = _check(scripts, capsys, repo, body_file)
        assert code == 0, lines
        assert _paths_line(lines) == "paths=PASS"
        argv = json.loads(probe.read_text(encoding="utf-8"))["argv"]
        assert argv[-2:] == ["--base", "refs/remotes/upstream/main"]

    @pytest.mark.parametrize(
        "url", ["https://gitlab.com/upstream/project.git", "git@work-gh:upstream/project.git"]
    )
    def test_a_fork_with_only_another_host_remote_does_not_read_it(
        self, make_repo, fakes, scripts, capsys, body_file, url
    ):
        repo = make_repo(FORK)
        git(repo, "remote", "add", "mirror", url)
        _seed_ref(repo, "refs/remotes/mirror/main")
        _open_pr(fakes, UPSTREAM_PR)
        _code, lines = _check(scripts, capsys, repo, body_file)
        assert "has no matching git remote" in _paths_line(lines)


class TestAliasUpstream:
    """``upstream`` keeps origin for the same owner and repository, whatever the host."""

    @pytest.fixture
    def context(self, make_repo):
        def build(origin: str, pr: int | None, pr_url: str):
            return make_repo(origin), pr, pr_url

        return build

    @pytest.mark.parametrize("origin", ALIAS_ORIGINS)
    def test_the_same_owner_and_repository_on_an_alias_host_keeps_origin(
        self, context, scripts, origin
    ):
        ctx = context(origin, 42, "https://github.com/octo/repo/pull/42")
        assert scripts[1].repo_mod.upstream(*ctx) is None

    def test_a_different_owner_on_an_alias_host_is_still_a_fork(self, context, scripts):
        ctx = context("git@work-gh:me/repo.git", 42, "https://github.com/octo/repo/pull/42")
        found = scripts[1].repo_mod.upstream(*ctx)
        assert found is not None
        assert found.key == ("github.com", "octo", "repo")


class TestRemoteFor:
    """``remote_for`` takes the exact host, or the port-443 ssh host of the PR host, never another."""

    @staticmethod
    def _ref(scripts):
        return scripts[1].repo_mod.pr_repo(UPSTREAM_PR, 42)

    def test_the_port_443_ssh_host_is_found_by_owner_and_repository(self, make_repo, scripts):
        repo = make_repo(FORK)
        git(repo, "remote", "add", "upstream", "ssh://git@ssh.github.com:443/Upstream/Project.git")
        found = scripts[1].repo_mod.remote_for(repo, self._ref(scripts))
        assert found == "upstream"

    def test_the_exact_host_wins_over_an_earlier_port_443_match(self, make_repo, scripts):
        repo = make_repo(FORK)
        git(repo, "remote", "add", "aaa-443", "ssh://git@ssh.github.com:443/upstream/project.git")
        git(repo, "remote", "add", "zzz-exact", UPSTREAM_URLS[0])
        found = scripts[1].repo_mod.remote_for(repo, self._ref(scripts))
        assert found == "zzz-exact"

    @pytest.mark.parametrize(
        "url",
        [
            "https://gitlab.com/upstream/project.git",
            "git@work-gh:upstream/project.git",
            "git@ssh.gitlab.com:upstream/project.git",
        ],
    )
    def test_the_same_owner_and_repository_on_another_host_never_matches(
        self, make_repo, scripts, url
    ):
        repo = make_repo(FORK)
        git(repo, "remote", "add", "mirror", url)
        found = scripts[1].repo_mod.remote_for(repo, self._ref(scripts))
        assert found is None

    def test_origin_of_a_different_owner_never_matches(self, make_repo, scripts):
        repo = make_repo("ssh://git@ssh.github.com:443/me/project.git")
        found = scripts[1].repo_mod.remote_for(repo, self._ref(scripts))
        assert found is None
