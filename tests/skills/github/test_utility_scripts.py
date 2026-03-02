"""Tests for GitHub utility skill scripts.

Covers:
- add_comment_reaction.py
- extract_github_context.py
- test_workflow_locally.py
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure importability.
_project_root = Path(__file__).resolve().parents[3]
_lib_dir = _project_root / ".claude" / "skills" / "github" / "lib"
_scripts_dir = _project_root / ".claude" / "skills" / "github" / "scripts"
for _p in (
    str(_lib_dir),
    str(_scripts_dir / "reactions"),
    str(_scripts_dir / "utils"),
    str(_scripts_dir),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def make_proc(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


# ---------------------------------------------------------------------------
# add_comment_reaction
# ---------------------------------------------------------------------------

class TestAddCommentReaction:
    """Tests for add_comment_reaction.add_comment_reaction."""

    def _import(self):
        import importlib

        import add_comment_reaction as mod
        importlib.reload(mod)
        return mod

    def test_happy_path_single_review_comment(self):
        mod = self._import()
        proc = make_proc(returncode=0, stdout='{"id":1}')
        with patch("add_comment_reaction._run_gh", return_value=proc):
            result = mod.add_comment_reaction("o", "r", [42], "review", "eyes")
        assert result["Succeeded"] == 1
        assert result["Failed"] == 0
        assert result["Results"][0]["Success"] is True
        assert result["Results"][0]["CommentId"] == 42

    def test_happy_path_issue_comment(self):
        mod = self._import()
        proc = make_proc(returncode=0)
        with patch("add_comment_reaction._run_gh", return_value=proc):
            result = mod.add_comment_reaction("o", "r", [10], "issue", "+1")
        assert result["CommentType"] == "issue"

    def test_batch_all_succeed(self):
        mod = self._import()
        proc = make_proc(returncode=0)
        with patch("add_comment_reaction._run_gh", return_value=proc):
            result = mod.add_comment_reaction("o", "r", [1, 2, 3], "review", "heart")
        assert result["TotalCount"] == 3
        assert result["Succeeded"] == 3
        assert result["Failed"] == 0

    def test_already_reacted_counts_as_success(self):
        mod = self._import()
        proc = make_proc(returncode=1, stdout="already reacted")
        with patch("add_comment_reaction._run_gh", return_value=proc):
            result = mod.add_comment_reaction("o", "r", [5], "review", "rocket")
        assert result["Succeeded"] == 1

    def test_api_failure_counted(self):
        mod = self._import()
        proc = make_proc(returncode=1, stderr="server error")
        with patch("add_comment_reaction._run_gh", return_value=proc):
            result = mod.add_comment_reaction("o", "r", [9], "review", "eyes")
        assert result["Failed"] == 1
        assert result["Results"][0]["Success"] is False

    def test_partial_batch_failure(self):
        mod = self._import()
        procs = [make_proc(returncode=0), make_proc(returncode=1, stderr="err")]
        with patch("add_comment_reaction._run_gh", side_effect=procs):
            result = mod.add_comment_reaction("o", "r", [1, 2], "review", "eyes")
        assert result["Succeeded"] == 1
        assert result["Failed"] == 1

    def test_main_exits_3_on_failure(self):
        import importlib

        import add_comment_reaction as mod
        importlib.reload(mod)
        proc = make_proc(returncode=1, stderr="error")
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch(
                "add_comment_reaction.resolve_repo_params",
                return_value={"owner": "o", "repo": "r"},
            ),
            patch("add_comment_reaction._run_gh", return_value=proc),
        ):
            sys.argv = [
                "add_comment_reaction.py",
                "--comment-id", "1",
                "--reaction", "eyes",
            ]
            with pytest.raises(SystemExit) as exc:
                mod.main()
        assert exc.value.code == 3

    def test_main_success(self, capsys):
        import importlib

        import add_comment_reaction as mod
        importlib.reload(mod)
        proc = make_proc(returncode=0)
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch(
                "add_comment_reaction.resolve_repo_params",
                return_value={"owner": "o", "repo": "r"},
            ),
            patch("add_comment_reaction._run_gh", return_value=proc),
        ):
            sys.argv = [
                "add_comment_reaction.py",
                "--comment-id", "5",
                "--reaction", "+1",
            ]
            mod.main()
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["Succeeded"] == 1

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["add_comment_reaction.py", "--help"]
            import add_comment_reaction as mod
            mod.main()
        assert exc.value.code == 0

    def test_review_endpoint_used_for_review_type(self):
        mod = self._import()
        captured_args = []

        def fake_run_gh(*args, **kwargs):
            captured_args.extend(args)
            return make_proc(returncode=0)

        with patch("add_comment_reaction._run_gh", side_effect=fake_run_gh):
            mod.add_comment_reaction("owner", "repo", [100], "review", "eyes")

        endpoint = next(a for a in captured_args if "pulls" in str(a))
        assert "pulls/comments" in endpoint

    def test_issue_endpoint_used_for_issue_type(self):
        mod = self._import()
        captured_args = []

        def fake_run_gh(*args, **kwargs):
            captured_args.extend(args)
            return make_proc(returncode=0)

        with patch("add_comment_reaction._run_gh", side_effect=fake_run_gh):
            mod.add_comment_reaction("owner", "repo", [200], "issue", "eyes")

        endpoint = next(a for a in captured_args if "issues/comments" in str(a))
        assert "issues/comments" in endpoint


# ---------------------------------------------------------------------------
# extract_github_context
# ---------------------------------------------------------------------------

class TestExtractGithubContext:
    """Tests for extract_github_context.extract_github_context."""

    def _import(self):
        import importlib

        import extract_github_context as mod
        importlib.reload(mod)
        return mod

    def test_extracts_pr_url(self):
        mod = self._import()
        text = "See github.com/owner/repo/pull/42 for details"
        result = mod.extract_github_context(text)
        assert 42 in result["PRNumbers"]
        assert result["Owner"] == "owner"
        assert result["Repo"] == "repo"

    def test_extracts_issue_url(self):
        mod = self._import()
        text = "See github.com/myorg/myrepo/issues/99"
        result = mod.extract_github_context(text)
        assert 99 in result["IssueNumbers"]

    def test_extracts_pr_keyword(self):
        mod = self._import()
        result = mod.extract_github_context("fix for PR #123 merged")
        assert 123 in result["PRNumbers"]

    def test_extracts_pr_keyword_no_hash(self):
        mod = self._import()
        result = mod.extract_github_context("please review PR 456")
        assert 456 in result["PRNumbers"]

    def test_extracts_pull_request_keyword(self):
        mod = self._import()
        result = mod.extract_github_context("see pull request #789 for details")
        assert 789 in result["PRNumbers"]

    def test_extracts_issue_keyword(self):
        mod = self._import()
        result = mod.extract_github_context("fixes issue #55")
        assert 55 in result["IssueNumbers"]

    def test_extracts_standalone_hash(self):
        mod = self._import()
        result = mod.extract_github_context("related to #11 and the fix")
        assert 11 in result["PRNumbers"]

    def test_no_duplicates(self):
        mod = self._import()
        text = "PR #5 and github.com/o/r/pull/5"
        result = mod.extract_github_context(text)
        assert result["PRNumbers"].count(5) == 1

    def test_require_pr_exits_1_when_missing(self):
        mod = self._import()
        with pytest.raises(SystemExit) as exc:
            mod.extract_github_context("no pr here", require_pr=True)
        assert exc.value.code == 1

    def test_require_issue_exits_1_when_missing(self):
        mod = self._import()
        with pytest.raises(SystemExit) as exc:
            mod.extract_github_context("no issue here", require_issue=True)
        assert exc.value.code == 1

    def test_require_pr_succeeds_when_present(self):
        mod = self._import()
        result = mod.extract_github_context("PR #10", require_pr=True)
        assert 10 in result["PRNumbers"]

    def test_empty_text_returns_empty_lists(self):
        mod = self._import()
        result = mod.extract_github_context("")
        assert result["PRNumbers"] == []
        assert result["IssueNumbers"] == []
        assert result["Owner"] is None

    def test_multiple_prs(self):
        mod = self._import()
        result = mod.extract_github_context("PR #1 and PR #2 and PR #3")
        assert 1 in result["PRNumbers"]
        assert 2 in result["PRNumbers"]
        assert 3 in result["PRNumbers"]

    def test_url_populates_urls_list(self):
        mod = self._import()
        result = mod.extract_github_context("github.com/org/proj/pull/7")
        assert len(result["URLs"]) >= 1
        url_obj = result["URLs"][0]
        assert url_obj["Type"] == "PR"
        assert url_obj["Number"] == 7

    def test_main_happy_path(self, capsys):
        import importlib

        import extract_github_context as mod
        importlib.reload(mod)
        sys.argv = [
            "extract_github_context.py",
            "--text", "Fix issue #77 and PR #88",
        ]
        mod.main()
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert 77 in parsed["IssueNumbers"]
        assert 88 in parsed["PRNumbers"]

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["extract_github_context.py", "--help"]
            import extract_github_context as mod
            mod.main()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# test_workflow_locally
# ---------------------------------------------------------------------------

class TestTestWorkflowLocally:
    """Tests for test_workflow_locally.test_workflow_locally."""

    def _import(self):
        import importlib

        import test_workflow_locally as mod
        importlib.reload(mod)
        return mod

    def test_prerequisites_missing_returns_exit_2(self):
        mod = self._import()
        with patch("shutil.which", return_value=None):
            result = mod.test_workflow_locally("pester-tests")
        assert result["Success"] is False
        assert result["ExitCode"] == 2
        assert len(result["Errors"]) > 0

    def test_workflow_not_found_returns_exit_1(self, tmp_path):
        mod = self._import()
        # act and docker both found
        with (
            patch("shutil.which", return_value="/usr/bin/act"),
            patch("subprocess.run", side_effect=[
                MagicMock(returncode=0),  # docker info
                MagicMock(returncode=0, stdout=str(tmp_path)),  # git rev-parse
            ]),
        ):
            result = mod.test_workflow_locally("nonexistent-workflow")
        assert result["Success"] is False
        assert result["ExitCode"] == 1

    def test_check_prerequisites_no_act(self):
        mod = self._import()

        def which_side(cmd):
            return None if cmd == "act" else "/usr/bin/docker"

        with patch("shutil.which", side_effect=which_side):
            errors = mod._check_prerequisites()
        assert any("act not found" in e for e in errors)

    def test_check_prerequisites_docker_not_running(self):
        mod = self._import()

        def which_side(cmd):
            return "/usr/bin/" + cmd  # both found

        with (
            patch("shutil.which", side_effect=which_side),
            patch(
                "subprocess.run",
                return_value=make_proc(returncode=1, stderr="daemon not running"),
            ),
        ):
            errors = mod._check_prerequisites()
        assert any("daemon" in e.lower() or "Docker" in e for e in errors)

    def test_resolve_workflow_path_mapped_name(self, tmp_path):
        mod = self._import()
        # Create the expected workflow file
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "pester-tests.yml").write_text("name: test")

        path = mod._resolve_workflow_path("pester-tests", str(tmp_path))
        assert path is not None
        assert path.endswith("pester-tests.yml")

    def test_resolve_workflow_path_yml_file(self, tmp_path):
        mod = self._import()
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        wf_file = wf_dir / "custom.yml"
        wf_file.write_text("name: custom")

        path = mod._resolve_workflow_path("custom.yml", str(tmp_path))
        assert path is not None
        assert path.endswith("custom.yml")

    def test_resolve_workflow_path_not_found(self, tmp_path):
        mod = self._import()
        path = mod._resolve_workflow_path("missing", str(tmp_path))
        assert path is None

    def test_get_gh_token_no_gh(self):
        mod = self._import()
        with patch("shutil.which", return_value=None):
            token = mod._get_gh_token()
        assert token is None

    def test_get_gh_token_success(self):
        mod = self._import()
        with (
            patch("shutil.which", return_value="/usr/bin/gh"),
            patch(
                "subprocess.run",
                return_value=make_proc(stdout="mytoken123", returncode=0),
            ),
        ):
            token = mod._get_gh_token()
        assert token == "mytoken123"

    def test_dry_run_passes_n_flag(self, tmp_path):
        mod = self._import()
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "pester-tests.yml").write_text("name: t")

        run_calls = []

        def fake_run(cmd, **kwargs):
            run_calls.append(cmd)
            if cmd[0] == "docker":
                return make_proc(returncode=0)
            if cmd[0] == "git":
                return make_proc(stdout=str(tmp_path), returncode=0)
            if cmd[0] == "gh":
                return make_proc(stdout="token", returncode=0)
            # act
            return make_proc(returncode=0)

        with (
            patch("shutil.which", return_value="/bin/act"),
            patch("subprocess.run", side_effect=fake_run),
        ):
            mod.test_workflow_locally("pester-tests", dry_run=True)

        # Find the act call
        act_calls = [c for c in run_calls if c and c[0] == "act"]
        assert any("-n" in c for c in act_calls)

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["test_workflow_locally.py", "--help"]
            import test_workflow_locally as mod
            mod.main()
        assert exc.value.code == 0
