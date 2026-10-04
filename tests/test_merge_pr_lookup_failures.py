"""Exit-code classification of a failed PR lookup in merge_pr.py (ADR-035).

Drives main(argv) with only subprocess.run faked, so the real auth check,
repo resolution, and envelope writers run.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / ".claude/skills/github/scripts/pr/merge_pr.py"
_SPEC = importlib.util.spec_from_file_location("merge_pr", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["merge_pr"] = _MOD
_SPEC.loader.exec_module(_MOD)

_HEAD = "a" * 40
# gh stderr for `gh pr view 999999 --repo rjmurillo/ai-agents`, captured live.
_GH_MISSING_PR = (
    "GraphQL: Could not resolve to a PullRequest with the number of 999999. "
    "(repository.pullRequest)\n"
)
_GH_MISSING_REPO = "GraphQL: Could not resolve to a Repository with the name 'o/r'. (repository)"
_PR_STATE = json.dumps({
    "state": "OPEN", "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
    "headRefName": "feature", "headRefOid": _HEAD,
})
_READBACK = json.dumps({
    "state": "MERGED", "mergeCommit": {"oid": "c" * 40}, "mergedBy": {"login": "octocat"},
    "autoMergeRequest": None, "headRefOid": _HEAD,
})
_OK = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")


def _failed(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=1, stdout=stdout, stderr=stderr)


def _drive_main(view, capsys, auth=_OK) -> tuple[int, dict, list[list[str]]]:
    """Run main() with gh answered by argv; return (exit code, envelope, gh calls)."""
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        argv = list(cmd)
        calls.append(argv)
        if argv[:3] in (["gh", "auth", "status"], ["gh", "api", "graphql"]):
            return auth
        if argv[:3] == ["gh", "pr", "view"] and "mergeCommit" in " ".join(argv):
            return subprocess.CompletedProcess(argv, 0, _READBACK, "")
        if argv[:3] == ["gh", "pr", "view"]:
            return view
        if argv[:3] == ["gh", "pr", "merge"]:
            return _OK
        raise AssertionError(f"unexpected command: {argv!r}")

    argv = ["--owner", "o", "--repo", "r", "--pull-request", "999999", "--strategy", "squash"]
    with patch("subprocess.run", side_effect=fake_run):
        try:
            code = _MOD.main(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
    out = capsys.readouterr().out
    return code, (json.loads(out) if out else {}), calls


@pytest.mark.parametrize(
    ("view", "code", "error_type"),
    [
        pytest.param(_failed(stderr=_GH_MISSING_PR), 2, "NotFound", id="AC1-gh-missing-pr"),
        pytest.param(
            _failed(stdout=_GH_MISSING_PR, stderr="warning: unrelated"), 2, "NotFound",
            id="AC1-marker-on-stdout-only",
        ),
        pytest.param(_failed(stderr="not found"), 2, "NotFound", id="AC2-legacy-wording"),
        pytest.param(_failed(stderr="gh: Not Found (HTTP 404)"), 2, "NotFound", id="AC2-any-case"),
        pytest.param(_failed(stderr="HTTP 502: Bad Gateway"), 3, "ApiError", id="AC3-external"),
        pytest.param(_failed(stderr=_GH_MISSING_REPO), 3, "ApiError", id="AC3-missing-repo"),
    ],
)
def test_failed_lookup_exit_code(view, code, error_type, capsys):
    """AC1-AC3: a failed PR lookup maps to the ADR-035 code and never merges."""
    exit_code, envelope, calls = _drive_main(view, capsys)
    assert exit_code == code
    assert envelope["Error"]["Type"] == error_type
    assert not any(c[:3] == ["gh", "pr", "merge"] for c in calls)
    if code == 2:
        gh_words = (view.stdout or view.stderr).splitlines()[0][:40]
        assert gh_words in envelope["Error"]["Message"]


def test_invalid_credentials_exit_4_before_pr_lookup(capsys):
    """AC4: a confirmed bad token exits 4 and never queries the PR."""
    bad = _failed(stderr="HTTP 401: Bad credentials (https://api.github.com/graphql)")
    exit_code, _, calls = _drive_main(_failed(stderr=_GH_MISSING_PR), capsys, auth=bad)
    assert exit_code == 4
    assert not any(c[:3] == ["gh", "pr", "view"] for c in calls)


def test_successful_lookup_still_merges(capsys):
    """AC5: the success path is unchanged by the classifier."""
    view = subprocess.CompletedProcess([], 0, _PR_STATE, "")
    exit_code, envelope, calls = _drive_main(view, capsys)
    assert exit_code == 0
    assert envelope["Success"] is True
    assert any(c[:3] == ["gh", "pr", "merge"] for c in calls)
