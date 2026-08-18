---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-14-session-14706-fix-issue-4951-close-verify.json
qaCommit: 558122b99e4df99e6c12564fe1f12937768dd4c1
---

# QA Report: PR #5011 Review Thread Fixes

**PR**: #5011 - fix(github-skill): separate a failed claim from a failed check in close verification
**Issue**: #4951
**Branch**: fix/4951-close-verify-tri-state
**Commit under test**: 49ded7589bbd32dea74b7f6ed2075eb1babc81ba
**Date**: 2026-08-15

## Gate results

| Gate | Command | Result |
|------|---------|--------|
| Full test suite | uv run pytest tests/ -q --numprocesses=auto | [PASS] 20920 passed, 35 skipped |
| Plugin lib mirrors | uv run python scripts/ci/check_plugin_lib_mirrors.py | [PASS] |
| Build staleness | uv run python build/scripts/build_all.py --check | [PASS] |

## Review threads addressed

| Thread | File | Fix | Tests |
|--------|------|-----|-------|
| PRRT_kwDOQoWRls6ZcLU- | api.py:_parse_graphql_response | Validate JSON shapes before .get() | TestParseGraphqlResponseShapeValidation (9 tests) |
| PRRT_kwDOQoWRls6ZcLVQ | api.py:is_auth_failure_text | Permission 403 exit 4; rate-limit 403 exit 3 | TestPermissionDenialExitCode (7 tests) |
| PRRT_kwDOQoWRls6ZcRCI | close_issue.py:_check_commit | Validate response body on exit 0 | TestCommitProbeBodyValidation (6 tests) |

## Test coverage

- 22 new tests in tests/test_pr_5011_review_fixes.py
- All 103 targeted tests pass (test_close_issue + test_pr_merge_state + test_pr_5011_review_fixes)
- 20920 full suite tests pass

## Code and security review

- Code review: no issues found
- Security review: no vulnerabilities found
