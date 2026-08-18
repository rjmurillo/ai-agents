---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-14-session-14706-fix-issue-4951-close-verify.json
qaCommit: 63beae2c1d628e02a0f9ca0cc811f9945af1ac13
---

# QA Report: Issue #4951 close-verification tri-state

**Issue**: #4951 - `close_issue.py --verify-claims` reports merged PRs as not merged
**Branch**: `fix/4951-close-verify-tri-state`
**Base**: `bc179ad3a`, merged up to `e60e3b896` (origin/main)
**Commit under test**: `43134500538660691e9f64b48dc3c729532217ff`
**Date**: 2026-08-14

## Gate results

| Gate | Command | Result |
|------|---------|--------|
| Full test suite | `uv run pytest tests/ -q -p no:randomly` | [PASS] 28476 passed, 37 skipped, 891.68s, run at this commit on the merged tree |
| Pre-PR validation | `uv run python scripts/validation/pre_pr.py --skip-tests` | [PASS] exit 0, "RESULT: All validations passed" |
| Generated artifact staleness | `uv run python build/scripts/build_all.py --check` | [PASS] exit 0, no staleness block |
| Plugin lib mirrors | `uv run python scripts/ci/check_plugin_lib_mirrors.py` | [PASS] exit 0, "All plugin lib copies are in sync" |
| Lint (repo) | `uv run ruff check .` | [PASS] 27 errors, all in files this branch does not touch; ruff ratchet reports 27 <= 27 |
| Lint (touched files) | `uv run ruff check` on each changed Python file | [PASS] "All checks passed!" |
| Count ratchets | `uv run python scripts/ci/merge_tree_ratchet_check.py` | [PASS] against `origin/main`: ruff 27<=27, taste 582<=583, type-ignore 44<=44, memory-index 376<=378, cli-exit-contract 27<=27 |

The type-ignore ratchet failed once at 45 > 44 on commit `fff4c1d1c`. The new
`# type: ignore[misc]` was in the frozen-dataclass test; commit `235c66d9e`
removed it rather than raising the baseline. Re-run is green.

## Behavior verified by test

The issue asks for five cases. Each is covered at the layer that owns it.

| Case the issue names | Reader test (`tests/test_pr_merge_state.py`) | Gate test (`tests/test_close_issue.py`) |
|----------------------|---------------------------------------------|------------------------------------------|
| Merged PR, close proceeds | `TestMerged::test_merged_pr_reports_merged` | `TestVerifyClaimsGate::test_verify_claims_passes_when_commit_and_pr_resolve` |
| Genuinely unmerged PR, exit 1 | `TestUnmerged::test_open_pr_reports_unmerged`, `test_closed_unmerged_pr_reports_unmerged` | `TestVerifyClaimsGate::test_verify_claims_blocks_unmerged_pr` |
| API failure, exit 3 | `TestApiFailure::test_transport_error_reports_probe_failed_exit_3`, `test_rate_limit_refusal_reports_exit_3` | `TestVerifyClaimsGate::test_verify_claims_api_failure_exits_3_not_1` |
| Auth failure, exit 4 | `TestAuthFailure::test_auth_failure_reports_exit_4` (4 params) | `TestVerifyClaimsGate::test_verify_claims_auth_failure_exits_4` |
| Malformed response, exit 3 | `TestMalformedResponse::test_malformed_payload_reports_probe_failed` (6 params), `test_non_boolean_merged_reports_probe_failed` (4 params) | `TestVerifyClaimsGate::test_verify_claims_malformed_response_exits_3` |

`tests/test_test_pr_merged.py::TestProbeFailures` covers the same five states
for the reader's other caller.

Additional coverage this change adds:

- No probe failure is ever worded as a merge verdict:
  `test_pr_merge_state.py::TestApiFailure::test_probe_failure_never_claims_unmerged`,
  `test_close_issue.py::TestVerifyClaims::test_pr_probe_failure_is_not_reported_as_unmerged`,
  `test_test_pr_merged.py::TestProbeFailures::test_error_message_never_says_not_merged`.
- Both headlines are pinned:
  `TestVerifyClaimsGate::test_verified_failure_keeps_the_documented_headline`
  and `::test_probe_failure_headline_cannot_be_read_as_a_verdict`.
- `subprocess.TimeoutExpired` cannot exit 1 and masquerade as a verdict:
  `test_timeout_reports_probe_failed_not_logic_error`,
  `TestVerifyClaims::test_commit_probe_timeout_exits_3_not_1`,
  `TestProbeFailures::test_timeout_exits_3`.
- The commit probe separates a 404 from an unreachable API:
  `TestVerifyClaims::test_missing_commit_fails`,
  `::test_commit_probe_api_failure_is_not_a_missing_commit`,
  `::test_commit_probe_silent_failure_is_unverifiable`.
- Exit-code precedence is asserted, not assumed:
  `TestVerifyClaims::test_probe_failure_outranks_verified_failure`,
  `::test_auth_probe_failure_outranks_external_probe_failure`.
- The GraphQL contract has one home:
  `test_test_pr_merged.py::TestSharedReaderContract`.

Suite counts for the three test files: 32 (`test_pr_merge_state.py`, new), 71
(`test_close_issue.py`, was 54), 24 (`test_test_pr_merged.py`, was 13). Names
above were read back from `pytest --collect-only`, not from memory.

## Reproduction of the reported defect

The defect is a code path, not a data condition, so it reproduces in test
rather than against the live API. On the base commit, `_pr_is_merged` returned
`False` for any nonzero `gh api` exit; the new
exit-3/4 gate cases fail against the base implementation: they assert exit 3
and a message carrying no merge claim, and the base returns exit 1 with
"cited PR #N is not merged".

The 2026-08-13 incident itself (PR #4729, PR #3076 reported unmerged while
merged) is not re-run here: it depended on a transient API failure that cannot
be reproduced on demand. The unit cases stand in for it by injecting the same
failure at the same seam.

## Residual risk

- `scripts/validation/verify_issue_close.py::verify_pr_merged` collapses probe
  failure into `False` in the same way. It is left unchanged: its callers
  (`triage_gateway.py`, `triage_batch_apply.py`) report "close aborted:
  unverified PR #N", which does not assert a merge state, so the specific harm
  in #4951 (a false factual claim) is not present there. Converting its
  `Callable[[int], bool]` contract to tri-state is a separate change.
- Five other scripts still carry copy-pasted `_AUTH_ERROR_MARKERS` tuples.
  `github_core.api.AUTH_ERROR_MARKERS` is now the shared home for new callers;
  the existing copies are untouched by this branch.

## PR #5011 Review Thread Fixes (2026-08-14)

Three Copilot review threads addressed in commit `8b55183a4`:

| Thread | File | Fix | Test Coverage |
|--------|------|-----|---------------|
| PRRT_kwDOQoWRls6ZcLU- | `api.py:_parse_graphql_response` | Validate JSON is dict; validate errors items are dicts | `TestParseGraphqlResponseShapeValidation` (9 tests) |
| PRRT_kwDOQoWRls6ZcLVQ | `api.py:is_auth_failure_text` | Add "Resource not accessible by integration" → exit 4; exclude rate-limit 403s | `TestPermissionDenialExitCode` (7 tests) |
| PRRT_kwDOQoWRls6ZcRCI | `close_issue.py:_check_commit` | Validate response body on exit 0 (JSON, sha field, prefix match) | `TestCommitProbeBodyValidation` (6 tests) |

Test counts: 22 new tests in `tests/test_pr_5011_review_fixes.py`.
All 20920 existing tests continue to pass (1 pre-existing temp-dir error in mutation harness, unrelated).
