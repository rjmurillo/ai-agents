"""Behavior tests for ship_detect.py with fake gh and az on PATH.

S1 to S7 in evals/skill-rewrites/ship/retired.json, which #7582 adds, name tests in
this file.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from tests.skills.ship.conftest import git
from tests.skills.ship.ship_helpers import SCRIPTS, invoke, values

ADO_HTTPS = "https://dev.azure.com/contoso/agent-platform/_git/ai-agents"
ADO_SSH = "git@ssh.dev.azure.com:v3/contoso/agent-platform/ai-agents"
ADO_VS = "https://contoso.visualstudio.com/agent-platform/_git/ai-agents"
GITHUB = "https://github.com/rjmurillo/ai-agents.git"


def _open_pr(author: str, state: str = "OPEN") -> dict:
    return {
        "stdout": json.dumps(
            {
                "number": 120,
                "state": state,
                "author": {"login": author},
                "url": "https://github.com/o/r/pull/120",
                "baseRefName": "main",
            }
        )
    }


def _detect(scripts, capsys, *argv):
    return invoke(scripts[1], list(argv), capsys)


def _ado_host(make_repo, fakes, scripts, capsys, url):
    make_repo(url)
    fakes.no_pr_ado()
    code, lines = _detect(scripts, capsys)
    assert code == 0
    assert values(lines, "HOST") == ["ado"]
    assert values(lines, "PR") == ["none"]
    assert lines[-1] == "NEXT: preflight"
    return lines


def test_classify_ado_dev_azure_https(make_repo, fakes, scripts, capsys):
    lines = _ado_host(make_repo, fakes, scripts, capsys, ADO_HTTPS)
    assert values(lines, "REMOTE_HOST") == ["dev.azure.com"]


def test_classify_ado_dev_azure_ssh(make_repo, fakes, scripts, capsys):
    lines = _ado_host(make_repo, fakes, scripts, capsys, ADO_SSH)
    assert values(lines, "REMOTE_HOST") == ["ssh.dev.azure.com"]


def test_classify_ado_visualstudio_https(make_repo, fakes, scripts, capsys):
    lines = _ado_host(make_repo, fakes, scripts, capsys, ADO_VS)
    assert values(lines, "REMOTE_HOST") == ["contoso.visualstudio.com"]


def test_classify_github_origin(make_repo, fakes, scripts, capsys):
    make_repo(GITHUB)
    fakes.no_pr_github()
    code, lines = _detect(scripts, capsys)
    assert code == 0
    assert values(lines, "HOST") == ["github"]
    assert values(lines, "MODE") == ["owner"]
    assert values(lines, "BRANCH") == ["feat/ship-change"]
    assert values(lines, "BASE") == ["main"]
    assert len(values(lines, "HEAD")[0]) == 40
    assert lines[-1] == "NEXT: preflight"


def test_no_origin_stops_exit_2(make_repo, fakes, scripts, capsys):
    make_repo(None)
    code, lines = _detect(scripts, capsys)
    assert code == 2
    assert lines[-1].startswith("STOP: no-origin")
    assert not values(lines, "HOST")


def test_open_pr_other_author_is_contributor(make_repo, fakes, scripts, capsys):
    make_repo(GITHUB)
    fakes.rule("gh", ["pr", "view"], _open_pr("teammate"))
    fakes.rule("gh", ["api", "user"], {"stdout": "rjmurillo\n"})
    code, lines = _detect(scripts, capsys)
    assert code == 0
    assert values(lines, "MODE") == ["contributor"]
    assert values(lines, "PR") == ["120"]
    assert values(lines, "PR_AUTHOR") == ["teammate"]
    assert lines[-1] == "NEXT: validate-only"


def test_merged_pr_is_owner_with_no_pr(make_repo, fakes, scripts, capsys):
    make_repo(GITHUB)
    fakes.rule("gh", ["pr", "view"], _open_pr("teammate", state="MERGED"))
    code, lines = _detect(scripts, capsys)
    assert code == 0
    assert values(lines, "MODE") == ["owner"]
    assert values(lines, "PR") == ["none"]
    assert not fakes.calls("gh")[1:], "no user query when no PR is open"


def test_own_open_pr_is_owner(make_repo, fakes, scripts, capsys):
    make_repo(GITHUB)
    fakes.rule("gh", ["pr", "view"], _open_pr("RJMurillo"))
    fakes.rule("gh", ["api", "user"], {"stdout": "rjmurillo\n"})
    code, lines = _detect(scripts, capsys)
    assert code == 0
    assert values(lines, "MODE") == ["owner"]
    assert values(lines, "PR_URL") == ["https://github.com/o/r/pull/120"]


@pytest.mark.parametrize(
    ("stderr", "reason", "code"),
    [
        ("HTTP 401: Bad credentials\n", "auth-failed", 4),
        ("To get started with GitHub CLI, please run: gh auth login\n", "auth-failed", 4),
        ("HTTP 502: Bad Gateway\n", "pr-query-failed", 3),
        ("", "pr-query-failed", 3),
    ],
)
def test_failed_pr_query_never_prints_pr_none(
    make_repo, fakes, scripts, capsys, stderr, reason, code
):
    make_repo(GITHUB)
    fakes.rule("gh", ["pr", "view"], {"rc": 1, "stderr": stderr})
    exit_code, lines = _detect(scripts, capsys)
    assert exit_code == code
    assert lines[-1].startswith(f"STOP: {reason}")
    assert "PR: none" not in lines


@pytest.mark.parametrize("stdout", ["not json", json.dumps({"state": "OPEN"})])
def test_unparseable_pr_reply_stops(make_repo, fakes, scripts, capsys, stdout):
    make_repo(GITHUB)
    fakes.rule("gh", ["pr", "view"], {"stdout": stdout})
    code, lines = _detect(scripts, capsys)
    assert code == 3
    assert lines[-1].startswith("STOP: pr-query-failed")


def test_user_query_failure_stops(make_repo, fakes, scripts, capsys):
    make_repo(GITHUB)
    fakes.rule("gh", ["pr", "view"], _open_pr("teammate"))
    fakes.rule("gh", ["api", "user"], {"rc": 1, "stderr": "HTTP 500\n"})
    code, lines = _detect(scripts, capsys)
    assert code == 3
    assert lines[-1].startswith("STOP: user-query-failed")


def test_on_base_branch_stops(make_repo, fakes, scripts, capsys):
    make_repo(GITHUB, branch="main")
    fakes.no_pr_github()
    code, lines = _detect(scripts, capsys)
    assert code == 1
    assert lines[-1].startswith("STOP: on-base-branch")


def test_explicit_base_changes_the_target(make_repo, fakes, scripts, capsys):
    make_repo(GITHUB)
    fakes.no_pr_github()
    code, lines = _detect(scripts, capsys, "--base", "release")
    assert code == 0
    assert values(lines, "BASE") == ["release"]


def test_origin_head_sets_the_default_base(make_repo, fakes, scripts, capsys):
    repo = make_repo(GITHUB)
    git(repo, "update-ref", "refs/remotes/origin/develop", "HEAD")
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/develop")
    fakes.no_pr_github()
    code, lines = _detect(scripts, capsys)
    assert code == 0
    assert values(lines, "BASE") == ["develop"]


def test_detached_head_stops(make_repo, fakes, scripts, capsys):
    repo = make_repo(GITHUB)
    git(repo, "switch", "-q", "--detach", "HEAD")
    code, lines = _detect(scripts, capsys)
    assert code == 2
    assert lines[-1].startswith("STOP: detached-head")


def test_local_path_remote_stops(make_repo, fakes, scripts, capsys, tmp_path):
    make_repo(str(tmp_path / "elsewhere.git"))
    code, lines = _detect(scripts, capsys)
    assert code == 2
    assert lines[-1].startswith("STOP: unsupported-remote")


def test_outside_a_repo_stops(fakes, scripts, capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, lines = _detect(scripts, capsys)
    assert code == 2
    assert lines[-1].startswith("STOP: no-repo")


def test_ado_open_pr_by_other_author_is_contributor(make_repo, fakes, scripts, capsys):
    make_repo(ADO_HTTPS)
    fakes.rule(
        "az",
        ["repos", "pr", "list"],
        {
            "stdout": json.dumps(
                [
                    {
                        "pullRequestId": 77,
                        "targetRefName": "refs/heads/main",
                        "createdBy": {"uniqueName": "alice@contoso.com"},
                        "repository": {"webUrl": "https://dev.azure.com/c/p/_git/r"},
                    }
                ]
            )
        },
    )
    fakes.rule("az", ["account", "show"], {"stdout": "bob@contoso.com\n"})
    code, lines = _detect(scripts, capsys)
    assert code == 0
    assert values(lines, "PR") == ["77"]
    assert values(lines, "PR_URL") == ["https://dev.azure.com/c/p/_git/r/pullrequest/77"]
    assert values(lines, "MODE") == ["contributor"]
    assert [
        "az",
        "repos",
        "pr",
        "list",
        "--source-branch",
        "refs/heads/feat/ship-change",
        "--status",
        "active",
        "--output",
        "json",
    ] in fakes.calls("az")


@pytest.mark.parametrize(
    ("response", "reason", "code"),
    [
        ({"rc": 1, "stderr": "Please run 'az login' to setup account.\n"}, "auth-failed", 4),
        ({"rc": 1, "stderr": "TF400813\n"}, "pr-query-failed", 3),
        ({"stdout": "{}"}, "pr-query-failed", 3),
        ({"stdout": json.dumps([{"title": "no id"}])}, "pr-query-failed", 3),
    ],
)
def test_ado_query_failures_stop(make_repo, fakes, scripts, capsys, response, reason, code):
    make_repo(ADO_HTTPS)
    fakes.rule("az", ["repos", "pr", "list"], response)
    exit_code, lines = _detect(scripts, capsys)
    assert exit_code == code
    assert lines[-1].startswith(f"STOP: {reason}")


def test_ado_user_query_failure_stops(make_repo, fakes, scripts, capsys):
    make_repo(ADO_HTTPS)
    fakes.rule(
        "az",
        ["repos", "pr", "list"],
        {
            "stdout": json.dumps(
                [
                    {
                        "pullRequestId": 5,
                        "targetRefName": "refs/heads/main",
                        "createdBy": {"uniqueName": "me"},
                    }
                ]
            )
        },
    )
    fakes.rule("az", ["account", "show"], {"rc": 1, "stderr": "boom\n"})
    code, lines = _detect(scripts, capsys)
    assert code == 3
    assert lines[-1].startswith("STOP: user-query-failed")


def test_remote_credentials_never_printed(make_repo, fakes, scripts, capsys):
    make_repo("https://bob:s3cr3t-token@github.com/o/r.git")
    fakes.no_pr_github()
    code, lines = _detect(scripts, capsys)
    assert code == 0
    assert "s3cr3t" not in "\n".join(lines)


@pytest.mark.parametrize(
    "argv",
    [
        ["--base", "-x"],
        ["--base", "a..b"],
        ["--bas", "main"],
        ["--unknown"],
        ["--output-format", "xml"],
    ],
)
def test_bad_arguments_stop_exit_2(make_repo, fakes, scripts, capsys, argv):
    make_repo(GITHUB)
    code = scripts[1].main(argv)
    out = capsys.readouterr().out
    assert code == 2
    if out.lstrip().startswith("{"):
        assert json.loads(out)["Error"]["Code"] == 2
    else:
        assert out.splitlines()[-1].startswith("STOP: bad-arguments")


def test_json_format_is_an_adr_103_envelope(make_repo, fakes, scripts, capsys):
    make_repo(GITHUB)
    fakes.no_pr_github()
    code = scripts[1].main(["--output-format", "json"])
    envelope = json.loads(capsys.readouterr().out)
    assert code == 0
    assert envelope["Success"] is True
    assert envelope["Data"]["HOST"] == "github"
    assert envelope["Data"]["NEXT"] == "preflight"
    assert envelope["Metadata"]["Script"] == "ship_detect.py"


def test_branch_with_unsafe_name_stops(make_repo, fakes, scripts, capsys):
    repo = make_repo(GITHUB)
    git(repo, "switch", "-q", "-c", "feat/a+b")
    code, lines = _detect(scripts, capsys)
    assert code == 2
    assert lines[-1].startswith("STOP: bad-arguments")


def test_script_runs_as_a_subprocess_under_isolated_mode(make_repo, fakes, scripts):
    repo = make_repo(GITHUB)
    fakes.no_pr_github()
    done = subprocess.run(
        [sys.executable, "-I", str(SCRIPTS / "ship_detect.py"), "--output-format", "human"],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    lines = done.stdout.splitlines()
    assert done.returncode == 0
    assert lines[-1] == "NEXT: preflight"
    assert sum(line.startswith(("NEXT:", "STOP:")) for line in lines) == 1
