"""Tests for the REST-backed bot reviewer assignment (issue #4335)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1] / ".github" / "scripts" / "assign_bot_reviewer.py"
)


def _import_script():
    spec = importlib.util.spec_from_file_location("assign_bot_reviewer", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["assign_bot_reviewer"] = module
    spec.loader.exec_module(module)
    return module


_mod = _import_script()

# Captured from the failing job on PR #4328, run 30766665304.
GRAPHQL_QUOTA = "GraphQL: API rate limit already exceeded for user ID 6811113."
REST_QUOTA_403 = "gh: API rate limit exceeded for user ID 6811113 (HTTP 403)"
BAD_CREDENTIALS = "gh: Bad credentials (HTTP 401)"
NOT_FOUND = "gh: Not Found (HTTP 404)"


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=["gh"], returncode=rc, stdout=stdout, stderr=stderr)


def test_uses_the_rest_requested_reviewers_endpoint():
    """gh pr edit --add-reviewer goes through GraphQL; REST does not."""
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _completed(rc=0)

    with patch("subprocess.run", side_effect=fake_run):
        assert _mod.assign_reviewer("rjmurillo/ai-agents", "4328", "rjmurillo-bot") == 0

    assert calls == [
        [
            "gh",
            "api",
            "--method",
            "POST",
            "repos/rjmurillo/ai-agents/pulls/4328/requested_reviewers",
            "-f",
            "reviewers[]=rjmurillo-bot",
        ]
    ]


def test_quota_refusal_is_retried_and_then_succeeds():
    """The observed refusals cleared on their own within about a minute."""
    responses = [
        _completed(stderr=GRAPHQL_QUOTA, rc=1),
        _completed(stderr=REST_QUOTA_403, rc=1),
        _completed(rc=0),
    ]
    delays: list[float] = []

    with patch("subprocess.run", side_effect=responses):
        code = _mod.assign_reviewer(
            "rjmurillo/ai-agents", "4328", "rjmurillo-bot", sleep=delays.append
        )

    assert code == 0
    assert delays == list(_mod.REFUSAL_BACKOFF_SECONDS)


def test_persistent_quota_refusal_exits_external():
    responses = [_completed(stderr=GRAPHQL_QUOTA, rc=1)] * _mod.MAX_ATTEMPTS

    with patch("subprocess.run", side_effect=responses):
        code = _mod.assign_reviewer(
            "rjmurillo/ai-agents", "4328", "rjmurillo-bot", sleep=lambda _s: None
        )

    assert code == 3


def test_bad_credentials_fails_fast_without_retry():
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _completed(stderr=BAD_CREDENTIALS, rc=1)

    with patch("subprocess.run", side_effect=fake_run):
        code = _mod.assign_reviewer(
            "rjmurillo/ai-agents", "4328", "rjmurillo-bot", sleep=lambda _s: None
        )

    assert code == 4
    assert len(calls) == 1


def test_permanent_non_auth_failure_is_not_retried():
    """A 404 will not clear; burning the retry budget on it wastes quota."""
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _completed(stderr=NOT_FOUND, rc=1)

    with patch("subprocess.run", side_effect=fake_run):
        code = _mod.assign_reviewer(
            "rjmurillo/ai-agents", "4328", "rjmurillo-bot", sleep=lambda _s: None
        )

    assert code == 3
    assert len(calls) == 1


def test_timeout_is_treated_as_transient():
    responses = [
        subprocess.TimeoutExpired(cmd="gh", timeout=30),
        _completed(rc=0),
    ]

    with patch("subprocess.run", side_effect=responses):
        code = _mod.assign_reviewer(
            "rjmurillo/ai-agents", "4328", "rjmurillo-bot", sleep=lambda _s: None
        )

    assert code == 0


def test_missing_gh_is_a_config_error():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        code = _mod.assign_reviewer("rjmurillo/ai-agents", "4328", "rjmurillo-bot")

    assert code == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["--repo", "rjmurillo/ai-agents", "--pull-request", "abc", "--reviewer", "b"],
        ["--repo", "not-a-slug", "--pull-request", "1", "--reviewer", "b"],
    ],
)
def test_main_rejects_malformed_arguments(argv):
    assert _mod.main(argv) == 2


def test_main_passes_valid_arguments_through():
    with patch("subprocess.run", return_value=_completed(rc=0)):
        code = _mod.main(
            ["--repo", "rjmurillo/ai-agents", "--pull-request", "4328", "--reviewer", "bot"]
        )

    assert code == 0


def test_failure_message_reports_attempts_actually_made(capsys):
    """A permanent refusal breaks out on attempt 1; do not claim three."""
    with patch("subprocess.run", return_value=_completed(stderr=NOT_FOUND, rc=1)):
        _mod.assign_reviewer(
            "rjmurillo/ai-agents", "4328", "rjmurillo-bot", sleep=lambda _s: None
        )

    assert "after 1 attempt(s)" in capsys.readouterr().err


def test_failure_message_reports_the_full_budget_when_it_is_spent(capsys):
    responses = [_completed(stderr=GRAPHQL_QUOTA, rc=1)] * _mod.MAX_ATTEMPTS

    with patch("subprocess.run", side_effect=responses):
        _mod.assign_reviewer(
            "rjmurillo/ai-agents", "4328", "rjmurillo-bot", sleep=lambda _s: None
        )

    assert f"after {_mod.MAX_ATTEMPTS} attempt(s)" in capsys.readouterr().err


def test_retry_budget_reaches_the_measured_recovery():
    """The retry has to outlast the refusal, or it only burns extra requests.

    Issue #4326 measured the refusal clearing "about a minute" later. The 5s and
    10s ladder this started with spent 15s, entirely inside that window, so all
    three attempts hit the same condition and the job failed anyway.
    """
    responses = [_completed(stderr=GRAPHQL_QUOTA, rc=1)] * _mod.MAX_ATTEMPTS
    sleeps: list[float] = []

    with patch("subprocess.run", side_effect=responses):
        _mod.assign_reviewer(
            "rjmurillo/ai-agents", "4328", "rjmurillo-bot", sleep=sleeps.append
        )

    assert sleeps == list(_mod.REFUSAL_BACKOFF_SECONDS)
    assert sum(sleeps) >= 45.0


def test_tolerate_external_downgrades_a_spent_budget_to_success(capsys):
    responses = [_completed(stderr=GRAPHQL_QUOTA, rc=1)] * _mod.MAX_ATTEMPTS

    with patch("subprocess.run", side_effect=responses), patch("time.sleep"):
        code = _mod.main(
            [
                "--repo",
                "rjmurillo/ai-agents",
                "--pull-request",
                "4328",
                "--reviewer",
                "rjmurillo-bot",
                "--tolerate-external",
            ]
        )

    assert code == 0
    assert "::warning::Bot reviewer not assigned" in capsys.readouterr().out


def test_tolerate_external_still_fails_on_an_auth_error(capsys):
    """A revoked BOT_PAT must stay visible.

    This is what `continue-on-error: true` on the step swallowed: the exit-4
    branch had no surviving observer, so an expired secret read as a green job
    forever and the only symptom was a missing bot review.
    """
    with patch("subprocess.run", return_value=_completed(stderr=BAD_CREDENTIALS, rc=1)):
        code = _mod.main(
            [
                "--repo",
                "rjmurillo/ai-agents",
                "--pull-request",
                "4328",
                "--reviewer",
                "rjmurillo-bot",
                "--tolerate-external",
            ]
        )

    assert code == 4
    assert "::warning::Bot reviewer not assigned" not in capsys.readouterr().out


def test_tolerate_external_still_fails_on_a_config_error():
    assert (
        _mod.main(
            [
                "--repo",
                "not-a-repo",
                "--pull-request",
                "4328",
                "--reviewer",
                "rjmurillo-bot",
                "--tolerate-external",
            ]
        )
        == 2
    )


def test_workflow_scopes_the_tolerance_to_the_script_not_the_step():
    """No blanket `continue-on-error` on the step that can swallow exit 4."""
    import yaml

    workflow = yaml.safe_load(
        (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "auto-assign-reviewer.yml"
        ).read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["assign-reviewer"]["steps"]
    assign = next(s for s in steps if "assign_bot_reviewer.py" in s.get("run", ""))

    assert assign.get("continue-on-error") is None
    assert "--tolerate-external" in assign["run"]
