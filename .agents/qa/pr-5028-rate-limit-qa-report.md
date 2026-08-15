---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-15000-fix-4901-rate-limit-classification.json
qaCommit: 381ba5fd0fe469680577f441eb4d0f37771531a6
---

# PR 5028 Rate-Limit Classification QA Report

## Scope

Validated that list_issues.py preserves GraphQL rate-limit classification from github_core instead of mapping all failures to ApiError.

## Evidence

| Check | Result |
|---|---|
| Targeted tests (test_list_issues.py) | 29 passed |
| Related tests (test_pr_5011, test_close_issue) | 93 passed |
| Total relevant tests | 122 passed |
| Ruff lint | All changed Python files pass |
| Mirror parity | Canonical and Copilot scripts matched |
| Rate-limit classification | RateLimitError emitted for rate-limit stderr |
| Auth classification | AuthError exit 4 for permission denial |
| Generic fallback | ApiError preserved for non-rate-limit errors |

## Test Coverage

- `test_rate_limit_classified_as_rate_limit_error`: Primary rate limit detection
- `test_secondary_rate_limit_classified`: Secondary/abuse rate limit detection
- `test_auth_failure_classified_as_auth_error`: Permission denial classification
- `test_generic_error_remains_api_error`: Non-rate-limit errors stay ApiError
- `test_empty_results_rate_limit_classified`: Rate limit in verify path

## Verdict

PASS. Rate-limit classification preserved through list_issues error paths.
