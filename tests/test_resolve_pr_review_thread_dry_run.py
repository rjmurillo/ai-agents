"""Tests for resolve_pr_review_thread.py --dry-run."""

from __future__ import annotations

import importlib.util
import json
import subprocess
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


_mod = _import_script("resolve_pr_review_thread")
main = _mod.main
build_parser = _mod.build_parser

_REPO_VIEW = subprocess.CompletedProcess(
    args=[], returncode=0, stdout=json.dumps({"owner": {"login": "o"}, "name": "r"}), stderr=""
)
_SINGLE = ["--thread-id", "PRRT_abc", "--expected-pull-request", "42", "--output-format", "json"]
_BATCH = ["--pull-request", "42", "--all", "--output-format", "json"]


def _thread_node(*, resolved: bool = False, pull_request: int = 42) -> dict:
    return {
        "node": {"id": "PRRT_abc", "isResolved": resolved, "pullRequest": {"number": pull_request}}
    }


def _threads_page(ids, *, resolved=False, cursor=None, has_next=False):
    return {
        "repository": {
            "pullRequest": {
                "reviewThreads": {
                    "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                    "nodes": [
                        {"id": i, "isResolved": resolved, "comments": {"nodes": []}} for i in ids
                    ],
                },
            },
        },
    }


def _data(capsys) -> dict:
    return json.loads(capsys.readouterr().out)["Data"]


def _run_single(node: dict, extra: list[str]):
    """Run single-thread mode; return rc and the mutation mock."""
    with (
        patch.object(_mod, "assert_gh_authenticated"),
        patch.object(_mod, "gh_graphql", return_value=node),
        patch.object(_mod, "resolve_review_thread") as mutation,
    ):
        rc = main([*_SINGLE, *extra])
    return rc, mutation


class TestParser:
    def test_dry_run_defaults_off(self):
        assert build_parser().parse_args(["--thread-id", "PRRT_abc"]).dry_run is False

    def test_dry_run_flag_sets_true(self):
        assert build_parser().parse_args(["--thread-id", "PRRT_abc", "--dry-run"]).dry_run is True

    def test_help_documents_dry_run_example_and_exit_codes(self, capsys):
        try:
            build_parser().parse_args(["--help"])
        except SystemExit as exc:
            assert exc.code == 0
        out = capsys.readouterr().out
        assert "--dry-run" in out
        assert "exit codes:" in out
        assert "  3  external error" in out


class TestSingleThreadDryRun:
    def test_unresolved_thread_reports_would_resolve(self, capsys):
        rc, mutation = _run_single(_thread_node(), ["--dry-run"])
        assert rc == 0
        data = _data(capsys)
        assert data["action"] == "would_resolve"
        assert data["reason"] == "thread_unresolved"
        assert data["dryRun"] is True
        assert data["thread_id"] == "PRRT_abc"
        mutation.assert_not_called()

    def test_never_sends_the_resolve_mutation(self):
        queries: list[str] = []

        def fake_graphql(query: str, variables: dict):
            queries.append(query)
            return _thread_node()

        with (
            patch.object(_mod, "assert_gh_authenticated"),
            patch.object(_mod, "gh_graphql", side_effect=fake_graphql),
        ):
            assert main([*_SINGLE, "--dry-run"]) == 0
        assert queries
        assert not any("resolveReviewThread(" in q for q in queries)

    def test_missing_thread_reports_would_skip_like_a_real_run(self, capsys):
        real_rc, _ = _run_single({"node": None}, [])
        real = _data(capsys)
        rc, mutation = _run_single({"node": None}, ["--dry-run"])
        data = _data(capsys)
        assert rc == real_rc == 0
        assert real["action"] == "SKIP"
        assert data["action"] == "would_skip"
        assert data["reason"] == real["reason"] == "not_found"
        assert data["dryRun"] is True
        mutation.assert_not_called()

    def test_already_resolved_reports_would_skip(self, capsys):
        rc, mutation = _run_single(_thread_node(resolved=True), ["--dry-run"])
        assert rc == 0
        data = _data(capsys)
        assert data["action"] == "would_skip"
        assert data["reason"] == "already_resolved"
        mutation.assert_not_called()

    def test_wrong_pull_request_reports_would_skip(self, capsys):
        rc, mutation = _run_single(_thread_node(pull_request=99), ["--dry-run"])
        assert rc == 0
        assert _data(capsys)["reason"] == "wrong_pull_request"
        mutation.assert_not_called()

    def test_state_query_failure_exits_3_as_a_real_run_does(self, capsys):
        with (
            patch.object(_mod, "assert_gh_authenticated"),
            patch.object(_mod, "gh_graphql", side_effect=RuntimeError("HTTP 502")),
            patch.object(_mod, "resolve_review_thread") as mutation,
        ):
            rc = main([*_SINGLE, "--dry-run"])
        assert rc == 3
        mutation.assert_not_called()
        capsys.readouterr()

    def test_invalid_expected_pull_request_still_exits_2(self):
        with patch.object(_mod, "assert_gh_authenticated"):
            rc = main(["--thread-id", "PRRT_abc", "--expected-pull-request", "0", "--dry-run"])
        assert rc == 2

    def test_real_run_has_no_dry_run_marker(self, capsys):
        with (
            patch.object(_mod, "assert_gh_authenticated"),
            patch.object(_mod, "gh_graphql", return_value=_thread_node()),
            patch.object(_mod, "resolve_review_thread", return_value=True) as mutation,
        ):
            assert main(_SINGLE) == 0
        data = _data(capsys)
        assert "dryRun" not in data
        assert data["action"] == "ACT"
        mutation.assert_called_once_with("PRRT_abc")


class TestBatchDryRun:
    def _run(self, unresolved, decisions):
        with (
            patch.object(_mod, "assert_gh_authenticated"),
            patch.object(_mod, "get_unresolved_threads", return_value=unresolved),
            patch.object(_mod, "_thread_decision", side_effect=decisions),
            patch.object(_mod, "resolve_review_thread") as mutation,
        ):
            rc = main([*_BATCH, "--dry-run"])
        return rc, mutation

    def test_reports_would_resolve_and_would_skip_counts(self, capsys):
        threads = [{"id": "t1", "comments": {"nodes": []}}, {"id": "t2", "comments": {"nodes": []}}]
        rc, mutation = self._run(
            threads, [("ACT", "thread_unresolved"), ("SKIP", "already_resolved")]
        )
        assert rc == 0
        data = _data(capsys)
        assert data["dryRun"] is True
        assert data["action"] == "would_resolve"
        assert data["wouldResolve"] == 1
        assert data["resolved"] == 0
        assert data["skipped"] == 1
        assert data["failed"] == 0
        assert [r["action"] for r in data["results"]] == ["would_resolve", "would_skip"]
        mutation.assert_not_called()

    def test_all_skipped_reports_would_skip(self, capsys):
        rc, mutation = self._run(
            [{"id": "t1", "comments": {"nodes": []}}], [("SKIP", "wrong_pull_request")]
        )
        assert rc == 0
        data = _data(capsys)
        assert data["action"] == "would_skip"
        assert data["wouldResolve"] == 0
        mutation.assert_not_called()

    def test_no_unresolved_threads_marks_dry_run(self, capsys):
        rc, mutation = self._run([], [])
        assert rc == 0
        data = _data(capsys)
        assert data["action"] == "would_skip"
        assert data["reason"] == "no_unresolved_threads"
        assert data["dryRun"] is True
        mutation.assert_not_called()

    def test_state_query_failure_exits_3(self, capsys):
        threads = [{"id": "t1", "comments": {"nodes": []}}]
        rc, mutation = self._run(threads, [RuntimeError("HTTP 500")])
        assert rc == 3
        mutation.assert_not_called()
        capsys.readouterr()

    def test_listing_failure_exits_3(self, capsys):
        with (
            patch.object(_mod, "assert_gh_authenticated"),
            patch.object(_mod, "get_unresolved_threads", side_effect=RuntimeError("API fail")),
            patch.object(_mod, "resolve_review_thread") as mutation,
        ):
            rc = main([*_BATCH, "--dry-run"])
        assert rc == 3
        mutation.assert_not_called()
        capsys.readouterr()

    def test_missing_cursor_fails_loud_and_never_mutates(self, capsys):
        first = _threads_page(["t0"], resolved=True, has_next=True)
        with (
            patch.object(_mod, "assert_gh_authenticated"),
            patch("subprocess.run", return_value=_REPO_VIEW),
            patch.object(_mod, "gh_graphql", return_value=first),
            patch.object(_mod, "resolve_review_thread") as mutation,
        ):
            rc = main([*_BATCH, "--dry-run"])
        out = capsys.readouterr().out
        assert rc == 3
        assert "no_unresolved_threads" not in out
        mutation.assert_not_called()

    def test_thread_on_page_two_is_previewed_not_resolved(self, capsys):
        first = _threads_page(["t0"], resolved=True, cursor="CUR1", has_next=True)
        second = _threads_page(["t100"], resolved=False)
        with (
            patch.object(_mod, "assert_gh_authenticated"),
            patch("subprocess.run", return_value=_REPO_VIEW),
            patch.object(_mod, "gh_graphql", side_effect=[first, second]),
            patch.object(_mod, "_thread_decision", return_value=("ACT", "thread_unresolved")),
            patch.object(_mod, "resolve_review_thread") as mutation,
        ):
            rc = main([*_BATCH, "--dry-run"])
        assert rc == 0
        data = _data(capsys)
        assert data["wouldResolve"] == 1
        assert data["results"][0]["thread_id"] == "t100"
        mutation.assert_not_called()
