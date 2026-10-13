"""Captured gh refusal bodies shared by the gh auth classification tests.

Every body below was captured from GitHub or a Claude Code session proxy and
quoted in the issue threads, not synthesized, so the tests cannot encode the
same assumption the code had. The classification, retry, exit-code, preflight,
and rate-limit gate test files import them from here so no file keeps a copy
that can drift.
"""

from __future__ import annotations

import subprocess

# Captured refusal bodies (issue #4326 Observations A, B, and the third
# observation; issue #4335 workflow log).
REST_403_QUOTA = "gh: API rate limit exceeded for user ID 6811113 (HTTP 403)"
RUN_LIST_403_QUOTA = "failed to get runs: HTTP 403: API rate limit exceeded for user ID 6811113"
REST_BODY_QUOTA = (
    '{"message": "API rate limit exceeded for user ID 6811113", '
    '"documentation_url": "https://docs.github.com/rest/overview/'
    'resources-in-the-rest-api#rate-limiting"}'
)
GRAPHQL_QUOTA = "GraphQL: API rate limit already exceeded for user ID 6811113."
SECONDARY_LIMIT = (
    "You have exceeded a secondary rate limit and have been temporarily blocked "
    "from content creation. Please retry your request again later."
)

# Captured from issue #3139: authenticated REST returned the GitHub Unicorn page.
REST_503 = "HTTP 503: Service unavailable (https://api.github.com/user)"

# Captured from the binary, not invented: `gh api --hostname
# invalid.example.test --method POST ... --verbose` on gh 2.97.0 emits exactly
# these three lines when it cannot reach the host. None of them carries an HTTP
# status, so before this fix they classified as INVALID_CREDENTIALS and the
# preflight told the operator to run `gh auth login` for a dead network, which
# is the #3139 symptom in its most common form.
GH_DIAL_FAILURE = "dial tcp: lookup invalid.example.test on 127.0.0.53:53: no such host"
GH_CONNECT_FAILURE = (
    "error connecting to invalid.example.test\n"
    "check your internet connection or https://githubstatus.com"
)
GH_DNS_FAILURE = "dial tcp: lookup api.github.com: no such host"
# A genuine permission denial. Also 403, and must stay permanent.
PERMISSION_DENIED = "HTTP 403: Resource not accessible by integration"
BAD_CREDENTIALS = "HTTP 401: Bad credentials (https://api.github.com/user)"

# Captured from gh 2.98.0 in a Claude Code remote session on 2026-09-03, where
# `gh api user` succeeded against the same token in the same second. gh renders
# any failure of its own status call this way, so the wording is about gh's
# error handling and not about the credential.
GH_AUTH_STATUS_INVALID = (
    "github.com\n"
    "  X Failed to log in to github.com using token (GH_TOKEN)\n"
    "  - Active account: true\n"
    "  - The token in GH_TOKEN is invalid."
)


# Bodies captured from a Claude Code remote session on 2026-09-03 (gh 2.98.0),
# by running `gh api repos/rjmurillo/ai-agents` and `gh api graphql` against
# the session proxy. Quoted rather than synthesized.
#
# Quoting the body is not the same as quoting it from the right command, and
# that distinction cost a round. `check_gh_auth` runs `gh auth status` and the
# GraphQL viewer query and nothing else, so its first subprocess slot can only
# ever hold `gh auth status` output, which reports "The token in GH_TOKEN is
# invalid" and never carries PROXY_REST_403. A case that puts the REST body in
# that slot pins a branch real data cannot reach. Where one does below, it says
# so and names what covers the real case instead (Copilot review on PR #5509).
PROXY_REST_403 = (
    '{"message":"GitHub access is not enabled for this session. An org admin '
    'must connect the Claude GitHub App for this organization.",'
    '"documentation_url":"https://docs.anthropic.com/en/docs/claude-code/'
    'github-actions"}\n'
    "gh: GitHub access is not enabled for this session. An org admin must "
    "connect the Claude GitHub App for this organization. (HTTP 403)"
)
PROXY_GRAPHQL_403 = (
    "gh: This GraphQL query is not enabled for this session, only the pinned "
    "set of PR-review operations is served. Use REST via "
    "`gh api repos/{owner}/{repo}/...` instead. (HTTP 403)"
)


def completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=["gh"], returncode=rc, stdout=stdout, stderr=stderr)
