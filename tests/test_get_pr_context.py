"""Tests for get_pr_context.py skill script.

100% block coverage for all code paths including:
- Argument parsing (required/optional flags)
- Authentication failure
- PR not found vs generic API failure
- Commits as list (gh CLI actual format)
- Merged PR with mergedBy
- Empty labels / missing author
- --include-diff, --diff-stat, --include-changed-files
- Diff/files fetch failures (non-zero rc)
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from scripts.github_core.api import RepoInfo

from tests.mock_fidelity import assert_mock_keys_match
from scripts.github_core.api import RepoInfo

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("get_pr_context")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _pr_data(**overrides):
    """Build a realistic PR data dict matching the canonical fixture shape.

    The ``commits`` field is a list of commit objects, matching the actual
    ``gh pr view --json commits`` output format.
    """
    data = {
        "number": 50,
        "title": "Test PR",
        "body": "Description",
        "headRefName": "feature",
        "baseRefName": "main",
        "state": "OPEN",
        "author": {"login": "alice"},
        "labels": [{"name": "bug"}],
        "reviewRequests": [],
        "commits": [
            {"oid": "abc123", "messageHeadline": "first commit"},
            {"oid": "def456", "messageHeadline": "second commit"},
            {"oid": "ghi789", "messageHeadline": "third commit"},
        ],
        "additions": 10,
        "deletions": 5,
        "changedFiles": 2,
        "mergeable": "MERGEABLE",
        "mergedAt": None,
        "mergedBy": None,
        "createdAt": "2025-01-01T00:00:00Z",
        "updatedAt": "2025-01-02T00:00:00Z",
    }
    data.update(overrides)
    return data


def _pr_json(**overrides):
    return json.dumps(_pr_data(**overrides))


def test_mock_shape_matches_fixture():
    """Validate that the test mock shape matches the canonical API fixture."""
    mock = _pr_data()
    assert_mock_keys_match(mock, "pull_request", allow_extra=True)


def _patch_auth_and_repo():
    """Common patches for auth and repo resolution."""
    return (
        patch("get_pr_context.assert_gh_authenticated"),
        patch(
            "get_pr_context.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ),
    )


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_minimal_args(self):
        args = build_parser().parse_args(["--pull-request", "42"])
        assert args.pull_request == 42
        assert args.include_diff is False
        assert args.diff_stat is False
        assert args.include_changed_files is False
        assert args.owner == ""
        assert args.repo == ""

    def test_all_flags(self):
        args = build_parser().parse_args([
            "--pull-request", "50",
            "--owner", "myorg",
            "--repo", "myrepo",
            "--include-diff",
            "--diff-stat",
            "--include-changed-files",
        ])
        assert args.pull_request == 50
        assert args.owner == "myorg"
        assert args.repo == "myrepo"
        assert args.include_diff is True
        assert args.diff_stat is True
        assert args.include_changed_files is True


# ---------------------------------------------------------------------------
# Tests: main - error paths
# ---------------------------------------------------------------------------


class TestMainErrors:
    def test_not_authenticated_exits_4(self):
        with patch(
            "get_pr_context.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_pr_not_found_exits_2(self):
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="not found"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "999"])
            assert exc.value.code == 2

    def test_api_failure_exits_3(self):
        """Generic API error (no 'not found' in message) exits with code 3."""
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="internal server error"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3

    def test_api_failure_uses_stdout_when_stderr_empty(self):
        """When stderr is empty, error message falls back to stdout."""
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="", stdout="some error in stdout"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3


# ---------------------------------------------------------------------------
# Tests: main - success paths
# ---------------------------------------------------------------------------


class TestMainSuccess:
    def test_basic_output(self, capsys):
        """Core fields are extracted correctly from the gh response."""
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(stdout=_pr_json(), rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert isinstance(output, dict)
        assert output["success"] is True
        assert isinstance(output["number"], int)
        assert output["number"] == 50
        assert isinstance(output["title"], str)
        assert output["title"] == "Test PR"
        assert isinstance(output["body"], str)
        assert output["body"] == "Description"
        assert output["state"] == "OPEN"
        assert output["author"] == "alice"
        assert output["head_branch"] == "feature"
        assert output["base_branch"] == "main"
        assert isinstance(output["labels"], list)
        assert output["labels"] == ["bug"]
        assert isinstance(output["additions"], int)
        assert output["additions"] == 10
        assert isinstance(output["deletions"], int)
        assert output["deletions"] == 5
        assert isinstance(output["changed_files"], int)
        assert output["changed_files"] == 2
        assert output["mergeable"] == "MERGEABLE"
        assert isinstance(output["merged"], bool)
        assert output["merged"] is False
        assert output["merged_by"] is None
        assert output["diff"] is None
        assert output["files"] is None
        assert output["owner"] == "o"
        assert output["repo"] == "r"

    def test_commits_count_from_list(self, capsys):
        """Regression: commits field is a list, not a dict with totalCount."""
        commits = [
            {"oid": "a1", "messageHeadline": "one"},
            {"oid": "b2", "messageHeadline": "two"},
        ]
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(stdout=_pr_json(commits=commits), rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["commits"] == 2

    def test_commits_empty_list(self, capsys):
        """Zero commits returns 0."""
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(stdout=_pr_json(commits=[]), rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["commits"] == 0

    def test_commits_missing_key(self, capsys):
        """If commits key is absent, default to 0."""
        raw = json.loads(_pr_json())
        del raw["commits"]
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(stdout=json.dumps(raw), rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["commits"] == 0

    def test_merged_pr(self, capsys):
        """Merged PR populates merged=True and merged_by."""
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(
                stdout=_pr_json(
                    state="MERGED",
                    mergedAt="2025-01-03T00:00:00Z",
                    mergedBy={"login": "bob"},
                ),
                rc=0,
            ),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["merged"] is True
        assert output["merged_by"] == "bob"

    def test_empty_labels(self, capsys):
        """PR with no labels returns empty list."""
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(stdout=_pr_json(labels=[]), rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["labels"] == []

    def test_missing_author(self, capsys):
        """PR with missing author field returns None."""
        raw = json.loads(_pr_json())
        del raw["author"]
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(stdout=json.dumps(raw), rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["author"] is None


# ---------------------------------------------------------------------------
# Tests: main - diff and changed files
# ---------------------------------------------------------------------------


class TestMainDiffAndFiles:
    def test_include_diff(self, capsys):
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=_pr_json(), rc=0)
            return _completed(stdout="diff output", rc=0)

        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "50", "--include-diff"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["diff"] == "diff output"

    def test_include_diff_with_stat(self, capsys):
        """--diff-stat appends --stat to the diff command."""
        calls = []

        def _side_effect(*args, **kwargs):
            calls.append(args[0])
            if len(calls) == 1:
                return _completed(stdout=_pr_json(), rc=0)
            return _completed(stdout="stat output", rc=0)

        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "50", "--include-diff", "--diff-stat"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["diff"] == "stat output"
        assert "--stat" in calls[1]

    def test_include_diff_failure(self, capsys):
        """Diff fetch failure leaves diff as None."""
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=_pr_json(), rc=0)
            return _completed(rc=1, stderr="diff failed")

        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "50", "--include-diff"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["diff"] is None

    def test_include_changed_files(self, capsys):
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=_pr_json(), rc=0)
            return _completed(stdout="file1.py\nfile2.py\n", rc=0)

        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "50", "--include-changed-files"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["files"] == ["file1.py", "file2.py"]

    def test_include_changed_files_filters_blanks(self, capsys):
        """Blank lines in name-only output are filtered."""
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=_pr_json(), rc=0)
            return _completed(stdout="a.py\n\n  \nb.py\n", rc=0)

        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "50", "--include-changed-files"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["files"] == ["a.py", "b.py"]

    def test_include_changed_files_failure(self, capsys):
        """Changed-files fetch failure leaves files as None."""
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=_pr_json(), rc=0)
            return _completed(rc=1, stderr="files failed")

        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "50", "--include-changed-files"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["files"] is None

    def test_both_diff_and_files(self, capsys):
        """Both flags trigger two additional subprocess calls."""
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=_pr_json(), rc=0)
            if call_count == 2:
                return _completed(stdout="the diff", rc=0)
            return _completed(stdout="x.py\ny.py\n", rc=0)

        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main([
                "--pull-request", "50",
                "--include-diff",
                "--include-changed-files",
            ])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["diff"] == "the diff"
        assert output["files"] == ["x.py", "y.py"]
