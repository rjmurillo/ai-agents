"""Shared helpers for the close_pr.py tests."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

from scripts.github_core.api import RepoInfo


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


OPEN = _completed(stdout=json.dumps({"state": "OPEN"}))
DENIED = "gh: Resource not accessible by integration (HTTP 403)"


def state_reply(state: str):
    return _completed(stdout=json.dumps({"state": state}))


def pages(*comments: tuple[str, str, str]):
    """Return a paginated comment listing from (body, login, user type) tuples."""
    items = [
        {"id": 100 + index, "body": body, "user": {"login": login, "type": kind}}
        for index, (body, login, kind) in enumerate(comments)
    ]
    return _completed(stdout=json.dumps([items]))


def run_close(argv, replies):
    """Run close_pr.main against scripted gh replies; return (exit code, mock)."""
    from tests.test_close_pr import main

    with (
        patch("close_pr.assert_gh_authenticated"),
        patch("close_pr.resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
        patch("subprocess.run", side_effect=replies) as run,
    ):
        rc = main(argv)
    return rc, run


def subcommands(run):
    return [call.args[0][1:3] for call in run.call_args_list]
