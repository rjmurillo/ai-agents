"""Tests for the new_issue.py --milestone check that runs before creation (issue #6033).

A missing or unreadable milestone must stop the run before any issue exists, so
a caller can fix the argument and retry without filing a duplicate.
"""

import json
import subprocess
from unittest.mock import patch

import pytest

from .new_issue_harness import (
    FakeGh,
    _make_proc,
    _run,
    main,
    resolve_repo_fixture,  # noqa: F401  (autouse fixture)
)

MILESTONES = ("api", "repos/owner/repo/milestones")
BASE = ["--title", "Title", "--source", "human"]
LIST_OK = _make_proc(stdout="v0.6.0\nv0.7.0\n")


def test_absent_flag_makes_no_milestone_calls(capsys, tmp_path, monkeypatch):
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))

    rc, gh = _run(BASE, FakeGh())

    assert rc == 0
    assert [c for c in gh.calls if c[1] == "api"] == []
    assert gh.milestone_edits() == []
    assert json.loads(capsys.readouterr().out)["Data"]["milestone"] is None
    assert "milestone=" not in out.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("milestones_route", "milestone", "code", "error_type", "message"),
    [
        (LIST_OK, "v9.9.9", 2, "NotFound", "Milestone 'v9.9.9' does not exist in owner/repo."),
        (_make_proc(returncode=1, stderr="boom"), "v0.7.0", 3, "ApiError", "boom"),
        (subprocess.TimeoutExpired(cmd="gh", timeout=30), "v0.7.0", 3, "Timeout", "Timed out"),
    ],
    ids=["missing", "query-fails", "query-times-out"],
)
def test_lookup_failure_creates_no_issue(
    capsys, milestones_route, milestone, code, error_type, message
):
    gh = FakeGh(extra_routes={MILESTONES: milestones_route})

    rc, gh = _run([*BASE, "--milestone", milestone], gh)

    assert rc == code
    assert gh.verbs() == [MILESTONES]
    data = json.loads(capsys.readouterr().out)
    assert data["Error"]["Type"] == error_type
    assert message in data["Error"]["Message"]
    assert data["Error"]["Message"].endswith("No issue was created.")
    assert data["Data"] == {"milestone": milestone}


def test_missing_milestone_human_output_says_no_issue(capsys):
    gh = FakeGh(extra_routes={MILESTONES: LIST_OK})

    with patch("subprocess.run", side_effect=gh):
        rc = main([*BASE, "--milestone", "v9.9.9", "--output-format", "human"])

    assert rc == 2
    captured = capsys.readouterr()
    assert "No issue was created." in captured.out + captured.err
    assert ("issue", "create") not in gh.verbs()


@pytest.mark.parametrize("milestone", ["", "  "], ids=["empty", "blank"])
def test_empty_milestone_exits_2_before_any_network_call(capsys, resolve_repo, milestone):
    rc, gh = _run([*BASE, "--milestone", milestone], FakeGh())

    assert rc == 2
    assert gh.calls == []
    resolve_repo.assert_not_called()
    error = json.loads(capsys.readouterr().out)["Error"]
    assert (error["Message"], error["Type"]) == ("Milestone cannot be empty.", "InvalidParams")


def test_surrounding_whitespace_is_stripped_before_lookup(capsys):
    gh = FakeGh(extra_routes={MILESTONES: LIST_OK})

    rc, gh = _run([*BASE, "--milestone", " v0.7.0 "], gh)

    assert rc == 0
    edit = gh.milestone_edits()[0]
    assert edit[edit.index("--milestone") + 1] == "v0.7.0"
    assert json.loads(capsys.readouterr().out)["Data"]["milestone"] == "v0.7.0"
