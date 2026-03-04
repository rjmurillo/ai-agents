"""Tests for GitHub issue skill scripts.

Covers:
- get_issue_context.py
- new_issue.py
- post_issue_comment.py
- set_issue_assignee.py
- set_issue_labels.py
- set_issue_milestone.py
- invoke_copilot_assignment.py
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from test_helpers import import_skill_script
from github_core.api import RepoInfo


def make_proc(stdout="", stderr="", returncode=0):
    """Return a mock CompletedProcess."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


def _extract_json(text: str) -> dict:
    """Extract the last JSON object from output that may contain text before it."""
    # Find the last '{' that starts a JSON object
    idx = text.rfind("{")
    if idx == -1:
        raise ValueError(f"No JSON found in output: {text!r}")
    return json.loads(text[idx:])


def _mock_repo():
    """Return a RepoInfo for test owner/repo."""
    return RepoInfo(owner="o", repo="r")


# ---------------------------------------------------------------------------
# get_issue_context
# ---------------------------------------------------------------------------

class TestGetIssueContext:
    """Tests for get_issue_context.main."""

    def _import(self):
        return import_skill_script("get_issue_context", "issue")

    def test_happy_path(self, capsys):
        mod = self._import()
        issue_data = {
            "number": 42,
            "title": "Test Issue",
            "body": "Some body",
            "state": "OPEN",
            "author": {"login": "alice"},
            "labels": [{"name": "bug"}],
            "milestone": {"title": "v1.0"},
            "assignees": [{"login": "bob"}],
            "createdAt": "2024-01-01",
            "updatedAt": "2024-01-02",
        }
        proc = make_proc(stdout=json.dumps(issue_data))
        with (
            patch("get_issue_context.assert_gh_authenticated"),
            patch("get_issue_context.resolve_repo_params", return_value=RepoInfo(owner="owner", repo="repo")),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main(["--issue", "42"])

        assert rc == 0
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["success"] is True
        assert result["number"] == 42
        assert result["title"] == "Test Issue"
        assert result["state"] == "OPEN"
        assert result["author"] == "alice"
        assert result["labels"] == ["bug"]
        assert result["milestone"] == "v1.0"
        assert result["assignees"] == ["bob"]
        assert result["owner"] == "owner"
        assert result["repo"] == "repo"

    def test_no_milestone(self, capsys):
        mod = self._import()
        issue_data = {
            "number": 1,
            "title": "No milestone",
            "body": "",
            "state": "OPEN",
            "author": {"login": "user"},
            "labels": [],
            "milestone": None,
            "assignees": [],
            "createdAt": "",
            "updatedAt": "",
        }
        proc = make_proc(stdout=json.dumps(issue_data))
        with (
            patch("get_issue_context.assert_gh_authenticated"),
            patch("get_issue_context.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main(["--issue", "1"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["milestone"] is None

    def test_api_not_found_exits_2(self):
        mod = self._import()
        proc = make_proc(stderr="not found", returncode=1)
        with (
            patch("get_issue_context.assert_gh_authenticated"),
            patch("get_issue_context.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "99"])
        assert exc.value.code == 2

    def test_api_other_error_exits_2(self):
        mod = self._import()
        proc = make_proc(stderr="connection refused", returncode=1)
        with (
            patch("get_issue_context.assert_gh_authenticated"),
            patch("get_issue_context.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "99"])
        assert exc.value.code == 2

    def test_empty_json_exits_3(self):
        mod = self._import()
        proc = make_proc(stdout="{}", returncode=0)
        with (
            patch("get_issue_context.assert_gh_authenticated"),
            patch("get_issue_context.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1"])
        assert exc.value.code == 3


class TestGetIssueContextMain:
    """Tests for get_issue_context.main via monkeypatching."""

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            mod = import_skill_script("get_issue_context", "issue")
            mod.main(["--help"])
        assert exc.value.code == 0

    def test_main_happy_path(self, capsys):
        mod = import_skill_script("get_issue_context", "issue")

        issue_data = {
            "number": 7,
            "title": "Main test",
            "body": "",
            "state": "OPEN",
            "author": {"login": "dev"},
            "labels": [{"name": "test"}],
            "milestone": None,
            "assignees": [],
            "createdAt": "2024-01-01",
            "updatedAt": "2024-01-01",
        }
        proc = make_proc(stdout=json.dumps(issue_data))

        with (
            patch("get_issue_context.assert_gh_authenticated"),
            patch(
                "get_issue_context.resolve_repo_params",
                return_value=_mock_repo(),
            ),
            patch("subprocess.run", return_value=proc),
        ):
            mod.main(["--issue", "7"])

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["success"] is True
        assert parsed["number"] == 7


# ---------------------------------------------------------------------------
# new_issue
# ---------------------------------------------------------------------------

class TestNewIssue:
    """Tests for new_issue.main."""

    def _import(self):
        return import_skill_script("new_issue", "issue")

    def test_happy_path(self, capsys):
        mod = self._import()
        proc = make_proc(stdout="https://github.com/o/r/issues/123")
        with (
            patch("new_issue.assert_gh_authenticated"),
            patch("new_issue.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main(["--title", "My Title", "--body", "body text", "--labels", "bug"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["success"] is True
        assert result["issue_number"] == 123
        assert result["title"] == "My Title"

    def test_empty_body_and_labels_omitted(self):
        mod = self._import()
        proc = make_proc(stdout="https://github.com/o/r/issues/5")
        with (
            patch("new_issue.assert_gh_authenticated"),
            patch("new_issue.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc) as mock_run,
        ):
            mod.main(["--title", "No Body"])
        cmd = mock_run.call_args[0][0]
        assert "--body" not in cmd
        assert "--label" not in cmd

    def test_api_error_exits_3(self):
        mod = self._import()
        proc = make_proc(stderr="server error", returncode=1)
        with (
            patch("new_issue.assert_gh_authenticated"),
            patch("new_issue.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--title", "title"])
        assert exc.value.code == 3

    def test_unparseable_output_exits_3(self):
        mod = self._import()
        proc = make_proc(stdout="no url here", returncode=0)
        with (
            patch("new_issue.assert_gh_authenticated"),
            patch("new_issue.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--title", "title"])
        assert exc.value.code == 3

    def test_main_empty_title_exits_2(self):
        mod = self._import()
        with (
            patch("new_issue.assert_gh_authenticated"),
            patch("new_issue.resolve_repo_params", return_value=_mock_repo()),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--title", "   "])
        assert exc.value.code == 2

    def test_main_body_file_not_found_exits_2(self, tmp_path):
        mod = self._import()
        with (
            patch("new_issue.assert_gh_authenticated"),
            patch("new_issue.resolve_repo_params", return_value=_mock_repo()),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main([
                    "--title", "T",
                    "--body-file", str(tmp_path / "missing.txt"),
                ])
        assert exc.value.code == 2

    def test_main_body_file_used(self, tmp_path, capsys):
        mod = self._import()
        body_file = tmp_path / "body.txt"
        body_file.write_text("file body content")
        proc = make_proc(stdout="https://github.com/o/r/issues/10")
        with (
            patch("new_issue.assert_gh_authenticated"),
            patch("new_issue.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main([
                "--title", "Title",
                "--body-file", str(body_file),
            ])
        assert rc == 0

    def test_help_does_not_crash(self):
        mod = import_skill_script("new_issue", "issue")
        with pytest.raises(SystemExit) as exc:
            mod.main(["--help"])
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# post_issue_comment
# ---------------------------------------------------------------------------

class TestPostIssueComment:
    """Tests for post_issue_comment.main."""

    def _import(self):
        return import_skill_script("post_issue_comment", "issue")

    def _make_post_proc(self, comment_id=99, html_url="https://gh/c/99"):
        data = {"id": comment_id, "html_url": html_url}
        return make_proc(stdout=json.dumps(data))

    def test_happy_path_no_marker(self, capsys):
        mod = self._import()
        proc = self._make_post_proc()
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main(["--issue", "1", "--body", "body text"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["success"] is True
        assert result["comment_id"] == 99
        assert result["skipped"] is False

    def test_marker_already_exists_skips(self, capsys):
        mod = self._import()
        marker = "my-marker"
        marker_html = f"<!-- {marker} -->"
        comments = [{"id": 55, "body": f"{marker_html}\nold body"}]
        # First call: fetch comments; Second call would be post (not reached)
        comments_proc = make_proc(stdout=json.dumps(comments))
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=comments_proc),
        ):
            rc = mod.main(["--issue", "1", "--body", "new body", "--marker", marker])
        assert rc == 0
        result = _extract_json(capsys.readouterr().out)
        assert result["skipped"] is True

    def test_marker_exists_update_if_exists(self, capsys):
        mod = self._import()
        marker = "my-marker"
        marker_html = f"<!-- {marker} -->"
        comments = [{"id": 55, "body": f"{marker_html}\nold body"}]
        comments_proc = make_proc(stdout=json.dumps(comments))
        updated = {"id": 55, "html_url": "https://gh/c/55", "updated_at": "2024-01-01"}

        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=comments_proc),
            patch("post_issue_comment.update_issue_comment", return_value=updated),
        ):
            rc = mod.main([
                "--issue", "1", "--body", "new body",
                "--marker", marker, "--update-if-exists",
            ])
        assert rc == 0
        result = _extract_json(capsys.readouterr().out)
        assert result["updated"] is True
        assert result["success"] is True

    def test_marker_new_post(self, capsys):
        mod = self._import()
        marker = "unique-marker"
        comments_proc = make_proc(stdout=json.dumps([]))
        post_proc = self._make_post_proc(comment_id=77)

        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[comments_proc, post_proc]),
        ):
            rc = mod.main(["--issue", "1", "--body", "body", "--marker", marker])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["success"] is True
        assert result["skipped"] is False

    def test_permission_error_exits_4(self):
        mod = self._import()
        err_proc = make_proc(stderr="HTTP 403 forbidden", returncode=1)
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=err_proc),
            patch("post_issue_comment._save_failed_comment_artifact", return_value=None),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--body", "body"])
        assert exc.value.code == 4

    def test_api_error_exits_3(self):
        mod = self._import()
        err_proc = make_proc(stderr="server error", returncode=1)
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=err_proc),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--body", "body"])
        assert exc.value.code == 3

    def test_parse_error_returns_gracefully(self, capsys):
        mod = self._import()
        bad_json_proc = make_proc(stdout="not-json", returncode=0)
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=bad_json_proc),
        ):
            rc = mod.main(["--issue", "1", "--body", "body"])
        assert rc == 0

    def test_prepend_marker_prepends(self):
        mod = self._import()
        marker = "<!-- x -->"
        result = mod._prepend_marker("text", marker)
        assert result.startswith(marker)
        assert "text" in result

    def test_prepend_marker_noop_when_present(self):
        mod = self._import()
        marker = "<!-- x -->"
        body = f"{marker}\n\ntext"
        result = mod._prepend_marker(body, marker)
        assert result == body

    def test_main_empty_body_exits_2(self):
        mod = self._import()
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1"])
        assert exc.value.code == 2

    def test_help_does_not_crash(self):
        mod = import_skill_script("post_issue_comment", "issue")
        with pytest.raises(SystemExit) as exc:
            mod.main(["--help"])
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# set_issue_assignee
# ---------------------------------------------------------------------------

class TestSetIssueAssignee:
    """Tests for set_issue_assignee.main."""

    def _import(self):
        return import_skill_script("set_issue_assignee", "issue")

    def test_happy_path_single(self, capsys):
        mod = self._import()
        proc = make_proc(returncode=0)
        with (
            patch("set_issue_assignee.assert_gh_authenticated"),
            patch("set_issue_assignee.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main(["--issue", "1", "--assignees", "alice"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["success"] is True
        assert result["applied"] == ["alice"]
        assert result["failed"] == []

    def test_multiple_assignees(self, capsys):
        mod = self._import()
        proc = make_proc(returncode=0)
        with (
            patch("set_issue_assignee.assert_gh_authenticated"),
            patch("set_issue_assignee.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main(["--issue", "1", "--assignees", "alice", "bob"])
        result = json.loads(capsys.readouterr().out)
        assert result["total_applied"] == 2
        assert result["success"] is True

    def test_partial_failure(self, capsys):
        mod = self._import()
        procs = [make_proc(returncode=0), make_proc(returncode=1)]
        with (
            patch("set_issue_assignee.assert_gh_authenticated"),
            patch("set_issue_assignee.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=procs),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--assignees", "alice", "bob"])
        assert exc.value.code == 3

    def test_main_exits_3_on_failure(self):
        mod = self._import()
        proc = make_proc(returncode=1)
        with (
            patch("set_issue_assignee.assert_gh_authenticated"),
            patch("set_issue_assignee.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--assignees", "bad"])
        assert exc.value.code == 3

    def test_help_does_not_crash(self):
        mod = import_skill_script("set_issue_assignee", "issue")
        with pytest.raises(SystemExit) as exc:
            mod.main(["--help"])
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# set_issue_labels
# ---------------------------------------------------------------------------

class TestSetIssueLabels:
    """Tests for set_issue_labels.main."""

    def _import(self):
        return import_skill_script("set_issue_labels", "issue")

    def test_happy_path_label_exists(self, capsys):
        mod = self._import()
        # _label_exists returns True, _apply_label returns True
        label_check_proc = make_proc(returncode=0, stdout='{"name":"bug"}')
        apply_proc = make_proc(returncode=0)
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[label_check_proc, apply_proc]),
        ):
            rc = mod.main(["--issue", "1", "--labels", "bug"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["success"] is True
        assert "bug" in result["applied"]

    def test_label_missing_auto_created(self, capsys):
        mod = self._import()
        # _label_exists -> fail, _create_label -> success, _apply_label -> success
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_proc(returncode=1),   # _label_exists fails
                make_proc(returncode=0),   # _create_label succeeds
                make_proc(returncode=0),   # _apply_label succeeds
            ]),
        ):
            rc = mod.main(["--issue", "1", "--labels", "new-label"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["success"] is True

    def test_label_missing_no_create(self, capsys):
        mod = self._import()
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_proc(returncode=1)),
        ):
            rc = mod.main(["--issue", "1", "--labels", "missing", "--no-create-missing"])
        # No labels applied, but no failure either since it just skips
        assert rc == 0

    def test_priority_label_added(self, capsys):
        mod = self._import()
        # _label_exists -> success, _apply_label -> success
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_proc(returncode=0),   # _label_exists
                make_proc(returncode=0),   # _apply_label
            ]),
        ):
            rc = mod.main(["--issue", "1", "--priority", "P1"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert any("priority:P1" in label for label in result["applied"])

    def test_no_labels_prints_message(self, capsys):
        mod = self._import()
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
        ):
            rc = mod.main(["--issue", "1"])
        assert rc == 0

    def test_add_label_fails(self):
        mod = self._import()
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_proc(returncode=0),   # _label_exists
                make_proc(returncode=1),   # _apply_label fails
            ]),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--labels", "bug"])
        assert exc.value.code == 3

    def test_main_exits_3_on_label_failure(self):
        mod = self._import()
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_proc(returncode=0),   # _label_exists
                make_proc(returncode=1),   # _apply_label fails
            ]),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--labels", "bug"])
        assert exc.value.code == 3

    def test_help_does_not_crash(self):
        mod = import_skill_script("set_issue_labels", "issue")
        with pytest.raises(SystemExit) as exc:
            mod.main(["--help"])
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# set_issue_milestone
# ---------------------------------------------------------------------------

class TestSetIssueMilestone:
    """Tests for set_issue_milestone.main."""

    def _import(self):
        return import_skill_script("set_issue_milestone", "issue")

    def test_assign_new_milestone(self, capsys):
        mod = self._import()
        with (
            patch("set_issue_milestone.assert_gh_authenticated"),
            patch("set_issue_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_proc(stdout="null"),                 # _get_current_milestone
                make_proc(stdout="v1.0\nv2.0"),           # _get_milestone_titles
                make_proc(returncode=0),                   # gh issue edit
            ]),
        ):
            rc = mod.main(["--issue", "1", "--milestone", "v1.0"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["success"] is True
        assert result["action"] == "assigned"

    def test_already_same_milestone_no_change(self, capsys):
        mod = self._import()
        with (
            patch("set_issue_milestone.assert_gh_authenticated"),
            patch("set_issue_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_proc(stdout="v1.0"),     # current milestone
                make_proc(stdout="v1.0"),     # list titles
            ]),
        ):
            rc = mod.main(["--issue", "1", "--milestone", "v1.0"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["action"] == "no_change"

    def test_different_milestone_no_force_exits_5(self):
        mod = self._import()
        with (
            patch("set_issue_milestone.assert_gh_authenticated"),
            patch("set_issue_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_proc(stdout="old-ms"),            # current milestone
                make_proc(stdout="old-ms\nnew-ms"),    # list titles
            ]),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--milestone", "new-ms"])
        assert exc.value.code == 5

    def test_force_replaces_milestone(self, capsys):
        mod = self._import()
        with (
            patch("set_issue_milestone.assert_gh_authenticated"),
            patch("set_issue_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_proc(stdout="old-ms"),
                make_proc(stdout="old-ms\nnew-ms"),
                make_proc(returncode=0),               # gh issue edit
            ]),
        ):
            rc = mod.main(["--issue", "1", "--milestone", "new-ms", "--force"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["action"] == "replaced"

    def test_clear_with_existing(self, capsys):
        mod = self._import()
        with (
            patch("set_issue_milestone.assert_gh_authenticated"),
            patch("set_issue_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_proc(stdout="old-ms"),   # _get_current_milestone
                make_proc(returncode=0),       # PATCH to clear
            ]),
        ):
            rc = mod.main(["--issue", "1", "--clear"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["action"] == "cleared"

    def test_clear_without_existing(self, capsys):
        mod = self._import()
        with (
            patch("set_issue_milestone.assert_gh_authenticated"),
            patch("set_issue_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_proc(stdout="null")),
        ):
            rc = mod.main(["--issue", "1", "--clear"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["action"] == "no_change"

    def test_milestone_not_found_exits_2(self):
        mod = self._import()
        with (
            patch("set_issue_milestone.assert_gh_authenticated"),
            patch("set_issue_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_proc(stdout="null"),         # no current milestone
                make_proc(stdout="other-ms"),     # list has different milestone
            ]),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--milestone", "missing-ms"])
        assert exc.value.code == 2

    def test_main_no_milestone_no_clear_exits_2(self):
        mod = self._import()
        with (
            patch("set_issue_milestone.assert_gh_authenticated"),
            patch("set_issue_milestone.resolve_repo_params", return_value=_mock_repo()),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1"])
        assert exc.value.code == 2

    def test_help_does_not_crash(self):
        mod = import_skill_script("set_issue_milestone", "issue")
        with pytest.raises(SystemExit) as exc:
            mod.main(["--help"])
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# invoke_copilot_assignment
# ---------------------------------------------------------------------------

class TestInvokeCopilotAssignment:
    """Tests for invoke_copilot_assignment helper functions and main."""

    def _import(self):
        return import_skill_script("invoke_copilot_assignment", "issue")

    def test_get_maintainer_guidance_extracts_bullets(self):
        mod = self._import()
        comments = [{
            "user": {"login": "rjmurillo"},
            "body": "Some text.\n- Do this important thing\n- Another requirement",
        }]
        guidance = mod._get_maintainer_guidance(comments, ["rjmurillo"])
        assert len(guidance) >= 1
        assert any("Do this important thing" in g for g in guidance)

    def test_get_maintainer_guidance_must_keywords(self):
        mod = self._import()
        comments = [{
            "user": {"login": "rjmurillo"},
            "body": "You MUST implement the feature. This SHOULD be done carefully.",
        }]
        guidance = mod._get_maintainer_guidance(comments, ["rjmurillo"])
        assert any("MUST" in g for g in guidance)

    def test_get_coderabbit_plan_extracts_impl(self):
        mod = self._import()
        comments = [{
            "user": {"login": "coderabbitai[bot]"},
            "body": "## Implementation\nDo step 1\nDo step 2\n## Another section",
        }]
        config_patterns = {
            "username": "coderabbitai[bot]",
            "implementation_plan": "## Implementation",
            "related_issues": "Similar Issues",
            "related_prs": "Related PRs",
        }
        plan = mod._get_coderabbit_plan(comments, config_patterns)
        assert plan is not None
        assert plan["implementation"] is not None

    def test_get_ai_triage_info_extracts_priority(self):
        mod = self._import()
        marker = "<!-- AI-ISSUE-TRIAGE -->"
        comments = [{
            "user": {"login": "bot"},
            "body": f"{marker}\n| **Priority** | `P1` |\n| **Category** | `bug` |",
        }]
        triage = mod._get_ai_triage_info(comments, marker)
        assert triage is not None
        assert triage["priority"] == "P1"

    def test_has_synthesizable_content_with_guidance(self):
        mod = self._import()
        assert mod._has_synthesizable_content(["some guidance"], None, None) is True

    def test_has_synthesizable_content_empty(self):
        mod = self._import()
        assert mod._has_synthesizable_content([], None, None) is False

    def test_build_synthesis_comment(self):
        mod = self._import()
        body = mod._build_synthesis_comment(
            "<!-- marker -->",
            ["Do X"],
            {"implementation": "impl text", "related_issues": ["#1"], "related_prs": []},
            {"priority": "P1", "category": "bug"},
        )
        assert "@copilot" in body
        assert "Do X" in body
        assert "P1" in body

    def test_find_existing_synthesis(self):
        mod = self._import()
        comments = [{"id": 1, "body": "<!-- MARKER -->\ntext"}]
        result = mod._find_existing_synthesis(comments, "<!-- MARKER -->")
        assert result is not None
        assert result["id"] == 1

    def test_find_existing_synthesis_none(self):
        mod = self._import()
        result = mod._find_existing_synthesis([], "<!-- MARKER -->")
        assert result is None

    def test_help_does_not_crash(self):
        mod = import_skill_script("invoke_copilot_assignment", "issue")
        with pytest.raises(SystemExit) as exc:
            mod.main(["--help"])
        assert exc.value.code == 0
