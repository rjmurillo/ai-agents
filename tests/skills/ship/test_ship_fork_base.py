"""The paths check reads the PR's target from the repository that owns the PR.

When origin is a fork and the open PR belongs to the upstream repository, the
target branch lives in a remote that names upstream, not in ``origin``.
"""

from __future__ import annotations

import json

import pytest

from tests.skills.ship.conftest import git
from tests.skills.ship.ship_helpers import TITLE, VALIDATOR_PASS, run_pr, values

FORK = "https://github.com/me/fork.git"
UPSTREAM_PR = "https://github.com/upstream/project/pull/42"
UPSTREAM_URLS = [
    "https://github.com/upstream/project.git",
    "https://github.com/Upstream/Project",
    "git@github.com:upstream/project.git",
    "ssh://git@github.com:22/upstream/project.git/",
    "https://token@github.com/UPSTREAM/project.git",
]
# The same repository, octo/repo, named through an ssh alias or the port-443 ssh host.
ALIAS_ORIGINS = [
    "git@work-gh:octo/repo.git",
    "ssh://git@ssh.github.com:443/octo/repo.git",
    "git@work-gh:OCTO/Repo.git",
]


def _open_pr(fakes, url: str, target: str = "main", number: int = 42) -> None:
    pr = {
        "number": number,
        "state": "OPEN",
        "author": {"login": "me"},
        "url": url,
        "baseRefName": target,
    }
    fakes.rule("gh", ["pr", "view"], {"stdout": json.dumps(pr)})
    fakes.rule("gh", ["api", "user"], {"stdout": "me\n"})


def _seed_ref(repo, ref: str, validator: str | None = VALIDATOR_PASS) -> None:
    """Point ``ref`` at a commit that holds the base validator, leaving the branch as it was."""
    branch = git(repo, "branch", "--show-current")
    git(repo, "switch", "-q", "-c", "seed-tmp", "main")
    if validator is not None:
        path = repo / "scripts" / "validation" / "pr_description.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(validator, encoding="utf-8")
        (repo / "scripts" / "__init__.py").write_text("", encoding="utf-8")
        package = repo / "scripts" / "github_core"
        package.mkdir(exist_ok=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        git(repo, "add", "scripts")
        git(repo, "commit", "-q", "-m", "chore: add the validator")
    git(repo, "update-ref", ref, "HEAD")
    git(repo, "switch", "-q", branch)
    git(repo, "branch", "-q", "-D", "seed-tmp")


def _check(scripts, capsys, repo, body_file):
    return run_pr(scripts, capsys, "check", "--title", TITLE, "--body-file", str(body_file(repo)))


def _paths_line(lines: list[str]) -> str:
    return next(line for line in values(lines, "CHECK") if line.startswith("paths="))


class TestForkOrigin:
    @pytest.mark.parametrize("url", UPSTREAM_URLS)
    def test_the_remote_that_names_the_pr_repository_supplies_the_base(
        self, make_repo, fakes, scripts, capsys, body_file, tmp_path, monkeypatch, url
    ):
        repo = make_repo(FORK)
        git(repo, "remote", "add", "upstream", url)
        _seed_ref(repo, "refs/remotes/upstream/main")
        _open_pr(fakes, UPSTREAM_PR)
        probe = tmp_path / "probe.json"
        monkeypatch.setenv("SHIP_VALIDATOR_PROBE", str(probe))
        code, lines = _check(scripts, capsys, repo, body_file)
        assert code == 0, lines
        assert _paths_line(lines) == "paths=PASS"
        argv = json.loads(probe.read_text(encoding="utf-8"))["argv"]
        assert argv[-2:] == ["--base", "refs/remotes/upstream/main"]

    def test_origin_is_not_used_when_it_holds_a_different_base(
        self, make_repo, fakes, scripts, capsys, body_file
    ):
        repo = make_repo(FORK)
        git(repo, "remote", "add", "upstream", UPSTREAM_URLS[0])
        _seed_ref(repo, "refs/remotes/upstream/main")
        _open_pr(fakes, UPSTREAM_PR)
        code, lines = _check(scripts, capsys, repo, body_file)
        assert code == 0, lines
        assert "origin/main has no path validator" not in " ".join(lines)

    def test_no_matching_remote_names_the_target_and_is_not_a_pass(
        self, make_repo, fakes, scripts, capsys, body_file
    ):
        repo = make_repo(FORK)
        git(repo, "remote", "add", "elsewhere", "https://github.com/other/thing.git")
        git(repo, "remote", "add", "local", str(repo))
        _open_pr(fakes, UPSTREAM_PR)
        code, lines = _check(scripts, capsys, repo, body_file)
        assert code == 0, lines
        assert _paths_line(lines) == (
            "paths=NOT-RUN upstream/project:main has no matching git remote; add one and fetch "
            "it; compare the body to the diff by hand"
        )
        assert lines[-1] == "NEXT: compare-paths-by-hand"

    def test_a_matching_remote_without_the_ref_names_the_target(
        self, make_repo, fakes, scripts, capsys, body_file
    ):
        repo = make_repo(FORK)
        git(repo, "remote", "add", "upstream", UPSTREAM_URLS[0])
        _open_pr(fakes, UPSTREAM_PR, target="release/2")
        code, lines = _check(scripts, capsys, repo, body_file)
        assert code == 0, lines
        assert _paths_line(lines) == (
            "paths=NOT-RUN upstream/project:release/2 (as upstream/release/2) not found; "
            "fetch it; compare the body to the diff by hand"
        )

    def test_a_remote_name_with_a_slash_is_not_used_in_a_ref(
        self, make_repo, fakes, scripts, capsys, body_file
    ):
        repo = make_repo(FORK)
        git(repo, "remote", "add", "team/up", UPSTREAM_URLS[0])
        _seed_ref(repo, "refs/remotes/team/up/main")
        _open_pr(fakes, UPSTREAM_PR)
        code, lines = _check(scripts, capsys, repo, body_file)
        assert code == 0, lines
        assert "has no matching git remote" in _paths_line(lines)


class TestOriginOwnsThePr:
    @pytest.mark.parametrize(
        ("origin", "pr_url"),
        [
            ("https://github.com/Octo/Repo.git", "https://github.com/octo/repo/pull/42"),
            ("git@github.com:octo/repo.git", "https://github.com/octo/repo/pull/42"),
            ("https://github.com/octo/repo.git", "https://GITHUB.com/octo/repo/pull/42"),
        ],
    )
    def test_the_same_repository_in_another_spelling_keeps_origin(
        self, make_repo, fakes, scripts, capsys, body_file, tmp_path, monkeypatch, origin, pr_url
    ):
        repo = make_repo(origin)
        git(repo, "remote", "add", "upstream", UPSTREAM_URLS[0])
        _seed_ref(repo, "refs/remotes/origin/main")
        _open_pr(fakes, pr_url)
        probe = tmp_path / "probe.json"
        monkeypatch.setenv("SHIP_VALIDATOR_PROBE", str(probe))
        code, lines = _check(scripts, capsys, repo, body_file)
        assert code == 0, lines
        assert _paths_line(lines) == "paths=PASS"
        argv = json.loads(probe.read_text(encoding="utf-8"))["argv"]
        assert argv[-2:] == ["--base", "refs/remotes/origin/main"]

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

    def test_a_fork_with_an_alias_upstream_remote_still_uses_that_remote(
        self, make_repo, fakes, scripts, capsys, body_file, tmp_path, monkeypatch
    ):
        repo = make_repo(FORK)
        git(repo, "remote", "add", "upstream", "git@work-gh:upstream/project.git")
        _seed_ref(repo, "refs/remotes/upstream/main")
        _open_pr(fakes, UPSTREAM_PR)
        probe = tmp_path / "probe.json"
        monkeypatch.setenv("SHIP_VALIDATOR_PROBE", str(probe))
        code, lines = _check(scripts, capsys, repo, body_file)
        assert code == 0, lines
        assert _paths_line(lines) == "paths=PASS"
        argv = json.loads(probe.read_text(encoding="utf-8"))["argv"]
        assert argv[-2:] == ["--base", "refs/remotes/upstream/main"]

    def test_a_new_pr_goes_to_origin(self, make_repo, fakes, scripts, capsys, body_file):
        repo = make_repo(FORK)
        fakes.no_pr_github()
        code, lines = _check(scripts, capsys, repo, body_file)
        assert code == 0, lines
        assert "paths=NOT-RUN origin/main has no path validator" in _paths_line(lines)

    def test_a_missing_origin_ref_keeps_the_origin_message(
        self, make_repo, fakes, scripts, capsys, body_file
    ):
        repo = make_repo(FORK)
        _open_pr(fakes, "https://github.com/me/fork/pull/42", target="release/2")
        code, lines = _check(scripts, capsys, repo, body_file)
        assert code == 0, lines
        assert _paths_line(lines).startswith("paths=NOT-RUN origin/release/2 not found; fetch it")


class TestUpstreamRepo:
    """``upstream`` returns None, and so keeps origin, unless it can prove another repo."""

    @pytest.fixture
    def context(self, make_repo):
        def build(origin: str, pr: int | None, pr_url: str):
            return make_repo(origin), pr, pr_url

        return build

    def test_an_unparsable_pr_url_keeps_origin(self, context, scripts):
        ado = "https://dev.azure.com/c/p/_git/r/pullrequest/5"
        ctx = context("https://dev.azure.com/c/p/_git/r", 5, ado)
        assert scripts[1].repo_mod.upstream(*ctx) is None

    def test_an_origin_that_names_no_owner_and_repo_keeps_origin(self, context, scripts):
        ctx = context("https://github.com/solo.git", 42, UPSTREAM_PR)
        assert scripts[1].repo_mod.upstream(*ctx) is None

    def test_another_repository_is_returned(self, context, scripts):
        ctx = context(FORK, 42, UPSTREAM_PR)
        found = scripts[1].repo_mod.upstream(*ctx)
        assert found is not None
        assert found.key == ("github.com", "upstream", "project")

    def test_no_pr_keeps_origin(self, context, scripts):
        assert scripts[1].repo_mod.upstream(*context(FORK, None, "")) is None

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
    """``remote_for`` prefers the exact host, then accepts the same owner and repository."""

    @staticmethod
    def _ref(scripts):
        return scripts[1].repo_mod.pr_repo(UPSTREAM_PR, 42)

    def test_an_alias_host_remote_is_found_by_owner_and_repository(self, make_repo, scripts):
        repo = make_repo(FORK)
        git(repo, "remote", "add", "upstream", "git@work-gh:Upstream/Project.git")
        found = scripts[1].repo_mod.remote_for(repo, self._ref(scripts))
        assert found == "upstream"

    def test_the_exact_host_wins_over_an_earlier_alias_match(self, make_repo, scripts):
        repo = make_repo(FORK)
        git(repo, "remote", "add", "aaa-alias", "ssh://git@ssh.github.com:443/upstream/project.git")
        git(repo, "remote", "add", "zzz-exact", UPSTREAM_URLS[0])
        found = scripts[1].repo_mod.remote_for(repo, self._ref(scripts))
        assert found == "zzz-exact"

    def test_the_first_alias_match_is_used_when_no_host_matches(self, make_repo, scripts):
        repo = make_repo(FORK)
        git(repo, "remote", "add", "aaa", "git@work-gh:upstream/project.git")
        git(repo, "remote", "add", "bbb", "git@other-gh:upstream/project.git")
        found = scripts[1].repo_mod.remote_for(repo, self._ref(scripts))
        assert found == "aaa"

    def test_origin_of_a_different_owner_never_matches(self, make_repo, scripts):
        repo = make_repo("git@work-gh:me/project.git")
        found = scripts[1].repo_mod.remote_for(repo, self._ref(scripts))
        assert found is None


class TestBaseRemote:
    """``base_remote`` is read at detect time and carried in ``Context``."""

    def test_no_pr_is_origin_with_no_label(self, make_repo, scripts):
        repo = make_repo(FORK)
        assert scripts[1].repo_mod.base_remote(repo, None, "") == ("origin", "")

    def test_a_fork_pr_is_the_remote_that_names_the_pr_repository(self, make_repo, scripts):
        repo = make_repo(FORK)
        git(repo, "remote", "add", "upstream", UPSTREAM_URLS[0])
        found = scripts[1].repo_mod.base_remote(repo, 42, UPSTREAM_PR)
        assert found == ("upstream", "upstream/project")

    def test_a_fork_pr_with_no_matching_remote_is_none_with_the_label(self, make_repo, scripts):
        repo = make_repo(FORK)
        found = scripts[1].repo_mod.base_remote(repo, 42, UPSTREAM_PR)
        assert found == (None, "upstream/project")

    def test_detect_stores_the_remote_and_label_in_the_context(self, make_repo, fakes, scripts):
        repo = make_repo(FORK)
        git(repo, "remote", "add", "upstream", UPSTREAM_URLS[0])
        _open_pr(fakes, UPSTREAM_PR)
        ctx = scripts[1].detect(repo)
        assert not isinstance(ctx, scripts[1].Halt)
        assert (ctx.base_remote, ctx.base_shown) == ("upstream", "upstream/project")

    def test_a_context_built_without_them_defaults_to_origin(self, make_repo, scripts):
        repo = make_repo(FORK)
        ctx = scripts[1].Context(
            repo, "github", "github.com", "feat/x", "main", "abc", None, "", "me", "owner"
        )
        assert (ctx.base_remote, ctx.base_shown) == ("origin", "")


class TestRepoRef:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://github.com/o/r.git", ("github.com", "o", "r")),
            ("https://github.com/o/r/", ("github.com", "o", "r")),
            ("https://u:p@GitHub.com:8443/O/R", ("github.com", "o", "r")),
            ("ssh://git@github.com:22/o/r.git", ("github.com", "o", "r")),
            ("git@github.com:o/r.git", ("github.com", "o", "r")),
            ("github.com:o/r", ("github.com", "o", "r")),
            ("https://ghe.example.com/team/sub/o/r.git", ("ghe.example.com", "o", "r")),
        ],
    )
    def test_a_remote_url_names_its_repository(self, scripts, url, expected):
        found = scripts[1].repo_mod.repo_ref(url)
        assert found is not None
        assert found.key == expected

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "/srv/git/o/r.git",
            "../o/r",
            "ext::sh -c id",
            "file:///o/r",
            "https://github.com/solo",
            "https://github.com/",
            "https://github.com",
            "git@github.com:solo.git",
            "https://github.com/o/r%20x",
            "https://github.com/o/<r>",
        ],
    )
    def test_a_url_that_names_no_repository_is_none(self, scripts, url):
        assert scripts[1].repo_mod.repo_ref(url) is None

    @pytest.mark.parametrize(
        ("url", "number", "found"),
        [
            ("https://github.com/o/r/pull/7", 7, True),
            ("https://github.com/o/r/pull/7/", 7, True),
            ("https://github.com/o/r/pull/8", 7, False),
            ("https://github.com/o/r/issues/7", 7, False),
            ("http://github.com/o/r/pull/7", 7, False),
            ("", 7, False),
        ],
    )
    def test_a_pr_url_names_the_repository_only_for_that_pr(self, scripts, url, number, found):
        assert (scripts[1].repo_mod.pr_repo(url, number) is not None) is found
