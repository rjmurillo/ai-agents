"""get_pr_checks.py --wait reaches github_core.api.wait_for_pr_event between reads."""

from __future__ import annotations

from unittest.mock import patch

from scripts.github_core.api import RepoInfo
from tests.test_get_pr_checks import (
    _FRESH,
    _RULESET,
    _RUN_TESTS_OK,
    _VALIDATE_OK,
    _aged_rollup,
    _mod,
    main,
)


class TestWaitUsesPrEventHelper:
    """--wait reaches github_core.api.wait_for_pr_event between reads.

    The two cases differ only in what the helper reports. A twenty second
    budget is two ten second windows, so a timeout wait ends the run after one
    wait, while an event wake does not spend a window and keeps reading until
    the queued check reports.
    """

    def _run(self, outcome, capsys):
        queued = _aged_rollup([_RUN_TESTS_OK], _FRESH)
        done = _aged_rollup([_RUN_TESTS_OK, _VALIDATE_OK], _FRESH)
        with (
            patch("get_pr_checks.assert_gh_authenticated"),
            patch(
                "get_pr_checks.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("get_pr_checks.gh_graphql", side_effect=[queued, queued, done]),
            patch("get_pr_checks.fetch_ruleset_required_contexts", return_value=_RULESET),
            patch("get_pr_checks.time.monotonic", return_value=0.0),
            patch("get_pr_checks.wait_for_pr_event", return_value=outcome) as wait,
        ):
            rc = main(
                [
                    "--pull-request",
                    "1",
                    "--wait",
                    "--timeout-seconds",
                    "20",
                    "--output-format",
                    "json",
                ]
            )
        capsys.readouterr()
        return rc, wait

    def test_event_wakes_do_not_spend_the_iteration_budget(self, capsys):
        rc, wait = self._run("event", capsys)

        assert rc == 0
        assert wait.call_count == 2
        wait.assert_called_with(
            "https://github.com/o/r/pull/1",
            _mod.CHECK_EVENTS,
            10,
            min_seconds=3,
        )

    def test_window_timeout_spends_the_budget_like_a_sleep(self, capsys):
        rc, wait = self._run("timeout", capsys)

        assert rc == 7
        assert wait.call_count == 1
