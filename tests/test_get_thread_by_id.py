"""Tests for get_thread_by_id.py skill script."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo
from tests.skills.claude_skills_import import import_skill_script

_mod = import_skill_script(".claude/skills/github/scripts/pr/get_thread_by_id.py")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_thread_id_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_valid_args(self):
        args = build_parser().parse_args(["--thread-id", "PRRT_abc123"])
        assert args.thread_id == "PRRT_abc123"


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_invalid_thread_id_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            main(["--thread-id", "INVALID_123"])
        assert exc.value.code == 2

    def test_not_authenticated_exits_4(self):
        with patch(
            "get_thread_by_id.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--thread-id", "PRRT_abc"])
            assert exc.value.code == 4

    @pytest.mark.parametrize(
        ("error", "not_found"),
        [
            ("Could not resolve to a node with the global id of 'PRRT_abc'", True),
            # Negative control: a DNS fault is an outage, not a missing thread.
            ("Could not resolve host: api.github.com", False),
        ],
    )
    def test_thread_lookup_failure_exits_3(self, capsys, error, not_found):
        with (
            patch(
                "get_thread_by_id.assert_gh_authenticated",
            ),
            patch(
                "get_thread_by_id.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "get_thread_by_id.gh_graphql",
                side_effect=RuntimeError(error),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--thread-id", "PRRT_abc"])
            assert exc.value.code == 3
        assert ("not found" in capsys.readouterr().err) is not_found

    def test_null_node_exits_3(self):
        with (
            patch(
                "get_thread_by_id.assert_gh_authenticated",
            ),
            patch(
                "get_thread_by_id.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "get_thread_by_id.gh_graphql",
                return_value={"node": None},
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--thread-id", "PRRT_abc"])
            assert exc.value.code == 3

    def test_success(self, capsys):
        thread_data = {
            "node": {
                "id": "PRRT_abc",
                "isResolved": False,
                "isOutdated": False,
                "path": "src/main.py",
                "line": 42,
                "startLine": None,
                "diffSide": "RIGHT",
                "comments": {
                    "totalCount": 2,
                    "nodes": [
                        {
                            "id": "C1",
                            "databaseId": 100,
                            "body": "First comment",
                            "author": {"login": "alice"},
                            "createdAt": "2025-01-01T00:00:00Z",
                            "updatedAt": "2025-01-01T00:00:00Z",
                            "isMinimized": False,
                            "minimizedReason": None,
                        },
                        {
                            "id": "C2",
                            "databaseId": 101,
                            "body": "Reply",
                            "author": {"login": "bob"},
                            "createdAt": "2025-01-02T00:00:00Z",
                            "updatedAt": "2025-01-02T00:00:00Z",
                            "isMinimized": False,
                            "minimizedReason": None,
                        },
                    ],
                },
            },
        }
        with (
            patch(
                "get_thread_by_id.assert_gh_authenticated",
            ),
            patch(
                "get_thread_by_id.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "get_thread_by_id.gh_graphql",
                return_value=thread_data,
            ),
        ):
            rc = main(["--thread-id", "PRRT_abc"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["success"] is True
        assert output["thread_id"] == "PRRT_abc"
        assert output["comment_count"] == 2
        assert len(output["comments"]) == 2
        assert output["comments"][0]["author"] == "alice"
        assert output["comments"][1]["author"] == "bob"

    def test_api_error_exits_3(self):
        with (
            patch(
                "get_thread_by_id.assert_gh_authenticated",
            ),
            patch(
                "get_thread_by_id.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "get_thread_by_id.gh_graphql",
                side_effect=RuntimeError("Server error"),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--thread-id", "PRRT_abc"])
            assert exc.value.code == 3
