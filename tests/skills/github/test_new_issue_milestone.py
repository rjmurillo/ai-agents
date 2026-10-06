"""Tests for new_issue.py --milestone (issue #6033)."""

import json
import subprocess
from unittest.mock import patch

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


def _gh(milestones=LIST_OK, **kwargs) -> FakeGh:
    return FakeGh(extra_routes={MILESTONES: milestones}, **kwargs)


def _milestone_edits(gh: FakeGh) -> list[list[str]]:
    return [c for c in gh.calls if c[1:3] == ["issue", "edit"] and "--milestone" in c]


def _api_calls(gh: FakeGh) -> list[list[str]]:
    return [c for c in gh.calls if c[1] == "api"]


def _envelope(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _assert_issue_number_reported(data: dict) -> None:
    assert data["Data"]["issue_number"] == 42
    assert data["Data"]["milestone"] == "v0.7.0"
    assert data["Error"]["Message"].startswith("Issue #42 created but")


class TestMilestoneAbsent:
    def test_no_milestone_calls_and_null_in_data(self, capsys):
        gh = FakeGh()
        rc, gh = _run(BASE, gh)
        assert rc == 0
        assert _api_calls(gh) == []
        assert _milestone_edits(gh) == []
        assert _envelope(capsys)["Data"]["milestone"] is None

    def test_github_output_omits_milestone(self, tmp_path, monkeypatch):
        out = tmp_path / "gh_output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        rc, _ = _run(BASE)
        assert rc == 0
        assert "milestone=" not in out.read_text(encoding="utf-8")


class TestMilestonePresent:
    def test_assigns_existing_milestone(self, capsys):
        rc, gh = _run([*BASE, "--milestone", "v0.7.0"], _gh())
        assert rc == 0
        edits = _milestone_edits(gh)
        assert len(edits) == 1
        assert edits[0][edits[0].index("--milestone") + 1] == "v0.7.0"
        assert edits[0][edits[0].index("--repo") + 1] == "owner/repo"
        assert edits[0][3] == "42"
        data = _envelope(capsys)
        assert data["Success"] is True
        assert data["Data"]["milestone"] == "v0.7.0"

    def test_github_output_carries_milestone(self, tmp_path, monkeypatch):
        out = tmp_path / "gh_output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        rc, _ = _run([*BASE, "--milestone", "v0.7.0"], _gh())
        assert rc == 0
        assert "milestone=v0.7.0\n" in out.read_text(encoding="utf-8")

    def test_labels_and_milestone_both_applied(self):
        rc, gh = _run([*BASE, "--labels", "bug", "--milestone", "v0.7.0"], _gh())
        assert rc == 0
        label_edits = [c for c in gh.calls if "--add-label" in c]
        assert len(label_edits) == 1
        assert len(_milestone_edits(gh)) == 1
        assert gh.calls.index(label_edits[0]) < gh.calls.index(_milestone_edits(gh)[0])

    def test_label_failure_returns_before_milestone(self):
        gh = _gh(issue_edit=_make_proc(returncode=1, stderr="label boom"))
        rc, gh = _run([*BASE, "--labels", "bug", "--milestone", "v0.7.0"], gh)
        assert rc == 3
        assert _api_calls(gh) == []
        assert _milestone_edits(gh) == []

    def test_human_output_prints_summary_with_milestone(self, capsys):
        gh = _gh()
        with patch("subprocess.run", side_effect=gh):
            rc = main([*BASE, "--milestone", "v0.7.0", "--output-format", "human"])
        assert rc == 0
        assert "[milestone v0.7.0]" in capsys.readouterr().out


class TestMilestoneFailures:
    def test_missing_milestone_exits_2_with_issue_number(self, capsys):
        rc, gh = _run([*BASE, "--milestone", "v9.9.9"], _gh())
        assert rc == 2
        assert _milestone_edits(gh) == []
        data = _envelope(capsys)
        assert data["Success"] is False
        assert data["Error"]["Type"] == "NotFound"
        assert data["Data"]["issue_number"] == 42
        assert data["Data"]["url"].endswith("/issues/42")
        assert data["Data"]["milestone"] == "v9.9.9"
        assert data["Error"]["Message"] == (
            "Issue #42 created but milestone 'v9.9.9' does not exist in owner/repo."
        )

    def test_missing_milestone_human_output_prints_issue_number(self, capsys):
        with patch("subprocess.run", side_effect=_gh()):
            rc = main([*BASE, "--milestone", "v9.9.9", "--output-format", "human"])
        assert rc == 2
        captured = capsys.readouterr()
        assert "Issue #42 created" in captured.out + captured.err

    def test_list_query_failure_exits_3_api_error(self, capsys):
        gh = _gh(milestones=_make_proc(returncode=1, stderr="boom"))
        rc, gh = _run([*BASE, "--milestone", "v0.7.0"], gh)
        assert rc == 3
        assert _milestone_edits(gh) == []
        data = _envelope(capsys)
        assert data["Error"]["Type"] == "ApiError"
        _assert_issue_number_reported(data)

    def test_list_query_timeout_exits_3_timeout(self, capsys):
        gh = _gh(milestones=subprocess.TimeoutExpired(cmd="gh", timeout=30))
        rc, gh = _run([*BASE, "--milestone", "v0.7.0"], gh)
        assert rc == 3
        assert _milestone_edits(gh) == []
        data = _envelope(capsys)
        assert data["Error"]["Type"] == "Timeout"
        _assert_issue_number_reported(data)

    def test_edit_failure_exits_3_api_error(self, capsys):
        gh = _gh(issue_edit=_make_proc(returncode=1, stderr="edit boom"))
        rc, _ = _run([*BASE, "--milestone", "v0.7.0"], gh)
        assert rc == 3
        data = _envelope(capsys)
        assert data["Error"]["Type"] == "ApiError"
        _assert_issue_number_reported(data)
        assert "milestone assignment failed: edit boom" in data["Error"]["Message"]

    def test_edit_failure_falls_back_to_stdout(self, capsys):
        gh = _gh(issue_edit=_make_proc(returncode=1, stdout="from stdout"))
        rc, _ = _run([*BASE, "--milestone", "v0.7.0"], gh)
        assert rc == 3
        assert "from stdout" in _envelope(capsys)["Error"]["Message"]

    def test_edit_timeout_exits_3_timeout(self, capsys):
        gh = _gh(issue_edit=subprocess.TimeoutExpired(cmd="gh", timeout=30))
        rc, _ = _run([*BASE, "--milestone", "v0.7.0"], gh)
        assert rc == 3
        data = _envelope(capsys)
        assert data["Error"]["Type"] == "Timeout"
        _assert_issue_number_reported(data)


class TestMilestoneValidation:
    def test_blank_milestone_exits_2_before_any_network_call(self, capsys, resolve_repo):
        gh = FakeGh()
        rc, gh = _run([*BASE, "--milestone", "  "], gh)
        assert rc == 2
        assert gh.calls == []
        resolve_repo.assert_not_called()
        data = _envelope(capsys)
        assert data["Error"]["Message"] == "Milestone cannot be empty."
        assert data["Error"]["Type"] == "InvalidParams"

    def test_empty_string_milestone_exits_2(self):
        rc, gh = _run([*BASE, "--milestone", ""])
        assert rc == 2
        assert gh.calls == []

