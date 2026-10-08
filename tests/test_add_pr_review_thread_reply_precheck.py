"""Thread state precheck tests for PR review replies."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "skills"
    / "github"
    / "scripts"
    / "pr"
    / "add_pr_review_thread_reply.py"
)
if "add_pr_review_thread_reply" in sys.modules:
    _MODULE = sys.modules["add_pr_review_thread_reply"]
else:
    _SPEC = importlib.util.spec_from_file_location(
        "add_pr_review_thread_reply",
        _SCRIPT,
    )
    assert _SPEC is not None
    assert _SPEC.loader is not None
    _MODULE = importlib.util.module_from_spec(_SPEC)
    sys.modules[_SPEC.name] = _MODULE
    _SPEC.loader.exec_module(_MODULE)
main = _MODULE.main

_UNRESOLVED_STATE: dict = {
    "id": "PRRT_abc",
    "isResolved": False,
    "pullRequest": {"number": 42},
}


class TestThreadStatePrecheck:
    def test_patches_reach_executed_module_after_sys_modules_swap(self, capsys, monkeypatch):
        """A later test file can load its own copy under the same module name.

        Patches must target the module that runs main, not the sys.modules entry.
        """
        spec = importlib.util.spec_from_loader("add_pr_review_thread_reply", loader=None)
        assert spec is not None
        empty = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, "add_pr_review_thread_reply", empty)
        self.test_resolved_thread_returns_skip_exit_0(capsys)

    def test_resolved_thread_returns_skip_exit_0(self, capsys):
        resolved_state = {"id": "PRRT_abc", "isResolved": True}
        with (
            patch.object(_MODULE, "assert_gh_authenticated"),
            patch.object(
                _MODULE,
                "query_thread_state",
                return_value=resolved_state,
            ),
            patch.object(_MODULE, "gh_graphql") as mock_gql,
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "test"])
        assert rc == 0
        mock_gql.assert_not_called()
        out = json.loads(capsys.readouterr().out)["Data"]
        assert out["action"] == "SKIP"
        assert out["reason"] == "thread_resolved"

    def test_not_found_thread_returns_skip_exit_0(self, capsys):
        with (
            patch.object(_MODULE, "assert_gh_authenticated"),
            patch.object(
                _MODULE,
                "query_thread_state",
                return_value=None,
            ),
            patch.object(_MODULE, "gh_graphql") as mock_gql,
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "test"])
        assert rc == 0
        mock_gql.assert_not_called()
        out = json.loads(capsys.readouterr().out)["Data"]
        assert out["action"] == "SKIP"
        assert out["reason"] == "not_found"

    def test_unresolved_thread_proceeds_to_act(self, capsys):
        reply_data = {
            "addPullRequestReviewThreadReply": {
                "comment": {
                    "id": "n1",
                    "databaseId": 99,
                    "url": "https://example.com",
                    "createdAt": "2025-01-01T00:00:00Z",
                    "author": {"login": "bot"},
                },
            },
        }
        with (
            patch.object(_MODULE, "assert_gh_authenticated"),
            patch.object(
                _MODULE,
                "query_thread_state",
                return_value=_UNRESOLVED_STATE,
            ),
            patch.object(
                _MODULE,
                "gh_graphql",
                return_value=reply_data,
            ),
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "LGTM"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)["Data"]
        assert out["action"] == "ACT"
        assert out["success"] is True

    def test_precheck_api_error_returns_exit_3(self, capsys):
        with (
            patch.object(_MODULE, "assert_gh_authenticated"),
            patch.object(
                _MODULE,
                "query_thread_state",
                side_effect=RuntimeError("API unavailable"),
            ),
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "test"])
        assert rc == 3
        out = json.loads(capsys.readouterr().out)["Data"]
        assert out["action"] == "SKIP"
        assert out["reason"] == "thread_state_query_failed"

    def test_wrong_pr_returns_skip_without_reply(self, capsys):
        with (
            patch.object(_MODULE, "assert_gh_authenticated"),
            patch.object(
                _MODULE,
                "query_thread_state",
                return_value=_UNRESOLVED_STATE,
            ),
            patch.object(_MODULE, "gh_graphql") as mock_gql,
        ):
            rc = main(
                [
                    "--thread-id",
                    "PRRT_abc",
                    "--pull-request",
                    "99",
                    "--body",
                    "test",
                ]
            )
        assert rc == 0
        mock_gql.assert_not_called()
        out = json.loads(capsys.readouterr().out)["Data"]
        assert out["action"] == "SKIP"
        assert out["reason"] == "wrong_pull_request"
