#!/usr/bin/env python3
"""Tests for invoke_checkout_freshness_check.py SessionStart hook (#4689).

Covers the three cases the issue's acceptance criteria name explicitly: a
nonzero commit gap, an exact-zero gap stated (not silent), and an
unresolvable origin/main reported as a failure rather than silently read as
zero. Also covers the fetch-failed-but-stale-ref-still-answers path, since a
hard failure on every offline session would be a worse regression than the
one this hook fixes.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from unittest.mock import patch

HOOKS_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "SessionStart")
sys.path.insert(0, HOOKS_DIR)

import invoke_checkout_freshness_check as freshness

FETCH_CMD = ("git", "fetch", "origin", "+refs/heads/main:refs/remotes/origin/main", "--quiet")
REV_LIST_CMD = ("git", "rev-list", "--count", "HEAD..origin/main")


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _dispatching_run(responses: Mapping[tuple, object]):
    """Fake subprocess.run keyed on the exact argv, per testing.md rule 11.

    Raises a named AssertionError on any command not given a canned
    response, so an unexpected third git call fails loudly rather than
    silently returning ``Mock()`` truthy garbage.
    """

    def _run(cmd, **kwargs):
        key = tuple(cmd)
        if key not in responses:
            raise AssertionError(f"unstubbed git command: {cmd}")
        response = responses[key]
        if isinstance(response, Exception):
            raise response
        return response

    return _run


# --- check_checkout_freshness: the three acceptance-criteria cases --------


def test_reports_nonzero_commits_behind() -> None:
    responses = {
        FETCH_CMD: _completed(0),
        REV_LIST_CMD: _completed(0, stdout="7\n"),
    }
    with patch.object(freshness.subprocess, "run", _dispatching_run(responses)):
        result = freshness.check_checkout_freshness("/repo")

    assert result.commits_behind == 7
    assert result.fetch_succeeded is True
    assert result.error is None


def test_reports_zero_commits_behind_explicitly() -> None:
    responses = {
        FETCH_CMD: _completed(0),
        REV_LIST_CMD: _completed(0, stdout="0\n"),
    }
    with patch.object(freshness.subprocess, "run", _dispatching_run(responses)):
        result = freshness.check_checkout_freshness("/repo")

    # 0 is a real int, not a None/falsy stand-in for "did not run".
    assert result.commits_behind == 0
    assert result.error is None


def test_unresolvable_origin_main_reports_failure_not_zero() -> None:
    responses = {
        FETCH_CMD: _completed(0),
        REV_LIST_CMD: _completed(
            128, stderr="fatal: ambiguous argument 'HEAD..origin/main': unknown revision"
        ),
    }
    with patch.object(freshness.subprocess, "run", _dispatching_run(responses)):
        result = freshness.check_checkout_freshness("/repo")

    assert result.commits_behind is None
    assert result.error is not None
    assert "unknown revision" in result.error


def test_rev_list_timeout_reports_failure_not_zero() -> None:
    responses = {
        FETCH_CMD: _completed(0),
        REV_LIST_CMD: subprocess.TimeoutExpired(cmd=list(REV_LIST_CMD), timeout=15),
    }
    with patch.object(freshness.subprocess, "run", _dispatching_run(responses)):
        result = freshness.check_checkout_freshness("/repo")

    assert result.commits_behind is None
    assert result.error


def test_git_missing_reports_failure_not_zero() -> None:
    responses = {
        FETCH_CMD: FileNotFoundError("git: command not found"),
        REV_LIST_CMD: FileNotFoundError("git: command not found"),
    }
    with patch.object(freshness.subprocess, "run", _dispatching_run(responses)):
        result = freshness.check_checkout_freshness("/repo")

    assert result.commits_behind is None
    assert result.fetch_succeeded is False
    assert result.error


# --- fetch failure degrades to stale-but-stated, not a hard failure -------


def test_fetch_network_failure_still_answers_from_stale_ref() -> None:
    responses = {
        FETCH_CMD: _completed(1, stderr="fatal: unable to access 'origin': network down"),
        REV_LIST_CMD: _completed(0, stdout="3\n"),
    }
    with patch.object(freshness.subprocess, "run", _dispatching_run(responses)):
        result = freshness.check_checkout_freshness("/repo")

    assert result.commits_behind == 3
    assert result.fetch_succeeded is False
    assert result.error is None


def test_fetch_timeout_still_answers_from_stale_ref() -> None:
    responses = {
        FETCH_CMD: subprocess.TimeoutExpired(cmd=list(FETCH_CMD), timeout=15),
        REV_LIST_CMD: _completed(0, stdout="12\n"),
    }
    with patch.object(freshness.subprocess, "run", _dispatching_run(responses)):
        result = freshness.check_checkout_freshness("/repo")

    assert result.commits_behind == 12
    assert result.fetch_succeeded is False


def test_unexpected_rev_list_output_reports_failure_not_zero() -> None:
    responses = {
        FETCH_CMD: _completed(0),
        REV_LIST_CMD: _completed(0, stdout="not-a-number\n"),
    }
    with patch.object(freshness.subprocess, "run", _dispatching_run(responses)):
        result = freshness.check_checkout_freshness("/repo")

    assert result.commits_behind is None
    assert result.error is not None
    assert "not-a-number" in result.error


# --- _format_message: what actually reaches the injected context ----------


def test_format_message_states_nonzero_count() -> None:
    check = freshness.FreshnessCheck(commits_behind=42, fetch_succeeded=True, error=None)
    message = freshness._format_message(check)

    assert "42 commit(s) behind" in message
    assert "(fetch failed" not in message


def test_format_message_states_zero_explicitly() -> None:
    check = freshness.FreshnessCheck(commits_behind=0, fetch_succeeded=True, error=None)
    message = freshness._format_message(check)

    # A passing check must be distinguishable from one that did not run:
    # "0" has to appear in the text, not just be absent.
    assert "0 commits behind" in message


def test_format_message_reports_failure_and_never_says_zero() -> None:
    check = freshness.FreshnessCheck(
        commits_behind=None, fetch_succeeded=False, error="unknown revision"
    )
    message = freshness._format_message(check)

    assert "FAILED to resolve origin/main" in message
    assert "unknown revision" in message
    assert "0 commit" not in message


def test_format_message_flags_stale_count_on_fetch_failure() -> None:
    check = freshness.FreshnessCheck(commits_behind=5, fetch_succeeded=False, error=None)
    message = freshness._format_message(check)

    assert "5 commit(s) behind" in message
    assert "fetch failed" in message
    assert "may be stale" in message


# --- main(): the skip-for-consumer-repo gate runs before any git work -----


def test_main_skips_git_work_entirely_for_consumer_repo(capsys) -> None:
    with (
        patch.object(freshness, "skip_if_consumer_repo", return_value=True),
        patch.object(
            freshness,
            "check_checkout_freshness",
            side_effect=AssertionError("must not run for a consumer repo"),
        ),
        patch.object(freshness.sys, "exit", side_effect=SystemExit) as mock_exit,
    ):
        try:
            freshness.main()
        except SystemExit:
            pass

    mock_exit.assert_called_once_with(0)
    assert capsys.readouterr().out == ""


def test_main_emits_the_freshness_message_for_a_contributor_repo(capsys, tmp_path) -> None:
    canned = freshness.FreshnessCheck(commits_behind=9, fetch_succeeded=True, error=None)
    with (
        patch.object(freshness, "skip_if_consumer_repo", return_value=False),
        patch.object(freshness, "get_project_directory", return_value=str(tmp_path)),
        patch.object(freshness, "check_checkout_freshness", return_value=canned),
        patch.object(freshness, "_write_audit_log"),
    ):
        freshness.main()

    out = capsys.readouterr().out
    assert "9 commit(s) behind" in out
