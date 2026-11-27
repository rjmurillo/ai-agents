"""A PR target outside the plain-ref allowlist, and several ADO PRs on one source branch.

``safe_ref`` is the reviewed allowlist for a name the user types and stays as it
is. A target the host returns is held to ``valid_branch``, which follows
``git check-ref-format``; these tests run the real git over it.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from tests.skills.ship.conftest import git
from tests.skills.ship.ship_helpers import (
    ADO,
    GITHUB,
    TITLE,
    VALIDATOR_PASS,
    invoke,
    run_pr,
    values,
)

PLUS = "release/2026+hotfix"
PLUS_REF = f"refs/remotes/origin/{PLUS}"

# git accepts each of these under refs/heads/, and valid_branch must too.
ACCEPTED = [
    "main",
    PLUS,
    "feat/a_b-c.d",
    "a/b/c",
    "release/2.0",
    "a=b",
    "a,b",
    "a#b",
    "a%b",
    "a!b",
    'a"b',
    "a$b",
    "a(b)",
    "a{b}",
    "a'b",
    "a@b",
    "feature/\u00e9\u00fc",
]
# git rejects each of these, and valid_branch must too.
REJECTED = [
    "",
    "a..b",
    "a b",
    "a~b",
    "a^b",
    "a:b",
    "a?b",
    "a*b",
    "a[b",
    "a\\b",
    "/a",
    "a/",
    "a//b",
    "a.",
    "a.lock",
    "a/b.lock",
    ".a",
    "a/.b",
    "a@{b",
    "a\tb",
    "a\x7fb",
    "a\nb",
]
# git accepts each of these under refs/heads/. valid_branch refuses them on purpose.
STRICTER = ["-x", "-", "HEAD", "@", "a\x85b", "a\u2028b", "x" * 256]


def _git_accepts(name: str) -> bool:
    done = subprocess.run(
        ["git", "check-ref-format", f"refs/heads/{name}"], capture_output=True, check=False
    )
    return done.returncode == 0


@pytest.fixture
def valid_branch(scripts):
    return scripts[1].pr_query_mod.valid_branch


class TestValidBranchMatchesGit:
    @pytest.mark.parametrize("name", ACCEPTED)
    def test_a_name_git_accepts_is_accepted(self, valid_branch, name):
        assert _git_accepts(name)
        assert valid_branch(name) is True

    @pytest.mark.parametrize("name", REJECTED)
    def test_a_name_git_rejects_is_rejected(self, valid_branch, name):
        assert not _git_accepts(name)
        assert valid_branch(name) is False

    @pytest.mark.parametrize("name", STRICTER)
    def test_a_name_git_accepts_but_ship_refuses_on_purpose(self, valid_branch, name):
        assert _git_accepts(name)
        assert valid_branch(name) is False

    def test_safe_ref_is_not_widened(self, scripts):
        assert scripts[0].safe_ref(PLUS) is False


def _open_github_pr(fakes, target: str, number: int = 7, repo: str = "o/r") -> None:
    pr = {
        "number": number,
        "state": "OPEN",
        "author": {"login": "me"},
        "url": f"https://github.com/{repo}/pull/{number}",
        "baseRefName": target,
    }
    fakes.rule("gh", ["pr", "view"], {"stdout": json.dumps(pr)})
    fakes.rule("gh", ["api", "user"], {"stdout": "me\n"})


class TestPlusTargetDetect:
    def test_the_target_of_an_open_pr_sets_the_base(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        _open_github_pr(fakes, PLUS)
        code, lines = invoke(scripts[1], [], capsys)
        assert code == 0, lines
        assert values(lines, "BASE") == [PLUS]

    def test_a_base_flag_naming_that_target_is_accepted(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        _open_github_pr(fakes, PLUS)
        code, lines = invoke(scripts[1], ["--base", PLUS], capsys)
        assert code == 0, lines
        assert values(lines, "BASE") == [PLUS]

    def test_a_base_flag_naming_another_target_still_mismatches(
        self, make_repo, fakes, scripts, capsys
    ):
        make_repo(GITHUB)
        _open_github_pr(fakes, "main")
        code, lines = invoke(scripts[1], ["--base", PLUS], capsys)
        assert code == 2
        assert (
            lines[-1] == f"STOP: base-mismatch --base {PLUS} is not the target of open PR 7, main"
        )

    @pytest.mark.parametrize("base", [PLUS, "a%b"])
    def test_a_new_pr_keeps_the_plain_ref_rule(self, make_repo, fakes, scripts, capsys, base):
        make_repo(GITHUB)
        fakes.no_pr_github()
        code, lines = invoke(scripts[1], ["--base", base], capsys)
        assert code == 2
        assert lines[-1] == "STOP: bad-arguments --base is not a plain ref"

    @pytest.mark.parametrize("target", ["-x", "a..b", "a b", "HEAD"])
    def test_a_target_git_would_refuse_stops(self, make_repo, fakes, scripts, capsys, target):
        make_repo(GITHUB)
        _open_github_pr(fakes, target)
        code, lines = invoke(scripts[1], [], capsys)
        assert code == 3
        assert lines[-1] == "STOP: pr-query-failed PR 7 has no target branch"

    def test_an_ado_target_with_a_plus_sets_the_base(self, make_repo, fakes, scripts, capsys):
        make_repo(ADO)
        entry = {
            "pullRequestId": 5,
            "targetRefName": f"refs/heads/{PLUS}",
            "createdBy": {"uniqueName": "me"},
        }
        fakes.rule("az", ["repos", "pr", "list"], {"stdout": json.dumps([entry])})
        fakes.rule("az", ["account", "show"], {"stdout": "me\n"})
        code, lines = invoke(scripts[1], ["--base", PLUS], capsys)
        assert code == 0, lines
        assert values(lines, "BASE") == [PLUS]


class TestPlusTargetReachesGitSafely:
    """The base is one argv element or a refs/remotes path part, so ``+`` stays inert."""

    def test_preflight_and_check_accept_the_flag_for_that_pr(
        self, make_repo, fakes, scripts, capsys, body_file
    ):
        repo = make_repo(GITHUB)
        _open_github_pr(fakes, PLUS)
        code, lines = invoke(scripts[2], ["--check", "tree", "--base", PLUS], capsys)
        assert code == 0, lines
        assert values(lines, "BASE") == [PLUS]
        body = body_file(repo)
        code, lines = run_pr(
            scripts, capsys, "check", "--title", TITLE, "--body-file", str(body), "--base", PLUS
        )
        assert values(lines, "BASE") == [PLUS], lines
        assert code == 0, lines

    def test_prepare_keeps_the_plain_ref_rule(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        code, lines = run_pr(scripts, capsys, "prepare", "--base", PLUS)
        assert code == 2
        assert lines[-1] == "STOP: bad-arguments --base is not a plain ref"
        assert not fakes.calls("new_pr")

    def test_the_paths_check_reads_and_diffs_the_plus_branch(
        self, make_repo, fakes, scripts, capsys, body_file, base_validator, tmp_path, monkeypatch
    ):
        repo = make_repo(GITHUB)
        base_validator(repo, VALIDATOR_PASS)
        git(repo, "push", "-q", "origin", f"main:refs/heads/{PLUS}")
        assert git(repo, "rev-parse", "--verify", PLUS_REF)
        _open_github_pr(fakes, PLUS, repo="rjmurillo/ai-agents")  # origin's own repository
        probe = tmp_path / "probe.json"
        monkeypatch.setenv("SHIP_VALIDATOR_PROBE", str(probe))
        code, lines = run_pr(
            scripts, capsys, "check", "--title", TITLE, "--body-file", str(body_file(repo))
        )
        assert code == 0, lines
        assert "paths=PASS" in values(lines, "CHECK")
        assert json.loads(probe.read_text(encoding="utf-8"))["argv"][-2:] == ["--base", PLUS_REF]


def _ado_rows(*rows: object) -> str:
    return json.dumps(list(rows))


def _ado_row(pr_id: int, target: str, author: str) -> dict:
    return {
        "pullRequestId": pr_id,
        "targetRefName": f"refs/heads/{target}",
        "createdBy": {"uniqueName": author},
        "repository": {"webUrl": "https://dev.azure.com/c/p/_git/r"},
    }


class TestAdoSeveralActivePrs:
    """Several active PRs can share one source branch, each with its own target."""

    @pytest.fixture
    def ado(self, make_repo, fakes):
        make_repo(ADO)
        fakes.rule("az", ["account", "show"], {"stdout": "me\n"})
        return fakes

    def test_base_selects_the_pr_that_targets_it_before_the_author_check(
        self, ado, scripts, capsys
    ):
        rows = _ado_rows(_ado_row(1, "main", "other@example.com"), _ado_row(2, "release/2", "me"))
        ado.rule("az", ["repos", "pr", "list"], {"stdout": rows})
        code, lines = invoke(scripts[1], ["--base", "release/2"], capsys)
        assert code == 0, lines
        assert values(lines, "PR") == ["2"]
        assert values(lines, "BASE") == ["release/2"]
        assert values(lines, "MODE") == ["owner"]
        assert lines[-1] == "NEXT: preflight"

    def test_a_row_that_is_not_an_object_is_skipped(self, ado, scripts, capsys):
        ado.rule(
            "az",
            ["repos", "pr", "list"],
            {"stdout": _ado_rows("junk", _ado_row(2, "release/2", "me"))},
        )
        code, lines = invoke(scripts[1], ["--base", "release/2"], capsys)
        assert code == 0, lines
        assert values(lines, "PR") == ["2"]

    def test_no_matching_pr_still_stops_on_the_mismatch(self, ado, scripts, capsys):
        rows = _ado_rows(_ado_row(1, "main", "me"), _ado_row(2, "release/2", "me"))
        ado.rule("az", ["repos", "pr", "list"], {"stdout": rows})
        code, lines = invoke(scripts[1], ["--base", "release/9"], capsys)
        assert code == 2
        assert (
            lines[-1] == "STOP: base-mismatch --base release/9 is not the target of open PR 1, main"
        )

    def test_without_base_the_first_pr_is_used(self, ado, scripts, capsys):
        rows = _ado_rows(_ado_row(1, "main", "other@example.com"), _ado_row(2, "release/2", "me"))
        ado.rule("az", ["repos", "pr", "list"], {"stdout": rows})
        code, lines = invoke(scripts[1], [], capsys)
        assert code == 0, lines
        assert values(lines, "PR") == ["1"]
        assert values(lines, "BASE") == ["main"]
        assert values(lines, "MODE") == ["contributor"]
