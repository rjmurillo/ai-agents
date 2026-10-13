"""Retry ladders and backoff envelopes for gh refusals (issues #4326, #4344).

Captured refusal bodies live in ``tests/gh_auth_refusal_fixtures.py``.
"""

from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import patch

import pytest

from scripts.github_core.api import (
    _GRAPHQL_BACKOFF_BASE_SECONDS,
    REFUSAL_BACKOFF_SECONDS,
    _is_retryable_rest_api_error,
    _is_transient_graphql_error,
    gh_graphql,
)
from tests.gh_auth_refusal_fixtures import (
    BAD_CREDENTIALS,
    GRAPHQL_QUOTA,
    PERMISSION_DENIED,
    PROXY_GRAPHQL_403,
    PROXY_REST_403,
    REST_403_QUOTA,
    REST_503,
    RUN_LIST_403_QUOTA,
    SECONDARY_LIMIT,
    completed,
)


class TestIsTransientGraphqlError:
    @pytest.mark.parametrize(
        "body", [REST_403_QUOTA, RUN_LIST_403_QUOTA, GRAPHQL_QUOTA, SECONDARY_LIMIT]
    )
    def test_quota_refusal_is_retried(self, body):
        assert _is_transient_graphql_error(body) is True

    @pytest.mark.parametrize("body", ["gh: something (HTTP 429)", "HTTP 503 upstream"])
    def test_existing_transient_statuses_still_retry(self, body):
        assert _is_transient_graphql_error(body) is True

    @pytest.mark.parametrize("body", [PERMISSION_DENIED, BAD_CREDENTIALS, "HTTP 404"])
    def test_permanent_failures_are_not_retried(self, body):
        assert _is_transient_graphql_error(body) is False


class TestGraphqlRetryEnvelope:
    """The retry has to outlast the condition it matches, or it only burns calls.

    Issue #4326 measured the refusal clearing "about a minute" later. The
    original ladder capped the whole retry at 3s and averaged 1.5s, so all three
    attempts landed inside the same refusal window: two extra requests, same
    outcome. These tests measure the envelope, which no classifier assertion can.
    """

    def _run_with_recorded_sleeps(self, bodies, drained, pin_jitter=False):
        calls = [completed(stderr=body, rc=1) for body in bodies]
        sleeps: list[float] = []
        jitter = (
            patch("random.uniform", side_effect=lambda low, high: high)
            if pin_jitter
            else nullcontext()
        )
        with (
            patch("subprocess.run", side_effect=calls),
            patch("scripts.github_core.api.drained_rate_limit_buckets", return_value=drained),
            patch("time.sleep", side_effect=sleeps.append),
            jitter,
        ):
            with pytest.raises(RuntimeError) as exc:
                gh_graphql("query { viewer { login } }")
        return sleeps, str(exc.value)

    def test_quota_retry_budget_reaches_the_measured_recovery(self):
        # Pin the jitter to its ceiling so the assertion reads the ladder the
        # code selected. An upper-bound assertion cannot do that: every value
        # the short 1s/2s exponential ladder produces also satisfies
        # `<= 15.0` and `<= 30.0`, so reverting the refusal branch of
        # `_graphql_retry_ceiling` left this test green while the worst-case
        # budget fell from 45s to 3s, back inside the refusal window issue
        # #4326 measured at about a minute.
        sleeps, _ = self._run_with_recorded_sleeps([GRAPHQL_QUOTA] * 3, drained=[], pin_jitter=True)

        assert len(sleeps) == 2
        assert sleeps == [REFUSAL_BACKOFF_SECONDS[0], REFUSAL_BACKOFF_SECONDS[1]]
        assert sum(sleeps) >= 45.0

    def test_transient_5xx_keeps_the_short_ladder(self):
        """The long ladder is for refusals only; a 5xx must not wait 45s."""
        sleeps, _ = self._run_with_recorded_sleeps(
            ["HTTP 503 upstream"] * 3, drained=[], pin_jitter=True
        )

        assert len(sleeps) == 2
        assert sum(sleeps) < sum(REFUSAL_BACKOFF_SECONDS)

    def test_drained_bucket_fails_fast_instead_of_burning_attempts(self):
        """Genuine exhaustion resets on the hour; no bounded retry reaches it."""
        sleeps, message = self._run_with_recorded_sleeps([GRAPHQL_QUOTA] * 3, drained=["graphql"])

        assert sleeps == []
        assert "bucket exhausted: graphql" in message

    def test_5xx_keeps_the_short_ladder(self):
        """An upstream wobble clears in seconds; do not sleep a minute on it."""
        sleeps, _ = self._run_with_recorded_sleeps([REST_503] * 3, drained=[])

        assert len(sleeps) == 2
        assert max(sleeps) <= _GRAPHQL_BACKOFF_BASE_SECONDS


class TestTransportBlockedIsNotRetried:
    """Retrying a refused session burns the run's budget for no chance of success."""

    @pytest.mark.parametrize("body", [PROXY_REST_403, PROXY_GRAPHQL_403])
    def test_rest_retry_ladder_declines(self, body):
        assert _is_retryable_rest_api_error(body) is False

    @pytest.mark.parametrize("body", [PROXY_REST_403, PROXY_GRAPHQL_403])
    def test_graphql_retry_ladder_declines(self, body):
        assert _is_transient_graphql_error(body) is False

    def test_a_5xx_is_still_retried(self):
        """Negative control: the retry ladder still fires for real transients."""
        assert _is_transient_graphql_error("HTTP 503 Service Unavailable") is True
