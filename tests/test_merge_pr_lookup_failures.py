"""Exit-code classification of a failed PR lookup in merge_pr.py.

Drives main(argv) with only subprocess.run faked, so the real auth check,
repo resolution, and envelope writers run. Exit codes follow ADR-035.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "pr" / "merge_pr.py"
)


def _import_merge_pr():
    spec = importlib.util.spec_from_file_location("merge_pr", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["merge_pr"] = mod
    spec.loader.exec_module(mod)
    return mod


main = _import_merge_pr().main

_HEAD = "a" * 40

# gh stderr for `gh pr view 999999 --repo rjmurillo/ai-agents`, captured live.
_GH_MISSING_PR = (
    "GraphQL: Could not resolve to a PullRequest with the number of 999999. "
    "(repository.pullRequest)\n"
)


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _pr_state() -> str:
    return json.dumps({
        "state": "OPEN", "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
        "headRefName": "feature", "headRefOid": _HEAD,
    })


def _readback() -> str:
    return json.dumps({
        "state": "MERGED", "mergeCommit": {"oid": "c" * 40},
        "mergedBy": {"login": "octocat"}, "autoMergeRequest": None,
        "headRefOid": _HEAD,
    })


class _ArgvGh:
    """Answer each gh call by its argv; only real gh boundaries are faked.

    auth: CompletedProcess for `gh auth status` and the GraphQL viewer probe.
    view: CompletedProcess for the `gh pr view` state query.
    """

    def __init__(self, *, view, auth=None):
        self.auth = auth if auth is not None else _completed(rc=0)
        self.view = view
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **kwargs):
        argv = list(cmd)
        self.calls.append(argv)
        if argv[:3] in (["gh", "auth", "status"], ["gh", "api", "graphql"]):
            return self.auth
        if argv[:3] == ["gh", "pr", "view"]:
            if "mergeCommit" in " ".join(argv):
                return _completed(stdout=_readback())
            return self.view
        if argv[:3] == ["gh", "pr", "merge"]:
            return _completed(rc=0)
        raise AssertionError(f"unexpected command: {argv!r}")

    def ran(self, *prefix: str) -> bool:
        return any(c[: len(prefix)] == list(prefix) for c in self.calls)


def _drive_main(fake: _ArgvGh, capsys) -> tuple[int, str]:
    """Run main() with only subprocess.run faked; return (exit code, stdout)."""
    argv = [
        "--owner", "o", "--repo", "r", "--pull-request", "999999",
        "--strategy", "squash",
    ]
    with patch("subprocess.run", side_effect=fake):
        try:
            code = main(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, capsys.readouterr().out


def _error_type(stdout: str) -> str:
    return json.loads(stdout)["Error"]["Type"]


def test_could_not_resolve_pull_request_exits_2(capsys):
    """AC1: gh's real missing-PR message is a not-found (exit 2)."""
    fake = _ArgvGh(view=_completed(rc=1, stderr=_GH_MISSING_PR))
    code, out = _drive_main(fake, capsys)
    assert code == 2
    assert _error_type(out) == "NotFound"
    assert not fake.ran("gh", "pr", "merge")


def test_missing_pr_message_on_stdout_exits_2(capsys):
    """AC1: the marker counts when gh writes it to stdout instead of stderr."""
    code, out = _drive_main(_ArgvGh(view=_completed(rc=1, stdout=_GH_MISSING_PR)), capsys)
    assert code == 2
    assert _error_type(out) == "NotFound"


@pytest.mark.parametrize("stderr", ["not found", "gh: Not Found (HTTP 404)"])
def test_not_found_wording_any_case_exits_2(stderr, capsys):
    """AC2: the older "not found" wording still maps to exit 2, in any case."""
    code, out = _drive_main(_ArgvGh(view=_completed(rc=1, stderr=stderr)), capsys)
    assert code == 2
    assert _error_type(out) == "NotFound"


def test_other_lookup_failure_exits_3(capsys):
    """AC3: a genuine external failure stays exit 3."""
    fake = _ArgvGh(view=_completed(rc=1, stderr="HTTP 502: Bad Gateway"))
    code, out = _drive_main(fake, capsys)
    assert code == 3
    assert _error_type(out) == "ApiError"


def test_invalid_credentials_exit_4_before_pr_lookup(capsys):
    """AC4: a confirmed bad token exits 4 and never queries the PR."""
    bad = _completed(rc=1, stderr="HTTP 401: Bad credentials (https://api.github.com/graphql)")
    fake = _ArgvGh(auth=bad, view=_completed(rc=1, stderr=_GH_MISSING_PR))
    code, _ = _drive_main(fake, capsys)
    assert code == 4
    assert not fake.ran("gh", "pr", "view")


def test_successful_lookup_still_merges(capsys):
    """AC5: the success path is unchanged by the classifier."""
    fake = _ArgvGh(view=_completed(stdout=_pr_state()))
    code, out = _drive_main(fake, capsys)
    assert code == 0
    assert json.loads(out)["Success"] is True
    assert fake.ran("gh", "pr", "merge")
