#!/usr/bin/env python3
"""Always-on unit tests for the shared Copilot probe helpers (issue #3275).

The gated CLI smokes import ``copilot_hook_probe`` for the fired-hook probe and
the auth-absent detector. These unit tests exercise the pure detector without a
real CLI, so the fail-fast diagnostic is covered in ordinary PR CI (no
RUN_CLI_E2E, no auth, no credits).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
# Scope the mutation to the import so the added path never leaks into other
# tests in the session (gemini review, PR #3294).
_original_sys_path = sys.path.copy()
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from copilot_hook_probe import (
        _head_tail_excerpt,
        copilot_auth_absent,
        copilot_auth_failed,
        copilot_auth_failure_headline,
        copilot_auth_rejected,
        copilot_rate_limited,
        copilot_run_blocked,
        copilot_transient_failure,
        copilot_transient_failure_headline,
    )
finally:
    sys.path[:] = _original_sys_path


def _completed(
    *, stdout: str | None = "", stderr: str | None = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["copilot"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_auth_absent_detects_missing_token_on_stderr() -> None:
    """The dead-secret signature on stderr is recognized (issue #3275)."""
    result = _completed(
        stderr="Error: No authentication information found. Set the COPILOT_GITHUB_TOKEN env var.",
        returncode=1,
    )
    assert copilot_auth_absent(result) is True


def test_auth_absent_detects_token_hint_alone() -> None:
    """The token-env hint alone is enough, even without the first-line phrase."""
    result = _completed(stderr="please Set the COPILOT_GITHUB_TOKEN variable", returncode=1)
    assert copilot_auth_absent(result) is True


def test_auth_absent_is_case_insensitive_and_matches_stdout() -> None:
    """A stream swap (auth line on stdout) and mixed case still match (#3275)."""
    result = _completed(stdout="NO AUTHENTICATION INFORMATION FOUND", stderr="", returncode=1)
    assert copilot_auth_absent(result) is True


def test_auth_absent_false_on_healthy_run() -> None:
    """A normal authenticated run is not misread as an auth failure."""
    result = _completed(stdout="ok", stderr="", returncode=0)
    assert copilot_auth_absent(result) is False


def test_auth_absent_false_when_marker_present_but_rc_zero() -> None:
    """A healthy run (rc=0) that echoes a marker string is not misclassified (#3275)."""
    result = _completed(stdout="No authentication information found", stderr="", returncode=0)
    assert copilot_auth_absent(result) is False


def test_auth_absent_tolerates_none_streams() -> None:
    """A timed-out or not-yet-run process (None streams) does not crash."""
    result = _completed(stdout=None, stderr=None, returncode=1)
    assert copilot_auth_absent(result) is False


def test_auth_failure_headline_leads_with_cause_and_tolerates_none() -> None:
    """The headline names the real cause, cites #3275, and survives None stderr."""
    headline = copilot_auth_failure_headline(_completed(stderr=None, returncode=1))
    assert headline.startswith("Copilot auth token is empty")
    assert "COPILOT_GITHUB_TOKEN" in headline
    assert "#3275" in headline


def test_auth_failure_headline_surfaces_rc_and_stdout() -> None:
    """A stdout-only auth failure stays actionable: rc and stdout appear (#3275)."""
    headline = copilot_auth_failure_headline(
        _completed(stdout="No authentication information found", stderr="", returncode=1)
    )
    assert "rc=1" in headline
    assert "No authentication information found" in headline


# Verbatim tail of the nightly-cli-smoke stderr on run 30148661127, where the
# secret was populated and the token had expired. It carries both the rejection
# and the CLI's generic "here is how to authenticate" list, so it is the exact
# shape that made a rejected token read as an empty one (issue #3275).
_REJECTED_STDERR = (
    "Failed to fetch PAT user login (401): GitHub returned: Bad credentials\n"
    "No authentication information found. You can use any of the following "
    "methods:\n  - Set the COPILOT_GITHUB_TOKEN environment variable\n"
)


def test_auth_rejected_detects_bad_credentials() -> None:
    """A populated but refused token is recognized as rejected, not absent."""
    result = _completed(stderr=_REJECTED_STDERR, returncode=1)
    assert copilot_auth_rejected(result) is True


def test_auth_rejected_matches_the_pat_lookup_failure_alone() -> None:
    """``failed to fetch pat user login`` alone is NOT enough: it fires on network errors too.

    Only ``github returned: bad credentials`` identifies a definite credential
    rejection. A PAT-fetch failure without the bad-credentials line may be a
    rate limit, a 5xx, or a network error (issue #4504).
    """
    result = _completed(stderr="failed to fetch pat user login (401)", returncode=1)
    assert copilot_auth_rejected(result) is False


def test_auth_rejected_matches_stdout_and_is_case_insensitive() -> None:
    result = _completed(stdout="GitHub Returned: BAD CREDENTIALS", returncode=2)
    assert copilot_auth_rejected(result) is True


def test_auth_rejected_false_on_healthy_run() -> None:
    """rc=0 is never an auth failure, even if the text appears in model output."""
    result = _completed(stdout="explaining Bad credentials errors", returncode=0)
    assert copilot_auth_rejected(result) is False


def test_auth_rejected_false_when_only_absent_markers_present() -> None:
    """A genuinely empty secret must not be reported as a rejected one."""
    result = _completed(stderr="No authentication information found.", returncode=1)
    assert copilot_auth_rejected(result) is False


def test_auth_rejected_tolerates_none_streams() -> None:
    assert copilot_auth_rejected(_completed(stdout=None, stderr=None, returncode=1)) is False


def test_auth_failed_covers_both_classes_and_ignores_success() -> None:
    """The gate the smokes call fires for either auth failure and nothing else."""
    assert copilot_auth_failed(_completed(stderr=_REJECTED_STDERR, returncode=1)) is True
    assert (
        copilot_auth_failed(_completed(stderr="No authentication information found.", returncode=1))
        is True
    )
    assert copilot_auth_failed(_completed(stderr="some other crash", returncode=1)) is False
    assert copilot_auth_failed(_completed(stderr=_REJECTED_STDERR, returncode=0)) is False


def test_headline_says_rotate_not_provision_for_a_rejected_token() -> None:
    """The regression: a rejected token used to be reported as an empty one.

    The remediation differs, so the headline has to differ. This is the exact
    stderr from run 30148661127, which matches the absent markers too.
    """
    headline = copilot_auth_failure_headline(_completed(stderr=_REJECTED_STDERR, returncode=1))
    assert "rejected" in headline
    assert "rotate" in headline
    assert "is empty" not in headline


def test_headline_still_says_provision_for_an_absent_token() -> None:
    headline = copilot_auth_failure_headline(
        _completed(stderr="No authentication information found.", returncode=1)
    )
    assert "is empty" in headline
    assert "provision" in headline.lower()
    assert "rejected" not in headline


def test_auth_absent_is_false_for_a_rejected_token() -> None:
    """A refused token is not an absent one, even though the CLI prints both.

    The rejection stderr carries the CLI's own "you can use any of the
    following methods" list, so the absent markers match a credential that
    plainly exists. The predicate must exclude that case itself rather than
    rely on every caller ordering the two checks correctly.
    """
    result = _completed(stderr=_REJECTED_STDERR, returncode=1)
    assert copilot_auth_rejected(result) is True
    assert copilot_auth_absent(result) is False
    assert copilot_auth_failed(result) is True


def test_auth_rejected_ignores_a_bare_bad_credentials_mention() -> None:
    """Model output may quote the phrase; only the CLI's auth-gate line counts.

    Misclassifying an unrelated crash as a rejection sends the reader to rotate
    a healthy secret, which is worse than no headline at all.
    """
    noisy = _completed(
        stdout="the API replied with bad credentials for the sample request",
        returncode=1,
    )
    assert copilot_auth_rejected(noisy) is False
    assert copilot_auth_failed(noisy) is False


# ---------------------------------------------------------------------------
# Rate-limit detection (issue #4504)
# ---------------------------------------------------------------------------

_RATE_LIMIT_STDERR = (
    "API rate limit exceeded for user ID 6811113. If you reach out to GitHub Support for help, "
    "please include the request ID 8DA0:35BFF7:1D6A8A3:2456E21:6A70F1A2 and timestamp "
    "2026-08-03 20:31:01 UTC. For more on scraping GitHub, see https://docs.github.com/en/site-policy/"
    "github-terms/github-acceptable-use-policies\n"
    "\nYour token may still be valid. Check your network connection and try again.\n"
    "\nTo authenticate, you can use any of the following methods:\n"
    "  * Start 'copilot' and run the '/login' command\n"
)

_SECONDARY_RATE_LIMIT_STDERR = (
    "secondary rate limit triggered for this request\n"
    "Your token may still be valid. Check your network connection and try again.\n"
)


def test_rate_limited_detects_api_rate_limit_exceeded() -> None:
    """The primary rate-limit phrase is recognized (issue #4504)."""
    result = _completed(stderr=_RATE_LIMIT_STDERR, returncode=1)
    assert copilot_rate_limited(result) is True


def test_rate_limited_detects_secondary_rate_limit() -> None:
    result = _completed(stderr=_SECONDARY_RATE_LIMIT_STDERR, returncode=1)
    assert copilot_rate_limited(result) is True


def test_rate_limited_detects_vendor_hedge_sentence() -> None:
    """The vendor's 'token may still be valid' line is itself a rate-limit signal."""
    result = _completed(
        stderr="Your token may still be valid. Check your network connection and try again.",
        returncode=1,
    )
    assert copilot_rate_limited(result) is True


def test_rate_limited_false_on_healthy_run() -> None:
    result = _completed(stdout="ok", returncode=0)
    assert copilot_rate_limited(result) is False


def test_rate_limited_false_for_absent_token() -> None:
    result = _completed(stderr="No authentication information found.", returncode=1)
    assert copilot_rate_limited(result) is False


def test_rate_limited_takes_precedence_over_auth_rejected() -> None:
    """A rate-limit response must not be reported as a rejected credential."""
    result = _completed(stderr=_RATE_LIMIT_STDERR, returncode=1)
    assert copilot_rate_limited(result) is True
    assert copilot_auth_rejected(result) is False
    assert copilot_auth_absent(result) is False
    assert copilot_auth_failed(result) is False


def test_rate_limited_takes_precedence_over_auth_absent_when_list_appears() -> None:
    """The CLI prints the auth-method list after a rate limit too.

    Without the rate-limit check, the COPILOT_GITHUB_TOKEN mention in the list
    would match COPILOT_AUTH_ABSENT_MARKERS (issue #4504).
    """
    result = _completed(
        stderr=(
            "API rate limit exceeded for user ID 123.\n"
            "To authenticate, you can use any of the following methods:\n"
            "  Set the COPILOT_GITHUB_TOKEN environment variable\n"
        ),
        returncode=1,
    )
    assert copilot_rate_limited(result) is True
    assert copilot_auth_absent(result) is False
    assert copilot_run_blocked(result) is True


def test_run_blocked_covers_rate_limit_absent_and_rejected() -> None:
    assert copilot_run_blocked(_completed(stderr=_RATE_LIMIT_STDERR, returncode=1)) is True
    assert (
        copilot_run_blocked(_completed(stderr="No authentication information found.", returncode=1))
        is True
    )
    assert copilot_run_blocked(_completed(stderr=_REJECTED_STDERR, returncode=1)) is True
    assert copilot_run_blocked(_completed(stdout="ok", returncode=0)) is False


def test_run_blocked_false_for_unrelated_failure() -> None:
    result = _completed(stderr="segmentation fault", returncode=1)
    assert copilot_run_blocked(result) is False


# ---------------------------------------------------------------------------
# Head+tail excerpt (issue #4504)
# ---------------------------------------------------------------------------


def test_head_tail_excerpt_short_string_returns_repr() -> None:
    """Strings shorter than head+tail are returned as repr without drop message."""
    s = "hello world"
    result = _head_tail_excerpt(s, head=300, tail=300)
    assert result == repr(s)
    assert "dropped" not in result


def test_head_tail_excerpt_long_string_shows_drop_count() -> None:
    """Long strings show how many chars were dropped in the middle."""
    s = "A" * 100 + "B" * 100 + "C" * 100
    result = _head_tail_excerpt(s, head=50, tail=50)
    assert "dropped" in result
    assert "200 chars dropped" in result
    assert repr("A" * 50) in result
    assert repr("C" * 50) in result


def test_head_tail_excerpt_none_is_empty_repr() -> None:
    assert _head_tail_excerpt(None) == repr("")


def test_headline_excerpt_uses_head_tail_not_tail_only() -> None:
    """Headline includes the leading diagnostic sentence, not just the boilerplate tail.

    This is the regression for issue #4504: the old tail-only slice kept the
    GitHub request-ID boilerplate and cut the 'API rate limit exceeded' sentence.
    """
    # Even when copilot_auth_absent fires (no rate-limit marker here in simplified form),
    # the headline must include the beginning of stderr.
    absent_result = _completed(
        stderr="No authentication information found. " + "X" * 1000,
        returncode=1,
    )
    headline = copilot_auth_failure_headline(absent_result)
    assert "No authentication information found" in headline


def test_headline_preserves_leading_cause_sentence() -> None:
    """The first 300 chars of stderr appear in the headline (issue #4504)."""
    leading = "API rate limit exceeded for user ID 999. "
    filler = "X" * 1000
    rejected_result = _completed(
        stderr="GitHub returned: Bad credentials\n" + leading + filler,
        returncode=1,
    )
    headline = copilot_auth_failure_headline(rejected_result)
    assert "GitHub returned: Bad credentials" in headline

# Excerpt of the stderr from a rate-limited run, captured 2026-08-04 from a
# pre-push `plugin-load-e2e` failure. It starts mid-request-id and its first line
# ends in an ellipsis, so treat this as a captured excerpt, not the full GitHub
# error payload. The request id and timestamp are GitHub's standard error footer.
# Note the auth-methods list: it is the SAME boilerplate a missing token
# produces, which is why the absent detector used to claim this run had no
# token. See issue #4504.
_RATE_LIMITED_STDERR = (
    "FF7:14E4D001:1566914C:6A71CB91 and timestamp 2026-08-04 11:22:57 UTC. F\u2026\n\n"
    "Your token may still be valid. Check your network connection and try again.\n\n"
    "To authenticate, you can use any of the following methods:\n"
    "  \u2022 Start 'copilot' and run the '/login' command\n"
    "  \u2022 Set the COPILOT_GITHUB_TOKEN, GH_TOKEN, or GITHUB_TOKEN environment variable\n"
    "  \u2022 Run 'gh auth login' to authenticate with the GitHub CLI\n"
)


def test_transient_failure_detects_the_measured_rate_limited_run() -> None:
    """The captured rate-limit stderr is classified as transient (issue #4504)."""
    assert copilot_transient_failure(_completed(stderr=_RATE_LIMITED_STDERR, returncode=1))


def test_rate_limited_run_is_not_an_auth_failure() -> None:
    """The regression this fixes: a rate limit read as an empty token (issue #4504).

    The auth-methods list in the captured stderr matches every absent marker, so
    without the transient carve-out the smoke failed with "provision
    COPILOT_GITHUB_TOKEN" for a token that exists and works.
    """
    result = _completed(stderr=_RATE_LIMITED_STDERR, returncode=1)
    assert not copilot_auth_absent(result)
    assert not copilot_auth_rejected(result)
    assert not copilot_auth_failed(result)


def test_transient_failure_matches_the_network_advice_alone() -> None:
    """Either half of the CLI's transient disclaimer is sufficient."""
    assert copilot_transient_failure(
        _completed(stderr="Check your network connection and try again.", returncode=1)
    )


def test_transient_failure_is_case_insensitive_and_matches_stdout() -> None:
    """Survives a stream swap and the CLI's own capitalization."""
    assert copilot_transient_failure(
        _completed(stdout="YOUR TOKEN MAY STILL BE VALID.", stderr="", returncode=1)
    )


def test_transient_failure_false_on_healthy_run() -> None:
    """rc=0 is never a transient failure, even if the text appears in output."""
    assert not copilot_transient_failure(
        _completed(stdout="your token may still be valid", returncode=0)
    )


def test_transient_failure_false_for_a_genuinely_absent_token() -> None:
    """A real missing-token abort stays an auth failure, not a transient one."""
    result = _completed(
        stderr="Error: No authentication information found. Set the COPILOT_GITHUB_TOKEN env var.",
        returncode=1,
    )
    assert not copilot_transient_failure(result)
    assert copilot_auth_absent(result)
    assert copilot_auth_failed(result)


def test_transient_failure_false_for_a_genuinely_rejected_token() -> None:
    """A real refusal stays an auth failure, not a transient one."""
    result = _completed(stderr="GitHub returned: Bad credentials", returncode=1)
    assert not copilot_transient_failure(result)
    assert copilot_auth_rejected(result)
    assert copilot_auth_failed(result)


def test_transient_failure_false_for_a_bare_5xx_or_socket_error() -> None:
    """Pins the docstring: only the CLI's disclaimer fires, not 5xx text itself.

    The predicate matches the CLI's own "token may still be valid" sentence. A
    status code or a raw socket message that never reaches that sentence is out
    of scope, and the docstring says so. Without this test the docstring could
    silently regrow the claim that it covers 5xx in general.
    """
    undetected = (
        "HTTP 502 Bad Gateway from api.github.com",
        "Server Error: 503 Service Unavailable",
        "dial tcp 140.82.113.6:443: connect: connection refused",
    )
    for stderr in undetected:
        assert not copilot_transient_failure(_completed(stderr=stderr, returncode=1))

    # Positive control: the same call shape DOES fire on the disclaimer, so the
    # assertions above are meaningful silence rather than a dead predicate.
    assert copilot_transient_failure(
        _completed(
            stderr="Your token may still be valid. Check your network connection and try again.",
            returncode=1,
        )
    )


def test_transient_failure_tolerates_none_streams() -> None:
    """A timed-out or not-yet-run process has None streams and must not raise."""
    assert not copilot_transient_failure(
        _completed(stdout=None, stderr=None, returncode=1)
    )


def test_transient_headline_names_the_cause_and_denies_an_auth_fault() -> None:
    """The skip reason must not send anyone to provision or rotate a secret."""
    text = copilot_transient_failure_headline(
        _completed(stderr=_RATE_LIMITED_STDERR, returncode=1)
    )
    lowered = text.lower()
    assert "transient" in lowered
    assert "not an auth" in lowered
    assert "rc=1" in lowered
    assert "provision" not in lowered
    assert "rotate" not in lowered


def test_transient_headline_tolerates_none_streams() -> None:
    """None streams must not raise while building the skip reason."""
    text = copilot_transient_failure_headline(
        _completed(stdout=None, stderr=None, returncode=3)
    )
    assert "rc=3" in text
