"""Tests for the new_issue.py --milestone assignment after creation (issue #6033).

A failed assignment must keep the created issue number in the output, so a
caller repairs the milestone instead of re-creating the issue.
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
ARGS = ["--title", "Title", "--source", "human", "--milestone", "v0.7.0"]
LIST_OK = _make_proc(stdout="v0.6.0\nv0.7.0\n")


def test_check_create_assign_in_one_call(capsys, tmp_path, monkeypatch):
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))

    rc, gh = _run(ARGS, FakeGh(extra_routes={MILESTONES: LIST_OK}))

    assert rc == 0
    assert gh.verbs() == [MILESTONES, ("label", "create"), ("issue", "create"), ("issue", "edit")]
    assert "--paginate" in gh.find(*MILESTONES)
    edit = gh.milestone_edits()[0]
    assert edit[3] == "42"
    assert edit[edit.index("--repo") + 1] == "owner/repo"
    assert edit[edit.index("--milestone") + 1] == "v0.7.0"
    data = json.loads(capsys.readouterr().out)
    assert (data["Success"], data["Data"]["milestone"]) == (True, "v0.7.0")
    assert "milestone=v0.7.0\n" in out.read_text(encoding="utf-8")


def test_human_summary_names_milestone(capsys):
    with patch("subprocess.run", side_effect=FakeGh(extra_routes={MILESTONES: LIST_OK})):
        rc = main([*ARGS, "--output-format", "human"])

    assert rc == 0
    assert "[milestone v0.7.0]" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("label_edit", "code", "milestone_edits"),
    [(_make_proc(), 0, 1), (_make_proc(returncode=1, stderr="label boom"), 3, 0)],
    ids=["labels-then-milestone", "label-failure-skips-milestone"],
)
def test_labels_apply_before_milestone(label_edit, code, milestone_edits):
    gh = FakeGh(issue_edit=label_edit, extra_routes={MILESTONES: LIST_OK})

    rc, gh = _run([*ARGS, "--labels", "bug"], gh)

    assert rc == code
    edits = [c for c in gh.calls if c[1:3] == ["issue", "edit"]]
    assert "--add-label" in edits[0]
    assert len(gh.milestone_edits()) == milestone_edits


@pytest.mark.parametrize(
    ("edit_route", "code", "error_type", "message"),
    [
        (_make_proc(returncode=1, stderr="edit boom"), 3, "ApiError", "failed: edit boom"),
        (_make_proc(returncode=1, stdout="from stdout"), 3, "ApiError", "failed: from stdout"),
        (subprocess.TimeoutExpired(cmd="gh", timeout=30), 3, "Timeout", "timed out after"),
        (_make_proc(returncode=1, stderr="authentication required"), 4, "AuthError",
         "failed: authentication required"),
    ],
    ids=["edit-fails", "edit-fails-stdout-only", "edit-times-out", "edit-auth-fails"],
)
def test_assignment_failure_keeps_issue_number(capsys, edit_route, code, error_type, message):
    gh = FakeGh(issue_edit=edit_route, extra_routes={MILESTONES: LIST_OK})

    rc, _ = _run(ARGS, gh)

    assert rc == code
    data = json.loads(capsys.readouterr().out)
    assert data["Error"]["Type"] == error_type
    assert data["Error"]["Message"].startswith("Issue #42 created but milestone assignment")
    assert message in data["Error"]["Message"]
    assert data["Data"]["issue_number"] == 42
    assert data["Data"]["url"].endswith("/issues/42")
    assert data["Data"]["milestone"] == "v0.7.0"
