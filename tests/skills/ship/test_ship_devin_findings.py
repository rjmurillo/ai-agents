"""Tests for the Devin review threads on PR #7737.

Each class names its thread: the checks helper on GitHub Enterprise, a CI
verdict bound to the PR's own repository, the base of an open PR, the shared
push lock (now in test_ship_push_lock.py), and the Windows guard when PATHEXT omits ``.EXE``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.skills.ship.conftest import git
from tests.skills.ship.ship_helpers import GITHUB, invoke, publish, remote_has_branch, values

# The push lock is flock, which Windows does not have.
fcntl = pytest.importorskip("fcntl")

ADO = "https://dev.azure.com/contoso/p/_git/r"
GREEN = {"stdout": json.dumps({"Data": {"RequiredState": "SUCCESS", "AllPassing": True}}) + "\n"}


def _env_calls(fakes, prog: str) -> list[str | None]:
    """Return the GH_HOST each call of ``prog`` saw."""
    path = Path(f"{fakes.log}.env")
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return [entry[1] for entry in entries if entry[0] == prog]


def _open_github_pr(fakes, number: int, url: str, target: str = "main") -> None:
    pr = {
        "number": number,
        "state": "OPEN",
        "author": {"login": "me"},
        "url": url,
        "baseRefName": target,
    }
    fakes.rule("gh", ["pr", "view"], {"stdout": json.dumps(pr)})
    fakes.rule("gh", ["api", "user"], {"stdout": "me\n"})


def _head(fakes, number: int, url: str, repo: Path) -> None:
    binding = {
        "headRefName": git(repo, "branch", "--show-current"),
        "headRefOid": git(repo, "rev-parse", "HEAD"),
        "url": url,
    }
    fakes.rule("gh", ["pr", "view", str(number)], {"stdout": json.dumps(binding)})


def _pipeline(scripts, capsys):
    return invoke(scripts[2], ["--check", "pipeline"], capsys)


class TestEnterpriseChecksHost:
    """PRRT_kwDOQoWRls68cAco: the checks helper reads the PR's host and repository."""

    def test_an_enterprise_pr_reads_checks_on_its_own_host(self, make_repo, fakes, scripts, capsys):
        repo = make_repo("https://github.example.com/acme/widget.git")
        url = "https://github.example.com/acme/widget/pull/42"
        _open_github_pr(fakes, 42, url)
        _head(fakes, 42, url, repo)
        fakes.rule("get_pr_checks", [], GREEN)
        code, lines = _pipeline(scripts, capsys)
        assert code == 0, lines
        assert values(lines, "CHECK")[0].startswith("pipeline=PASS pr=42")
        call = fakes.calls("get_pr_checks")[0]
        assert call[1:5] == ["--owner", "acme", "--repo", "widget"]
        assert _env_calls(fakes, "get_pr_checks") == ["github.example.com"]

    def test_a_caller_gh_host_never_reaches_the_helper(
        self, make_repo, fakes, scripts, capsys, monkeypatch
    ):
        repo = make_repo(GITHUB)
        monkeypatch.setenv("GH_HOST", "evil.example")
        url = "https://github.com/rjmurillo/ai-agents/pull/9"
        _open_github_pr(fakes, 9, url)
        _head(fakes, 9, url, repo)
        fakes.rule("get_pr_checks", [], GREEN)
        code, _lines = _pipeline(scripts, capsys)
        assert code == 0
        assert _env_calls(fakes, "get_pr_checks") == ["github.com"]
        assert set(_env_calls(fakes, "gh")) == {None}


class TestCiVerdictRepository:
    """PRRT_kwDOQoWRls68cAeP: CI is read from the repository that owns the PR."""

    def test_a_fork_origin_reads_the_upstream_pr_checks(self, make_repo, fakes, scripts, capsys):
        repo = make_repo("https://github.com/me/fork.git")
        url = "https://github.com/upstream/project/pull/42"
        _open_github_pr(fakes, 42, url)
        _head(fakes, 42, url, repo)
        fakes.rule("get_pr_checks", [], GREEN)
        code, lines = _pipeline(scripts, capsys)
        assert code == 0, lines
        call = fakes.calls("get_pr_checks")[0]
        assert call[1:5] == ["--owner", "upstream", "--repo", "project"]
        heads = [c for c in fakes.calls("gh") if c[1:4] == ["pr", "view", "42"]]
        assert len(heads) == 2
        assert "--repo" not in heads[0]
        assert heads[1][4:6] == ["--repo", "github.com/upstream/project"]

    def test_the_second_head_read_moving_repository_is_pending(
        self, make_repo, fakes, scripts, capsys
    ):
        repo = make_repo(GITHUB)
        head = git(repo, "rev-parse", "HEAD")
        _open_github_pr(fakes, 42, "https://github.com/up/a/pull/42")
        first = {"headRefName": "feat/ship-change", "headRefOid": head}
        fakes.rule(
            "gh",
            ["pr", "view", "42"],
            {"stdout": json.dumps({**first, "url": "https://github.com/up/a/pull/42"})},
            {"stdout": json.dumps({**first, "url": "https://github.com/up/b/pull/42"})},
        )
        fakes.rule("get_pr_checks", [], GREEN)
        code, lines = _pipeline(scripts, capsys)
        assert code == 0
        assert values(lines, "CHECK")[0] == "pipeline=PENDING pr=42 head moved during the check"

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "u",
            "https://github.com/up/a/pull/43",
            "https://github.com/up/a/issues/42",
            "http://github.com/up/a/pull/42",
            "https://github.com/up/a/pull/42/files",
        ],
    )
    def test_a_pr_url_that_does_not_name_this_pr_stops(
        self, make_repo, fakes, scripts, capsys, url
    ):
        repo = make_repo(GITHUB)
        _open_github_pr(fakes, 42, "https://github.com/up/a/pull/42")
        _head(fakes, 42, url, repo)
        code, lines = _pipeline(scripts, capsys)
        assert code == 3
        assert lines[-1].startswith("STOP: checks-query-failed PR 42 URL did not parse:")
        assert not fakes.calls("get_pr_checks")


class TestOpenPrBase:
    """PRRT_kwDOQoWRls68cAg-: an open PR's target branch is the base."""

    def test_a_github_pr_on_a_release_branch_sets_the_base(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        _open_github_pr(fakes, 7, "https://github.com/o/r/pull/7", target="release/2")
        code, lines = invoke(scripts[1], [], capsys)
        assert code == 0, lines
        assert values(lines, "BASE") == ["release/2"]

    def test_a_matching_base_flag_is_accepted(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        _open_github_pr(fakes, 7, "https://github.com/o/r/pull/7", target="release/2")
        code, lines = invoke(scripts[1], ["--base", "release/2"], capsys)
        assert code == 0
        assert values(lines, "BASE") == ["release/2"]

    def test_a_base_flag_naming_another_target_stops(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        _open_github_pr(fakes, 7, "https://github.com/o/r/pull/7", target="release/2")
        code, lines = invoke(scripts[1], ["--base", "main"], capsys)
        assert code == 2
        assert lines[-1] == (
            "STOP: base-mismatch --base main is not the target of open PR 7, release/2"
        )

    def test_publish_never_pushes_on_a_base_mismatch(
        self, make_repo, fakes, scripts, capsys, body_file, tmp_path
    ):
        repo = make_repo(GITHUB)
        _open_github_pr(fakes, 7, "https://github.com/o/r/pull/7", target="release/2")
        code, lines = publish(scripts, capsys, body_file(repo), "--base", "main")
        assert code == 2
        assert lines[-1].startswith("STOP: base-mismatch")
        assert not remote_has_branch(tmp_path)

    @pytest.mark.parametrize("target", ["", "-x", "a..b"])
    def test_a_github_pr_without_a_usable_target_stops(
        self, make_repo, fakes, scripts, capsys, target
    ):
        make_repo(GITHUB)
        _open_github_pr(fakes, 7, "https://github.com/o/r/pull/7", target=target)
        code, lines = invoke(scripts[1], [], capsys)
        assert code == 3
        assert lines[-1] == "STOP: pr-query-failed PR 7 has no target branch"

    def test_an_ado_pr_target_sets_the_base(self, make_repo, fakes, scripts, capsys):
        make_repo(ADO)
        entry = {
            "pullRequestId": 5,
            "targetRefName": "refs/heads/release/2",
            "createdBy": {"uniqueName": "me"},
        }
        fakes.rule("az", ["repos", "pr", "list"], {"stdout": json.dumps([entry])})
        fakes.rule("az", ["account", "show"], {"stdout": "me\n"})
        code, lines = invoke(scripts[1], [], capsys)
        assert code == 0, lines
        assert values(lines, "BASE") == ["release/2"]

    @pytest.mark.parametrize("target", [None, "", "release/2", "refs/tags/v1"])
    def test_an_ado_target_outside_refs_heads_stops(
        self, make_repo, fakes, scripts, capsys, target
    ):
        make_repo(ADO)
        entry = {"pullRequestId": 5, "createdBy": {"uniqueName": "me"}}
        if target is not None:
            entry["targetRefName"] = target
        fakes.rule("az", ["repos", "pr", "list"], {"stdout": json.dumps([entry])})
        fakes.rule("az", ["account", "show"], {"stdout": "me\n"})
        code, lines = invoke(scripts[1], [], capsys)
        assert code == 3
        assert lines[-1] == "STOP: pr-query-failed PR 5 has no target branch"

    def test_no_open_pr_keeps_the_origin_default(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        fakes.no_pr_github()
        code, lines = invoke(scripts[1], [], capsys)
        assert code == 0
        assert values(lines, "BASE") == ["main"]


class TestPlantedExe:
    """PRRT_kwDOQoWRls68cAnD: CreateProcess appends .exe whatever PATHEXT says."""

    def test_an_exe_is_seen_when_pathext_omits_it(self, scripts, monkeypatch, tmp_path):
        windows = scripts[0]._windows
        monkeypatch.setenv("PATHEXT", ".BAT;.CMD")
        (tmp_path / "git.EXE").write_bytes(b"")
        assert windows.planted_programs(tmp_path) == ["git.EXE"]

    def test_pathext_with_exe_is_not_doubled(self, scripts, monkeypatch, tmp_path):
        windows = scripts[0]._windows
        monkeypatch.setenv("PATHEXT", ".exe;.CMD")
        (tmp_path / "gh.exe").write_bytes(b"")
        assert windows.planted_programs(tmp_path) == ["gh.exe"]
