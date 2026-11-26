"""Behavior tests for ship_preflight.py with fake gh, az, and helpers.

S8 in evals/skill-rewrites/ship/retired.json, which #7582 adds, names a test in this file.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from tests.skills.ship.conftest import git
from tests.skills.ship.ship_helpers import invoke, values

GITHUB = "https://github.com/rjmurillo/ai-agents.git"
ADO = "https://dev.azure.com/contoso/p/_git/r"
MERGE = "m" * 40


def _checks(data: dict, rc: int = 0) -> dict:
    return {"rc": rc, "stdout": json.dumps({"Success": rc == 0, "Data": data}) + "\n"}


def _green() -> dict:
    return _checks({"RequiredState": "SUCCESS", "AllPassing": True})


def _head(fakes, pr: int, *, branch: str | None = None, sha: str | None = None) -> None:
    """Make PR ``pr`` report this checkout's branch and HEAD unless overridden."""
    repo = Path.cwd()
    fakes.rule(
        "gh",
        ["pr", "view", str(pr)],
        {
            "stdout": json.dumps(
                {
                    "headRefName": branch or git(repo, "branch", "--show-current"),
                    "headRefOid": sha or git(repo, "rev-parse", "HEAD"),
                }
            )
        },
    )


def _show(
    fakes, *, merge: str = MERGE, branch: str | None = None, sha: str | None = None, rc: int = 0
):
    repo = Path.cwd()
    state = {
        "source": f"refs/heads/{branch or git(repo, 'branch', '--show-current')}",
        "head": sha or git(repo, "rev-parse", "HEAD"),
        "merge": merge,
    }
    fakes.rule("az", ["repos", "pr", "show"], {"rc": rc, "stdout": json.dumps(state)})


def _preflight(scripts, capsys, *argv):
    return invoke(scripts[2], list(argv), capsys)


@pytest.fixture
def github(make_repo, fakes):
    repo = make_repo(GITHUB)
    fakes.no_pr_github()
    return repo


@pytest.fixture
def github_pr(make_repo, fakes):
    repo = make_repo(GITHUB)
    fakes.rule(
        "gh",
        ["pr", "view"],
        {
            "stdout": json.dumps(
                {"number": 9, "state": "OPEN", "author": {"login": "me"}, "url": "u"}
            )
        },
    )
    fakes.rule("gh", ["api", "user"], {"stdout": "me\n"})
    _head(fakes, 9)
    return repo


def test_owner_without_marker_fails_reviewed(github, fakes, scripts, capsys):
    fakes.marker(1)
    code, lines = _preflight(scripts, capsys, "--check", "reviewed")
    assert code == 1
    assert values(lines, "CHECK") == ["reviewed=FAIL [FAIL] HEAD is not a review marker commit"]
    assert lines[-1] == "STOP: check-failed reviewed"


def test_marker_pass_reports_declared_axes(github, fakes, scripts, capsys):
    fakes.marker(0, axes="analyst,security")
    code, lines = _preflight(scripts, capsys, "--check", "reviewed", "--require-axis", "security")
    assert code == 0
    assert values(lines, "CHECK") == ["reviewed=PASS axes=analyst,security"]
    call = fakes.calls("validate_review_marker")[0]
    assert call[1:3] == ["--ref", "HEAD"]
    assert call[-2:] == ["--require-axis", "security"]
    assert lines[-1] == "NEXT: write-body"


def test_marker_pass_without_axes_reports_unknown(github, fakes, scripts, capsys):
    fakes.rule("validate_review_marker", [], {"stdout": "[PASS] ok\n"})
    code, lines = _preflight(scripts, capsys, "--check", "reviewed")
    assert values(lines, "CHECK") == ["reviewed=PASS axes=unknown"]


def test_marker_fail_without_stderr_has_a_default_detail(github, fakes, scripts, capsys):
    fakes.rule("validate_review_marker", [], {"rc": 1})
    code, lines = _preflight(scripts, capsys, "--check", "reviewed")
    assert values(lines, "CHECK") == ["reviewed=FAIL no valid review marker"]


def test_validator_config_error_stops_exit_2(github, fakes, scripts, capsys):
    fakes.marker(2)
    code, lines = _preflight(scripts, capsys, "--check", "reviewed")
    assert code == 2
    assert lines[-1].startswith("STOP: validator-config")


def test_missing_validator_stops_exit_2(github, fakes, scripts, capsys):
    (fakes.skills / "review" / "scripts" / "validate_review_marker.py").unlink()
    code, lines = _preflight(scripts, capsys, "--check", "reviewed")
    assert code == 2
    assert lines[-1].startswith("STOP: validator-missing")


def test_draft_skips_the_marker(github, fakes, scripts, capsys):
    code, lines = _preflight(scripts, capsys, "--check", "reviewed", "--draft")
    assert code == 0
    assert values(lines, "CHECK") == ["reviewed=SKIPPED draft"]
    assert not fakes.calls("validate_review_marker")


def test_contributor_is_advisory_and_never_runs_the_validator(make_repo, fakes, scripts, capsys):
    make_repo(GITHUB)
    fakes.rule(
        "gh",
        ["pr", "view"],
        {
            "stdout": json.dumps(
                {"number": 9, "state": "OPEN", "author": {"login": "alice"}, "url": "u"}
            )
        },
    )
    fakes.rule("gh", ["api", "user"], {"stdout": "bob\n"})
    _head(fakes, 9)
    fakes.rule("get_pr_checks", [], _green())
    code, lines = _preflight(scripts, capsys, "--check", "reviewed", "--check", "pipeline")
    assert code == 0
    assert values(lines, "CHECK")[0].startswith("reviewed=ADVISORY")
    assert not fakes.calls("validate_review_marker")
    assert lines[-1] == "NEXT: report"


def test_clean_and_dirty_tree(github, fakes, scripts, capsys):
    code, lines = _preflight(scripts, capsys, "--check", "tree")
    assert code == 0 and values(lines, "CHECK") == ["tree=clean"]
    (github / "new.txt").write_text("x", encoding="utf-8")
    code, lines = _preflight(scripts, capsys, "--check", "tree")
    assert code == 1
    assert values(lines, "CHECK") == ["tree=dirty files=1"]
    assert lines[-1] == "STOP: check-failed tree"


def test_no_pr_defers_the_pipeline(github, fakes, scripts, capsys):
    code, lines = _preflight(scripts, capsys, "--check", "pipeline")
    assert code == 0
    assert values(lines, "CHECK") == ["pipeline=DEFERRED no open PR yet"]
    assert lines[-1] == "NEXT: publish-then-discharge"
    assert not fakes.calls("get_pr_checks")


def test_github_green_needs_success_and_all_passing(github_pr, fakes, scripts, capsys):
    fakes.rule("get_pr_checks", [], _green())
    code, lines = _preflight(scripts, capsys, "--check", "pipeline")
    assert code == 0
    assert values(lines, "CHECK")[0].startswith("pipeline=PASS pr=9 head=")
    call = fakes.calls("get_pr_checks")[0]
    assert call[1:] == [
        "--pull-request",
        "9",
        "--wait",
        "--timeout-seconds",
        "300",
        "--required-only",
        "--output-format",
        "json",
    ]


@pytest.mark.parametrize(("wait", "expected"), [("0", None), ("45", "45"), ("540", "300")])
def test_wait_seconds_bounds_the_github_wait(github_pr, fakes, scripts, capsys, wait, expected):
    fakes.rule("get_pr_checks", [], _green())
    code, _lines = _preflight(scripts, capsys, "--check", "pipeline", "--wait-seconds", wait)
    call = fakes.calls("get_pr_checks")[0]
    assert code == 0
    if expected is None:
        assert "--wait" not in call and "--timeout-seconds" not in call
    else:
        assert call[call.index("--timeout-seconds") + 1] == expected


@pytest.mark.parametrize(
    "data",
    [
        {"RequiredState": "SUCCESS", "AllPassing": False},
        {"RequiredState": "UNKNOWN", "AllPassing": True},
    ],
)
def test_github_exit_zero_alone_is_not_green(github_pr, fakes, scripts, capsys, data):
    fakes.rule("get_pr_checks", [], _checks(data))
    code, lines = _preflight(scripts, capsys, "--check", "pipeline")
    assert code == 1
    assert values(lines, "CHECK")[0].startswith("pipeline=FAIL")


def test_github_failed_checks_are_named(github_pr, fakes, scripts, capsys):
    data = {
        "RequiredState": "FAILURE",
        "AllPassing": False,
        "FailedRequiredChecks": [{"Name": "pytest"}, "lint"],
    }
    fakes.rule("get_pr_checks", [], _checks(data, rc=1))
    code, lines = _preflight(scripts, capsys, "--check", "pipeline")
    assert code == 1
    assert values(lines, "CHECK")[0].endswith("failing=pytest,lint")


def test_github_pending_asks_for_a_rerun_with_a_deadline(github_pr, fakes, scripts, capsys):
    fakes.rule("get_pr_checks", [], {"rc": 7, "stdout": "{}\n"})
    code, lines = _preflight(scripts, capsys, "--check", "pipeline")
    assert code == 0
    assert values(lines, "CHECK")[0].startswith("pipeline=PENDING")
    deadline = int(values(lines, "PIPELINE_DEADLINE")[0])
    assert deadline > time.time()
    assert lines[-1] == "NEXT: rerun-pipeline"


def test_github_pending_past_the_deadline_fails(github_pr, fakes, scripts, capsys):
    fakes.rule("get_pr_checks", [], {"rc": 7, "stdout": "{}\n"})
    code, lines = _preflight(
        scripts, capsys, "--check", "pipeline", "--deadline", str(int(time.time()) - 1)
    )
    assert code == 1
    assert values(lines, "CHECK") == ["pipeline=FAIL still pending after 30 minutes"]


@pytest.mark.parametrize(
    ("response", "reason", "code"),
    [
        ({"rc": 4}, "auth-failed", 4),
        ({"rc": 3, "stdout": "{}"}, "checks-query-failed", 3),
        ({"rc": 0, "stdout": "not json"}, "checks-query-failed", 3),
        ({"rc": 0, "stdout": ""}, "checks-query-failed", 3),
    ],
)
def test_github_query_failures_stop(github_pr, fakes, scripts, capsys, response, reason, code):
    fakes.rule("get_pr_checks", [], response)
    exit_code, lines = _preflight(scripts, capsys, "--check", "pipeline")
    assert exit_code == code
    assert lines[-1].startswith(f"STOP: {reason}")
    assert not any(value.startswith("pipeline=PASS") for value in values(lines, "CHECK"))


def test_github_missing_helper_stops(github_pr, fakes, scripts, capsys):
    (fakes.skills / "github" / "scripts" / "pr" / "get_pr_checks.py").unlink()
    code, lines = _preflight(scripts, capsys, "--check", "pipeline")
    assert code == 2
    assert lines[-1].startswith("STOP: checks-query-failed")


def test_discharge_with_explicit_pr_ends_on_report(github, fakes, scripts, capsys):
    _head(fakes, 41)
    fakes.rule("get_pr_checks", [], _green())
    code, lines = _preflight(scripts, capsys, "--check", "pipeline", "--pr", "41")
    assert code == 0
    assert values(lines, "CHECK")[0].startswith("pipeline=PASS pr=41 head=")
    assert lines[-1] == "NEXT: report"


def _ado(make_repo, fakes, pr: int | None = 77):
    make_repo(ADO)
    if pr is None:
        fakes.no_pr_ado()
        return
    fakes.rule(
        "az",
        ["repos", "pr", "list"],
        {"stdout": json.dumps([{"pullRequestId": pr, "createdBy": {"uniqueName": "me"}}])},
    )
    fakes.rule("az", ["account", "show"], {"stdout": "me\n"})


def _policies(*rows):
    return {"stdout": json.dumps([{"status": status, "buildId": build} for status, build in rows])}


def test_ado_approved_build_on_merge_commit_passes(make_repo, fakes, scripts, capsys):
    _ado(make_repo, fakes)
    fakes.rule(
        "az", ["repos", "pr", "policy", "list"], _policies(("approved", 5), ("notApplicable", None))
    )
    _show(fakes)
    fakes.rule(
        "az",
        ["pipelines", "build", "show"],
        {"stdout": json.dumps({"result": "succeeded", "sourceVersion": MERGE})},
    )
    code, lines = _preflight(scripts, capsys, "--check", "pipeline", "--wait-seconds", "0")
    assert code == 0
    assert values(lines, "CHECK") == [f"pipeline=PASS pr=77 builds=1 merge={MERGE}"]
    builds = [call for call in fakes.calls("az") if call[1:4] == ["pipelines", "build", "show"]]
    assert len(builds) == 1


@pytest.mark.parametrize(
    ("rows", "build"),
    [
        ((("approved", 5),), {"result": "succeeded", "sourceVersion": "old"}),
        ((("approved", 5),), {"result": "failed", "sourceVersion": MERGE}),
        ((("rejected", 5),), None),
        ((("approved", None),), None),
    ],
)
def test_ado_policy_failures(make_repo, fakes, scripts, capsys, rows, build):
    _ado(make_repo, fakes)
    fakes.rule("az", ["repos", "pr", "policy", "list"], _policies(*rows))
    _show(fakes)
    if build is not None:
        fakes.rule("az", ["pipelines", "build", "show"], {"stdout": json.dumps(build)})
    code, lines = _preflight(scripts, capsys, "--check", "pipeline", "--wait-seconds", "0")
    assert code == 1
    assert values(lines, "CHECK")[0].startswith("pipeline=FAIL pr=77")


def test_ado_without_merge_commit_fails(make_repo, fakes, scripts, capsys):
    _ado(make_repo, fakes)
    fakes.rule("az", ["repos", "pr", "policy", "list"], _policies(("approved", 5)))
    _show(fakes, merge="")
    code, lines = _preflight(scripts, capsys, "--check", "pipeline", "--wait-seconds", "0")
    assert code == 1
    assert "no merge commit" in values(lines, "CHECK")[0]


def test_ado_without_policy_fails_before_publish(make_repo, fakes, scripts, capsys):
    _ado(make_repo, fakes)
    _show(fakes)
    fakes.rule("az", ["repos", "pr", "policy", "list"], _policies(("notApplicable", None)))
    code, lines = _preflight(scripts, capsys, "--check", "pipeline", "--wait-seconds", "0")
    assert code == 1
    assert "no blocking build policy" in values(lines, "CHECK")[0]


def test_ado_discharge_waits_for_policies_to_appear(make_repo, fakes, scripts, capsys):
    _ado(make_repo, fakes, pr=None)
    _show(fakes)
    fakes.rule("az", ["repos", "pr", "policy", "list"], {"stdout": "[]"})
    code, lines = _preflight(
        scripts, capsys, "--check", "pipeline", "--pr", "77", "--wait-seconds", "0"
    )
    assert code == 0
    assert values(lines, "CHECK")[0].startswith("pipeline=PENDING pr=77")
    assert lines[-1] == "NEXT: rerun-pipeline"


def test_ado_polls_until_queued_policies_settle(make_repo, fakes, scripts, capsys, monkeypatch):
    preflight = scripts[2]
    monkeypatch.setattr(preflight.time, "sleep", lambda seconds: None)
    _ado(make_repo, fakes)
    fakes.rule(
        "az",
        ["repos", "pr", "policy", "list"],
        _policies(("queued", 5)),
        _policies(("approved", 5)),
    )
    _show(fakes)
    fakes.rule(
        "az",
        ["pipelines", "build", "show"],
        {"stdout": json.dumps({"result": "succeeded", "sourceVersion": MERGE})},
    )
    code, lines = _preflight(scripts, capsys, "--check", "pipeline", "--wait-seconds", "60")
    assert code == 0
    assert values(lines, "CHECK")[0].startswith("pipeline=PASS")
    polls = [call for call in fakes.calls("az") if call[1:5] == ["repos", "pr", "policy", "list"]]
    assert len(polls) == 2


@pytest.mark.parametrize(
    "failing",
    [["repos", "pr", "policy", "list"], ["repos", "pr", "show"], ["pipelines", "build", "show"]],
)
def test_ado_query_failure_stops_exit_3(make_repo, fakes, scripts, capsys, failing):
    _ado(make_repo, fakes)
    fakes.rule("az", ["repos", "pr", "policy", "list"], _policies(("approved", 5)))
    _show(fakes)
    fakes.rule(
        "az",
        ["pipelines", "build", "show"],
        {"stdout": json.dumps({"result": "succeeded", "sourceVersion": MERGE})},
    )
    fakes.rule("az", failing, {"rc": 1, "stderr": "TF000\n"})
    code, lines = _preflight(scripts, capsys, "--check", "pipeline", "--wait-seconds", "0")
    assert code == 3
    assert lines[-1].startswith("STOP: pipeline-query-failed")


@pytest.mark.parametrize(
    "failing", [["repos", "pr", "policy", "list"], ["pipelines", "build", "show"]]
)
def test_ado_unparseable_reply_stops(make_repo, fakes, scripts, capsys, failing):
    _ado(make_repo, fakes)
    fakes.rule("az", ["repos", "pr", "policy", "list"], _policies(("approved", 5)))
    _show(fakes)
    fakes.rule(
        "az",
        ["pipelines", "build", "show"],
        {"stdout": json.dumps({"result": "succeeded", "sourceVersion": MERGE})},
    )
    fakes.rule("az", failing, {"stdout": "not json"})
    code, lines = _preflight(scripts, capsys, "--check", "pipeline", "--wait-seconds", "0")
    assert code == 3
    assert lines[-1].startswith("STOP: pipeline-query-failed")


def test_all_checks_in_one_call(github, fakes, scripts, capsys):
    fakes.marker(0)
    code, lines = _preflight(
        scripts, capsys, "--check", "tree", "--check", "reviewed", "--check", "pipeline"
    )
    assert code == 0
    assert [value.split("=")[0] for value in values(lines, "CHECK")] == [
        "tree",
        "reviewed",
        "pipeline",
    ]
    assert lines[-1] == "NEXT: publish-then-discharge"


def test_detect_stop_propagates(make_repo, fakes, scripts, capsys):
    make_repo(None)
    code, lines = _preflight(scripts, capsys, "--check", "tree")
    assert code == 2
    assert lines[-1].startswith("STOP: no-origin")


def test_git_status_failure_stops(github, fakes, scripts, capsys, monkeypatch):
    common = scripts[0]
    real_git = common.git

    def broken(args, cwd=None, timeout=60):
        if args[:1] == ["status"]:
            return common.Completed(128, "", "fatal")
        return real_git(args, cwd=cwd, timeout=timeout)

    monkeypatch.setattr(common, "git", broken)
    code, lines = _preflight(scripts, capsys, "--check", "tree")
    assert code == 2
    assert lines[-1].startswith("STOP: no-repo")


@pytest.mark.parametrize(
    "argv",
    [
        ["--check", "bogus"],
        [],
        ["--check", "tree", "--check", "tree"],
        ["--check", "tree", "--wait-seconds", "999"],
        ["--check", "tree", "--require-axis", "Bad Axis"],
        ["--check", "tree", "--pr", "0"],
        ["--check", "tree", "--pr", "abc"],
        ["--check", "tree", "--base", "-main"],
        ["--chec", "tree"],
    ],
)
def test_bad_arguments_stop_exit_2(github, fakes, scripts, capsys, argv):
    code, lines = _preflight(scripts, capsys, *argv)
    assert code == 2
    assert lines[-1].startswith("STOP: bad-arguments")
