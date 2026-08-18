"""Tests for ai-review context construction."""
# taste-lint: ignore file-size -- this legacy regression harness still needs
# one-file visibility across the ai-review context matrix while the functional
# split continues in focused companion modules.

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/ci/build_ai_review_context.py"


def _import_script():
    spec = importlib.util.spec_from_file_location("build_ai_review_context", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_ai_review_context"] = module
    spec.loader.exec_module(module)
    return module


_mod = _import_script()
CommandResult = _mod.CommandResult
ReviewContext = _mod.ReviewContext


def _pulls_payload(number: int, title: str, body: str) -> str:
    """One REST pulls response, the shape fetch_pr_metadata reads."""
    return json.dumps({"number": number, "title": title, "body": body})


def test_builds_full_pr_context(monkeypatch: pytest.MonkeyPatch):
    """Small PR diffs become full context with title and body."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(_pulls_payload(7, 'Fix `$bad" title\\\\', "Body text"), "", 0)
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult("diff --git a/file b/file\n+change\n", "", 0)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert context.mode == "full"
    assert context.infrastructure_failure is False
    assert "## PR #7: Fix bad title" in context.text
    assert "## PR Description\nBody text" in context.text
    assert "diff --git" in context.text


def test_pr_title_is_redacted_before_actions_log_sink(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """Credential-like PR titles cannot reach the persisted Actions log."""
    credential = "opaque-title-secret"

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(
                _pulls_payload(7, f"DB_PASSWORD={credential}", "Body"),
                "",
                0,
            )
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult("diff --git a/file b/file\n+change\n", "", 0)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert context.infrastructure_failure is False
    captured = capsys.readouterr().out
    assert credential not in captured
    assert "DB_PASSWORD=***" in captured


@pytest.mark.parametrize(
    ("refusal", "expected_delay"),
    [
        (
            "HTTP 403: API rate limit exceeded for user ID 6811113; Retry-After: 7",
            7.0,
        ),
        (
            "HTTP 403: You have exceeded a secondary rate limit\nX-RateLimit-Reset: 1010",
            11.0,
        ),
    ],
)
def test_run_gh_retries_primary_and_secondary_403_until_success(
    monkeypatch: pytest.MonkeyPatch,
    refusal: str,
    expected_delay: float,
):
    """Primary and secondary limit headers control the wait before recovery."""
    calls: list[list[str]] = []
    sleeps: list[float] = []

    def fake_subprocess_run(command: list[str], **kwargs):
        del kwargs
        calls.append(command)
        if len(calls) == 1:
            return _mod.subprocess.CompletedProcess(command, 1, "", refusal)
        return _mod.subprocess.CompletedProcess(command, 0, "recovered", "")

    monkeypatch.setattr(_mod.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(_mod.time, "time", lambda: 1000.0)
    monkeypatch.setattr(_mod.time, "sleep", sleeps.append)

    result = _mod.run_gh(["pr", "diff", "7"])

    assert result == CommandResult("recovered", "", 0)
    assert len(calls) == 2
    assert sleeps == [expected_delay]


def test_run_gh_requests_and_honors_rest_rate_limit_headers(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[list[str]] = []
    sleeps: list[float] = []

    def fake_subprocess_run(command: list[str], **kwargs):
        del kwargs
        calls.append(command)
        if len(calls) == 1:
            return _mod.subprocess.CompletedProcess(
                command,
                1,
                (
                    "HTTP/2.0 403 Forbidden\n"
                    "Retry-After: 7\n"
                    "X-RateLimit-Remaining: 0\n\n"
                    '{"message":"secondary rate limit"}'
                ),
                "gh: secondary rate limit (HTTP 403)",
            )
        return _mod.subprocess.CompletedProcess(
            command,
            0,
            'HTTP/2.0 200 OK\nContent-Type: application/json\n\n{"number":7}',
            "",
        )

    monkeypatch.setattr(_mod.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(_mod.time, "sleep", sleeps.append)

    result = _mod.run_gh(["api", "repos/owner/repo/pulls/7"])

    assert all(call[-1] == "--include" for call in calls)
    assert sleeps == [7.0]
    assert result == CommandResult('{"number":7}', "", 0)


def test_rate_limit_reset_is_ignored_when_resource_quota_remains(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(_mod.time, "time", lambda: 1000.0)

    delay, source = _mod._retry_delay(
        "X-RateLimit-Remaining: 42\nX-RateLimit-Reset: 5000",
        60.0,
    )

    assert delay == 60.0
    assert source == "exponential backoff"


def test_pr_diff_uses_header_exposing_rest_transport(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[list[str]] = []

    def fake_subprocess_run(command: list[str], **kwargs):
        del kwargs
        calls.append(command)
        return _mod.subprocess.CompletedProcess(
            command,
            0,
            "HTTP/2.0 200 OK\nContent-Type: text/plain\n\ndiff --git a/file b/file\n+change\n",
            "",
        )

    monkeypatch.setattr(_mod.subprocess, "run", fake_subprocess_run)

    result = _mod.run_gh(["pr", "diff", "7", "--repo", "owner/repo"])

    assert calls == [
        [
            "gh",
            "api",
            "repos/owner/repo/pulls/7",
            "--method",
            "GET",
            "--header",
            "Accept: application/vnd.github.v3.diff",
            "--include",
        ]
    ]
    assert result.stdout.startswith("diff --git")


def test_run_gh_exhausts_bounded_rate_limit_retries(
    monkeypatch: pytest.MonkeyPatch,
):
    """A persistent transient refusal returns failure after the fixed attempt cap."""
    calls: list[list[str]] = []
    sleeps: list[float] = []

    def fake_subprocess_run(command: list[str], **kwargs):
        del kwargs
        calls.append(command)
        return _mod.subprocess.CompletedProcess(
            command,
            1,
            "",
            "GraphQL: API rate limit already exceeded for user ID 6811113",
        )

    monkeypatch.setattr(_mod.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(_mod.time, "sleep", sleeps.append)

    result = _mod.run_gh(["pr", "diff", "7"])

    assert len(calls) == len(_mod.GH_REFUSAL_BACKOFF_SECONDS) + 1
    assert sleeps == list(_mod.GH_REFUSAL_BACKOFF_SECONDS)
    assert result.returncode == 1
    assert "retry attempts exhausted" in result.stderr


def test_run_gh_retries_transient_not_accessible_503(
    monkeypatch: pytest.MonkeyPatch,
):
    """Generic availability wording cannot override an explicit retryable status."""
    calls: list[list[str]] = []

    def fake_subprocess_run(command: list[str], **kwargs):
        del kwargs
        calls.append(command)
        if len(calls) == 1:
            return _mod.subprocess.CompletedProcess(
                command,
                1,
                "",
                "HTTP 503: service temporarily not accessible",
            )
        return _mod.subprocess.CompletedProcess(command, 0, "recovered", "")

    monkeypatch.setattr(_mod.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(_mod.time, "sleep", lambda _seconds: None)

    result = _mod.run_gh(["pr", "diff", "7"])

    assert result == CommandResult("recovered", "", 0)
    assert len(calls) == 2


@pytest.mark.parametrize(
    "rejection",
    [
        "HTTP 401: Bad credentials",
        "HTTP 403: Resource not accessible by integration",
        "Authentication token found but could not be validated",
    ],
)
def test_run_gh_does_not_retry_permanent_authentication_rejection(
    monkeypatch: pytest.MonkeyPatch,
    rejection: str,
):
    """Credential and permission failures require operator action, not retries."""
    calls: list[list[str]] = []
    sleeps: list[float] = []

    def fake_subprocess_run(command: list[str], **kwargs):
        del kwargs
        calls.append(command)
        return _mod.subprocess.CompletedProcess(command, 1, "", rejection)

    monkeypatch.setattr(_mod.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(_mod.time, "sleep", sleeps.append)

    result = _mod.run_gh(["api", "repos/owner/repo/pulls/7"])

    assert result.returncode == 1
    assert len(calls) == 1
    assert sleeps == []


def test_metadata_authentication_rejection_skips_transport_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    """A permanent REST credential rejection must not be retried through GraphQL."""
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        calls.append(arguments)
        return CommandResult("", "HTTP 401: Bad credentials", 1)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert len(calls) == 1
    assert calls[0][0] == "api"
    assert context.infrastructure_failure is True
    assert "Bad credentials" in context.text


def test_metadata_permission_rejection_skips_transport_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    """Permanent authorization denials must not spend a second transport call."""
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        calls.append(arguments)
        return CommandResult("", "HTTP 403: Must have admin rights to Repository", 1)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert len(calls) == 1
    assert context.infrastructure_failure is True
    assert "admin rights" in context.text


def test_rate_limit_reset_beyond_context_budget_fails_without_sleeping(
    monkeypatch: pytest.MonkeyPatch,
):
    """A reset beyond the job budget classifies immediately instead of timing out."""
    sleeps: list[float] = []
    calls: list[list[str]] = []

    def fake_subprocess_run(command: list[str], **kwargs):
        del kwargs
        calls.append(command)
        return _mod.subprocess.CompletedProcess(
            command,
            1,
            "",
            "HTTP 403: API rate limit exceeded\nRetry-After: 500",
        )

    monkeypatch.setattr(_mod.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(_mod.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(_mod.time, "sleep", sleeps.append)

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert len(calls) == 2  # REST plus the existing GraphQL transport fallback.
    assert sleeps == []
    assert context.infrastructure_failure is True
    assert "retry budget exhausted" in context.text


def test_context_deadline_subtracts_elapsed_action_setup(
    monkeypatch: pytest.MonkeyPatch,
):
    """Validation and cache setup consume context time, not downstream reserves."""
    monkeypatch.setenv(_mod.AI_REVIEW_ACTION_DEADLINE_ENV, "670")
    monkeypatch.setattr(_mod.time, "time", lambda: 100.0)
    monkeypatch.setattr(_mod.time, "monotonic", lambda: 20.0)

    deadline = _mod._new_context_retry_deadline()

    # 570 seconds remain in the action, minus 360 downstream, leaving 210.
    assert deadline == 230.0

    monkeypatch.setattr(_mod.time, "time", lambda: 160.0)

    # Sixty seconds of setup elapsed, so only 150 context seconds remain.
    assert _mod._new_context_retry_deadline() == 170.0


def test_expired_action_budget_fails_before_local_context(
    monkeypatch: pytest.MonkeyPatch,
):
    """Even local context cannot invoke the model after its reserved window."""
    monkeypatch.setenv(_mod.AI_REVIEW_ACTION_DEADLINE_ENV, "460")
    monkeypatch.setattr(_mod.time, "time", lambda: 100.0)
    monkeypatch.setattr(_mod.time, "monotonic", lambda: 20.0)
    monkeypatch.setattr(
        _mod,
        "_build_context_from_environment",
        lambda: pytest.fail("expired budget must fail before building context"),
    )

    context = _mod.build_context_from_environment()

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert "action budget exhausted" in context.text


@pytest.mark.parametrize(
    ("context_type", "environment"),
    [
        (
            "issue",
            {
                "ISSUE_NUMBER": "7",
                "GITHUB_REPOSITORY": "owner/repo",
            },
        ),
        (
            "spec-file",
            {
                "CONTEXT_PATH": "unused",
                "PR_NUMBER": "7",
                "GITHUB_REPOSITORY": "owner/repo",
            },
        ),
    ],
)
def test_all_remote_context_types_share_the_retry_budget(
    monkeypatch: pytest.MonkeyPatch,
    context_type: str,
    environment: dict[str, str],
):
    """Issue and spec lookups cannot honor reset headers beyond the job deadline."""
    sleeps: list[float] = []

    monkeypatch.setenv("CONTEXT_TYPE", context_type)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    if context_type == "spec-file":
        monkeypatch.setattr(_mod.Path, "is_file", lambda _path: True)
        monkeypatch.setattr(_mod, "read_utf8_file", lambda _path, _description: "Spec")

    monkeypatch.setattr(
        _mod.subprocess,
        "run",
        lambda command, **kwargs: _mod.subprocess.CompletedProcess(
            command,
            1,
            "",
            "HTTP 403: API rate limit exceeded\nRetry-After: 500",
        ),
    )
    monkeypatch.setattr(_mod.time, "sleep", sleeps.append)

    context = _mod.build_context_from_environment()

    assert sleeps == []
    assert context.mode == "error"
    assert context.infrastructure_failure is True


def test_malformed_metadata_responses_fail_as_infrastructure(
    monkeypatch: pytest.MonkeyPatch,
):
    """Two malformed success responses cannot become reviewable context."""
    responses = iter(
        [
            CommandResult("<html>not json</html>", "", 0),
            CommandResult('{"title":"missing number"}', "", 0),
        ]
    )
    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda arguments, timeout=_mod.GH_TIMEOUT_SECONDS: next(responses),
    )

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert context.text.startswith("INFRASTRUCTURE_FAILURE:")
    assert "response was unusable" in context.text


def test_empty_infrastructure_detail_stays_nonempty_and_blocking(
    capsys: pytest.CaptureFixture[str],
):
    """Silent infrastructure failures emit actionable context, never a blank success."""
    context = _mod._pr_fetch_failure_context("7", "")

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert context.text == (
        "INFRASTRUCTURE_FAILURE: Could not fetch PR #7: GitHub API returned no diagnostic output"
    )
    assert "GitHub API returned no diagnostic output" in capsys.readouterr().out


def test_retry_diagnostics_redact_environment_secrets(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """Refusal diagnostics may classify failures but must not expose workflow tokens."""
    secret = "ghp_this_value_must_never_escape"
    monkeypatch.setenv("GH_TOKEN", secret)
    monkeypatch.setattr(
        _mod.subprocess,
        "run",
        lambda command, **kwargs: _mod.subprocess.CompletedProcess(
            command,
            1,
            "",
            f"HTTP 403: API rate limit exceeded; token={secret}",
        ),
    )
    monkeypatch.setattr(_mod.time, "sleep", lambda _seconds: None)

    result = _mod.run_gh(["pr", "diff", "7"])
    context = _mod._pr_fetch_failure_context("7", result.stderr)
    output = capsys.readouterr().out

    assert secret not in result.stderr
    assert secret not in context.text
    assert secret not in output
    assert "***" in context.text


def test_retry_diagnostics_redact_secrets_from_stdout(
    monkeypatch: pytest.MonkeyPatch,
):
    """A secret returned through stdout receives the same treatment as stderr."""
    secret = "github_pat_stdout_must_never_escape"
    monkeypatch.setenv("GITHUB_TOKEN", secret)
    monkeypatch.setattr(
        _mod.subprocess,
        "run",
        lambda command, **kwargs: _mod.subprocess.CompletedProcess(
            command,
            1,
            f"HTTP 503: temporary failure; Authorization: Bearer {secret}",
            "",
        ),
    )
    monkeypatch.setattr(_mod.time, "sleep", lambda _seconds: None)

    result = _mod.run_gh(["pr", "diff", "7"])

    assert secret not in result.stdout
    assert "***" in result.stdout


def test_retry_diagnostics_redact_uninstalled_github_token_shape(
    monkeypatch: pytest.MonkeyPatch,
):
    """Token-shaped credentials are removed without matching environment state."""
    token = f"ghp_{'A' * 36}"
    for variable in _mod.SECRET_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)

    redacted = _mod._redact_secrets(f"cached credential: {token}")

    assert token not in redacted
    assert "[redacted: github-token]" in redacted


def test_environment_secret_value_is_removed_from_stdout(
    monkeypatch: pytest.MonkeyPatch,
):
    """Environment-backed credentials are removed from raw standard output."""
    credential = "github_pat_dynamic_stdout_value"
    monkeypatch.setenv("GITHUB_TOKEN", credential)

    def fake_subprocess_run(command: list[str], **kwargs):
        del kwargs
        return _mod.subprocess.CompletedProcess(
            command,
            1,
            "HTTP 503: workflow-value=" + credential,
            "",
        )

    monkeypatch.setattr(_mod.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(_mod.time, "sleep", lambda _seconds: None)

    result = _mod.run_gh(["pr", "diff", "7"])

    assert credential not in result.stdout
    assert "workflow-value=***" in result.stdout


def test_marks_pr_number_mismatch_as_infrastructure_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    """Wrong PR data fails closed for downstream parsing."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(_pulls_payload(8, "Mismatch", ""), "", 0)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert "INFRASTRUCTURE_FAILURE" in context.text
    assert "Could not fetch PR #7" in context.text


def test_marks_rate_limited_empty_diff_as_infrastructure_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    """A 403 that empties the diff must take the DID_NOT_RUN infra path.

    Issue #4547: the rate-limit 403 raised ExternalGhError, which exits 3 and
    fails the composite step. Every later step, including the infra gate that
    writes the DID_NOT_RUN verdict, was then skipped, so the verdict file was
    never written. Downstream read an empty verdict and defaulted to
    NEEDS_REVIEW with INFRA_FAILURE recorded as false, which is
    indistinguishable from a real finding and blocked the PR on a transient
    error.
    """

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(_pulls_payload(7, "Rate limited", ""), "", 0)
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult(
                "",
                "could not find pull request diff: HTTP 403: API rate limit "
                "exceeded for user ID 6811113.",
                1,
            )
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert context.infrastructure_failure is True
    assert context.mode == "error"
    assert "INFRASTRUCTURE_FAILURE" in context.text
    # The observed error must survive into the context so a reader can tell a
    # rate limit apart from a permissions problem without opening the raw log.
    assert "403" in context.text
    assert "rate limit" in context.text


def test_marks_empty_diff_with_no_stderr_as_infrastructure_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    """An empty diff with a silent gh failure still fails closed, not exit 3."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(_pulls_payload(7, "Silent", ""), "", 0)
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult("", "", 0)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert context.infrastructure_failure is True
    assert "Failed to fetch PR diff" in context.text


def test_marks_whitespace_only_diff_as_infrastructure_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    """Whitespace is not reviewable PR context and cannot unlock a model verdict."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(_pulls_payload(7, "Whitespace", ""), "", 0)
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult(" \t\n", "", 0)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert "Failed to fetch PR diff" in context.text


def test_marks_nonzero_diff_with_partial_stdout_as_infrastructure_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    """A failed PR diff cannot become full context through partial stdout."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(_pulls_payload(7, "Partial", ""), "", 0)
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult("diff --git a/a.py b/a.py\n+partial\n", "upstream reset", 1)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert "Failed to fetch PR diff" in context.text


def test_empty_diff_no_longer_raises_external_gh_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """Pin the regression directly: exit 3 bypasses the infra gate entirely.

    This is the vacuity guard for the two tests above. If the raise is ever
    restored, those tests would error out rather than fail on an assertion, so
    this test names the exception type explicitly.
    """

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(_pulls_payload(7, "NoRaise", ""), "", 0)
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult("", "boom", 1)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    try:
        _mod.build_pr_diff_context("7", "owner/repo", 100)
    except _mod.ExternalGhError as exc:  # pragma: no cover - regression guard
        raise AssertionError(
            "an empty diff must not raise ExternalGhError; exit 3 skips the "
            f"infra gate and no verdict file is written (issue #4547): {exc}"
        ) from exc


def test_large_pr_uses_file_list_summary(monkeypatch: pytest.MonkeyPatch):
    """Diff size failures degrade to a file-list summary."""

    monkeypatch.setattr(
        _mod,
        "get_paginated_file_list",
        lambda pr_number, repository: ("src/a.py\nsrc/b.py", False, ""),
    )

    context = _mod.build_large_pr_context("7", "owner/repo")

    assert context.mode == "summary"
    assert ">300 files" in context.text
    assert "src/a.py" in context.text
    assert "src/b.py" in context.text


def test_large_pr_raises_when_all_fallbacks_fail(monkeypatch: pytest.MonkeyPatch):
    """An unreadable large PR returns a nonzero script path."""

    monkeypatch.setattr(
        _mod,
        "get_paginated_file_list",
        lambda pr_number, repository: ("", False, "API unavailable"),
    )
    monkeypatch.setattr(_mod, "get_pr_name_only", lambda pr_number, repository: "")

    with pytest.raises(_mod.ExternalGhError):
        _mod.build_large_pr_context("7", "owner/repo")


def test_get_pr_name_only_rejects_stdout_from_nonzero_diff(
    monkeypatch: pytest.MonkeyPatch,
):
    """A failed name-only call cannot pass partial stdout to the model."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult("src/partial.py\n", "upstream reset", 1)
        if arguments[:1] == ["api"]:
            if "page=1" in arguments[1]:
                return CommandResult("src/complete.py\n", "", 0)
            return CommandResult("", "", 0)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    assert _mod.get_pr_name_only("7", "owner/repo") == "src/complete.py"


def test_get_pr_name_only_does_not_fallback_after_auth_rejection(
    monkeypatch: pytest.MonkeyPatch,
):
    """Permanent authentication rejection stops before REST pagination."""
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        calls.append(arguments)
        return CommandResult("", "HTTP 401: Bad credentials", 1)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    assert _mod.get_pr_name_only("7", "owner/repo") == ""
    assert len(calls) == 1
    assert calls[0][:2] == ["pr", "diff"]


def test_paginated_file_list_marks_later_api_failure_as_truncated(
    monkeypatch: pytest.MonkeyPatch,
):
    """A later page failure returns the pages already fetched and marks truncation."""

    first_page = "\n".join(f"src/file_{index}.py" for index in range(_mod.FILES_PER_PAGE))
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        calls.append(arguments)
        if "&page=1" in arguments[1]:
            return CommandResult(first_page, "", 0)
        if "&page=2" in arguments[1]:
            return CommandResult("", "api unavailable", 1)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    file_list, truncated, api_failure = _mod.get_paginated_file_list("7", "owner/repo")

    assert truncated is True
    assert api_failure == "api unavailable"
    assert file_list == first_page
    assert len(calls) == 2


@pytest.mark.parametrize(("sentinel", "truncated"), [("", False), ("src/501.py", True)])
def test_paginated_file_list_uses_sentinel_page_to_confirm_completeness(
    monkeypatch: pytest.MonkeyPatch,
    sentinel: str,
    truncated: bool,
):
    full_page = "\n".join(f"src/{index}.py" for index in range(_mod.FILES_PER_PAGE))

    def fake_run_gh(arguments: list[str]):
        page = int(arguments[1].rsplit("page=", 1)[1])
        return CommandResult(sentinel if page == _mod.MAX_FILE_PAGES + 1 else full_page, "", 0)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    file_list, observed_truncated, api_failure = _mod.get_paginated_file_list(
        "7",
        "owner/repo",
    )

    assert _mod.count_lines(file_list) == _mod.MAX_FILE_PAGES * _mod.FILES_PER_PAGE
    assert observed_truncated is truncated
    assert api_failure == ""


def test_large_pr_rejects_truncated_file_list_without_complete_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        _mod,
        "get_paginated_file_list",
        lambda _pr, _repo: ("src/partial.py", True, ""),
    )
    monkeypatch.setattr(_mod, "get_pr_name_only", lambda _pr, _repo: "")

    with pytest.raises(_mod.ExternalGhError, match="completeness cap"):
        _mod.build_large_pr_context("7", "owner/repo")


def test_large_pr_uses_complete_fallback_after_partial_api_pagination(
    monkeypatch: pytest.MonkeyPatch,
):
    """A complete alternate transport can recover from partial REST pagination."""

    monkeypatch.setattr(
        _mod,
        "get_paginated_file_list",
        lambda pr_number, repository: ("src/partial.py", True, "HTTP 503"),
    )
    monkeypatch.setattr(
        _mod,
        "get_pr_name_only",
        lambda pr_number, repository: "src/complete.py",
    )

    context = _mod.build_large_pr_context("7", "owner/repo")

    assert context.mode == "summary"
    assert "src/complete.py" in context.text
    assert "src/partial.py" not in context.text


def test_large_pr_does_not_fallback_after_pagination_auth_rejection(
    monkeypatch: pytest.MonkeyPatch,
):
    """Permanent REST authentication rejection stops alternate transports."""
    monkeypatch.setattr(
        _mod,
        "get_paginated_file_list",
        lambda pr_number, repository: (
            "src/partial.py",
            True,
            "HTTP 401: Bad credentials",
        ),
    )
    monkeypatch.setattr(
        _mod,
        "get_pr_name_only",
        lambda _pr, _repo: pytest.fail("auth rejection must not use a fallback"),
    )

    with pytest.raises(_mod.ExternalGhError, match="Bad credentials"):
        _mod.build_large_pr_context("7", "owner/repo")


def test_build_issue_context_fetches_issue_details(monkeypatch: pytest.MonkeyPatch):
    """Issue context uses gh issue data as review input."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        assert arguments[:5] == ["issue", "view", "2814", "--repo", "owner/repo"]
        return CommandResult("Title: ADR-006\n\nBody:\nExtract YAML logic\n\nLabels: ci", "", 0)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_issue_context("2814", "owner/repo")

    assert context.mode == "full"
    assert "Title: ADR-006" in context.text
    assert "Labels: ci" in context.text


def test_build_issue_context_redacts_credential_assignments(
    monkeypatch: pytest.MonkeyPatch,
):
    credential = "ordinary-secret-value"
    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda arguments, timeout=_mod.GH_TIMEOUT_SECONDS: CommandResult(
            f"Title: Configure\n\nBody:\npassword: {credential}\n\nLabels: ci",
            "",
            0,
        ),
    )

    context = _mod.build_issue_context("2814", "owner/repo")

    assert credential not in context.text
    assert "password: ***" in context.text


def test_build_issue_context_without_issue_number_skips_gh(
    monkeypatch: pytest.MonkeyPatch,
):
    """Missing issue input fails closed without hitting GitHub."""

    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda arguments, timeout=_mod.GH_TIMEOUT_SECONDS: pytest.fail(
            f"unexpected gh call: {arguments}"
        ),
    )

    context = _mod.build_issue_context("", "")

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert context.text == "INFRASTRUCTURE_FAILURE: No issue number provided"


def test_build_issue_context_requires_repository() -> None:
    """Issue context needs explicit repo routing for gh calls."""

    with pytest.raises(_mod.ConfigError, match="GITHUB_REPOSITORY"):
        _mod.build_issue_context("2814", "")


def test_build_session_log_context_reads_file(tmp_path: Path):
    """Session-log context reads the requested file with UTF-8 decoding."""

    session_path = tmp_path / "session.json"
    session_path.write_text('{"endingCommit":"abc"}', encoding="utf-8")

    context = _mod.build_session_log_context(str(session_path))

    assert context.mode == "full"
    assert context.text == '{"endingCommit":"abc"}'


def test_build_session_log_context_reports_missing(tmp_path: Path):
    """Missing session logs cannot produce a model verdict."""

    missing_path = tmp_path / "missing.json"

    context = _mod.build_session_log_context(str(missing_path))

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert context.text == (f"INFRASTRUCTURE_FAILURE: Session log file not found: {missing_path}")


def test_build_session_log_context_rejects_empty_file(tmp_path: Path):
    """Empty session logs cannot claim full context."""
    session_path = tmp_path / "empty.json"
    session_path.write_text(" \n\t", encoding="utf-8")

    context = _mod.build_session_log_context(str(session_path))

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert context.text == (f"INFRASTRUCTURE_FAILURE: Session log file is empty: {session_path}")


def test_invalid_session_log_encoding_returns_config_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """Non-UTF-8 session logs map to the repository config exit code."""

    session_path = tmp_path / "session.json"
    session_path.write_bytes(b"\xff")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setenv("CONTEXT_TYPE", "session-log")
    monkeypatch.setenv("CONTEXT_PATH", str(session_path))

    assert _mod.main() == 2
    assert "Session log file must be UTF-8" in capsys.readouterr().err


def test_build_spec_context_without_pr_uses_spec_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Spec context can be built when no PR diff is available by design."""

    spec_path = tmp_path / "spec.md"
    spec_path.write_text("Spec body", encoding="utf-8")
    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda arguments, timeout=_mod.GH_TIMEOUT_SECONDS: pytest.fail(
            f"unexpected gh call: {arguments}"
        ),
    )

    context = _mod.build_spec_context(str(spec_path), "", "owner/repo", 100)

    assert context.mode == "partial"
    assert "## Specification\nSpec body" in context.text
    assert "## Implementation Changes\n[No PR diff provided]" in context.text


def test_build_spec_context_reports_missing_as_infrastructure(tmp_path: Path):
    """Missing spec files cannot produce a model verdict."""

    missing_path = tmp_path / "missing.md"

    context = _mod.build_spec_context(str(missing_path), "", "owner/repo", 100)

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert context.text == (f"INFRASTRUCTURE_FAILURE: Spec file not found: {missing_path}")


def test_build_spec_context_rejects_empty_spec(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Empty specification content cannot produce a model verdict."""
    spec_path = tmp_path / "spec.md"
    spec_path.write_text(" \n\t", encoding="utf-8")
    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda _args: pytest.fail("empty spec must fail before remote context fetch"),
    )

    context = _mod.build_spec_context(str(spec_path), "7", "owner/repo", 100)

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert context.text == (f"INFRASTRUCTURE_FAILURE: Specification file is empty: {spec_path}")


def test_build_spec_context_truncates_large_diff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Large spec diffs keep the review context under the configured line limit."""

    spec_path = tmp_path / "spec.md"
    spec_path.write_text("Spec body", encoding="utf-8")
    diff = "line 1\nline 2\nline 3\nline 4\n"

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult(diff, "", 0)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_spec_context(str(spec_path), "7", "owner/repo", 2)

    assert context.mode == "partial"
    assert "[Diff truncated to first 2 of 4 lines]" in context.text
    assert "line 1\nline 2" in context.text
    assert "line 3" not in context.text


def test_build_spec_context_falls_back_to_file_list_when_diff_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Unavailable spec diffs degrade to a file-list summary."""

    spec_path = tmp_path / "spec.md"
    spec_path.write_text("Spec body", encoding="utf-8")
    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda arguments, timeout=_mod.GH_TIMEOUT_SECONDS: CommandResult(
            "",
            "diff unavailable",
            1,
        ),
    )
    monkeypatch.setattr(
        _mod,
        "get_pr_name_only",
        lambda pr_number, repository: "scripts/ci/build_ai_review_context.py",
    )

    context = _mod.build_spec_context(str(spec_path), "7", "owner/repo", 100)

    assert context.mode == "summary"
    assert "[Diff unavailable, showing file list only]" in context.text
    assert "scripts/ci/build_ai_review_context.py" in context.text


def test_build_spec_context_rejects_whitespace_only_diff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Whitespace-only output cannot claim full implementation context."""
    spec_path = tmp_path / "spec.md"
    spec_path.write_text("Spec body", encoding="utf-8")
    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda arguments, timeout=_mod.GH_TIMEOUT_SECONDS: CommandResult(
            " \t\n",
            "",
            0,
        ),
    )
    monkeypatch.setattr(_mod, "get_pr_name_only", lambda _pr, _repo: "")

    context = _mod.build_spec_context(str(spec_path), "7", "owner/repo", 100)

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert "INFRASTRUCTURE_FAILURE" in context.text


def test_build_spec_context_rejects_stdout_from_nonzero_diff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """A failed diff cannot turn partial stdout into full implementation context."""

    spec_path = tmp_path / "spec.md"
    spec_path.write_text("Spec body", encoding="utf-8")
    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda arguments, timeout=_mod.GH_TIMEOUT_SECONDS: CommandResult(
            "diff --git a/spec.md b/spec.md\n+change\n",
            "warning",
            1,
        ),
    )
    monkeypatch.setattr(
        _mod,
        "get_pr_name_only",
        lambda pr_number, repository: "",
    )

    context = _mod.build_spec_context(str(spec_path), "7", "owner/repo", 100)

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert "INFRASTRUCTURE_FAILURE" in context.text
    assert "diff --git a/spec.md b/spec.md" not in context.text


def test_build_spec_context_does_not_fallback_after_auth_rejection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Permanent authentication rejection cannot trigger alternate API calls."""
    spec_path = tmp_path / "spec.md"
    spec_path.write_text("Spec body", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        calls.append(arguments)
        return CommandResult("", "HTTP 403: Resource not accessible by integration", 1)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)
    monkeypatch.setattr(
        _mod,
        "get_pr_name_only",
        lambda _pr, _repo: pytest.fail("auth rejection must not use a fallback"),
    )

    context = _mod.build_spec_context(str(spec_path), "7", "owner/repo", 100)

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert "Resource not accessible by integration" in context.text
    assert len(calls) == 1


def test_build_spec_context_reports_unavailable_when_diff_and_file_list_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Spec context names the missing diff when no fallback data exists."""

    spec_path = tmp_path / "spec.md"
    spec_path.write_text("Spec body", encoding="utf-8")
    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda arguments, timeout=_mod.GH_TIMEOUT_SECONDS: CommandResult(
            "",
            "diff unavailable",
            1,
        ),
    )
    monkeypatch.setattr(_mod, "get_pr_name_only", lambda pr_number, repository: "")

    context = _mod.build_spec_context(str(spec_path), "7", "owner/repo", 100)

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert "INFRASTRUCTURE_FAILURE" in context.text
    assert "diff unavailable" in context.text


def test_invalid_spec_encoding_returns_config_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """Non-UTF-8 spec files map to the repository config exit code."""

    spec_path = tmp_path / "spec.md"
    spec_path.write_bytes(b"\xff")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setenv("CONTEXT_TYPE", "spec-file")
    monkeypatch.setenv("CONTEXT_PATH", str(spec_path))
    monkeypatch.delenv("PR_NUMBER", raising=False)

    assert _mod.main() == 2
    assert "Spec file must be UTF-8" in capsys.readouterr().err


def test_pr_diff_context_requires_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """PR diff context fails with a config error when repository is missing."""

    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setenv("CONTEXT_TYPE", "pr-diff")
    monkeypatch.setenv("PR_NUMBER", "7")
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    assert _mod.main() == 2
    assert "GITHUB_REPOSITORY is required for pr-diff context" in capsys.readouterr().err


def test_pr_diff_context_requires_pr_number(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """PR diff context must fail closed when no PR number is available."""

    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setenv("CONTEXT_TYPE", "pr-diff")
    monkeypatch.delenv("PR_NUMBER", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    assert _mod.main() == 2
    assert "PR_NUMBER is required for pr-diff context" in capsys.readouterr().err


def test_issue_context_gh_failure_is_infrastructure(monkeypatch: pytest.MonkeyPatch):
    """Issue lookup failures must not invoke a model without issue context."""

    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda arguments, timeout=_mod.GH_TIMEOUT_SECONDS: CommandResult("", "fail", 1),
    )

    context = _mod.build_issue_context("2814", "owner/repo")

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert context.text == ("INFRASTRUCTURE_FAILURE: Could not fetch issue #2814: fail")


def test_issue_context_empty_output_is_infrastructure(monkeypatch: pytest.MonkeyPatch):
    """A successful exit without issue context must not invoke the model."""
    monkeypatch.setattr(
        _mod,
        "run_gh",
        lambda _args: _mod.CommandResult(stdout=" \n", stderr="", returncode=0),
    )

    context = _mod.build_issue_context("2814", "owner/repo")

    assert context.mode == "error"
    assert context.infrastructure_failure is True
    assert context.text == (
        "INFRASTRUCTURE_FAILURE: Could not fetch issue #2814: GitHub API returned no issue output"
    )


def test_unknown_context_type_returns_config_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """Unknown context types must fail closed instead of unlocking PASS."""

    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setenv("CONTEXT_TYPE", "typo")

    assert _mod.main() == 2
    assert "Unknown CONTEXT_TYPE: typo" in capsys.readouterr().err


def test_main_maps_external_gh_error_to_external_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """GitHub outages must report the repository external exit code."""

    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setattr(
        _mod,
        "build_context_from_environment",
        lambda: (_ for _ in ()).throw(_mod.ExternalGhError("gh unavailable")),
    )

    assert _mod.main() == 3
    assert "::error::gh unavailable" in capsys.readouterr().err


def test_main_exits_zero_and_flags_infra_when_the_diff_is_rate_limited(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """End to end: a 403 must leave the composite step green and set the flag.

    This is the claim the fix for issue #4547 rests on. Exit 0 keeps the later
    steps running, and ``context_infra_failure=true`` is what the infra gate
    reads to skip the model invocation and write the DID_NOT_RUN verdict. If
    this regressed to exit 3, the gate would never run and the verdict file
    would never be written.
    """

    output_path = tmp_path / "github-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setenv("CONTEXT_TYPE", "pr-diff")
    monkeypatch.setenv("PR_NUMBER", "7")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("MAX_DIFF_LINES", "100")

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(_pulls_payload(7, "Rate limited", ""), "", 0)
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult("", "HTTP 403: API rate limit exceeded", 1)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    assert _mod.main() == 0

    output = output_path.read_text(encoding="utf-8")
    assert "context_infra_failure=true" in output
    assert "context_mode=error" in output


def test_spec_file_pr_context_requires_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """Spec-file PR context fails with a config error when repository is missing."""

    spec_path = tmp_path / "spec.md"
    spec_path.write_text("Spec body", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setenv("CONTEXT_TYPE", "spec-file")
    monkeypatch.setenv("CONTEXT_PATH", str(spec_path))
    monkeypatch.setenv("PR_NUMBER", "7")
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    assert _mod.main() == 2
    assert "GITHUB_REPOSITORY is required for spec-file PR context" in capsys.readouterr().err


def test_pr_context_preserves_whitespace_body(monkeypatch: pytest.MonkeyPatch):
    """Whitespace PR bodies are preserved when gh returns them."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(_pulls_payload(7, "Title", "   \n"), "", 0)
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult("diff --git a/file b/file\n+change\n", "", 0)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert "## PR Description\n   \n\n## Changes" in context.text


def test_invalid_max_diff_lines_returns_config_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """Invalid action input maps to the repository config exit code."""

    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setenv("CONTEXT_TYPE", "pr-diff")
    monkeypatch.setenv("PR_NUMBER", "7")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("MAX_DIFF_LINES", "not-a-number")

    assert _mod.main() == 2
    assert "MAX_DIFF_LINES must be an integer" in capsys.readouterr().err


def test_write_outputs_uses_runner_temp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """GitHub outputs include the context file and multiline payload."""

    output_path = tmp_path / "github-output.txt"
    runner_temp = tmp_path / "runner"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    monkeypatch.setenv("RUNNER_TEMP", str(runner_temp))
    monkeypatch.setenv("PR_NUMBER", "7")

    _mod.write_outputs(ReviewContext("hello\nworld", "summary", True))

    output = output_path.read_text(encoding="utf-8")
    context_file = runner_temp / "ai-review-context-pr7.txt"
    assert context_file.read_text(encoding="utf-8") == "hello\nworld"
    assert "context_mode=summary" in output
    assert f"context_file={context_file}" in output
    assert "context_infra_failure=true" in output
    assert "context_built<<EOF_CONTEXT_BUILT\nhello\nworld\nEOF_CONTEXT_BUILT" in output


def test_successful_metadata_json_is_parsed_before_sink_redaction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Untrusted credential-like metadata cannot corrupt structured API parsing."""
    credential = "opaque-secret-for-json"

    def fake_subprocess_run(command: list[str], **kwargs):
        del kwargs
        if "Accept: application/vnd.github.v3.diff" in command:
            return _mod.subprocess.CompletedProcess(
                command,
                0,
                "HTTP/2.0 200 OK\nContent-Type: text/plain\n\ndiff --git a/file b/file\n+change\n",
                "",
            )
        if command[1:2] == ["api"]:
            return _mod.subprocess.CompletedProcess(
                command,
                0,
                _pulls_payload(
                    7,
                    "Credential-like body",
                    f"DB_PASSWORD={credential}\nbody retained",
                ),
                "",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(_mod.subprocess, "run", fake_subprocess_run)
    context = _mod.build_pr_diff_context("7", "owner/repo", 100)

    assert context.infrastructure_failure is False
    assert "body retained" in context.text

    output_path = tmp_path / "github-output.txt"
    runner_temp = tmp_path / "runner"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    monkeypatch.setenv("RUNNER_TEMP", str(runner_temp))
    monkeypatch.setenv("PR_NUMBER", "7")
    _mod.write_outputs(context)

    context_file = runner_temp / "ai-review-context-pr7.txt"
    persisted = output_path.read_text(encoding="utf-8") + context_file.read_text(encoding="utf-8")
    assert credential not in persisted
    assert "DB_PASSWORD=***" in persisted
    assert "body retained" in persisted


def test_write_outputs_redacts_context_before_every_sink(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Local context credentials cannot reach files or GitHub outputs."""
    output_path = tmp_path / "github-output.txt"
    runner_temp = tmp_path / "runner"
    environment_secret = "arbitrary-workflow-secret"
    shaped_secret = f"github_pat_{'A' * 22}"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    monkeypatch.setenv("RUNNER_TEMP", str(runner_temp))
    monkeypatch.setenv("GITHUB_TOKEN", environment_secret)
    monkeypatch.delenv("PR_NUMBER", raising=False)

    _mod.write_outputs(
        ReviewContext(
            f"environment={environment_secret}\nshape={shaped_secret}",
            "full",
        )
    )

    context_file = next(runner_temp.glob("ai-review-context-pr*.txt"))
    persisted = output_path.read_text(encoding="utf-8") + context_file.read_text(encoding="utf-8")
    assert environment_secret not in persisted
    assert shaped_secret not in persisted
    assert "***" in persisted
    assert "[redacted: github-pat]" in persisted


def test_write_outputs_preserves_source_assignment_semantics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    output_path = tmp_path / "github-output.txt"
    runner_temp = tmp_path / "runner"
    source = "+token = accept_unverified_jwt(user_input)"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    monkeypatch.setenv("RUNNER_TEMP", str(runner_temp))
    monkeypatch.delenv("PR_NUMBER", raising=False)

    _mod.write_outputs(ReviewContext(source, "full"))

    context_file = next(runner_temp.glob("ai-review-context-pr*.txt"))
    persisted = output_path.read_text(encoding="utf-8") + context_file.read_text(encoding="utf-8")
    assert source in persisted


def test_write_outputs_sanitizes_context_file_identifier(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """PR_NUMBER cannot introduce path separators into the context file path."""

    output_path = tmp_path / "github-output.txt"
    runner_temp = tmp_path / "runner"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    monkeypatch.setenv("RUNNER_TEMP", str(runner_temp))
    monkeypatch.setenv("PR_NUMBER", "../evil/path")

    _mod.write_outputs(ReviewContext("hello", "full"))

    output = output_path.read_text(encoding="utf-8")
    context_file = runner_temp / "ai-review-context-previl_path.txt"
    assert context_file.read_text(encoding="utf-8") == "hello"
    assert f"context_file={context_file}" in output
    assert not (tmp_path / "evil").exists()


def test_main_returns_config_error_when_github_output_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """Missing GITHUB_OUTPUT maps to the repository config exit code."""

    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr(
        _mod,
        "build_context_from_environment",
        lambda: ReviewContext("hello", "full"),
    )

    assert _mod.main() == 2
    assert "::error::GITHUB_OUTPUT is required" in capsys.readouterr().err


def test_main_returns_config_error_when_runner_temp_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """Missing RUNNER_TEMP does not write the context file into the repository."""

    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output.txt"))
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    monkeypatch.setattr(
        _mod,
        "build_context_from_environment",
        lambda: ReviewContext("hello", "full"),
    )

    assert _mod.main() == 2
    assert "::error::RUNNER_TEMP is required" in capsys.readouterr().err


def test_main_reports_output_io_separately_from_gh_launch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    """Output write failures are not reported as gh launch failures."""

    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "missing" / "github-output.txt"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    monkeypatch.setattr(
        _mod,
        "build_context_from_environment",
        lambda: ReviewContext("hello", "full"),
    )

    assert _mod.main() == 2
    stderr = capsys.readouterr().err
    assert "Failed to read or write context files" in stderr
    assert "Failed to run gh" not in stderr


def test_append_multiline_output_uses_collision_free_delimiter(tmp_path: Path):
    """GitHub output delimiters cannot be injected through PR-controlled text."""

    output_path = tmp_path / "github-output.txt"

    _mod.append_multiline_output(
        output_path,
        "context_built",
        "safe line\nEOF_CONTEXT_BUILT\ncontext_mode=full",
    )

    output = output_path.read_text(encoding="utf-8")
    assert "context_built<<EOF_CONTEXT_BUILT_1" in output
    assert output.endswith("\nEOF_CONTEXT_BUILT_1\n")


GRAPHQL_QUOTA_ERROR = "GraphQL: API rate limit already exceeded for user ID 6811113."


def test_pr_metadata_uses_one_rest_call(monkeypatch: pytest.MonkeyPatch):
    """Number, title, and body come from a single REST response (issue #4333)."""

    calls: list[list[str]] = []

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        calls.append(arguments)
        return CommandResult(_pulls_payload(4323, "Title", "Body"), "", 0)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    metadata = _mod.fetch_pr_metadata("4323", "rjmurillo/ai-agents")

    assert metadata == _mod.PrMetadata("4323", "Title", "Body", "")
    assert calls == [["api", "repos/rjmurillo/ai-agents/pulls/4323"]]


def test_pr_metadata_falls_back_to_gh_pr_view_when_rest_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    """A REST-only outage still yields context through gh pr view."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult("", "HTTP 503: Service unavailable", 1)
        return CommandResult(_pulls_payload(7, "Title", "Body"), "", 0)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    assert _mod.fetch_pr_metadata("7", "owner/repo").number == "7"


def test_graphql_quota_does_not_break_pr_context(monkeypatch: pytest.MonkeyPatch):
    """REST serves the context while the GraphQL bucket is drained (issue #4333)."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:1] == ["api"]:
            return CommandResult(_pulls_payload(4323, "Title", "Body"), "", 0)
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult("diff --git a/f b/f\n+x\n", "", 0)
        raise AssertionError(f"unexpected GraphQL call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("4323", "owner/repo", 100)

    assert context.infrastructure_failure is False
    assert context.mode == "full"


def test_both_transports_failing_still_fails_closed(monkeypatch: pytest.MonkeyPatch):
    """REQ-008-05: DID_NOT_RUN survives when REST and GraphQL both fail."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        return CommandResult("", GRAPHQL_QUOTA_ERROR, 1)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("4323", "owner/repo", 100)

    assert context.infrastructure_failure is True
    assert "INFRASTRUCTURE_FAILURE" in context.text
    assert "API rate limit already exceeded" in context.text
    assert "first-time contributor" not in context.text


def test_permission_failure_still_names_fork_permissions(
    monkeypatch: pytest.MonkeyPatch,
):
    """The fork hint survives for the failure it actually describes."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        return CommandResult("", "HTTP 404: Not Found", 1)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("4323", "owner/repo", 100)

    assert context.infrastructure_failure is True
    assert "first-time contributor" in context.text


@pytest.mark.parametrize(
    "stderr",
    [
        "HTTP 403: API rate limit exceeded for user ID 6811113",
        "HTTP 403: You have exceeded a secondary rate limit",
        "HTTP 403: You have triggered an abuse detection mechanism",
    ],
)
def test_rate_limited_403_is_not_reported_as_a_permission_problem(
    monkeypatch: pytest.MonkeyPatch,
    stderr: str,
):
    """A rate-limit 403 must not be blamed on token permissions.

    FORK_PERMISSION_SIGNAL matches the bare `HTTP 403` status, so every
    REST-transport rate-limit refusal used to collect the fork hint. That is the
    #4333 misdiagnosis arriving through a transport it was never fixed for.
    """

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        return CommandResult("", stderr, 1)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    context = _mod.build_pr_diff_context("4575", "owner/repo", 100)

    assert context.infrastructure_failure is True
    assert "INFRASTRUCTURE_FAILURE" in context.text
    assert stderr in context.text
    assert "first-time contributor" not in context.text


def test_fork_hint_survives_when_no_rate_limit_wording_is_present():
    """Negative control: the suppression is specific, not a blanket disable.

    Without this, deleting the hint outright would still pass the test above
    while silently dropping a real diagnostic.
    """
    real_fork_failure = "HTTP 403: Resource not accessible by integration"

    context = _mod._pr_fetch_failure_context("4575", real_fork_failure)

    assert "first-time contributor" in context.text


def test_graphql_rate_limit_never_matched_the_permission_signal():
    """Edge: the GraphQL form carries no HTTP status, so it never matched.

    Records why dropping the unconditional hint sufficed for GraphQL, and why
    the REST form needed the second condition.
    """
    graphql_failure = "GraphQL: API rate limit already exceeded for user ID 6811113."

    context = _mod._pr_fetch_failure_context("4575", graphql_failure)

    assert "first-time contributor" not in context.text


def test_name_only_falls_back_to_rest_file_list(monkeypatch: pytest.MonkeyPatch):
    """gh pr diff --name-only is GraphQL; REST pagination backs it up."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        if arguments[:2] == ["pr", "diff"]:
            return CommandResult("", GRAPHQL_QUOTA_ERROR, 1)
        if arguments[:1] == ["api"]:
            if "page=1" in arguments[1]:
                return CommandResult("src/a.py\nsrc/b.py\n", "", 0)
            return CommandResult("", "", 0)
        raise AssertionError(f"unexpected gh call: {arguments}")

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    assert _mod.get_pr_name_only("7", "owner/repo") == "src/a.py\nsrc/b.py"


def test_unusable_rest_payload_is_not_treated_as_success(
    monkeypatch: pytest.MonkeyPatch,
):
    """A 200 with an unparseable body must not become a silent 'Unknown PR'."""

    def fake_run_gh(arguments: list[str], timeout: int = _mod.GH_TIMEOUT_SECONDS):
        del timeout
        return CommandResult("<html>Unicorn!</html>", "", 0)

    monkeypatch.setattr(_mod, "run_gh", fake_run_gh)

    metadata = _mod.fetch_pr_metadata("7", "owner/repo")

    assert metadata.error != ""
    assert metadata.number == ""
