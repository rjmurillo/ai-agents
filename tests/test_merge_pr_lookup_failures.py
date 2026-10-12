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
# A private module name: test_merge_pr.py owns sys.modules["merge_pr"] and patches
# "merge_pr.*", so re-registering that name here would break its patches.
_MODULE_NAME = "merge_pr_under_lookup_test"
_SPEC = importlib.util.spec_from_file_location(_MODULE_NAME, _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules[_MODULE_NAME] = _MOD
_SPEC.loader.exec_module(_MOD)

_HEAD = "a" * 40
# gh stderr for `gh pr view 999999 --repo rjmurillo/ai-agents`, captured live.
_GH_MISSING_PR = (
    "GraphQL: Could not resolve to a PullRequest with the number of 999999. "
    "(repository.pullRequest)\n"
)
_GH_MISSING_REPO = "GraphQL: Could not resolve to a Repository with the name 'o/r'. (repository)"
_PR_STATE = json.dumps(
    {
        "state": "OPEN",
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "headRefName": "feature",
        "headRefOid": _HEAD,
    }
)
_READBACK = json.dumps(
    {
        "state": "MERGED",
        "mergeCommit": {"oid": "c" * 40},
        "mergedBy": {"login": "octocat"},
        "autoMergeRequest": None,
        "headRefOid": _HEAD,
    }
)
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
            _failed(stdout=_GH_MISSING_PR, stderr="warning: unrelated"),
            2,
            "NotFound",
            id="AC1-marker-on-stdout-only",
        ),
        pytest.param(_failed(stderr="not found"), 2, "NotFound", id="AC2-legacy-wording"),
        pytest.param(_failed(stderr="gh: Not Found (HTTP 404)"), 2, "NotFound", id="AC2-any-case"),
        pytest.param(_failed(stderr="HTTP 502: Bad Gateway"), 3, "ApiError", id="AC3-external"),
        pytest.param(_failed(stderr=_GH_MISSING_REPO), 2, "NotFound", id="AC6-missing-repo-stderr"),
        pytest.param(
            _failed(stdout=_GH_MISSING_REPO, stderr="warning: unrelated"),
            2,
            "NotFound",
            id="AC6-missing-repo-stdout-only",
        ),
        pytest.param(
            _failed(stderr=_GH_MISSING_REPO.upper()),
            2,
            "NotFound",
            id="AC6-missing-repo-any-case",
        ),
        pytest.param(
            _failed(stderr="HTTP 500: could not resolve host"),
            3,
            "ApiError",
            id="AC3-resolve-wording-is-not-a-repo",
        ),
    ],
)
def test_failed_lookup_exit_code(view, code, error_type, capsys):
    """AC1-AC3, AC6: a failed PR lookup maps to the ADR-035 code and never merges."""
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


def _drive_default_strategy(settings, capsys) -> tuple[int, dict, list[list[str]]]:
    """Run main() without --strategy so repository-settings discovery runs first."""
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        argv = list(cmd)
        calls.append(argv)
        if argv[:3] == ["gh", "auth", "status"]:
            return _OK
        if argv[:2] == ["gh", "api"] and argv[2].startswith("repos/"):
            return settings
        raise AssertionError(f"unexpected command: {argv!r}")

    argv = ["--owner", "o", "--repo", "missing", "--pull-request", "42"]
    with patch("subprocess.run", side_effect=fake_run):
        try:
            code = _MOD.main(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
    out = capsys.readouterr().out
    return code, (json.loads(out) if out else {}), calls


@pytest.mark.parametrize(
    ("settings", "code", "error_type"),
    [
        pytest.param(
            _failed(stderr="gh: Not Found (HTTP 404)"),
            2,
            "NotFound",
            id="missing-repo-settings-404",
        ),
        pytest.param(
            _failed(stderr="HTTP 502: Bad Gateway"),
            3,
            "ApiError",
            id="settings-gateway-error-stays-retryable",
        ),
    ],
)
def test_default_strategy_settings_failure_exit_code(settings, code, error_type, capsys):
    """A 404 on repository settings is a missing repo (exit 2); other failures stay 3."""
    exit_code, envelope, calls = _drive_default_strategy(settings, capsys)
    assert exit_code == code
    assert envelope["Error"]["Type"] == error_type
    assert not any(c[:3] == ["gh", "pr", "merge"] for c in calls)


# Issue #6164: exit 3 messages must not carry raw gh output (CWE-117, CWE-209).
_TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3"
_SHA_TOKEN = "b" * 40
_HOSTILE = f"HTTP 502: Bad Gateway token={_TOKEN}\nforged: ok\r\nsha={_SHA_TOKEN}"


def _assert_envelope_is_safe(envelope: dict) -> None:
    """The error message holds neither a token nor a line break."""
    message = envelope["Error"]["Message"]
    assert _TOKEN not in message
    assert _SHA_TOKEN not in message
    assert "[REDACTED]" in message
    assert "\n" not in message
    assert "\r" not in message


def test_pr_state_failure_sanitizes_gh_output(capsys):
    """AC1, AC2: the exit 3 'Failed to get PR state' message is redacted and collapsed."""
    exit_code, envelope, _ = _drive_main(_failed(stderr=_HOSTILE), capsys)
    assert exit_code == 3
    assert envelope["Error"]["Type"] == "ApiError"
    assert envelope["Error"]["Message"].startswith("Failed to get PR state: HTTP 502")
    _assert_envelope_is_safe(envelope)


def test_pr_state_failure_falls_back_to_stdout_and_bounds_length(capsys):
    """AC1: stdout is used when stderr is empty, and the detail is capped at 200 chars."""
    view = _failed(stdout=_HOSTILE + " x" * 400, stderr="")
    exit_code, envelope, _ = _drive_main(view, capsys)
    assert exit_code == 3
    _assert_envelope_is_safe(envelope)
    detail = envelope["Error"]["Message"].removeprefix("Failed to get PR state: ")
    assert detail.endswith("...")
    assert len(detail) <= 203


def _drive_merge_failure(merge, capsys) -> tuple[int, dict]:
    """Run main() with `gh pr merge` failing as given and the readback query failing."""

    def fake_run(cmd, **kwargs):
        argv = list(cmd)
        if argv[:3] == ["gh", "auth", "status"]:
            return _OK
        if argv[:3] == ["gh", "pr", "view"] and "mergeCommit" in " ".join(argv):
            return _failed(stderr="readback unavailable")
        if argv[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(argv, 0, _PR_STATE, "")
        if argv[:3] == ["gh", "pr", "merge"]:
            return merge
        raise AssertionError(f"unexpected command: {argv!r}")

    argv = ["--owner", "o", "--repo", "r", "--pull-request", "999999", "--strategy", "squash"]
    with patch("subprocess.run", side_effect=fake_run):
        try:
            code = _MOD.main(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_merge_failure_sanitizes_gh_output(capsys):
    """AC1, AC2: the exit 3 'Failed to merge PR' message is redacted and collapsed."""
    exit_code, envelope = _drive_merge_failure(_failed(stderr=_HOSTILE), capsys)
    assert exit_code == 3
    assert envelope["Error"]["Type"] == "ApiError"
    assert envelope["Error"]["Message"].startswith("Failed to merge PR #999999: HTTP 502")
    _assert_envelope_is_safe(envelope)
    original = envelope["Data"]["audit"]["original_error"]
    assert original.startswith("Failed to merge PR #999999: HTTP 502")
    assert _TOKEN not in original
    assert _SHA_TOKEN not in original
    assert "\n" not in original


def test_default_strategy_settings_failure_sanitizes_gh_output(capsys):
    """AC1, AC2: the exit 3 repository-settings message is redacted and collapsed."""
    exit_code, envelope, _ = _drive_default_strategy(_failed(stderr=_HOSTILE), capsys)
    assert exit_code == 3
    assert envelope["Error"]["Type"] == "ApiError"
    assert envelope["Error"]["Message"].startswith("Failed to query repository settings")
    _assert_envelope_is_safe(envelope)
