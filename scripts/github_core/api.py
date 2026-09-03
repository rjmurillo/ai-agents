# taste-lint: ignore file-size, facade keeps the legacy import surface stable.
"""GitHub API helpers: auth, pagination, GraphQL, issue comments, rate limits.

Cohesive sub-concerns live in sibling modules and are re-exported here so the
public import surface ``from scripts.github_core.api import ...`` stays stable
(Issue #1910):

- ``log_safety``: ``safe_log_str`` (CWE-117 log-forging defense).
- ``review_threads``: review-thread shape, predicates, paginated fetch,
  ``FetchStatus``, ``get_unresolved_review_threads``.
- ``rate_limit``: ``RateLimitResult``, ``RateLimitStatus``,
  ``DEFAULT_RATE_THRESHOLDS``,
  ``check_workflow_rate_limit``.
"""

from __future__ import annotations

import json
import logging
import random
import re
import subprocess
import sys
import time
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, NoReturn

if TYPE_CHECKING:
    from scripts.github_core.protocol import GitHubClient

from scripts.github_core.log_safety import safe_log_str
from scripts.github_core.rate_limit import (  # noqa: F401
    DEFAULT_RATE_THRESHOLDS,
    RateLimitResult,
    RateLimitStatus,
    check_workflow_rate_limit,
)
from scripts.github_core.review_threads import (  # noqa: F401
    _REVIEW_THREADS_MAX_PAGES,
    _REVIEW_THREADS_QUERY,
    FetchStatus,
    _fetch_review_threads_page,
    _log_review_threads_page,
    _warn_review_threads_capped,
    count_unresolved_threads,
    filter_unresolved_threads,
    get_unresolved_review_threads,
    transform_review_thread,
)
from scripts.github_core.validation import is_github_name_valid

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepoInfo:
    """Repository owner and name.

    Replaces raw ``dict[str, str]`` returns that had inconsistent key
    casing across modules.  Attribute access (``info.owner``) is enforced
    by the type checker, eliminating ``KeyError`` risks.
    """

    owner: str
    repo: str


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def error_and_exit(message: str, exit_code: int) -> NoReturn:
    """Write an error to stderr and exit with the given code.

    Exit codes follow ADR-035:
        0 - Success
        1 - Invalid parameters / logic error
        2 - Config error
        3 - External error (API failure)
        4 - Auth error (not authenticated, permission denied)
    """
    print(message, file=sys.stderr)
    raise SystemExit(exit_code)


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

_GITHUB_REMOTE_PATTERN = re.compile(
    r"^(?:[A-Za-z][A-Za-z0-9+.-]*://)?(?:[^/@]+@)?"
    r"github\.com[:/]([^/]+)/([^/]+)$"
)


def get_repo_info() -> RepoInfo | None:
    """Infer repository owner and name from git remote origin URL.

    Preserves dots in repository names and removes only a trailing ``.git``.

    Returns:
        RepoInfo with owner and repo, or None if not in a git repo.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if result.returncode != 0:
            return None

        match = _GITHUB_REMOTE_PATTERN.search(result.stdout.strip())
        if match:
            return RepoInfo(
                owner=match.group(1),
                repo=re.sub(r"\.git$", "", match.group(2)),
            )
    except subprocess.TimeoutExpired:
        logger.debug("git remote get-url origin timed out")
    except FileNotFoundError:
        logger.debug("git executable not found on PATH")
    return None


def resolve_repo_params(owner: str = "", repo: str = "") -> RepoInfo:
    """Resolve owner and repo, inferring from git remote if not provided.

    Raises SystemExit if parameters cannot be determined or are invalid.

    Returns:
        RepoInfo with owner and repo.
    """
    if not owner or not repo:
        repo_info = get_repo_info()
        if repo_info:
            owner = owner or repo_info.owner
            repo = repo or repo_info.repo
        else:
            error_and_exit(
                "Could not infer repository info. Please provide -Owner and -Repo parameters.",
                2,
            )

    if not is_github_name_valid(owner, "Owner"):
        error_and_exit(f"Invalid GitHub owner name: {owner}", 2)
    if not is_github_name_valid(repo, "Repo"):
        error_and_exit(f"Invalid GitHub repository name: {repo}", 2)

    return RepoInfo(owner=owner, repo=repo)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class GhAuthStatus(Enum):
    """Classification of a GitHub CLI authentication preflight.

    ``gh auth status`` reduces every failure to a nonzero exit. Collapsing that
    to a bool sent operators to ``gh auth login`` for a GitHub 5xx (issue #3139)
    and for an exhausted GraphQL quota (issue #4344). Each cause needs a
    different remedy, so each gets its own member.

    ``TRANSPORT_BLOCKED`` is the agent-sandbox case: ``gh`` is installed and
    carries a credential, but the session's egress policy refuses GitHub, so
    no ``gh`` invocation can succeed no matter how the token is repaired.
    ``gh auth login`` is the wrong remedy and retrying is wasted work; the
    remedy is a different transport. See :data:`_TRANSPORT_BLOCKED_SIGNATURE`.
    """

    AUTHENTICATED = "authenticated"
    MISSING_GH = "missing_gh"
    INVALID_CREDENTIALS = "invalid_credentials"
    TRANSIENT_ERROR = "transient_error"
    RATE_LIMITED = "rate_limited"
    SECONDARY_RATE_LIMITED = "secondary_rate_limited"
    TRANSPORT_BLOCKED = "transport_blocked"


# Statuses that are a token problem the operator can fix (exit 4). Everything
# else that is not AUTHENTICATED is an upstream condition (exit 3), with one
# exception: TRANSPORT_BLOCKED is an environment configuration fault and maps
# to exit 2, because exit 3 is the retry signal and a refused session has no
# reset. See describe_gh_auth_failure.
_AUTH_FAILURE_STATUSES = frozenset(
    {GhAuthStatus.MISSING_GH, GhAuthStatus.INVALID_CREDENTIALS}
)

# Substrings that prove a gh failure message is a credential fault (ADR-035
# exit 4). Quoted verbatim from the canonical per-script copy in
# `.claude/skills/github/scripts/issue/close_issue.py::_AUTH_ERROR_MARKERS`
# as of commit bc179ad3a:
#
#     _AUTH_ERROR_MARKERS = (
#         "credential",
#         "not logged in",
#         "bad credentials",
#         "could not authenticate",
#         "authentication",
#         "requires authentication",
#     )
#
# The same tuple is copy-pasted into new_issue.py (with a "Copied verbatim from
# close_issue.py" comment), reopen_issue.py, get_issue_comments.py, and
# get_pr_reviews.py. This is the shared home so new callers stop adding copy
# number six; the existing copies are left alone (issue #4951 touches only
# close_issue.py).
AUTH_ERROR_MARKERS = (
    "credential",
    "not logged in",
    "bad credentials",
    "could not authenticate",
    "authentication",
    "requires authentication",
)


# GitHub's permission-denial wording for installations/apps (HTTP 403 but NOT
# rate-limit).  Checked separately from AUTH_ERROR_MARKERS because it must not
# match when the 403 is a rate-limit response (issue #4951, PR #5011).
_PERMISSION_DENIED_MARKER = "resource not accessible by integration"

# Patterns that identify a 403 as a rate-limit response rather than a
# permission denial.  When present, the text is NOT an auth failure.
_RATE_LIMIT_MARKERS = (
    "rate limit",
    "abuse detection",
    "secondary rate limit",
)


def is_auth_failure_text(text: str) -> bool:
    """Return True when gh failure text names a credential or permission fault (exit 4).

    Stricter than :func:`classify_gh_failure_text`, on purpose. That function
    classifies the output of an auth *preflight*, where the probe has already
    failed, so its fallback bucket is ``INVALID_CREDENTIALS``. Applied to an
    arbitrary API error ("Could not resolve to a PullRequest") the fallback
    would report a credential fault and send the operator to ``gh auth login``
    for an upstream problem. This predicate requires an explicit marker and
    leaves everything else to the caller, which maps it to exit 3 (external).

    GitHub returns HTTP 403 for two unrelated situations: rate-limiting and
    permission denial ("Resource not accessible by integration").  Only the
    latter is an auth/permission failure (exit 4).  Rate-limit 403s remain
    external failures (exit 3).
    """
    lowered = (text or "").lower()
    # Explicit credential markers always win.
    if any(marker in lowered for marker in AUTH_ERROR_MARKERS):
        return True
    # Permission denial marker, but only when NOT a rate-limit response.
    if _PERMISSION_DENIED_MARKER in lowered:
        if any(rl in lowered for rl in _RATE_LIMIT_MARKERS):
            return False
        return True
    return False


@dataclass(frozen=True)
class GhAuthResult:
    """Outcome of :func:`check_gh_auth` with a sanitized diagnostic detail."""

    status: GhAuthStatus
    detail: str = ""

    @property
    def is_authenticated(self) -> bool:
        return self.status is GhAuthStatus.AUTHENTICATED


# Credentials that must never reach an error envelope or log line.
_TOKEN_REDACTION_PATTERN = re.compile(
    r"gh[opsu]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|\b[A-Fa-f0-9]{40}\b"
)

# Signatures that mark a transport (REST/GraphQL) as transiently degraded
# rather than proof of an invalid token: 5xx responses, the GitHub "Unicorn"
# page, timeouts, and connection failures (issue #3139).
#
# The second block is gh's own connectivity wording, captured from the binary
# rather than guessed. `gh api --hostname invalid.example.test user` on gh
# 2.97.0 prints:
#
#     dial tcp: lookup invalid.example.test on 127.0.0.53:53: no such host
#     error connecting to invalid.example.test
#     check your internet connection or https://githubstatus.com
#
# None of the first-block alternatives matches any of those lines, so a plain
# loss of connectivity used to fall through to INVALID_CREDENTIALS and send the
# operator to `gh auth login`, which is the exact #3139 symptom. gh is a Go
# program, so its transport errors carry Go's net wording ("no such host",
# "i/o timeout", "network is unreachable"), never curl's "could not resolve
# host"; both are listed because callers also shell out through other clients.
_TRANSIENT_SIGNATURE = re.compile(
    r"HTTP 5\d\d"
    r"|status(?:\s+code)?\s+5\d\d"
    r"|\b50[0-4]\b"
    r"|unicorn"
    r"|try again"
    r"|temporarily unavailable"
    r"|service unavailable"
    r"|bad gateway"
    r"|gateway time"
    r"|timed out"
    r"|timeout"
    r"|connection (?:reset|refused|error|timed out)"
    r"|could not resolve host"
    r"|server error"
    r"|no server is currently available"
    r"|error connecting to"
    r"|check your internet connection"
    r"|githubstatus\.com"
    r"|dial tcp"
    r"|no such host"
    r"|i/o timeout"
    r"|network is unreachable"
    r"|tls handshake"
    r"|unexpected eof",
    re.IGNORECASE,
)

# GitHub's secondary limit and abuse-detection wording. Checked before the
# primary pattern because both bodies say "rate limit" and the remedies differ:
# secondary clears in about a minute, primary waits for the bucket reset.
_SECONDARY_RATE_LIMIT_SIGNATURE = re.compile(
    r"secondary rate limit|abuse detection", re.IGNORECASE
)

# Primary quota refusal, in every shape GitHub emits it: with an HTTP code
# ("... (HTTP 403)"), without one ("GraphQL: API rate limit already exceeded
# for user ID ..."), and the REST body form (issues #4326, #4344).
_RATE_LIMIT_SIGNATURE = re.compile(r"rate limit (?:already )?exceeded", re.IGNORECASE)
_RATE_LIMIT_REMAINING_HEADER = re.compile(
    r"(?im)^x-ratelimit-remaining:\s*(\d+)\s*$"
)

# An agent sandbox that proxies egress can refuse GitHub for the whole session
# while leaving `gh` installed and a GH_TOKEN set. The refusal arrives as HTTP
# 403 with no rate-limit and no transport wording, so it used to fall through
# to INVALID_CREDENTIALS and tell the operator to run `gh auth login`, which
# cannot fix it: the credential is not the thing being refused.
#
# Wording captured from the running proxy on 2026-09-03 rather than guessed
# (gh 2.98.0, Claude Code remote session). REST:
#
#     GitHub access is not enabled for this session. An org admin must connect
#     the Claude GitHub App for this organization. (HTTP 403)
#
# GraphQL refuses separately, with its own body: "This GraphQL query is not
# enabled for this session [...]" followed by a steer back to REST.
#
# The two bodies do NOT mean the same thing, and an earlier version of this
# matcher treated them as if they did (Copilot review on PR #5509). The REST
# body refuses GitHub for the session as a whole. The GraphQL body refuses one
# query shape and says in the same breath that REST is still served, so on its
# own it is not evidence that gh is unusable. Because this classifier also runs
# on individual operation failures, the broad reading let one refused GraphQL
# query suppress retries and declare the whole transport dead while other gh
# calls still worked.
#
# So the global verdict requires the global wording. Anything narrower is
# matched by _SESSION_POLICY_REFUSAL below and only counts as evidence once
# BOTH transports have been observed failing, which only the auth preflight
# can establish.
#
# This taxonomy was already measured and written down before this classifier
# existed: ADR-100 ("Retire PR size ceilings"), the "Two different 403s"
# paragraph, records that the GraphQL body is a query allowlist naming a
# working alternative while the REST body is the account-level denial that
# closes it. Read that before widening this pattern again.
_TRANSPORT_BLOCKED_SIGNATURE = re.compile(
    r"github access is not enabled for this session",
    re.IGNORECASE,
)

# Any session-policy refusal, query-scoped ones included. Never sufficient on
# its own: :func:`check_gh_auth` pairs it with the fact that REST and GraphQL
# both failed before returning TRANSPORT_BLOCKED.
_SESSION_POLICY_REFUSAL = re.compile(
    r"not enabled for this session"
    r"|docs\.anthropic\.com/en/docs/claude-code/github-actions",
    re.IGNORECASE,
)


def sanitize_failure_detail(text: object, limit: int = 200) -> str:
    """Redact tokens and collapse whitespace so detail is envelope/log safe.

    Collapsing whitespace also strips CR/LF, which is the CWE-117 log-forging
    defense ``log_safety.safe_log_str`` provides; this helper additionally
    redacts credentials and bounds the length, so remote text (a gh stderr
    body, a GraphQL error) is safe to place in an error envelope.

    Was ``_sanitize_auth_detail``. Renamed and made public in issue #4951 so
    the PR merge-state reader and the close verifier sanitize probe details
    the same way instead of each growing a copy.
    """
    redacted = _TOKEN_REDACTION_PATTERN.sub("[REDACTED]", str(text) if text else "")
    redacted = " ".join(redacted.split())
    if len(redacted) > limit:
        redacted = redacted[:limit] + "..."
    return redacted


def classify_gh_failure_text(text: str) -> GhAuthStatus:
    """Map gh failure output to the condition that produced it.

    Rate-limit wording wins over the transient signature because a quota
    refusal is often delivered as ``HTTP 403 ... API rate limit exceeded`` and
    the 403 alone would otherwise read as a permission denial.

    A sandbox refusal is checked after the quota buckets and before the
    transient signature: it is neither, and it must not reach the
    ``INVALID_CREDENTIALS`` fallback, whose remedy tells the operator to
    re-authenticate a token that is not the problem.
    """
    haystack = text or ""
    if _SECONDARY_RATE_LIMIT_SIGNATURE.search(haystack):
        return GhAuthStatus.SECONDARY_RATE_LIMITED
    if _RATE_LIMIT_SIGNATURE.search(haystack):
        remaining = _RATE_LIMIT_REMAINING_HEADER.search(haystack)
        if remaining is not None and int(remaining.group(1)) > 0:
            return GhAuthStatus.SECONDARY_RATE_LIMITED
        return GhAuthStatus.RATE_LIMITED
    if _TRANSPORT_BLOCKED_SIGNATURE.search(haystack):
        return GhAuthStatus.TRANSPORT_BLOCKED
    if _TRANSIENT_SIGNATURE.search(haystack):
        return GhAuthStatus.TRANSIENT_ERROR
    return GhAuthStatus.INVALID_CREDENTIALS


def classify_gh_failure_response(
    text: str,
    headers: Mapping[str, str] | None = None,
) -> GhAuthStatus:
    """Classify a failed GitHub response from its own headers.

    ``gh api rate_limit`` is exempt from the limiter it reports, so it cannot
    prove a 403 is not throttling. The failed response's ``x-ratelimit-*``
    headers are the local evidence: remaining zero means primary exhaustion;
    remaining above zero with rate-limit wording means a secondary limiter.
    """
    status = classify_gh_failure_text(text)
    if status is not GhAuthStatus.RATE_LIMITED:
        return status

    normalized = {key.lower(): value for key, value in (headers or {}).items()}
    remaining = normalized.get("x-ratelimit-remaining")
    if remaining is None:
        return status
    try:
        remaining_count = int(remaining.strip())
    except ValueError:
        return status
    if remaining_count > 0:
        return GhAuthStatus.SECONDARY_RATE_LIMITED
    return GhAuthStatus.RATE_LIMITED


def _run_gh(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _graphql_viewer_probe() -> GhAuthResult:
    """Confirm auth over the GraphQL transport (issue #3139).

    ``gh auth status`` uses the REST transport, which can return a transient
    5xx or a quota refusal while the same token authenticates GraphQL and git.
    When REST status is inconclusive, probe ``gh api graphql`` for the viewer: a
    clean success means the token is valid and only REST was degraded.
    """
    try:
        result = _run_gh(["api", "graphql", "-f", "query=query { viewer { login } }"])
    except FileNotFoundError:
        logger.debug("GitHub CLI (gh) not found on PATH")
        return GhAuthResult(GhAuthStatus.MISSING_GH)
    except subprocess.TimeoutExpired:
        logger.debug("gh api graphql viewer probe timed out")
        return GhAuthResult(
            GhAuthStatus.TRANSIENT_ERROR, "GraphQL viewer probe timed out"
        )

    if result.returncode == 0:
        return GhAuthResult(GhAuthStatus.AUTHENTICATED)

    combined = f"{result.stdout}\n{result.stderr}"
    return GhAuthResult(
        classify_gh_failure_text(combined), sanitize_failure_detail(combined)
    )


def _rest_credential_probe() -> GhAuthResult:
    """Ask REST whether the credential itself works, via ``gh api user``.

    ``gh auth status`` is not that question. It renders any failure of its own
    call as "The token in GH_TOKEN is invalid", so a proxy that refuses one
    endpoint by policy reads as a bad token. Measured on gh 2.98.0 in a Claude
    Code remote session on 2026-09-03: ``gh auth status`` reported the token
    invalid while ``gh api user`` returned the real account, and the same
    session refused ``gh api repos/{owner}/{repo}`` and every GraphQL query.

    ``/user`` is authenticated and repository-independent, so a success proves
    the credential and a 401 disproves it. It is reached only when the GraphQL
    confirmation was refused by session policy and so tested nothing.
    """
    try:
        result = _run_gh(["api", "user"])
    except FileNotFoundError:
        logger.debug("GitHub CLI (gh) not found on PATH")
        return GhAuthResult(GhAuthStatus.MISSING_GH)
    except subprocess.TimeoutExpired:
        logger.debug("gh api user credential probe timed out")
        return GhAuthResult(
            GhAuthStatus.TRANSIENT_ERROR, "REST credential probe timed out"
        )

    if result.returncode == 0:
        return GhAuthResult(GhAuthStatus.AUTHENTICATED)

    combined = f"{result.stdout}\n{result.stderr}"
    return GhAuthResult(
        classify_gh_failure_text(combined), sanitize_failure_detail(combined)
    )


# Quota refusals clear on their own, so they must survive the promotion below.
_RETRYABLE_REFUSAL_STATUSES = frozenset(
    {GhAuthStatus.RATE_LIMITED, GhAuthStatus.SECONDARY_RATE_LIMITED}
)


def _is_session_wide_refusal(rest_text: str, graphql_text: str) -> bool:
    """Return True when the pair of failures proves the session is refused.

    "Both probes failed" is not that proof, and an earlier version of this
    logic accepted it (Copilot review on PR #5509). A transient REST 503
    alongside a query-scoped GraphQL refusal satisfies "either transport
    mentions a policy refusal", so it was promoted to TRANSPORT_BLOCKED and
    suppressed the REST retry ladder even though REST would have recovered.

    Two shapes qualify:

    1. REST returns the account-level denial. That closes the session on its
       own, whatever GraphQL said.
    2. Both transports report a policy refusal. Neither body alone proves more
       than its own scope; together they leave no transport unrefused.

    ADR-100's "Two different 403s" paragraph is the measurement behind the
    distinction between the two bodies.
    """
    if _TRANSPORT_BLOCKED_SIGNATURE.search(rest_text):
        return True
    return bool(
        _SESSION_POLICY_REFUSAL.search(rest_text)
        and _SESSION_POLICY_REFUSAL.search(graphql_text)
    )


def check_gh_auth() -> GhAuthResult:
    """Classify GitHub CLI auth across the REST and GraphQL transports.

    ``gh auth status`` (REST) can misreport a transient 5xx or an exhausted
    quota as an invalid token, which sent operators to ``gh auth login`` for a
    GitHub outage (issue #3139) and blocked the pr-autofix gates during a
    GraphQL quota window (issue #4344). When REST status is nonzero but ``gh``
    is installed, confirm the real state via a GraphQL viewer probe before
    declaring an auth failure.

    Returns:
        A :class:`GhAuthResult`. ``MISSING_GH`` and ``INVALID_CREDENTIALS`` map
        to auth exit 4; ``TRANSPORT_BLOCKED`` maps to config exit 2; every
        other non-authenticated status maps to external exit 3.
    """
    try:
        result = _run_gh(["auth", "status"])
    except FileNotFoundError:
        logger.debug("GitHub CLI (gh) not found on PATH")
        return GhAuthResult(GhAuthStatus.MISSING_GH)
    except subprocess.TimeoutExpired:
        logger.debug("gh auth status timed out")
        # A REST status timeout is not proof of an invalid token; confirm via
        # the GraphQL transport before failing.
        return _graphql_viewer_probe()

    if result.returncode == 0:
        return GhAuthResult(GhAuthStatus.AUTHENTICATED)

    # REST status failed. Do not trust its verdict (it may relabel a 5xx or a
    # quota refusal as an invalid token); confirm the real state over GraphQL.
    rest_text = f"{result.stdout}\n{result.stderr}"
    probe = _graphql_viewer_probe()
    if probe.is_authenticated or probe.status is GhAuthStatus.MISSING_GH:
        return probe

    # Both transports failed. That is the only evidence that proves a refusal
    # is session-wide rather than scoped to one query shape, so a policy
    # refusal seen on either transport is promoted to TRANSPORT_BLOCKED only
    # here (Copilot review on PR #5509).
    # A quota verdict from the probe outranks promotion. Quota has a reset and
    # its own backoff, so overwriting it with TRANSPORT_BLOCKED would convert a
    # condition that clears into a config failure and drop the retry the caller
    # should make (Copilot review on PR #5509).
    if probe.status in _RETRYABLE_REFUSAL_STATUSES:
        return probe
    if probe.status is not GhAuthStatus.TRANSPORT_BLOCKED and _is_session_wide_refusal(
        rest_text, probe.detail
    ):
        return GhAuthResult(GhAuthStatus.TRANSPORT_BLOCKED, probe.detail)

    # A policy refusal on GraphQL is evidence about the policy and none at all
    # about the credential, so the confirmation this function exists to make did
    # not happen. INVALID_CREDENTIALS here is only classify_gh_failure_text's
    # unrecognized-text fallback, and returning it reports REST's unconfirmed
    # verdict as if it had been confirmed, which is the #3139 and #4344 shape.
    if probe.status is GhAuthStatus.INVALID_CREDENTIALS and _SESSION_POLICY_REFUSAL.search(
        probe.detail
    ):
        # A REST failure that classifies as anything but the fallback said
        # something real. A 5xx is still retryable and a quota window still has
        # a reset, so neither is overwritten (Copilot review on PR #5509).
        rest_status = classify_gh_failure_text(rest_text)
        if rest_status is not GhAuthStatus.INVALID_CREDENTIALS:
            return GhAuthResult(rest_status, sanitize_failure_detail(rest_text))
        # Both narrators are unreliable here, so ask the one question that has
        # a decisive answer: does the credential authenticate at all?
        confirmation = _rest_credential_probe()
        if confirmation.is_authenticated:
            return GhAuthResult(GhAuthStatus.TRANSPORT_BLOCKED, probe.detail)
        return confirmation
    return probe


def is_gh_authenticated() -> bool:
    """Return True if the GitHub token authenticates on any supported transport.

    Thin boolean wrapper over :func:`check_gh_auth` for callers that only need a
    gate. A transient REST failure (for example a 5xx "Unicorn" page) no longer
    reads as unauthenticated when the same token still works over GraphQL
    (issue #3139).
    """
    return check_gh_auth().is_authenticated


def _rate_limit_resources() -> dict:
    """Best-effort ``gh api rate_limit`` resources map, or ``{}``.

    ``gh api rate_limit`` is exempt from the quota it reports, so it keeps
    answering during a refusal. Never raises: every caller only enriches or
    shortens a diagnostic with it.
    """
    try:
        result = _run_gh(["api", "rate_limit"])
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    try:
        return (json.loads(result.stdout) or {}).get("resources") or {}
    except json.JSONDecodeError:
        return {}


def drained_rate_limit_buckets() -> list[str]:
    """Names of buckets the exempt payload reports at zero remaining.

    Issue #4326 measured two different conditions behind the same "API rate
    limit exceeded" wording. The velocity refusal leaves every bucket healthy
    and clears in about a minute, so retrying wins. Genuine exhaustion shows in
    the payload (``core 4950/5000, graphql 0/5000, reset 34m``) and no bounded
    retry can outlast it, so retrying only burns requests. This separates them.

    An empty list means "no drained bucket observed", which includes the case
    where the payload could not be read: without evidence of exhaustion the
    caller should retry rather than fail early.
    """
    resources = _rate_limit_resources()
    drained = []
    for name, bucket in resources.items():
        if isinstance(bucket, dict) and bucket.get("remaining") == 0:
            drained.append(name)
    return sorted(drained)


def _rate_limit_reset_hint() -> str:
    """Bucket and reset evidence for a quota refusal, or ``""``."""
    resources = _rate_limit_resources()
    parts = []
    for name in ("core", "graphql"):
        bucket = resources.get(name) or {}
        if "remaining" not in bucket:
            continue
        reset = bucket.get("reset")
        reset_text = (
            datetime.fromtimestamp(reset, tz=timezone.utc).isoformat()
            if isinstance(reset, int)
            else "unknown"
        )
        parts.append(
            f"{name} {bucket['remaining']}/{bucket.get('limit', '?')} reset {reset_text}"
        )
    return "; ".join(parts)


_RATE_LIMIT_REMEDY = {
    GhAuthStatus.RATE_LIMITED: (
        "GitHub refused the request for exceeding an API rate limit. This is not "
        "an authentication failure; the token is valid. Wait for the bucket reset "
        "and retry."
    ),
    GhAuthStatus.SECONDARY_RATE_LIMITED: (
        "GitHub applied a secondary rate limit. This is not an authentication "
        "failure; the token is valid. Back off for about a minute and retry."
    ),
}


_MISSING_OR_INVALID_MESSAGE = (
    "GitHub CLI (gh) is not installed or not authenticated. Run 'gh auth login' first."
)

# Named remedy for a session-wide refusal. Says what is actually wrong, what
# will not fix it, and which transport still works, because the agent reading
# this decides its next call from this string alone.
_TRANSPORT_BLOCKED_MESSAGE = (
    "This session's environment refuses GitHub for the gh CLI, so every gh "
    "call fails with HTTP 403 regardless of the token. The credential is not "
    "the fault: 'gh auth login' and retrying both cannot clear it. Use the "
    "GitHub MCP operations for this work (spelled mcp__github__* in Claude "
    "Code, github/* in Copilot CLI), or run it where gh has "
    "direct GitHub access, such as CI. If an org admin must connect the "
    "Claude GitHub App for this organization, that is the environment fix."
)


def describe_gh_auth_failure(result: GhAuthResult) -> tuple[str, int, str]:
    """Message, ADR-035 exit code, and error type for a non-authenticated result.

    Single source of the auth-failure vocabulary. :func:`assert_gh_authenticated`
    prints it as plain text and exits; envelope-emitting skill scripts feed it to
    ``write_skill_error``. Before issue #4344 those scripts called
    :func:`is_gh_authenticated` and hardcoded the "run gh auth login" message, so
    a quota refusal reported as ``AuthError`` exit 4, which is the misdiagnosis
    this module exists to remove.

    Args:
        result: A non-authenticated :class:`GhAuthResult`.

    Returns:
        ``(message, exit_code, error_type)``. Missing ``gh`` and confirmed
        invalid credentials map to exit 4 / ``AuthError``; quota refusals and
        transport failures map to exit 3 / ``ApiError`` (the envelope vocabulary
        in ADR-056 has no rate-limit member). A session-wide refusal maps to
        exit 2 / ``ApiError``: it is an environment configuration fault, and
        exit 3 would advertise it as worth retrying.
    """
    if result.status in _AUTH_FAILURE_STATUSES:
        return _MISSING_OR_INVALID_MESSAGE, 4, "AuthError"

    detail = f" ({result.detail})" if result.detail else ""
    if result.status is GhAuthStatus.TRANSPORT_BLOCKED:
        # Exit 2 (config), not 3 (external): 3 invites the caller's retry
        # ladder, and no number of retries makes a refused session succeed.
        return f"{_TRANSPORT_BLOCKED_MESSAGE}{detail}", 2, "ApiError"

    remedy = _RATE_LIMIT_REMEDY.get(result.status)
    if remedy is None:
        return (
            "GitHub API is temporarily unavailable (transport error); this is "
            f"not an authentication failure. Retry shortly.{detail}",
            3,
            "ApiError",
        )
    reset_hint = _rate_limit_reset_hint()
    evidence = f" Buckets: {reset_hint}." if reset_hint else ""
    return f"{remedy}{detail}{evidence}", 3, "ApiError"


def assert_gh_authenticated() -> None:
    """Ensure GitHub CLI can authenticate. Raises SystemExit if not.

    Quota refusals and transient transport failures (5xx, timeouts) exit 3
    (external) and name the observed condition without leaking credentials;
    missing ``gh`` and confirmed invalid credentials exit 4 (auth); a session
    whose environment refuses GitHub outright exits 2 (config) and names the
    MCP transport that still works. See :func:`check_gh_auth`, issue #3139,
    and issue #4344.
    """
    result = check_gh_auth()
    if result.status is GhAuthStatus.AUTHENTICATED:
        return
    message, code, _ = describe_gh_auth_failure(result)
    error_and_exit(message, code)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

REST_PAGE_PACE_SECONDS = 3.0
REST_REFUSAL_BACKOFF_SECONDS = (300.0, 600.0)
_RETRYABLE_REST_HTTP_PATTERN = re.compile(
    r"\(?\bHTTP\s+(429|500|502|503|504)\b", re.IGNORECASE
)
_RETRYABLE_REST_REFUSALS = frozenset(
    {GhAuthStatus.RATE_LIMITED, GhAuthStatus.SECONDARY_RATE_LIMITED}
)


def _is_retryable_rest_api_error(error_text: str) -> bool:
    """Return True when a REST page failure should be retried."""
    if _RETRYABLE_REST_HTTP_PATTERN.search(error_text):
        return True
    return classify_gh_failure_text(error_text) in _RETRYABLE_REST_REFUSALS


def _run_gh_api_page(url: str) -> subprocess.CompletedProcess[str]:
    attempts = len(REST_REFUSAL_BACKOFF_SECONDS) + 1
    for attempt in range(attempts):
        result = subprocess.run(
            ["gh", "api", url],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode == 0:
            return result

        error_text = result.stderr.strip() or result.stdout.strip()
        if attempt >= len(REST_REFUSAL_BACKOFF_SECONDS) or not _is_retryable_rest_api_error(
            error_text
        ):
            return result

        delay = REST_REFUSAL_BACKOFF_SECONDS[attempt]
        warnings.warn(
            "GitHub REST page request refused. "
            f"Retrying in {delay:.0f}s: {safe_log_str(error_text)}",
            stacklevel=2,
        )
        time.sleep(delay)

    raise RuntimeError("unreachable REST pagination retry loop")


def gh_api_paginated(endpoint: str, page_size: int = 100) -> list[dict]:
    """Fetch all pages from a GitHub REST API endpoint.

    Args:
        endpoint: API path (e.g. "repos/owner/repo/pulls/1/comments").
        page_size: Items per page (1-100, default 100).

    Returns:
        Combined list of items across all pages.
    """
    all_items: list[dict] = []
    page = 1

    while True:
        separator = "&" if "?" in endpoint else "?"
        url = f"{endpoint}{separator}per_page={page_size}&page={page}"

        result = _run_gh_api_page(url)

        if result.returncode != 0:
            msg = (
                f"GitHub API request failed for endpoint '{endpoint}' "
                f"(page {page}): {result.stderr}"
            )
            if page == 1:
                error_and_exit(msg, 3)
            else:
                warnings.warn(
                    f"{msg}. Returning partial results from {len(all_items)} items.",
                    stacklevel=2,
                )
                break

        try:
            items = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            msg = f"Invalid JSON from endpoint '{endpoint}' (page {page}): {exc}"
            if page == 1:
                error_and_exit(msg, 3)
            else:
                warnings.warn(
                    f"{msg}. Returning {len(all_items)} partial results.",
                    stacklevel=2,
                )
                break
        if not items:
            break

        all_items.extend(items)
        if len(items) < page_size:
            break

        time.sleep(REST_PAGE_PACE_SECONDS)
        page += 1

    return all_items


# Bounded retry policy for transient GraphQL transport failures (issue #2631).
# release-it.md: integration points are suspect; retry only transient (5xx/429)
# failures, bounded, with exponential backoff. Permanent errors fail fast.
_GRAPHQL_MAX_ATTEMPTS = 3
_GRAPHQL_BACKOFF_BASE_SECONDS = 2.0
_TRANSIENT_HTTP_PATTERN = re.compile(r"\(?\bHTTP\s+(429|500|502|503|504)\b")

# Ceiling for the jittered wait before retrying a refusal, per attempt. Sized to
# the recovery measured on issue #4326, where "the next call of the same shape
# succeeded about a minute later". The 5xx ladder (1s then 2s) is wrong for this
# condition: full-jitter over it spends 1.5s on average and 3s at worst, so the
# three attempts land inside the same refusal window and the retry burns two
# extra requests for the same failure. Full jitter is kept, so the expected
# total is about 22s and the worst case 45s.
REFUSAL_BACKOFF_SECONDS = (15.0, 30.0)

# Quota and secondary-limit refusals clear on their own, so a bounded retry
# recovers them (issue #4326). 5xx and 429 keep their existing coverage through
# _TRANSIENT_HTTP_PATTERN; nothing else becomes retryable here.
_RETRYABLE_REFUSAL_STATUSES = frozenset(
    {GhAuthStatus.RATE_LIMITED, GhAuthStatus.SECONDARY_RATE_LIMITED}
)


def _is_transient_graphql_error(error_msg: str) -> bool:
    """Return True when the gh error text indicates a retryable upstream status.

    Transient = HTTP 429 or 5xx (500/502/503/504), plus any refusal whose body
    carries rate-limit wording. GitHub still delivers quota and secondary-limit
    refusals as HTTP 403, and as a code-less GraphQL message ("GraphQL: API rate
    limit already exceeded for user ID ..."); both cleared on their own within
    about a minute in the measurements on issue #4326, so both are retryable.

    Matching a bare 403 would be wrong: a genuine permission denial is also 403.
    The rate-limit wording is what separates the two, so it is required.

    Client errors without that wording, and GraphQL-level errors, stay permanent.
    """
    if _TRANSIENT_HTTP_PATTERN.search(error_msg) is not None:
        return True
    return classify_gh_failure_text(error_msg) in _RETRYABLE_REFUSAL_STATUSES


def _graphql_retry_ceiling(error_text: str, attempt: int) -> float | None:
    """Jitter ceiling for the next retry, or ``None`` when retry cannot help.

    A 5xx or 429 keeps the original exponential ladder. A rate-limit refusal
    gets the longer ladder sized to its measured recovery, unless the exempt
    ``rate_limit`` payload shows the bucket actually drained, in which case the
    reset is bucket-scale (34 minutes in the issue #4326 measurement) and no
    bounded retry reaches it.
    """
    if classify_gh_failure_text(error_text) not in _RETRYABLE_REFUSAL_STATUSES:
        return _GRAPHQL_BACKOFF_BASE_SECONDS ** (attempt - 1)
    if drained_rate_limit_buckets():
        return None
    return REFUSAL_BACKOFF_SECONDS[min(attempt, len(REFUSAL_BACKOFF_SECONDS)) - 1]


_RETRY_AFTER_PATTERN = re.compile(r"\bRetry-After:\s*(\d+)", re.IGNORECASE)


def _retry_after_delay(error_text: str, backoff: float) -> float:
    """Return Retry-After delay if present in error text, else jittered backoff.

    GitHub may include ``Retry-After: <seconds>`` in gh error text for HTTP 429
    responses. Honouring it avoids hammering the rate limit.
    Falls back to full-jitter exponential backoff (``random.uniform(0, backoff)``)
    to prevent synchronized retry storms (release-it.md: exponential backoff with
    jitter).
    """
    match = _RETRY_AFTER_PATTERN.search(error_text)
    if match:
        return float(match.group(1))
    return random.uniform(0, backoff)


def _build_gh_graphql_args(query: str, variables: dict) -> list[str]:
    """Assemble the ``gh api graphql`` argv with typed variable flags."""
    gh_args = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if isinstance(value, (int, bool)):
            gh_args.extend(["-F", f"{key}={value}"])
        else:
            gh_args.extend(["-f", f"{key}={value}"])
    return gh_args


def _extract_graphql_error(result: subprocess.CompletedProcess[str]) -> str:
    """Pull a human-readable error message out of a failed gh invocation."""
    error_msg = result.stderr.strip() or result.stdout.strip()
    msg_match = re.search(r'"message"\s*:\s*"([^"]+)"', error_msg)
    if msg_match:
        return str(msg_match.group(1))
    return error_msg


def _parse_graphql_response(stdout: str) -> dict:
    """Parse a successful gh stdout into the GraphQL ``data`` payload.

    Raises RuntimeError on unparseable output, unexpected shapes, or
    GraphQL-level errors; all are permanent (not retried by the caller).

    Shape validation (issue #4951, PR #5011): decoded JSON that is not a dict,
    or an ``errors`` list whose items are not dicts, would raise
    ``AttributeError`` on the ``.get()`` calls below.  That uncaught exception
    exits 1 (Python default), which ADR-035 reserves for verified logic
    failures.  Catching the shapes here and raising ``RuntimeError`` lets the
    caller map them to exit 3 (external/malformed).
    """
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse GraphQL response: {stdout}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError(
            f"GraphQL response is not a JSON object: {type(parsed).__name__}"
        )

    errors = parsed.get("errors")
    if errors:
        if not isinstance(errors, list):
            raise RuntimeError(
                f"GraphQL 'errors' field is not a list: {type(errors).__name__}"
            )
        messages: list[str] = []
        for entry in errors:
            if isinstance(entry, dict):
                messages.append(entry.get("message", str(entry)))
            else:
                messages.append(str(entry))
        raise RuntimeError(f"GraphQL errors: {'; '.join(messages)}")

    data: dict = parsed.get("data", {})
    return data


def gh_graphql(query: str, variables: dict | None = None) -> dict:
    """Execute a GitHub GraphQL query or mutation with bounded retry.

    Uses GraphQL variables for safe parameterization (ADR-015 compliant).
    Transient upstream failures (HTTP 429/5xx) are retried with exponential
    backoff up to ``_GRAPHQL_MAX_ATTEMPTS`` (issue #2631, release-it.md). A
    persistent transient failure, or any permanent error, still raises.

    Args:
        query: The GraphQL query string.
        variables: Dict of variables. Strings use -f, ints/bools use -F.

    Returns:
        The 'data' portion of the GraphQL response.

    Raises:
        RuntimeError: On GraphQL transport or response errors.
    """
    if variables is None:
        variables = {}

    gh_args = _build_gh_graphql_args(query, variables)

    for attempt in range(1, _GRAPHQL_MAX_ATTEMPTS + 1):
        result = subprocess.run(
            gh_args,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

        if result.returncode == 0:
            return _parse_graphql_response(result.stdout)

        # Check transient status against raw output BEFORE extraction (issue #2631).
        # _extract_graphql_error may strip HTTP status from messages like
        # '{"message": "..."} (HTTP 504)', so transient detection must use raw text.
        raw_error = result.stderr.strip() or result.stdout.strip()
        error_msg = _extract_graphql_error(result)
        is_last = attempt == _GRAPHQL_MAX_ATTEMPTS
        if not is_last and _is_transient_graphql_error(raw_error):
            backoff = _graphql_retry_ceiling(raw_error, attempt)
            if backoff is None:
                drained = ", ".join(drained_rate_limit_buckets())
                raise RuntimeError(
                    f"GraphQL request failed: {error_msg} "
                    f"(bucket exhausted: {drained}; retry cannot outlast the reset)"
                )
            delay = _retry_after_delay(raw_error, backoff)
            logger.warning(
                "Transient GraphQL failure (attempt %d/%d), retrying in %.1fs: %s",
                attempt,
                _GRAPHQL_MAX_ATTEMPTS,
                delay,
                safe_log_str(error_msg),
            )
            time.sleep(delay)
            continue
        raise RuntimeError(f"GraphQL request failed: {error_msg}")

    # Unreachable: the loop either returns, retries, or raises on every path.
    raise RuntimeError("GraphQL request failed: retries exhausted")


_ALL_PRS_QUERY = """\
query($owner: String!, $repo: String!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequests(first: 50, orderBy: {field: UPDATED_AT, direction: DESC}, after: $cursor) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        number
        title
        state
        author {
          login
          ... on Bot { databaseId }
          ... on User { databaseId }
        }
        createdAt
        updatedAt
        mergedAt
        closedAt
        reviewThreads(first: 100) {
          nodes {
            isResolved
            isOutdated
            comments(first: 50) {
              nodes {
                id
                body
                author {
                  login
                  ... on Bot { databaseId }
                  ... on User { databaseId }
                }
                createdAt
                path
              }
            }
          }
        }
      }
    }
  }
}"""


def _extract_pull_requests_page(data: dict, owner: str, repo: str) -> dict:
    """Pull the ``pullRequests`` connection out of a GraphQL response.

    Raises RuntimeError when the repository or its pullRequests field is null,
    so the caller does not have to repeat the two None checks.
    """
    repo_data = data.get("repository")
    if repo_data is None:
        raise RuntimeError(f"Repository {owner}/{repo} not found or not accessible")
    pr_data: dict | None = repo_data.get("pullRequests")
    if pr_data is None:
        raise RuntimeError(f"Could not retrieve pull requests for {owner}/{repo}")
    return pr_data


def _collect_prs_with_comments(
    nodes: list[dict],
    since: datetime,
) -> tuple[list[dict], bool]:
    """Filter one page of PR nodes to those with comments in the time range.

    Returns ``(matched, reached_since_boundary)``. ``reached_since_boundary``
    is True once a PR older than *since* is seen; since PRs are ordered by
    updatedAt DESC, that signals the caller to stop paginating.
    """
    matched: list[dict] = []
    for pr in nodes:
        updated_at = datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00"))
        if updated_at < since:
            return matched, True

        threads = (pr.get("reviewThreads") or {}).get("nodes") or []
        has_comments = any(
            len((t.get("comments") or {}).get("nodes") or []) > 0 for t in threads
        )
        if has_comments:
            matched.append(pr)
    return matched, False


def get_all_prs_with_comments(
    owner: str,
    repo: str,
    since: datetime,
    max_pages: int = 50,
) -> list[dict]:
    """Fetch PRs with review comments using GraphQL cursor-based pagination.

    PRs are ordered by updatedAt DESC; pagination stops when PRs fall
    outside the requested time range.

    Args:
        owner: Repository owner.
        repo: Repository name.
        since: Only include PRs updated since this datetime.
        max_pages: Safety limit (default 50, yielding up to 2500 PRs).

    Returns:
        List of PR dicts that have review comments within the time range.
    """
    all_prs: list[dict] = []
    cursor: str | None = None
    has_next_page = True
    page_count = 0

    while has_next_page and page_count < max_pages:
        page_count += 1

        variables: dict = {"owner": owner, "repo": repo}
        if cursor:
            variables["cursor"] = cursor

        data = gh_graphql(_ALL_PRS_QUERY, variables)
        pr_data = _extract_pull_requests_page(data, owner, repo)

        matched, reached_boundary = _collect_prs_with_comments(pr_data["nodes"], since)
        all_prs.extend(matched)

        if reached_boundary:
            has_next_page = False
        else:
            has_next_page = pr_data["pageInfo"]["hasNextPage"]
            cursor = pr_data["pageInfo"]["endCursor"]

        logger.debug("Page %d processed, total PRs with comments: %d", page_count, len(all_prs))

    if page_count >= max_pages:
        warnings.warn(f"Reached maximum page limit ({max_pages})", stacklevel=2)

    return all_prs


# ---------------------------------------------------------------------------
# Issue comments
# ---------------------------------------------------------------------------

# Regex for detecting 403 permission errors (negative lookarounds prevent
# false positives on IDs like "Comment ID 4030").
_403_PATTERN = re.compile(
    r"((?<!\d)403(?!\d)|\bforbidden\b|Resource not accessible by integration)",
    re.IGNORECASE,
)

_403_GUIDANCE = """\
PERMISSION DENIED (403): Cannot update comment {comment_id} in {owner}/{repo}.

LIKELY CAUSES:
- GitHub Apps: Missing "issues": "write" permission in app manifest
- Workflow GITHUB_TOKEN: Add 'permissions: issues: write' to workflow YAML
- Fine-grained PAT: Enable 'Issues' repository permission (Read and Write)
- Classic PAT: Requires 'repo' scope for private repos or 'public_repo' for public repos
- Not the comment author: Only the comment author or repo admin can edit comments

RAW ERROR: {error}"""


def get_issue_comments(
    owner: str,
    repo: str,
    issue_number: int,
    client: GitHubClient | None = None,
) -> list[dict]:
    """Fetch all comments for a GitHub issue.

    When *client* is provided, delegates to ``client.rest_get``.
    Otherwise falls back to the existing paginated ``gh api`` subprocess call.
    """
    if client is not None:
        endpoint = f"repos/{owner}/{repo}/issues/{issue_number}/comments"
        result = client.rest_get(endpoint)
        return result if isinstance(result, list) else [result]
    return gh_api_paginated(f"repos/{owner}/{repo}/issues/{issue_number}/comments")


def update_issue_comment(owner: str, repo: str, comment_id: int, body: str) -> dict:
    """Update an existing GitHub issue comment.

    Raises SystemExit with code 4 for permission errors, code 3 for other API errors.
    """
    payload = json.dumps({"body": body})

    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/issues/comments/{comment_id}",
            "-X", "PATCH",
            "--input", "-",
        ],
        input=payload,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )

    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        if _403_PATTERN.search(error_str):
            guidance = _403_GUIDANCE.format(
                comment_id=comment_id,
                owner=owner,
                repo=repo,
                error=error_str,
            )
            error_and_exit(guidance, 4)
        error_and_exit(f"Failed to update comment: {error_str}", 3)

    try:
        response: dict = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Comment {comment_id} may have been updated but response was not valid JSON: "
            f"{result.stdout!r}"
        ) from exc
    return response


def create_issue_comment(
    owner: str,
    repo: str,
    issue_number: int,
    body: str,
    client: GitHubClient | None = None,
) -> dict:
    """Create a new GitHub issue comment.

    When *client* is provided, delegates to ``client.rest_post``.
    Otherwise falls back to the existing ``gh api`` subprocess call.

    Raises SystemExit with code 3 on API failure (subprocess path only).
    """
    endpoint = f"repos/{owner}/{repo}/issues/{issue_number}/comments"

    if client is not None:
        return client.rest_post(endpoint, {"body": body})

    payload = json.dumps({"body": body})

    result = subprocess.run(
        ["gh", "api", endpoint, "-X", "POST", "--input", "-"],
        input=payload,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )

    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        error_and_exit(f"Failed to post comment: {error_str}", 3)

    try:
        response: dict = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Comment creation succeeded but response was not valid JSON: {result.stdout!r}"
        ) from exc
    return response


# ---------------------------------------------------------------------------
# Trusted sources
# ---------------------------------------------------------------------------


def get_trusted_source_comments(
    comments: list[dict],
    trusted_users: list[str],
) -> list[dict]:
    """Filter comments to those from trusted source users.

    Args:
        comments: List of comment dicts with nested user.login.
        trusted_users: Usernames to keep.

    Returns:
        Filtered list of comments from trusted users.
    """
    if not comments:
        return []
    return [c for c in comments if c.get("user", {}).get("login") in trusted_users]
