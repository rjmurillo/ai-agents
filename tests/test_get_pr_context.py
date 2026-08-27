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


def _review_threads_response(**overrides):
    review_threads = {
        "totalCount": 0,
        "pageInfo": {"hasNextPage": False, "endCursor": None},
        "nodes": [],
    }
    review_threads.update(overrides)
    return {"repository": {"pullRequest": {"reviewThreads": review_threads}}}


def _thread(thread_id: int, is_resolved: bool) -> dict[str, object]:
    return {"id": f"PRRT_{thread_id}", "isResolved": is_resolved}


def _threads(count: int, *, start: int = 1) -> list[dict[str, object]]:
    return [_thread(thread_id, True) for thread_id in range(start, start + count)]


@pytest.fixture(autouse=True)
def _mock_review_threads():
    with patch("get_pr_context.gh_graphql", return_value=_review_threads_response()):
        yield


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
        "headRefOid": "abc123def4567890abc123def4567890abc12345",
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
        "statusCheckRollup": [
            {
                "__typename": "CheckRun",
                "name": "tests",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            },
            {
                "__typename": "StatusContext",
                "context": "legacy-check",
                "state": "SUCCESS",
            },
        ],
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

    def test_invalid_json_pr_response_exits_3(self):
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(stdout="not-json", rc=0),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3

    def test_missing_status_check_rollup_exits_3(self):
        """Missing check rollup is an API failure, not an empty result."""
        pr = json.loads(_pr_json())
        pr.pop("statusCheckRollup")
        auth_patch, repo_patch = _patch_auth_and_repo()
        with (
            auth_patch,
            repo_patch,
            patch(
                "subprocess.run",
                return_value=_completed(stdout=json.dumps(pr), rc=0),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3


    def test_object_status_check_rollup_exits_3(self):
        """The helper rejects the GraphQL connection shape gh does not return."""
        auth_patch, repo_patch = _patch_auth_and_repo()
        with (
            auth_patch,
            repo_patch,
            patch(
                "subprocess.run",
                return_value=_completed(
                    stdout=_pr_json(statusCheckRollup={"contexts": {"nodes": []}}),
                    rc=0,
                ),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3


    def test_malformed_status_check_exits_3(self):
        auth_patch, repo_patch = _patch_auth_and_repo()
        with (
            auth_patch,
            repo_patch,
            patch(
                "subprocess.run",
                return_value=_completed(
                    stdout=_pr_json(statusCheckRollup=[{"__typename": "CheckRun"}]),
                    rc=0,
                ),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3


    def test_non_object_pr_response_exits_3(self):
        auth_patch, repo_patch = _patch_auth_and_repo()
        with (
            auth_patch,
            repo_patch,
            patch(
                "subprocess.run",
                return_value=_completed(stdout="[]", rc=0),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3


    def test_review_threads_fetch_failure_exits_3(self):
        """GraphQL review-thread failure is not reported as zero threads."""
        auth_patch, repo_patch = _patch_auth_and_repo()
        with (
            auth_patch,
            repo_patch,
            patch("subprocess.run", return_value=_completed(stdout=_pr_json(), rc=0)),
            patch("get_pr_context.gh_graphql", side_effect=RuntimeError("rate limit")),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3


    def test_review_threads_timeout_exits_3(self):
        auth_patch, repo_patch = _patch_auth_and_repo()
        with (
            auth_patch,
            repo_patch,
            patch("subprocess.run", return_value=_completed(stdout=_pr_json(), rc=0)),
            patch(
                "get_pr_context.gh_graphql",
                side_effect=subprocess.TimeoutExpired("gh", 30),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3


    def test_review_threads_missing_cursor_exits_3(self):
        """A paginated response cannot silently stop without a cursor."""
        auth_patch, repo_patch = _patch_auth_and_repo()
        response = _review_threads_response(
            totalCount=101,
            pageInfo={"hasNextPage": True, "endCursor": None},
            nodes=_threads(100),
        )
        with (
            auth_patch,
            repo_patch,
            patch("subprocess.run", return_value=_completed(stdout=_pr_json(), rc=0)),
            patch("get_pr_context.gh_graphql", return_value=response),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3


    def test_review_threads_invalid_node_exits_3(self):
        """A missing isResolved value cannot become a false zero."""
        auth_patch, repo_patch = _patch_auth_and_repo()
        response = _review_threads_response(totalCount=1, nodes=[{}])
        with (
            auth_patch,
            repo_patch,
            patch("subprocess.run", return_value=_completed(stdout=_pr_json(), rc=0)),
            patch("get_pr_context.gh_graphql", return_value=response),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3


    @pytest.mark.parametrize(
        ("response", "expected_code"),
        [
            ([], 3),
            ({}, 3),
            ({"repository": {"pullRequest": None}}, 2),
            ({"repository": {"pullRequest": []}}, 3),
            ({"repository": {"pullRequest": {}}}, 3),
        ],
    )
    def test_review_threads_reject_structural_failures(
        self,
        response,
        expected_code,
    ):
        auth_patch, repo_patch = _patch_auth_and_repo()
        with (
            auth_patch,
            repo_patch,
            patch("subprocess.run", return_value=_completed(stdout=_pr_json(), rc=0)),
            patch("get_pr_context.gh_graphql", return_value=response),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == expected_code


    def test_review_threads_invalid_page_metadata_exits_3(self):
        auth_patch, repo_patch = _patch_auth_and_repo()
        response = _review_threads_response(totalCount=-1)
        with (
            auth_patch,
            repo_patch,
            patch("subprocess.run", return_value=_completed(stdout=_pr_json(), rc=0)),
            patch("get_pr_context.gh_graphql", return_value=response),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3


    def test_review_threads_changed_total_exits_3(self):
        auth_patch, repo_patch = _patch_auth_and_repo()
        first_page = _review_threads_response(
            totalCount=2,
            pageInfo={"hasNextPage": True, "endCursor": "cursor-1"},
            nodes=[_thread(1, True)],
        )
        second_page = _review_threads_response(
            totalCount=3,
            nodes=[_thread(2, False)],
        )
        with (
            auth_patch,
            repo_patch,
            patch("subprocess.run", return_value=_completed(stdout=_pr_json(), rc=0)),
            patch(
                "get_pr_context.gh_graphql",
                side_effect=[first_page, second_page],
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3


    def test_review_threads_page_limit_exits_3(self):
        auth_patch, repo_patch = _patch_auth_and_repo()
        response = _review_threads_response(
            totalCount=2,
            pageInfo={"hasNextPage": True, "endCursor": "cursor-1"},
            nodes=[_thread(1, True)],
        )
        with (
            auth_patch,
            repo_patch,
            patch("subprocess.run", return_value=_completed(stdout=_pr_json(), rc=0)),
            patch("get_pr_context.gh_graphql", return_value=response),
            patch("get_pr_context._MAX_REVIEW_THREAD_PAGES", 1),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3


    def test_review_threads_repeated_cursor_exits_3(self):
        auth_patch, repo_patch = _patch_auth_and_repo()
        first_page = _review_threads_response(
            totalCount=3,
            pageInfo={"hasNextPage": True, "endCursor": "cursor-1"},
            nodes=[_thread(1, True)],
        )
        second_page = _review_threads_response(
            totalCount=3,
            pageInfo={"hasNextPage": True, "endCursor": "cursor-1"},
            nodes=[_thread(2, True)],
        )
        with (
            auth_patch,
            repo_patch,
            patch("subprocess.run", return_value=_completed(stdout=_pr_json(), rc=0)),
            patch(
                "get_pr_context.gh_graphql",
                side_effect=[first_page, second_page],
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3


    def test_review_threads_duplicate_thread_exits_3(self):
        auth_patch, repo_patch = _patch_auth_and_repo()
        first_page = _review_threads_response(
            totalCount=2,
            pageInfo={"hasNextPage": True, "endCursor": "cursor-1"},
            nodes=[_thread(1, True)],
        )
        second_page = _review_threads_response(
            totalCount=2,
            nodes=[_thread(1, False)],
        )
        with (
            auth_patch,
            repo_patch,
            patch("subprocess.run", return_value=_completed(stdout=_pr_json(), rc=0)),
            patch(
                "get_pr_context.gh_graphql",
                side_effect=[first_page, second_page],
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3

    def test_review_threads_duplicate_thread_in_page_exits_3(self):
        auth_patch, repo_patch = _patch_auth_and_repo()
        response = _review_threads_response(
            totalCount=2,
            nodes=[_thread(1, True), _thread(1, False)],
        )
        with (
            auth_patch,
            repo_patch,
            patch("subprocess.run", return_value=_completed(stdout=_pr_json(), rc=0)),
            patch("get_pr_context.gh_graphql", return_value=response),
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
        assert output["Success"] is True
        data = output["Data"]
        assert isinstance(data["number"], int)
        assert data["number"] == 50
        assert isinstance(data["title"], str)
        assert data["title"] == "Test PR"
        assert isinstance(data["body"], str)
        assert data["body"] == "Description"
        assert data["state"] == "OPEN"
        assert data["author"] == "alice"
        assert data["head_branch"] == "feature"
        assert isinstance(data["head_sha"], str)
        assert data["head_sha"] == "abc123def4567890abc123def4567890abc12345"
        assert data["base_branch"] == "main"
        assert isinstance(data["labels"], list)
        assert data["labels"] == ["bug"]
        assert isinstance(data["additions"], int)
        assert data["additions"] == 10
        assert isinstance(data["deletions"], int)
        assert data["deletions"] == 5
        assert isinstance(data["changed_files"], int)
        assert data["changed_files"] == 2
        assert data["mergeable"] == "MERGEABLE"
        assert len(data["status_checks"]) == 2
        assert data["status_check_total_count"] == 2
        assert data["review_thread_total_count"] == 0
        assert data["review_thread_returned_count"] == 0
        assert data["review_thread_unresolved_count"] == 0
        assert data["review_thread_counts_complete"] is True
        assert isinstance(data["merged"], bool)
        assert data["merged"] is False
        assert data["merged_by"] is None
        assert data["diff"] is None
        assert data["files"] is None
        assert data["owner"] == "o"
        assert data["repo"] == "r"

    def test_status_check_rollup_is_requested(self, capsys):
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(stdout=_pr_json(), rc=0),
        ) as run:
            rc = main(["--pull-request", "50"])
        assert rc == 0
        capsys.readouterr()
        command = run.call_args.args[0]
        fields = command[command.index("--json") + 1].split(",")
        assert "statusCheckRollup" in fields

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
        assert output["Data"]["commits"] == 2

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
        assert output["Data"]["commits"] == 0

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
        assert output["Data"]["commits"] == 0

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
        data = output["Data"]
        assert data["merged"] is True
        assert data["merged_by"] == "bob"

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
        assert output["Data"]["labels"] == []

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
        assert output["Data"]["author"] is None

    def test_null_author(self, capsys):
        """PR with explicit null author returns None."""
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(stdout=_pr_json(author=None), rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["author"] is None

    def test_head_sha_maps_from_head_ref_oid(self, capsys):
        """head_sha is sourced directly from the gh headRefOid field (#2315)."""
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(
                stdout=_pr_json(headRefOid="0123456789abcdef0123456789abcdef01234567"),
                rc=0,
            ),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["head_sha"] == (
            "0123456789abcdef0123456789abcdef01234567"
        )

    def test_head_sha_missing_key_is_none(self, capsys):
        """If headRefOid is absent from the response, head_sha is None (no KeyError)."""
        raw = json.loads(_pr_json())
        del raw["headRefOid"]
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(stdout=json.dumps(raw), rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["head_sha"] is None

    def test_head_sha_empty_string_maps_through(self, capsys):
        """An empty headRefOid maps through unchanged (not coerced to None)."""
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(stdout=_pr_json(headRefOid=""), rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["head_sha"] == ""


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
        assert output["Data"]["diff"] == "diff output"
        assert output["Data"]["context_fetch_failures"] == []

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
        assert output["Data"]["diff"] == "stat output"
        assert "--stat" in calls[1]

    def test_include_diff_failure(self, capsys):
        """Diff fetch failure records an explicit context gap."""
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
        assert output["Data"]["diff"] is None
        assert output["Data"]["context_fetch_failures"] == [
            {"field": "diff", "message": "diff failed"}
        ]

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
        assert output["Data"]["files"] == ["file1.py", "file2.py"]
        assert output["Data"]["context_fetch_failures"] == []

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
        assert output["Data"]["files"] == ["a.py", "b.py"]

    def test_include_changed_files_failure(self, capsys):
        """Changed-files fetch failure records an explicit context gap."""
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
        assert output["Data"]["files"] is None
        assert output["Data"]["context_fetch_failures"] == [
            {"field": "files", "message": "files failed"}
        ]

    def test_diff_and_files_failures_without_output_use_return_code_fallback(self, capsys):
        """Blank child output still produces actionable diff and file failure records."""
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=_pr_json(), rc=0)
            if call_count == 2:
                return _completed(rc=17)
            return _completed(rc=19)

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
        assert output["Data"]["context_fetch_failures"] == [
            {
                "field": "diff",
                "message": "gh pr diff exited with return code 17 and no error output",
            },
            {
                "field": "files",
                "message": (
                    "gh pr diff --name-only exited with return code 19 and no error output"
                ),
            },
        ]

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
        data = output["Data"]
        assert data["diff"] == "the diff"
        assert data["files"] == ["x.py", "y.py"]


# ---------------------------------------------------------------------------
# Tests: extended metadata fields (issue #3912)
# ---------------------------------------------------------------------------


class TestExtendedMetadata:
    """Verify the new fields added for issue #3912 are present in output."""

    def test_base_sha_present(self, capsys):
        pr = _pr_data(
            baseRefOid="deadbeef0000000000000000000000000000dead",
        )
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run", return_value=_completed(stdout=json.dumps(pr)),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["Data"]["base_sha"] == "deadbeef0000000000000000000000000000dead"

    def test_is_draft_false_by_default(self, capsys):
        pr = _pr_data(isDraft=False)
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run", return_value=_completed(stdout=json.dumps(pr)),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["Data"]["is_draft"] is False

    def test_is_draft_true(self, capsys):
        pr = _pr_data(isDraft=True)
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run", return_value=_completed(stdout=json.dumps(pr)),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["Data"]["is_draft"] is True

    def test_merge_state_status_present(self, capsys):
        pr = _pr_data(mergeStateStatus="CLEAN")
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run", return_value=_completed(stdout=json.dumps(pr)),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["Data"]["merge_state_status"] == "CLEAN"

    def test_auto_merge_none(self, capsys):
        pr = _pr_data(autoMergeRequest=None)
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run", return_value=_completed(stdout=json.dumps(pr)),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        data = out["Data"]
        assert data["auto_merge"] is False
        assert data["auto_merge_method"] is None

    def test_auto_merge_set(self, capsys):
        pr = _pr_data(autoMergeRequest={"mergeMethod": "SQUASH"})
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run", return_value=_completed(stdout=json.dumps(pr)),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        data = out["Data"]
        assert data["auto_merge"] is True
        assert data["auto_merge_method"] == "SQUASH"

    def test_head_repo_fields(self, capsys):
        pr = _pr_data(headRepository={
            "name": "ai-agents",
            "owner": {"login": "rjmurillo"},
        })
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run", return_value=_completed(stdout=json.dumps(pr)),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        data = out["Data"]
        assert data["head_repo_name"] == "ai-agents"
        assert data["head_repo_owner"] == "rjmurillo"

    def test_reviews_list(self, capsys):
        pr = _pr_data(reviews=[
            {"author": {"login": "reviewer1"}, "state": "APPROVED"},
        ])
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run", return_value=_completed(stdout=json.dumps(pr)),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert len(out["Data"]["reviews"]) == 1

    def test_review_counts_aggregated(self, capsys):
        pr = _pr_data(reviews=[
            {"id": "r1", "state": "APPROVED", "author": {"login": "bob"}},
            {"id": "r2", "state": "APPROVED", "author": {"login": "carol"}},
            {"id": "r3", "state": "CHANGES_REQUESTED", "author": {"login": "dave"}},
        ])
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run", return_value=_completed(stdout=json.dumps(pr)),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["Data"]["review_counts"] == {"APPROVED": 2, "CHANGES_REQUESTED": 1}

    def test_review_threads_count_unresolved(self, capsys):
        auth_patch, repo_patch = _patch_auth_and_repo()
        threads = [
            {"id": "PRRT_1", "isResolved": False},
            {"id": "PRRT_2", "isResolved": True},
        ]
        with (
            auth_patch,
            repo_patch,
            patch("subprocess.run", return_value=_completed(stdout=_pr_json(), rc=0)),
            patch(
                "get_pr_context.gh_graphql",
                return_value=_review_threads_response(totalCount=2, nodes=threads),
            ),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        data = out["Data"]
        assert data["review_thread_total_count"] == 2
        assert data["review_thread_returned_count"] == 2
        assert data["review_thread_unresolved_count"] == 1
        assert data["review_thread_counts_complete"] is True


    def test_review_threads_paginates_past_first_hundred(self, capsys):
        auth_patch, repo_patch = _patch_auth_and_repo()
        first_page = _review_threads_response(
            totalCount=101,
            pageInfo={"hasNextPage": True, "endCursor": "cursor-100"},
            nodes=_threads(100),
        )
        second_page = _review_threads_response(
            totalCount=101,
            nodes=[_thread(101, False)],
        )
        with (
            auth_patch,
            repo_patch,
            patch("subprocess.run", return_value=_completed(stdout=_pr_json(), rc=0)),
            patch(
                "get_pr_context.gh_graphql",
                side_effect=[first_page, second_page],
            ) as graphql,
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        data = out["Data"]
        assert data["review_thread_total_count"] == 101
        assert data["review_thread_returned_count"] == 101
        assert data["review_thread_unresolved_count"] == 1
        assert data["review_thread_counts_complete"] is True
        assert "cursor" not in graphql.call_args_list[0].args[1]
        assert graphql.call_args_list[1].args[1]["cursor"] == "cursor-100"


    def test_review_thread_count_reports_hidden_nodes(self, capsys):
        auth_patch, repo_patch = _patch_auth_and_repo()
        response = _review_threads_response(
            totalCount=2,
            nodes=[_thread(1, False)],
        )
        with (
            auth_patch,
            repo_patch,
            patch("subprocess.run", return_value=_completed(stdout=_pr_json(), rc=0)),
            patch("get_pr_context.gh_graphql", return_value=response),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        data = out["Data"]
        assert data["review_thread_total_count"] == 2
        assert data["review_thread_returned_count"] == 1
        assert data["review_thread_unresolved_count"] == 1
        assert data["review_thread_counts_complete"] is False


    def test_empty_status_checks_are_authoritative(self, capsys):
        auth_patch, repo_patch = _patch_auth_and_repo()
        with (
            auth_patch,
            repo_patch,
            patch(
                "subprocess.run",
                return_value=_completed(stdout=_pr_json(statusCheckRollup=[]), rc=0),
            ),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["Data"]["status_checks"] == []
        assert out["Data"]["status_check_total_count"] == 0

    def test_null_status_checks_are_authoritative(self, capsys):
        auth_patch, repo_patch = _patch_auth_and_repo()
        with (
            auth_patch,
            repo_patch,
            patch(
                "subprocess.run",
                return_value=_completed(stdout=_pr_json(statusCheckRollup=None), rc=0),
            ),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["Data"]["status_checks"] == []
        assert out["Data"]["status_check_total_count"] == 0

    def test_missing_new_fields_handled_gracefully(self, capsys):
        """API response lacking new fields should not crash."""
        pr = _pr_data()
        # Remove new fields to simulate old API response
        for key in ("baseRefOid", "isDraft", "mergeStateStatus",
                    "autoMergeRequest", "headRepository", "reviews"):
            pr.pop(key, None)
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run", return_value=_completed(stdout=json.dumps(pr)),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        data = out["Data"]
        assert data["base_sha"] is None
        assert data["is_draft"] is False
        assert data["merge_state_status"] is None
        assert data["auto_merge"] is False
        assert data["reviews"] == []


# ---------------------------------------------------------------------------
# Tests: author_is_bot (issue #5208)
# ---------------------------------------------------------------------------


class TestAuthorIsBot:
    """`author_is_bot` is what lets `/pr-autofix` reach tier T5.

    `classify_tier` in `test_pr_merge_ready.py` returns T5 only when
    `is_bot and (has_ci_failures or has_threads)`, and its `is_bot` parameter
    defaults to `False`. The command had no author lookup at all, so it never
    passed `--is-bot`, and every bot PR with a failing check or an unresolved
    thread was classified T2-T4 and entered the unattended thread-fix loop.

    Three states, not two. `None` means the author could not be read, which the
    consumer must be able to tell apart from a real `False` so it can fail
    closed. `test_unreadable_author_is_null_not_false` pins that distinction.

    The delegation to `github_core.bot_config` is load bearing, not stylistic,
    and it was measured rather than assumed. Replacing the two lines

        user_type = "Bot" if author.get("is_bot") is True else None
        return bool(is_bot(canonicalize_login(login), user_type))

    with the cheap alternative, `return login.lower().endswith("[bot]")`, fails
    four of these cases and passes the other five:

        test_a_hyphen_bot_suffix_is_a_bot                            (rjmurillo-bot)
        test_the_gh_author_spelling_of_the_copilot_coding_agent_is_a_bot
        test_the_copilot_reviewer_alias_is_a_bot                     (Copilot)
        test_the_api_bot_flag_is_honored_over_the_login

    Those four are the discrimination probe for the design choice. The first
    three fail on the alias table; the fourth fails because the substitution
    drops the `user_type` argument as well, so GitHub's own `is_bot` flag stops
    being consulted at all and `{"login": "somebody", "is_bot": True}` comes
    back False. This said "exactly three" and listed three names until the
    control was re-run: the substitution is one edit spanning both lines, and
    counting only the alias failures reads the docstring instead of the diff.

    The middle two are the ones that matter operationally: `app/copilot-swe-agent`
    and `Copilot` are the spellings this repository's own bot PRs arrive under,
    so a suffix test would read them as human-authored and leave issue #5208
    unfixed for the exact population it is about.
    """

    def _data(self, capsys, author):
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(stdout=_pr_json(author=author), rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        return json.loads(capsys.readouterr().out)["Data"]

    def test_a_human_login_is_not_a_bot(self, capsys):
        assert self._data(capsys, {"login": "alice"})["author_is_bot"] is False

    def test_a_bracket_bot_suffix_is_a_bot(self, capsys):
        assert self._data(capsys, {"login": "dependabot[bot]"})["author_is_bot"] is True

    def test_a_hyphen_bot_suffix_is_a_bot(self, capsys):
        assert self._data(capsys, {"login": "rjmurillo-bot"})["author_is_bot"] is True

    def test_the_gh_author_spelling_of_the_copilot_coding_agent_is_a_bot(self, capsys):
        """`app/copilot-swe-agent` carries no `[bot]` suffix and is still a bot.

        `bot_config.py`'s `_DEFAULT_BOT_ALIASES` records this spelling with the
        comment "gh pr view --json author returns this spelling", and maps it to
        `copilot-swe-agent[bot]`. A suffix test at the call site would read the
        Copilot coding agent's own PRs as human-authored, which is the exact
        population issue #5208 is about.
        """
        assert self._data(capsys, {"login": "app/copilot-swe-agent"})["author_is_bot"] is True

    def test_the_copilot_reviewer_alias_is_a_bot(self, capsys):
        """`Copilot` is a configured bot carrying no suffix of either kind."""
        assert self._data(capsys, {"login": "Copilot"})["author_is_bot"] is True

    def test_the_api_bot_flag_is_honored_over_the_login(self, capsys):
        """A login that looks human is still a bot when GitHub says so."""
        assert self._data(capsys, {"login": "somebody", "is_bot": True})["author_is_bot"] is True

    def test_a_non_boolean_api_bot_flag_falls_back_to_the_login(self, capsys):
        """Only a real `True` counts; anything else leaves the login deciding.

        Without the `is True` check, a truthy non-boolean such as the string
        `"no"` would classify every author as a bot.
        """
        assert self._data(capsys, {"login": "alice", "is_bot": "no"})["author_is_bot"] is False
        assert self._data(capsys, {"login": "alice", "is_bot": None})["author_is_bot"] is False

    def test_unreadable_author_is_null_not_false(self, capsys):
        """Three states. `False` is a claim; `None` is the absence of one.

        Collapsing these to `False` is the fail-open direction: `/pr-autofix`
        would read "not a bot" off a PR whose author GitHub never returned and
        send it into the unattended loop.
        """
        assert self._data(capsys, None)["author_is_bot"] is None
        assert self._data(capsys, {})["author_is_bot"] is None
        assert self._data(capsys, {"login": ""})["author_is_bot"] is None
        assert self._data(capsys, {"login": 7})["author_is_bot"] is None
        assert self._data(capsys, "alice")["author_is_bot"] is None

    @pytest.mark.parametrize(
        "login",
        [
            pytest.param("   ", id="spaces-only"),
            pytest.param("\t", id="tab-only"),
            pytest.param("\n", id="newline-only"),
            pytest.param(" \t \n ", id="mixed-whitespace-only"),
            pytest.param(" alice ", id="padded-human-login"),
            pytest.param(" dependabot[bot] ", id="padded-bot-login"),
            pytest.param("al ice", id="interior-space"),
        ],
    )
    def test_a_whitespace_bearing_login_is_null_not_false(self, capsys, login):
        """A login nobody could have typed is unreadable, not human.

        Same direction as `test_unreadable_author_is_null_not_false`, and the
        hole that one left. `""` is rejected by `not login`, but `"   "` is
        truthy, so it reached `is_bot`, matched no suffix and no configured
        name, and came back a real `False`.

        Negative control, measured against the pre-fix code at `49e1c1a96` by
        calling `_author_is_bot` directly: `{"login": "   "}` returned `False`
        and `{"login": "\\t"}` returned `False`, while `{"login": ""}` already
        returned `None`. A PR whose author GitHub returned blank was therefore
        forwarded to the tier producer as a human and entered the unattended
        thread-fix loop, which is the fail-open direction the `None` state
        exists to refuse.

        The padded and interior cases are rejected rather than stripped and
        classified: a whitespace-bearing login is malformed whichever end the
        whitespace sits on, and classifying `" alice "` by its stripped form
        would still hand back an unearned `False` off data GitHub cannot
        produce. Real logins are `[A-Za-z0-9-]` only.
        """
        assert self._data(capsys, {"login": login})["author_is_bot"] is None

    def test_the_whitespace_guard_does_not_reclassify_a_known_bot(self, capsys):
        """No-over-fire control for the guard above.

        A guard broad enough to reject `"   "` must not reject a name `is_bot`
        already recognizes. Enumerated on this checkout, `bot_config`'s
        `_BOT_ALIAS_MAP` keys and values together with `get_bot_authors()` are
        28 names, and none contains a whitespace character, so the two
        populations do not overlap. The three bot spellings below are the ones
        this repository's own bot PRs arrive under; a broadened guard that also
        swallowed them would leave issue #5208 unfixed while looking fixed.
        """
        for login in ("dependabot[bot]", "app/copilot-swe-agent", "Copilot"):
            assert self._data(capsys, {"login": login})["author_is_bot"] is True, login
        assert self._data(capsys, {"login": "alice"})["author_is_bot"] is False

    def test_a_missing_author_key_is_null(self, capsys):
        raw = json.loads(_pr_json())
        del raw["author"]
        auth_patch, repo_patch = _patch_auth_and_repo()
        with auth_patch, repo_patch, patch(
            "subprocess.run",
            return_value=_completed(stdout=json.dumps(raw), rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)["Data"]
        assert data["author"] is None
        assert data["author_is_bot"] is None
