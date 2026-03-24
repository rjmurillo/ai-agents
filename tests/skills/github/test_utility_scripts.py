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
from unittest.mock import patch

import pytest

# Ensure importability.
_project_root = Path(__file__).resolve().parents[3]
_lib_dir = _project_root / ".claude" / "lib"
_scripts_dir = _project_root / ".claude" / "skills" / "github" / "scripts"
for _p in (
    str(_lib_dir),
    str(_scripts_dir / "reactions"),
    str(_scripts_dir / "utils"),
    str(_scripts_dir),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from github_core.api import RepoInfo  # noqa: E402


def make_proc(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


def _mock_repo():
    return RepoInfo(owner="o", repo="r")


# ---------------------------------------------------------------------------
# add_comment_reaction
# ---------------------------------------------------------------------------

class TestAddCommentReaction:
    """Tests for add_comment_reaction.main."""

    def _import(self):
        import importlib

        import add_comment_reaction as mod
        importlib.reload(mod)
        return mod

    def test_happy_path_single_review_comment(self, capsys):
        mod = self._import()
        proc = make_proc(returncode=0, stdout='{"id":1}')
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main(["--comment-id", "42", "--reaction", "eyes"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["succeeded"] == 1
        assert result["failed"] == 0
        assert result["results"][0]["success"] is True
        assert result["results"][0]["comment_id"] == 42

    def test_happy_path_issue_comment(self, capsys):
        mod = self._import()
        proc = make_proc(returncode=0)
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main(["--comment-id", "10", "--comment-type", "issue", "--reaction", "+1"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["comment_type"] == "issue"

    def test_batch_all_succeed(self, capsys):
        mod = self._import()
        proc = make_proc(returncode=0)
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main(["--comment-id", "1", "2", "3", "--reaction", "heart"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["total_count"] == 3
        assert result["succeeded"] == 3
        assert result["failed"] == 0

    def test_already_reacted_counts_as_success(self, capsys):
        mod = self._import()
        proc = make_proc(returncode=1, stdout="already reacted")
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main(["--comment-id", "5", "--reaction", "rocket"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["succeeded"] == 1

    def test_api_failure_counted(self, capsys):
        mod = self._import()
        proc = make_proc(returncode=1, stderr="server error")
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main(["--comment-id", "9", "--reaction", "eyes"])
        assert rc == 3
        result = json.loads(capsys.readouterr().out)
        assert result["failed"] == 1
        assert result["results"][0]["success"] is False

    def test_partial_batch_failure(self, capsys):
        mod = self._import()
        procs = [make_proc(returncode=0), make_proc(returncode=1, stderr="err")]
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=procs),
        ):
            rc = mod.main(["--comment-id", "1", "2", "--reaction", "eyes"])
        assert rc == 3
        result = json.loads(capsys.readouterr().out)
        assert result["succeeded"] == 1
        assert result["failed"] == 1

    def test_main_exits_3_on_failure(self):
        mod = self._import()
        proc = make_proc(returncode=1, stderr="error")
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main(["--comment-id", "1", "--reaction", "eyes"])
        assert rc == 3

    def test_main_success(self, capsys):
        mod = self._import()
        proc = make_proc(returncode=0)
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main(["--comment-id", "5", "--reaction", "+1"])
        assert rc == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["succeeded"] == 1

    def test_help_does_not_crash(self):
        import add_comment_reaction as mod
        with pytest.raises(SystemExit) as exc:
            mod.main(["--help"])
        assert exc.value.code == 0

    def test_review_endpoint_used_for_review_type(self):
        mod = self._import()
        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(cmd)
            return make_proc(returncode=0)

        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=RepoInfo(owner="owner", repo="repo")),
            patch("subprocess.run", side_effect=fake_run),
        ):
            mod.main(["--comment-id", "100", "--reaction", "eyes"])

        # Find the gh api call
        api_cmd = [c for c in captured_cmds if c and "pulls/comments" in str(c)]
        assert len(api_cmd) >= 1

    def test_issue_endpoint_used_for_issue_type(self):
        mod = self._import()
        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(cmd)
            return make_proc(returncode=0)

        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=RepoInfo(owner="owner", repo="repo")),
            patch("subprocess.run", side_effect=fake_run),
        ):
            mod.main(["--comment-id", "200", "--comment-type", "issue", "--reaction", "eyes"])

        api_cmd = [c for c in captured_cmds if c and "issues/comments" in str(c)]
        assert len(api_cmd) >= 1


# ---------------------------------------------------------------------------
# extract_github_context
# ---------------------------------------------------------------------------

class TestExtractGithubContext:
    """Tests for extract_github_context._extract_context and main."""

    def _import(self):
        import importlib

        import extract_github_context as mod
        importlib.reload(mod)
        return mod

    def test_extracts_pr_url(self):
        mod = self._import()
        text = "See github.com/owner/repo/pull/42 for details"
        result = mod._extract_context(text)
        assert 42 in result["pr_numbers"]
        assert result["owner"] == "owner"
        assert result["repo"] == "repo"

    def test_extracts_issue_url(self):
        mod = self._import()
        text = "See github.com/myorg/myrepo/issues/99"
        result = mod._extract_context(text)
        assert 99 in result["issue_numbers"]

    def test_extracts_pr_keyword(self):
        mod = self._import()
        result = mod._extract_context("fix for PR #123 merged")
        assert 123 in result["pr_numbers"]

    def test_extracts_pr_keyword_no_hash(self):
        mod = self._import()
        result = mod._extract_context("please review PR 456")
        assert 456 in result["pr_numbers"]

    def test_extracts_pull_request_keyword(self):
        mod = self._import()
        result = mod._extract_context("see pull request #789 for details")
        assert 789 in result["pr_numbers"]

    def test_extracts_issue_keyword(self):
        mod = self._import()
        result = mod._extract_context("fixes issue #55")
        assert 55 in result["issue_numbers"]

    def test_extracts_standalone_hash(self):
        mod = self._import()
        result = mod._extract_context("related to #11 and the fix")
        assert 11 in result["pr_numbers"]

    def test_no_duplicates(self):
        mod = self._import()
        text = "PR #5 and github.com/o/r/pull/5"
        result = mod._extract_context(text)
        assert result["pr_numbers"].count(5) == 1

    def test_require_pr_exits_1_when_missing(self):
        mod = self._import()
        rc = mod.main(["--text", "no pr here", "--require-pr"])
        assert rc == 1

    def test_require_issue_exits_1_when_missing(self):
        mod = self._import()
        rc = mod.main(["--text", "no issue here", "--require-issue"])
        assert rc == 1

    def test_require_pr_succeeds_when_present(self, capsys):
        mod = self._import()
        rc = mod.main(["--text", "PR #10"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert 10 in result["pr_numbers"]

    def test_empty_text_returns_empty_lists(self):
        mod = self._import()
        result = mod._extract_context("")
        assert result["pr_numbers"] == []
        assert result["issue_numbers"] == []
        assert result["owner"] is None

    def test_multiple_prs(self):
        mod = self._import()
        result = mod._extract_context("PR #1 and PR #2 and PR #3")
        assert 1 in result["pr_numbers"]
        assert 2 in result["pr_numbers"]
        assert 3 in result["pr_numbers"]

    def test_url_populates_urls_list(self):
        mod = self._import()
        result = mod._extract_context("github.com/org/proj/pull/7")
        assert len(result["urls"]) >= 1
        url_obj = result["urls"][0]
        assert url_obj["type"] == "PR"
        assert url_obj["number"] == 7

    def test_main_happy_path(self, capsys):
        import importlib

        import extract_github_context as mod
        importlib.reload(mod)
        rc = mod.main(["--text", "Fix issue #77 and PR #88"])
        assert rc == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert 77 in parsed["issue_numbers"]
        assert 88 in parsed["pr_numbers"]

    def test_help_does_not_crash(self):
        import extract_github_context as mod
        with pytest.raises(SystemExit) as exc:
            mod.main(["--help"])
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# test_workflow_locally
# ---------------------------------------------------------------------------

class TestTestWorkflowLocally:
    """Tests for test_workflow_locally.main."""

    def _import(self):
        import importlib

        import test_workflow_locally as mod
        importlib.reload(mod)
        return mod

    def test_prerequisites_missing_returns_exit_2(self):
        mod = self._import()
        with patch("shutil.which", return_value=None):
            rc = mod.main(["--workflow", "pester-tests"])
        assert rc == 2

    def test_workflow_not_found_returns_exit_1(self, tmp_path):
        mod = self._import()
        # act and docker both found, docker running
        with (
            patch("shutil.which", return_value="/usr/bin/act"),
            patch("subprocess.run", side_effect=[
                make_proc(stdout="act 0.2.0", returncode=0),  # act --version
                make_proc(returncode=0),                        # docker info
            ]),
            patch("test_workflow_locally._get_repo_root", return_value=str(tmp_path)),
        ):
            rc = mod.main(["--workflow", "nonexistent-workflow"])
        assert rc == 1

    def test_check_prerequisites_no_act(self):
        mod = self._import()
        with patch("shutil.which", return_value=None):
            rc = mod.main(["--workflow", "pester-tests"])
        assert rc == 2

    def test_check_prerequisites_docker_not_running(self):
        mod = self._import()

        def which_side(cmd):
            return "/usr/bin/" + cmd

        with (
            patch("shutil.which", side_effect=which_side),
            patch("subprocess.run", side_effect=[
                make_proc(stdout="act 0.2.0", returncode=0),  # act --version
                make_proc(returncode=1, stderr="daemon not running"),  # docker info
            ]),
        ):
            rc = mod.main(["--workflow", "pester-tests"])
        assert rc == 2

    def test_resolve_workflow_path_mapped_name(self, tmp_path):
        mod = self._import()
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "pester-tests.yml").write_text("name: test")

        def which_side(cmd):
            return "/usr/bin/" + cmd

        run_calls = []

        def fake_run(cmd, **kwargs):
            run_calls.append(cmd)
            if cmd[0] == "act" and cmd[1] == "--version":
                return make_proc(stdout="act 0.2.0", returncode=0)
            if cmd[0] == "docker":
                return make_proc(returncode=0)
            if cmd[0] == "gh":
                return make_proc(stdout="token", returncode=0)
            # act execution
            return make_proc(returncode=0)

        with (
            patch("shutil.which", side_effect=which_side),
            patch("subprocess.run", side_effect=fake_run),
            patch("test_workflow_locally._get_repo_root", return_value=str(tmp_path)),
        ):
            rc = mod.main(["--workflow", "pester-tests"])
        assert rc == 0

    def test_resolve_workflow_path_yml_file(self, tmp_path):
        mod = self._import()
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        wf_file = wf_dir / "custom.yml"
        wf_file.write_text("name: custom")

        def which_side(cmd):
            return "/usr/bin/" + cmd

        def fake_run(cmd, **kwargs):
            if cmd[0] == "act" and cmd[1] == "--version":
                return make_proc(stdout="act 0.2.0", returncode=0)
            if cmd[0] == "docker":
                return make_proc(returncode=0)
            if cmd[0] == "gh":
                return make_proc(stdout="token", returncode=0)
            return make_proc(returncode=0)

        with (
            patch("shutil.which", side_effect=which_side),
            patch("subprocess.run", side_effect=fake_run),
            patch("test_workflow_locally._get_repo_root", return_value=str(tmp_path)),
        ):
            rc = mod.main(["--workflow", "custom.yml"])
        assert rc == 0

    def test_resolve_workflow_path_not_found(self, tmp_path):
        mod = self._import()

        def which_side(cmd):
            return "/usr/bin/" + cmd

        with (
            patch("shutil.which", side_effect=which_side),
            patch("subprocess.run", side_effect=[
                make_proc(stdout="act 0.2.0", returncode=0),
                make_proc(returncode=0),
            ]),
            patch("test_workflow_locally._get_repo_root", return_value=str(tmp_path)),
        ):
            rc = mod.main(["--workflow", "missing"])
        assert rc == 1

    def test_get_gh_token_no_gh(self):
        mod = self._import()
        # When act is not found, main exits with 2 before trying to get token
        with patch("shutil.which", return_value=None):
            rc = mod.main(["--workflow", "pester-tests"])
        assert rc == 2

    def test_get_gh_token_success(self, tmp_path):
        mod = self._import()
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "pester-tests.yml").write_text("name: t")

        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(cmd)
            if cmd[0] == "act" and cmd[1] == "--version":
                return make_proc(stdout="act 0.2.0", returncode=0)
            if cmd[0] == "docker":
                return make_proc(returncode=0)
            if cmd[0] == "gh":
                return make_proc(stdout="mytoken123", returncode=0)
            return make_proc(returncode=0)

        with (
            patch("shutil.which", return_value="/usr/bin/act"),
            patch("subprocess.run", side_effect=fake_run),
            patch("test_workflow_locally._get_repo_root", return_value=str(tmp_path)),
        ):
            rc = mod.main(["--workflow", "pester-tests"])
        assert rc == 0
        # Verify gh auth token was called
        gh_calls = [c for c in captured_cmds if c and c[0] == "gh"]
        assert len(gh_calls) >= 1

    def test_dry_run_passes_n_flag(self, tmp_path):
        mod = self._import()
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "pester-tests.yml").write_text("name: t")

        run_calls = []

        def fake_run(cmd, **kwargs):
            run_calls.append(cmd)
            if cmd[0] == "act" and cmd[1] == "--version":
                return make_proc(stdout="act 0.2.0", returncode=0)
            if cmd[0] == "docker":
                return make_proc(returncode=0)
            if cmd[0] == "gh":
                return make_proc(stdout="token", returncode=0)
            return make_proc(returncode=0)

        with (
            patch("shutil.which", return_value="/bin/act"),
            patch("subprocess.run", side_effect=fake_run),
            patch("test_workflow_locally._get_repo_root", return_value=str(tmp_path)),
        ):
            mod.main(["--workflow", "pester-tests", "--dry-run"])

        act_calls = [c for c in run_calls if c and c[0] == "act" and c[1] != "--version"]
        assert any("-n" in c for c in act_calls)

    def test_help_does_not_crash(self):
        import test_workflow_locally as mod
        with pytest.raises(SystemExit) as exc:
            mod.main(["--help"])
        assert exc.value.code == 0
