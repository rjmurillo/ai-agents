"""Tests for add_pr_review_thread_reply.py --dry-run."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("add_pr_review_thread_reply")
main = _mod.main
build_parser = _mod.build_parser

_BASE = ["--thread-id", "PRRT_abc", "--pull-request", "42", "--body", "Fixed in abc1234"]
_HEAD = ["--expected-head-sha", "aaa111"]


def _state(*, resolved: bool = False, pull_request: int = 42, head: str = "aaa111") -> dict:
    return {
        "id": "PRRT_abc",
        "isResolved": resolved,
        "pullRequest": {
            "number": pull_request,
            "state": "OPEN",
            "headRefOid": head,
            "baseRefName": "main",
            "baseRefOid": "bbb222",
        },
    }


def _run(state, args: list[str]):
    """Run main() against one scripted thread state; return rc and the three mutation mocks."""
    with (
        patch.object(_mod, "assert_gh_authenticated"),
        patch.object(_mod, "query_thread_state", return_value=state),
        patch.object(_mod, "gh_graphql") as graphql,
        patch.object(_mod, "guard_auto_merge_before_final_thread_resolution") as guard,
    ):
        rc = main([*args, "--output-format", "json"])
    return rc, graphql, guard


def _data(capsys) -> dict:
    return json.loads(capsys.readouterr().out)["Data"]


class TestParser:
    def test_dry_run_defaults_off(self):
        assert build_parser().parse_args(_BASE).dry_run is False

    def test_dry_run_flag_sets_true(self):
        assert build_parser().parse_args([*_BASE, "--dry-run"]).dry_run is True

    def test_help_documents_dry_run_example_and_exit_codes(self, capsys):
        try:
            build_parser().parse_args(["--help"])
        except SystemExit as exc:
            assert exc.code == 0
        out = capsys.readouterr().out
        assert "--dry-run" in out
        assert "exit codes:" in out
        assert "  4  auth error" in out


class TestDryRunReply:
    def test_valid_target_reports_would_post(self, capsys):
        rc, graphql, guard = _run(_state(), [*_BASE, "--dry-run"])
        assert rc == 0
        data = _data(capsys)
        assert data["action"] == "would_post"
        assert data["dryRun"] is True
        assert data["reply_posted"] is False
        assert data["thread_id"] == "PRRT_abc"
        assert data["body_length"] == len("Fixed in abc1234")
        assert data["resolve_action"] == "SKIP"
        assert data["resolve_reason"] == "not_requested"
        graphql.assert_not_called()
        guard.assert_not_called()

    def test_missing_thread_reports_would_skip_like_a_real_run(self, capsys):
        real_rc, _, _ = _run(None, _BASE)
        real = _data(capsys)
        rc, graphql, guard = _run(None, [*_BASE, "--dry-run"])
        assert rc == real_rc == 0
        data = _data(capsys)
        assert real["action"] == "SKIP"
        assert data["action"] == "would_skip"
        assert data["reason"] == real["reason"] == "not_found"
        assert data["dryRun"] is True
        assert data["reply_posted"] is False
        graphql.assert_not_called()
        guard.assert_not_called()

    def test_already_resolved_thread_reports_would_skip(self, capsys):
        rc, graphql, guard = _run(_state(resolved=True), [*_BASE, "--dry-run"])
        assert rc == 0
        data = _data(capsys)
        assert data["action"] == "would_skip"
        assert data["reason"] == "thread_resolved"
        graphql.assert_not_called()
        guard.assert_not_called()

    def test_wrong_pull_request_reports_would_skip(self, capsys):
        rc, graphql, _ = _run(_state(pull_request=99), [*_BASE, "--dry-run"])
        assert rc == 0
        assert _data(capsys)["reason"] == "wrong_pull_request"
        graphql.assert_not_called()

    def test_state_query_failure_exits_3(self, capsys):
        with (
            patch.object(_mod, "assert_gh_authenticated"),
            patch.object(_mod, "query_thread_state", side_effect=RuntimeError("HTTP 502")),
            patch.object(_mod, "gh_graphql") as graphql,
        ):
            rc = main([*_BASE, "--dry-run", "--output-format", "json"])
        assert rc == 3
        graphql.assert_not_called()
        capsys.readouterr()

    def test_real_run_has_no_dry_run_marker(self, capsys):
        reply = {
            "addPullRequestReviewThreadReply": {
                "comment": {
                    "id": "n",
                    "databaseId": 1,
                    "url": "u",
                    "createdAt": "t",
                    "author": None,
                }
            }
        }
        with (
            patch.object(_mod, "assert_gh_authenticated"),
            patch.object(_mod, "query_thread_state", return_value=_state()),
            patch.object(_mod, "gh_graphql", return_value=reply) as graphql,
        ):
            assert main([*_BASE, "--output-format", "json"]) == 0
        data = _data(capsys)
        assert "dryRun" not in data
        assert data["action"] == "ACT"
        graphql.assert_called_once()


class TestDryRunWithResolve:
    def test_reports_both_would_post_and_would_resolve(self, capsys):
        rc, graphql, guard = _run(_state(), [*_BASE, "--resolve", *_HEAD, "--dry-run"])
        assert rc == 0
        data = _data(capsys)
        assert data["action"] == "would_post"
        assert data["resolve_action"] == "would_resolve"
        assert data["resolve_reason"] == "thread_unresolved"
        assert data["thread_resolved"] is False
        assert data["dryRun"] is True
        graphql.assert_not_called()
        guard.assert_not_called()

    def test_resolve_without_identity_flag_still_exits_2(self):
        with patch.object(_mod, "assert_gh_authenticated"):
            try:
                main([*_BASE, "--resolve", "--dry-run"])
            except SystemExit as exc:
                assert exc.code == 2
            else:
                raise AssertionError("expected exit 2")

    def test_moved_head_exits_1_and_names_no_mutation(self, capsys):
        rc, graphql, guard = _run(_state(head="ccc333"), [*_BASE, "--resolve", *_HEAD, "--dry-run"])
        assert rc == 1
        out = capsys.readouterr().out
        assert "No mutation made" in out
        assert "would_post" not in out
        graphql.assert_not_called()
        guard.assert_not_called()

    def test_already_resolved_with_resolve_reports_would_skip(self, capsys):
        rc, graphql, guard = _run(_state(resolved=True), [*_BASE, "--resolve", *_HEAD, "--dry-run"])
        assert rc == 0
        assert _data(capsys)["action"] == "would_skip"
        graphql.assert_not_called()
        guard.assert_not_called()

    def test_expected_head_sha_alone_without_resolve_still_checked(self, capsys):
        rc, graphql, _ = _run(_state(head="ccc333"), [*_BASE, *_HEAD, "--dry-run"])
        assert rc == 1
        graphql.assert_not_called()
        capsys.readouterr()
