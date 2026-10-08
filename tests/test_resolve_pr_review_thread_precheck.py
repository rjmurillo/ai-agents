"""Thread state precheck tests for PR review resolution."""

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
    / "resolve_pr_review_thread.py"
)
if "resolve_pr_review_thread" in sys.modules:
    _MODULE = sys.modules["resolve_pr_review_thread"]
else:
    _SPEC = importlib.util.spec_from_file_location(
        "resolve_pr_review_thread",
        _SCRIPT,
    )
    assert _SPEC is not None
    assert _SPEC.loader is not None
    _MODULE = importlib.util.module_from_spec(_SPEC)
    sys.modules[_SPEC.name] = _MODULE
    _SPEC.loader.exec_module(_MODULE)
main = _MODULE.main


class TestThreadStatePrecheck:
    def test_patches_reach_executed_module_after_sys_modules_swap(self, capsys, monkeypatch):
        """A later test file can load its own copy under the same module name.

        Patches must target the module that runs main, not the sys.modules entry.
        """
        spec = importlib.util.spec_from_loader("resolve_pr_review_thread", loader=None)
        assert spec is not None
        empty = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, "resolve_pr_review_thread", empty)
        self.test_not_found_returns_skip_exit_0(capsys)

    def test_not_found_returns_skip_exit_0(self, capsys):
        with (
            patch.object(_MODULE, "assert_gh_authenticated"),
            patch.object(
                _MODULE,
                "query_thread_state",
                return_value=None,
            ),
            patch.object(
                _MODULE,
                "resolve_review_thread",
            ) as mock_resolve,
        ):
            rc = main(["--thread-id", "PRRT_abc"])
        assert rc == 0
        mock_resolve.assert_not_called()
        out = json.loads(capsys.readouterr().out)["Data"]
        assert out["action"] == "SKIP"
        assert out["reason"] == "not_found"

    def test_already_resolved_returns_skip_exit_0(self, capsys):
        resolved_state = {"id": "PRRT_abc", "isResolved": True}
        with (
            patch.object(_MODULE, "assert_gh_authenticated"),
            patch.object(
                _MODULE,
                "query_thread_state",
                return_value=resolved_state,
            ),
            patch.object(
                _MODULE,
                "resolve_review_thread",
            ) as mock_resolve,
        ):
            rc = main(["--thread-id", "PRRT_abc"])
        assert rc == 0
        mock_resolve.assert_not_called()
        out = json.loads(capsys.readouterr().out)["Data"]
        assert out["action"] == "SKIP"
        assert out["reason"] == "already_resolved"

    def test_unresolved_thread_proceeds_to_act(self, capsys):
        unresolved_state = {"id": "PRRT_abc", "isResolved": False}
        with (
            patch.object(_MODULE, "assert_gh_authenticated"),
            patch.object(
                _MODULE,
                "query_thread_state",
                return_value=unresolved_state,
            ),
            patch.object(
                _MODULE,
                "resolve_review_thread",
                return_value=True,
            ) as mock_resolve,
        ):
            rc = main(["--thread-id", "PRRT_abc"])
        assert rc == 0
        mock_resolve.assert_called_once_with("PRRT_abc")
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
            rc = main(["--thread-id", "PRRT_abc"])
        assert rc == 3
        out = json.loads(capsys.readouterr().out)["Data"]
        assert out["action"] == "SKIP"
        assert out["reason"] == "thread_state_query_failed"

    def test_wrong_pr_returns_skip_without_resolve(self, capsys):
        with (
            patch.object(_MODULE, "assert_gh_authenticated"),
            patch.object(
                _MODULE,
                "query_thread_state",
                return_value={
                    "id": "PRRT_abc",
                    "isResolved": False,
                    "pullRequest": {"number": 42},
                },
            ),
            patch.object(
                _MODULE,
                "resolve_review_thread",
            ) as mock_resolve,
        ):
            rc = main(
                [
                    "--thread-id",
                    "PRRT_abc",
                    "--expected-pull-request",
                    "99",
                ]
            )
        assert rc == 0
        mock_resolve.assert_not_called()
        out = json.loads(capsys.readouterr().out)["Data"]
        assert out["action"] == "SKIP"
        assert out["reason"] == "wrong_pull_request"

    def test_external_resolution_after_triage_skips_bulk_mutation(self, capsys):
        cached_thread = {
            "id": "PRRT_abc",
            "isResolved": False,
            "comments": {"nodes": []},
        }
        live_state = {
            "id": "PRRT_abc",
            "isResolved": True,
            "pullRequest": {"number": 10},
        }
        with (
            patch.object(_MODULE, "assert_gh_authenticated"),
            patch.object(
                _MODULE,
                "get_unresolved_threads",
                return_value=[cached_thread],
            ),
            patch.object(
                _MODULE,
                "query_thread_state",
                return_value=live_state,
            ),
            patch.object(
                _MODULE,
                "resolve_review_thread",
            ) as mock_resolve,
        ):
            rc = main(["--pull-request", "10"])
        assert rc == 0
        mock_resolve.assert_not_called()
        out = json.loads(capsys.readouterr().out)["Data"]
        assert out["action"] == "SKIP"
        assert out["skipped"] == 1
        assert out["results"][0]["reason"] == "already_resolved"
