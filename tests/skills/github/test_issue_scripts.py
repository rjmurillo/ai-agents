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

# Ensure the shared lib and script directories are importable.
_project_root = Path(__file__).resolve().parents[3]
_lib_dir = _project_root / ".claude" / "skills" / "github" / "lib"
_scripts_dir = _project_root / ".claude" / "skills" / "github" / "scripts"
for _p in (
    str(_lib_dir),
    str(_scripts_dir / "issue"),
    str(_scripts_dir / "milestone"),
    str(_scripts_dir / "reactions"),
    str(_scripts_dir / "utils"),
    str(_scripts_dir),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def make_proc(stdout="", stderr="", returncode=0):
    """Return a mock CompletedProcess."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


# ---------------------------------------------------------------------------
# get_issue_context
# ---------------------------------------------------------------------------

class TestGetIssueContext:
    """Tests for get_issue_context.get_issue_context."""

    def _import(self):
        import importlib

        import get_issue_context as mod
        importlib.reload(mod)
        return mod

    def test_happy_path(self):
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
        with patch("subprocess.run", return_value=proc):
            result = mod.get_issue_context("owner", "repo", 42)

        assert result["Success"] is True
        assert result["Number"] == 42
        assert result["Title"] == "Test Issue"
        assert result["State"] == "OPEN"
        assert result["Author"] == "alice"
        assert result["Labels"] == ["bug"]
        assert result["Milestone"] == "v1.0"
        assert result["Assignees"] == ["bob"]
        assert result["Owner"] == "owner"
        assert result["Repo"] == "repo"

    def test_no_milestone(self):
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
        with patch("subprocess.run", return_value=proc):
            result = mod.get_issue_context("o", "r", 1)
        assert result["Milestone"] is None

    def test_api_not_found_exits_2(self):
        mod = self._import()
        proc = make_proc(stderr="not found", returncode=1)
        with patch("subprocess.run", return_value=proc):
            with pytest.raises(SystemExit) as exc:
                mod.get_issue_context("o", "r", 99)
        assert exc.value.code == 2

    def test_api_other_error_exits_2(self):
        mod = self._import()
        proc = make_proc(stderr="connection refused", returncode=1)
        with patch("subprocess.run", return_value=proc):
            with pytest.raises(SystemExit) as exc:
                mod.get_issue_context("o", "r", 99)
        assert exc.value.code == 2

    def test_empty_json_exits_3(self):
        mod = self._import()
        proc = make_proc(stdout="{}", returncode=0)
        with patch("subprocess.run", return_value=proc):
            with pytest.raises(SystemExit) as exc:
                mod.get_issue_context("o", "r", 1)
        assert exc.value.code == 3


class TestGetIssueContextMain:
    """Tests for get_issue_context.main via monkeypatching."""

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["get_issue_context.py", "--help"]
            import get_issue_context as mod
            mod.main()
        assert exc.value.code == 0

    def test_main_happy_path(self, capsys):
        import get_issue_context as mod

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
                return_value={"owner": "o", "repo": "r"},
            ),
            patch("subprocess.run", return_value=proc),
        ):
            sys.argv = ["get_issue_context.py", "--issue", "7"]
            mod.main()

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["Success"] is True
        assert parsed["Number"] == 7


# ---------------------------------------------------------------------------
# new_issue
# ---------------------------------------------------------------------------

class TestNewIssue:
    """Tests for new_issue.new_issue."""

    def _import(self):
        import importlib

        import new_issue as mod
        importlib.reload(mod)
        return mod

    def test_happy_path(self):
        mod = self._import()
        proc = make_proc(stdout="https://github.com/o/r/issues/123")
        with patch("subprocess.run", return_value=proc):
            result = mod.new_issue("o", "r", "My Title", "body text", "bug")
        assert result["Success"] is True
        assert result["IssueNumber"] == 123
        assert result["Title"] == "My Title"

    def test_empty_body_and_labels_omitted(self):
        mod = self._import()
        proc = make_proc(stdout="https://github.com/o/r/issues/5")
        with patch("subprocess.run", return_value=proc) as mock_run:
            mod.new_issue("o", "r", "No Body", "", "")
        cmd = mock_run.call_args[0][0]
        assert "--body" not in cmd
        assert "--label" not in cmd

    def test_api_error_exits_3(self):
        mod = self._import()
        proc = make_proc(stderr="server error", returncode=1)
        with patch("subprocess.run", return_value=proc):
            with pytest.raises(SystemExit) as exc:
                mod.new_issue("o", "r", "title")
        assert exc.value.code == 3

    def test_unparseable_output_exits_3(self):
        mod = self._import()
        proc = make_proc(stdout="no url here", returncode=0)
        with patch("subprocess.run", return_value=proc):
            with pytest.raises(SystemExit) as exc:
                mod.new_issue("o", "r", "title")
        assert exc.value.code == 3

    def test_main_empty_title_exits_1(self, tmp_path):
        import importlib

        import new_issue as mod
        importlib.reload(mod)
        with (
            patch("github_core.api.assert_gh_authenticated"),
            patch(
                "github_core.api.resolve_repo_params",
                return_value={"owner": "o", "repo": "r"},
            ),
        ):
            sys.argv = ["new_issue.py", "--title", "   "]
            with pytest.raises(SystemExit) as exc:
                mod.main()
        assert exc.value.code == 1

    def test_main_body_file_not_found_exits_2(self, tmp_path):
        import importlib

        import new_issue as mod
        importlib.reload(mod)
        with (
            patch("github_core.api.assert_gh_authenticated"),
            patch(
                "github_core.api.resolve_repo_params",
                return_value={"owner": "o", "repo": "r"},
            ),
        ):
            sys.argv = [
                "new_issue.py", "--title", "T",
                "--body-file", str(tmp_path / "missing.txt"),
            ]
            with pytest.raises(SystemExit) as exc:
                mod.main()
        assert exc.value.code == 2

    def test_main_body_file_used(self, tmp_path):
        import importlib

        import new_issue as mod
        importlib.reload(mod)
        body_file = tmp_path / "body.txt"
        body_file.write_text("file body content")
        proc = make_proc(stdout="https://github.com/o/r/issues/10")
        with (
            patch("github_core.api.assert_gh_authenticated"),
            patch(
                "github_core.api.resolve_repo_params",
                return_value={"owner": "o", "repo": "r"},
            ),
            patch("subprocess.run", return_value=proc),
        ):
            sys.argv = [
                "new_issue.py", "--title", "Title",
                "--body-file", str(body_file),
            ]
            mod.main()

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["new_issue.py", "--help"]
            import new_issue as mod
            mod.main()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# post_issue_comment
# ---------------------------------------------------------------------------

class TestPostIssueComment:
    """Tests for post_issue_comment.post_issue_comment."""

    def _import(self):
        import importlib

        import post_issue_comment as mod
        importlib.reload(mod)
        return mod

    def _make_post_proc(self, comment_id=99, html_url="https://gh/c/99"):
        data = {"id": comment_id, "html_url": html_url}
        return make_proc(stdout=json.dumps(data))

    def test_happy_path_no_marker(self):
        mod = self._import()
        proc = self._make_post_proc()
        with patch("subprocess.run", return_value=proc):
            result = mod.post_issue_comment("o", "r", 1, "body text")
        assert result["Success"] is True
        assert result["CommentId"] == 99
        assert result["Skipped"] is False
        assert result["Marker"] is None

    def test_marker_already_exists_skips(self):
        mod = self._import()
        marker = "my-marker"
        marker_html = f"<!-- {marker} -->"
        comments = [{"id": 55, "body": f"{marker_html}\nold body"}]
        api_proc = make_proc(stdout=json.dumps(comments))
        with patch("post_issue_comment._run_gh", return_value=api_proc):
            result = mod.post_issue_comment("o", "r", 1, "new body", marker)
        assert result["Skipped"] is True
        assert result["CommentId"] == 55

    def test_marker_exists_update_if_exists(self):
        mod = self._import()
        marker = "my-marker"
        marker_html = f"<!-- {marker} -->"
        comments = [{"id": 55, "body": f"{marker_html}\nold body"}]
        api_proc = make_proc(stdout=json.dumps(comments))
        updated = {"id": 55, "html_url": "https://gh/c/55"}
        patch_proc = make_proc(stdout=json.dumps(updated))

        with (
            patch("post_issue_comment._run_gh", return_value=api_proc),
            patch("subprocess.run", return_value=patch_proc),
        ):
            result = mod.post_issue_comment(
                "o", "r", 1, "new body", marker, update_if_exists=True
            )
        assert result["Updated"] is True
        assert result["Skipped"] is False

    def test_marker_new_post(self):
        mod = self._import()
        marker = "unique-marker"
        api_proc = make_proc(stdout=json.dumps([]))
        post_proc = self._make_post_proc(comment_id=77)

        with (
            patch("post_issue_comment._run_gh", return_value=api_proc),
            patch("subprocess.run", return_value=post_proc),
        ):
            result = mod.post_issue_comment("o", "r", 1, "body", marker)
        assert result["Success"] is True
        assert result["Skipped"] is False
        assert result["Marker"] == marker

    def test_permission_error_exits_4(self):
        mod = self._import()
        err_proc = make_proc(stderr="HTTP 403 forbidden", returncode=1)
        api_proc = make_proc(stdout=json.dumps([]))
        with (
            patch("github_core.api._run_gh", return_value=api_proc),
            patch("subprocess.run", return_value=err_proc),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.post_issue_comment("o", "r", 1, "body")
        assert exc.value.code == 4

    def test_api_error_exits_3(self):
        mod = self._import()
        err_proc = make_proc(stderr="server error", returncode=1)
        api_proc = make_proc(stdout=json.dumps([]))
        with (
            patch("github_core.api._run_gh", return_value=api_proc),
            patch("subprocess.run", return_value=err_proc),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.post_issue_comment("o", "r", 1, "body")
        assert exc.value.code == 3

    def test_parse_error_returns_gracefully(self):
        mod = self._import()
        api_proc = make_proc(stdout=json.dumps([]))
        bad_json_proc = make_proc(stdout="not-json", returncode=0)
        with (
            patch("github_core.api._run_gh", return_value=api_proc),
            patch("subprocess.run", return_value=bad_json_proc),
        ):
            result = mod.post_issue_comment("o", "r", 1, "body")
        assert result["Success"] is True
        assert result.get("ParseError") is True

    def test_ensure_marker_in_body_prepends(self):
        mod = self._import()
        marker = "<!-- x -->"
        result = mod._ensure_marker_in_body("text", marker)
        assert result.startswith(marker)
        assert "text" in result

    def test_ensure_marker_in_body_noop_when_present(self):
        mod = self._import()
        marker = "<!-- x -->"
        body = f"{marker}\n\ntext"
        result = mod._ensure_marker_in_body(body, marker)
        assert result == body

    def test_main_empty_body_exits_1(self):
        import importlib

        import post_issue_comment as mod
        importlib.reload(mod)
        with (
            patch("github_core.api.assert_gh_authenticated"),
            patch(
                "github_core.api.resolve_repo_params",
                return_value={"owner": "o", "repo": "r"},
            ),
        ):
            sys.argv = ["post_issue_comment.py", "--issue", "1"]
            with pytest.raises(SystemExit) as exc:
                mod.main()
        assert exc.value.code == 1

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["post_issue_comment.py", "--help"]
            import post_issue_comment as mod
            mod.main()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# set_issue_assignee
# ---------------------------------------------------------------------------

class TestSetIssueAssignee:
    """Tests for set_issue_assignee.set_issue_assignee."""

    def _import(self):
        import importlib

        import set_issue_assignee as mod
        importlib.reload(mod)
        return mod

    def test_happy_path_single(self):
        mod = self._import()
        proc = make_proc(returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod.set_issue_assignee("o", "r", 1, ["alice"])
        assert result["Success"] is True
        assert result["Applied"] == ["alice"]
        assert result["Failed"] == []

    def test_multiple_assignees(self):
        mod = self._import()
        proc = make_proc(returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod.set_issue_assignee("o", "r", 1, ["alice", "bob"])
        assert result["TotalApplied"] == 2
        assert result["Success"] is True

    def test_partial_failure(self):
        mod = self._import()
        procs = [make_proc(returncode=0), make_proc(returncode=1)]
        with patch("subprocess.run", side_effect=procs):
            result = mod.set_issue_assignee("o", "r", 1, ["alice", "bob"])
        assert result["Success"] is False
        assert "alice" in result["Applied"]
        assert "bob" in result["Failed"]

    def test_empty_assignees_returns_empty(self):
        mod = self._import()
        result = mod.set_issue_assignee("o", "r", 1, [])
        assert result["Success"] is True
        assert result["TotalApplied"] == 0

    def test_main_exits_3_on_failure(self):
        import importlib

        import set_issue_assignee as mod
        importlib.reload(mod)
        proc = make_proc(returncode=1)
        with (
            patch("set_issue_assignee.assert_gh_authenticated"),
            patch(
                "set_issue_assignee.resolve_repo_params",
                return_value={"owner": "o", "repo": "r"},
            ),
            patch("subprocess.run", return_value=proc),
        ):
            sys.argv = ["set_issue_assignee.py", "--issue", "1", "--assignees", "bad"]
            with pytest.raises(SystemExit) as exc:
                mod.main()
        assert exc.value.code == 3

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["set_issue_assignee.py", "--help"]
            import set_issue_assignee as mod
            mod.main()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# set_issue_labels
# ---------------------------------------------------------------------------

class TestSetIssueLabels:
    """Tests for set_issue_labels.set_issue_labels."""

    def _import(self):
        import importlib

        import set_issue_labels as mod
        importlib.reload(mod)
        return mod

    def _run_gh_exists(self, *args, **kwargs):
        return make_proc(returncode=0, stdout='{"name":"existing"}')

    def _run_gh_missing(self, *args, **kwargs):
        return make_proc(returncode=1)

    def test_happy_path_label_exists(self):
        mod = self._import()
        with (
            patch("github_core.api._run_gh", side_effect=self._run_gh_exists),
            patch("subprocess.run", return_value=make_proc(returncode=0)),
        ):
            result = mod.set_issue_labels("o", "r", 1, ["bug"])
        assert result["Success"] is True
        assert "bug" in result["Applied"]

    def test_label_missing_auto_created(self):
        mod = self._import()
        # Stub procs used via side_effect below
        with (
            patch("github_core.api._run_gh", return_value=make_proc(returncode=1)),
            patch("subprocess.run", side_effect=[make_proc(returncode=0), make_proc(returncode=0)]),
        ):
            result = mod.set_issue_labels("o", "r", 1, ["new-label"])
        assert result["Success"] is True

    def test_label_missing_no_create(self):
        mod = self._import()
        with patch("github_core.api._run_gh", return_value=make_proc(returncode=1)):
            result = mod.set_issue_labels("o", "r", 1, ["missing"], create_missing=False)
        assert result["Applied"] == []
        assert result["Created"] == []

    def test_priority_label_added(self):
        mod = self._import()
        with (
            patch("github_core.api._run_gh", side_effect=self._run_gh_exists),
            patch("subprocess.run", return_value=make_proc(returncode=0)),
        ):
            result = mod.set_issue_labels("o", "r", 1, [], priority="P1")
        assert any("priority:P1" in l for l in result["Applied"])

    def test_no_labels_returns_empty(self):
        mod = self._import()
        result = mod.set_issue_labels("o", "r", 1, [])
        assert result["TotalApplied"] == 0
        assert result["Success"] is True

    def test_add_label_fails(self):
        mod = self._import()
        with (
            patch("github_core.api._run_gh", side_effect=self._run_gh_exists),
            patch("subprocess.run", return_value=make_proc(returncode=1)),
        ):
            result = mod.set_issue_labels("o", "r", 1, ["bug"])
        assert "bug" in result["Failed"]
        assert result["Success"] is False

    def test_main_exits_3_on_label_failure(self):
        import importlib

        import set_issue_labels as mod
        importlib.reload(mod)
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch(
                "set_issue_labels.resolve_repo_params",
                return_value={"owner": "o", "repo": "r"},
            ),
            patch("set_issue_labels._run_gh", return_value=make_proc(returncode=0)),
            patch("subprocess.run", return_value=make_proc(returncode=1)),
        ):
            sys.argv = ["set_issue_labels.py", "--issue", "1", "--labels", "bug"]
            with pytest.raises(SystemExit) as exc:
                mod.main()
        assert exc.value.code == 3

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["set_issue_labels.py", "--help"]
            import set_issue_labels as mod
            mod.main()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# set_issue_milestone
# ---------------------------------------------------------------------------

class TestSetIssueMilestone:
    """Tests for set_issue_milestone.set_issue_milestone."""

    def _import(self):
        import importlib

        import set_issue_milestone as mod
        importlib.reload(mod)
        return mod

    def _gh(self, stdout="", returncode=0):
        return make_proc(stdout=stdout, returncode=returncode)

    def test_assign_new_milestone(self):
        mod = self._import()
        with (
            patch("set_issue_milestone._run_gh", side_effect=[
                self._gh("null"),   # _get_current_milestone
                self._gh("v1.0\nv2.0"),  # _list_milestone_titles
            ]),
            patch("subprocess.run", return_value=self._gh()),
        ):
            result = mod.set_issue_milestone("o", "r", 1, milestone="v1.0")
        assert result["Success"] is True
        assert result["Action"] == "assigned"

    def test_already_same_milestone_no_change(self):
        mod = self._import()
        with patch("set_issue_milestone._run_gh", side_effect=[
            self._gh("v1.0"),     # current milestone
            self._gh("v1.0"),     # list titles
        ]):
            result = mod.set_issue_milestone("o", "r", 1, milestone="v1.0")
        assert result["Action"] == "no_change"

    def test_different_milestone_no_force_exits_5(self):
        mod = self._import()
        with patch("set_issue_milestone._run_gh", side_effect=[
            self._gh("old-ms"),   # current milestone
            self._gh("old-ms\nnew-ms"),  # list titles
        ]):
            with pytest.raises(SystemExit) as exc:
                mod.set_issue_milestone("o", "r", 1, milestone="new-ms")
        assert exc.value.code == 5

    def test_force_replaces_milestone(self):
        mod = self._import()
        with (
            patch("set_issue_milestone._run_gh", side_effect=[
                self._gh("old-ms"),
                self._gh("old-ms\nnew-ms"),
            ]),
            patch("subprocess.run", return_value=self._gh()),
        ):
            result = mod.set_issue_milestone("o", "r", 1, milestone="new-ms", force=True)
        assert result["Action"] == "replaced"

    def test_clear_with_existing(self):
        mod = self._import()
        with (
            patch("set_issue_milestone._run_gh", return_value=self._gh("old-ms")),
            patch("subprocess.run", return_value=self._gh()),
        ):
            result = mod.set_issue_milestone("o", "r", 1, clear=True)
        assert result["Action"] == "cleared"

    def test_clear_without_existing(self):
        mod = self._import()
        with patch("set_issue_milestone._run_gh", return_value=self._gh("null")):
            result = mod.set_issue_milestone("o", "r", 1, clear=True)
        assert result["Action"] == "no_change"

    def test_milestone_not_found_exits_2(self):
        mod = self._import()
        with patch("set_issue_milestone._run_gh", side_effect=[
            self._gh("null"),        # no current milestone
            self._gh("other-ms"),    # list has different milestone
        ]):
            with pytest.raises(SystemExit) as exc:
                mod.set_issue_milestone("o", "r", 1, milestone="missing-ms")
        assert exc.value.code == 2

    def test_main_no_milestone_no_clear_exits_1(self):
        import importlib

        import set_issue_milestone as mod
        importlib.reload(mod)
        with (
            patch("github_core.api.assert_gh_authenticated"),
            patch(
                "github_core.api.resolve_repo_params",
                return_value={"owner": "o", "repo": "r"},
            ),
        ):
            sys.argv = ["set_issue_milestone.py", "--issue", "1"]
            with pytest.raises(SystemExit) as exc:
                mod.main()
        assert exc.value.code == 1

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["set_issue_milestone.py", "--help"]
            import set_issue_milestone as mod
            mod.main()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# invoke_copilot_assignment
# ---------------------------------------------------------------------------

class TestInvokeCopilotAssignment:
    """Tests for invoke_copilot_assignment.invoke_copilot_assignment."""

    def _import(self):
        import importlib

        import invoke_copilot_assignment as mod
        importlib.reload(mod)
        return mod

    def _make_issue(self):
        return {
            "number": 10,
            "title": "Test",
            "body": "desc",
            "labels": [],
            "assignees": [],
        }

    def test_dry_run(self):
        mod = self._import()
        issue_proc = make_proc(stdout=json.dumps(self._make_issue()))
        comments_proc = make_proc(stdout=json.dumps([]))
        with (
            patch("invoke_copilot_assignment._run_gh", side_effect=[issue_proc, comments_proc]),
        ):
            result = mod.invoke_copilot_assignment("o", "r", 10, dry_run=True)
        assert result["Action"] == "DryRun"
        assert result["Success"] is True

    def test_prepare_context_only(self, tmp_path):
        mod = self._import()
        issue_proc = make_proc(stdout=json.dumps(self._make_issue()))
        comments_proc = make_proc(stdout=json.dumps([]))
        with (
            patch("invoke_copilot_assignment._run_gh", side_effect=[issue_proc, comments_proc]),
            patch("tempfile.gettempdir", return_value=str(tmp_path)),
        ):
            result = mod.invoke_copilot_assignment("o", "r", 10, prepare_context_only=True)
        assert result["Success"] is True
        assert "ContextFile" in result

    def test_issue_not_found_exits_2(self):
        mod = self._import()
        err_proc = make_proc(stdout="Not Found", returncode=1)
        with patch("invoke_copilot_assignment._run_gh", return_value=err_proc):
            with pytest.raises(SystemExit) as exc:
                mod.invoke_copilot_assignment("o", "r", 999)
        assert exc.value.code == 2

    def test_api_error_exits_3(self):
        mod = self._import()
        err_proc = make_proc(stderr="connection error", returncode=1)
        with patch("invoke_copilot_assignment._run_gh", return_value=err_proc):
            with pytest.raises(SystemExit) as exc:
                mod.invoke_copilot_assignment("o", "r", 1)
        assert exc.value.code == 3

    def test_skip_assignment(self):
        mod = self._import()
        issue_proc = make_proc(stdout=json.dumps(self._make_issue()))
        comments_proc = make_proc(stdout=json.dumps([]))
        with (
            patch("invoke_copilot_assignment._run_gh", side_effect=[issue_proc, comments_proc]),
        ):
            result = mod.invoke_copilot_assignment(
                "o", "r", 10, skip_assignment=True, dry_run=True
            )
        assert result["Action"] == "DryRun"

    def test_get_maintainer_guidance_extracts_bullets(self):
        mod = self._import()
        comments = [{
            "user": {"login": "rjmurillo"},
            "body": "Some text.\n- Do this important thing\n- Another requirement",
        }]
        guidance = mod.get_maintainer_guidance(comments, ["rjmurillo"])
        assert len(guidance) >= 1
        assert any("Do this important thing" in g for g in guidance)

    def test_get_maintainer_guidance_must_keywords(self):
        mod = self._import()
        comments = [{
            "user": {"login": "rjmurillo"},
            "body": "You MUST implement the feature. This SHOULD be done carefully.",
        }]
        guidance = mod.get_maintainer_guidance(comments, ["rjmurillo"])
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
            "related_issues": "Related Issues",
            "related_prs": "Related PRs",
        }
        plan = mod.get_coderabbit_plan(comments, config_patterns)
        assert plan is not None
        assert plan["Implementation"] is not None

    def test_get_ai_triage_info_extracts_priority(self):
        mod = self._import()
        marker = "<!-- AI-ISSUE-TRIAGE -->"
        comments = [{
            "user": {"login": "bot"},
            "body": f"{marker}\n| **Priority** | `P1` |\n| **Category** | `bug` |",
        }]
        triage = mod.get_ai_triage_info(comments, marker)
        assert triage is not None
        assert triage["Priority"] == "P1"

    def test_has_synthesizable_content_with_guidance(self):
        mod = self._import()
        assert mod.has_synthesizable_content(["some guidance"], None, None) is True

    def test_has_synthesizable_content_empty(self):
        mod = self._import()
        assert mod.has_synthesizable_content([], None, None) is False

    def test_build_synthesis_comment(self):
        mod = self._import()
        body = mod.build_synthesis_comment(
            "<!-- marker -->",
            ["Do X"],
            {"Implementation": "impl text", "RelatedIssues": ["#1"], "RelatedPRs": []},
            {"Priority": "P1", "Category": "bug"},
        )
        assert "@copilot" in body
        assert "Do X" in body
        assert "P1" in body

    def test_find_existing_synthesis(self):
        mod = self._import()
        comments = [{"id": 1, "body": "<!-- MARKER -->\ntext"}]
        result = mod.find_existing_synthesis(comments, "<!-- MARKER -->")
        assert result is not None
        assert result["id"] == 1

    def test_find_existing_synthesis_none(self):
        mod = self._import()
        result = mod.find_existing_synthesis([], "<!-- MARKER -->")
        assert result is None

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["invoke_copilot_assignment.py", "--help"]
            import invoke_copilot_assignment as mod
            mod.main()
        assert exc.value.code == 0
