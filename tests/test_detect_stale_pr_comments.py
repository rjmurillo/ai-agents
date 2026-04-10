"""Tests for detect_stale_pr_comments.py skill script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

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


_mod = _import_script("detect_stale_pr_comments")
main = _mod.main
build_parser = _mod.build_parser
detect_stale_comments = _mod.detect_stale_comments
fetch_review_threads = _mod.fetch_review_threads
fetch_pr_files = _mod.fetch_pr_files


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_thread(
    thread_id: str, path: str, line: int, author: str,
) -> dict[str, object]:
    return {
        "id": thread_id,
        "isResolved": False,
        "path": path,
        "line": line,
        "comments": {
            "nodes": [
                {"author": {"login": author}, "body": "Some review comment"},
            ],
        },
    }


def _make_file_entry(filename: str) -> dict[str, str]:
    return {"filename": filename, "status": "modified"}


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_valid_pull_request(self):
        args = build_parser().parse_args(["--pull-request", "42"])
        assert args.pull_request == 42

    def test_owner_and_repo_optional(self):
        args = build_parser().parse_args(["--pull-request", "1"])
        assert args.owner == ""
        assert args.repo == ""

    def test_all_args(self):
        args = build_parser().parse_args([
            "--owner", "myorg", "--repo", "myrepo", "--pull-request", "99",
        ])
        assert args.owner == "myorg"
        assert args.repo == "myrepo"
        assert args.pull_request == 99


# ---------------------------------------------------------------------------
# Tests: detect_stale_comments - all active
# ---------------------------------------------------------------------------


class TestAllActive:
    def test_all_comments_on_existing_files(self):
        threads = [
            _make_thread("PRRT_1", "src/main.py", 10, "gemini-code-assist[bot]"),
            _make_thread("PRRT_2", "src/utils.py", 20, "copilot[bot]"),
        ]
        with patch(
            "detect_stale_pr_comments.fetch_review_threads",
            return_value=threads,
        ), patch(
            "detect_stale_pr_comments.fetch_pr_files",
            return_value={"src/main.py", "src/utils.py"},
        ):
            result = detect_stale_comments("o", "r", 1)

        assert result["Success"] is True
        assert result["StaleComments"] == 0
        assert result["ActiveComments"] == 2
        assert result["TotalComments"] == 2
        assert all(not c["IsStale"] for c in result["Comments"])


# ---------------------------------------------------------------------------
# Tests: detect_stale_comments - all stale
# ---------------------------------------------------------------------------


class TestAllStale:
    def test_all_comments_on_deleted_files(self):
        threads = [
            _make_thread("PRRT_1", "old/deleted.sh", 5, "gemini-code-assist[bot]"),
            _make_thread("PRRT_2", "old/removed.py", 15, "copilot[bot]"),
        ]

        with patch(
            "detect_stale_pr_comments.fetch_review_threads",
            return_value=threads,
        ), patch(
            "detect_stale_pr_comments.fetch_pr_files",
            return_value={"src/new_file.py"},
        ):
            result = detect_stale_comments("o", "r", 1)

        assert result["StaleComments"] == 2
        assert result["ActiveComments"] == 0
        assert all(c["IsStale"] for c in result["Comments"])
        assert all(c["Reason"] == "File not present at PR HEAD" for c in result["Comments"])


# ---------------------------------------------------------------------------
# Tests: detect_stale_comments - mixed
# ---------------------------------------------------------------------------


class TestMixed:
    def test_mixed_stale_and_active(self):
        threads = [
            _make_thread("PRRT_1", "src/keep.py", 1, "gemini-code-assist[bot]"),
            _make_thread("PRRT_2", "old/gone.sh", 10, "gemini-code-assist[bot]"),
            _make_thread("PRRT_3", "src/keep.py", 25, "copilot[bot]"),
        ]

        with patch(
            "detect_stale_pr_comments.fetch_review_threads",
            return_value=threads,
        ), patch(
            "detect_stale_pr_comments.fetch_pr_files",
            return_value={"src/keep.py"},
        ):
            result = detect_stale_comments("o", "r", 1)

        assert result["StaleComments"] == 1
        assert result["ActiveComments"] == 2
        stale = [c for c in result["Comments"] if c["IsStale"]]
        assert len(stale) == 1
        assert stale[0]["Path"] == "old/gone.sh"
        assert stale[0]["ThreadId"] == "PRRT_2"


# ---------------------------------------------------------------------------
# Tests: detect_stale_comments - no comments
# ---------------------------------------------------------------------------


class TestNoComments:
    def test_pr_with_no_review_comments(self):
        with patch(
            "detect_stale_pr_comments.fetch_review_threads",
            return_value=[],
        ), patch(
            "detect_stale_pr_comments.fetch_pr_files",
            return_value={"src/main.py"},
        ):
            result = detect_stale_comments("o", "r", 1)

        assert result["Success"] is True
        assert result["TotalComments"] == 0
        assert result["StaleComments"] == 0
        assert result["ActiveComments"] == 0
        assert result["Comments"] == []


# ---------------------------------------------------------------------------
# Tests: main - auth error
# ---------------------------------------------------------------------------


class TestAuthError:
    def test_not_authenticated_exits_4(self):
        with patch(
            "detect_stale_pr_comments.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4


# ---------------------------------------------------------------------------
# Tests: main - API failure
# ---------------------------------------------------------------------------


class TestApiFailure:
    def test_graphql_failure_exits_3(self):
        with patch(
            "detect_stale_pr_comments.assert_gh_authenticated",
        ), patch(
            "detect_stale_pr_comments.resolve_repo_params",
        ) as mock_resolve, patch(
            "detect_stale_pr_comments.fetch_review_threads",
            side_effect=RuntimeError("GraphQL transport error"),
        ):
            mock_resolve.return_value = type("R", (), {"owner": "o", "repo": "r"})()
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 3

    def test_files_api_failure_exits_3(self):
        with patch(
            "detect_stale_pr_comments.assert_gh_authenticated",
        ), patch(
            "detect_stale_pr_comments.resolve_repo_params",
        ) as mock_resolve, patch(
            "detect_stale_pr_comments.fetch_review_threads",
            return_value=[],
        ), patch(
            "detect_stale_pr_comments.fetch_pr_files",
            side_effect=RuntimeError("REST API error"),
        ):
            mock_resolve.return_value = type("R", (), {"owner": "o", "repo": "r"})()
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 3


# ---------------------------------------------------------------------------
# Tests: main - success path
# ---------------------------------------------------------------------------


class TestMainSuccess:
    def test_success_outputs_json(self, capsys):
        threads = [
            _make_thread("PRRT_1", "src/main.py", 10, "bot[bot]"),
        ]

        with patch(
            "detect_stale_pr_comments.assert_gh_authenticated",
        ), patch(
            "detect_stale_pr_comments.resolve_repo_params",
        ) as mock_resolve, patch(
            "detect_stale_pr_comments.fetch_review_threads",
            return_value=threads,
        ), patch(
            "detect_stale_pr_comments.fetch_pr_files",
            return_value={"src/main.py"},
        ):
            mock_resolve.return_value = type("R", (), {"owner": "o", "repo": "r"})()
            rc = main(["--pull-request", "42"])

        assert rc == 0
        stdout = capsys.readouterr().out
        output = json.loads(stdout)
        assert output["Success"] is True
        assert output["PullRequest"] == 42
        assert output["StaleComments"] == 0
        assert output["ActiveComments"] == 1


# ---------------------------------------------------------------------------
# Tests: thread with missing author
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_thread_with_no_author(self):
        thread = {
            "id": "PRRT_x",
            "isResolved": False,
            "path": "gone.py",
            "line": 1,
            "comments": {"nodes": [{"author": None, "body": "test"}]},
        }
        with patch(
            "detect_stale_pr_comments.fetch_review_threads",
            return_value=[thread],
        ), patch(
            "detect_stale_pr_comments.fetch_pr_files",
            return_value=set(),
        ):
            result = detect_stale_comments("o", "r", 1)

        assert result["Comments"][0]["Author"] == ""
        assert result["Comments"][0]["IsStale"] is True

    def test_thread_with_empty_comments_nodes(self):
        thread = {
            "id": "PRRT_y",
            "isResolved": False,
            "path": "src/ok.py",
            "line": 5,
            "comments": {"nodes": []},
        }
        with patch(
            "detect_stale_pr_comments.fetch_review_threads",
            return_value=[thread],
        ), patch(
            "detect_stale_pr_comments.fetch_pr_files",
            return_value={"src/ok.py"},
        ):
            result = detect_stale_comments("o", "r", 1)

        assert result["Comments"][0]["Author"] == ""
        assert result["Comments"][0]["IsStale"] is False

    def test_thread_with_no_path(self):
        thread = {
            "id": "PRRT_z",
            "isResolved": False,
            "path": None,
            "line": None,
            "comments": {"nodes": [{"author": {"login": "bot"}, "body": "x"}]},
        }
        with patch(
            "detect_stale_pr_comments.fetch_review_threads",
            return_value=[thread],
        ), patch(
            "detect_stale_pr_comments.fetch_pr_files",
            return_value={"src/a.py"},
        ):
            result = detect_stale_comments("o", "r", 1)

        # A thread with no path should not be marked stale
        assert result["Comments"][0]["IsStale"] is False
