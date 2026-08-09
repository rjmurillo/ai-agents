---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-08-session-10018-b2f6a78e7-fix-issue-3912-authoritative-github.json
qaCommit: a0090308df0e7eb7bfe99f1e73a5d5bea299a26b
---
# Test Report: Issue #3912 - Authoritative GitHub PR Context Metadata

**Scope**: `.claude/skills/github/scripts/pr/get_pr_context.py`, its generated mirror
(`src/copilot-cli/skills/github/scripts/pr/get_pr_context.py`), the API reference doc,
and `tests/test_get_pr_context.py`.

**Branch**: `fix/3912-authoritative-pr-context` in
`/home/richard/src/GitHub/rjmurillo/ai-agents2-fix-3912`

**Date**: 2026-08-07 (initial), 2026-08-08 (re-evaluation, scope correction)

## Scope Correction (2026-08-08)

The 2026-08-07 run graded this branch against an acceptance criterion that
does not belong to issue #3912: classification of `gh pr view`'s generic
PR-not-found error text into exit code 2. That check was invented during
review, not sourced from the issue.

Issue #3912's body, its auto-generated PRD, and its reopening comment define
the required scope. Verified directly against `gh issue view 3912 --comments`:

- **Issue body** requires: "head repository and owner, head and base SHA,
  state, draft status, `mergeable`, `mergeStateStatus`, auto-merge state,
  checks, reviews, and review-thread counts."
- **PR #4078 comment** (first fix attempt): added `isDraft`,
  `mergeStateStatus`, `autoMergeRequest`, `headRepository`, `reviews`.
- **Reopening comment** (the operative, final scope statement): "still omits
  **status checks and review-thread counts** from its returned metadata.
  Those acceptance items remain unmet." This is the only outstanding scope
  this branch was written to close.

Nothing in the issue, the PRD, or the reopening comment mentions `gh pr
view`'s not-found error text or exit-code classification for a nonexistent
PR. That code path (`_load_pr_data`'s `if "not found" in err_msg` check) is
confirmed present, byte-identical, on `main` before this branch's diff
(verified below); it predates issue #3912 entirely and is unrelated to
status-check or review-thread metadata.

Per explicit user instruction: combining unrelated issues into one fix is
forbidden. The not-found classification defect is preserved below as
**nonblocking, out-of-scope evidence** for a separate issue to be filed. It
is not a blocking gap for issue #3912 and is not required or implemented
here.

## Summary

| Metric | Value |
|--------|-------|
| Total Tests (targeted file) | 62 |
| Passed | 62 |
| Failed | 0 |
| Skipped | 0 |
| Line coverage (get_pr_context.py) | 96% (169 stmts, 7 missed: lines 30, 32, 38-39, 249, 273, 434; plugin-root fallback branches and unreachable defensive asserts, none in issue-scoped code paths) |
| Broader regression suite (`-k "github or pr_context or pr_review or review_thread"`) | 1337 passed, 0 failed, 21.33s |
| Lint (ruff) | All checks passed |
| Type check (mypy) | Success, no issues |
| Live GitHub probes (re-run 2026-08-08) | 4, all reproduced identically to 2026-08-07 |

## Reconciliation

```text
Promised (issue #3912 scope, per reopening comment): actual status checks +
          count; review-thread total/returned/unresolved/completeness
          counts; pagination past 100 threads; null statusCheckRollup ==
          authoritative zero; malformed/missing external responses exit 3;
          canonical/generated mirrors match; docs describe new fields.
Delivered: status_checks + status_check_total_count fields (typed,
          validated); 62 deterministic tests, all pass; review_thread_
          total_count/returned_count/unresolved_count/counts_complete
          fields; verified deterministically and against live PR
          rjmurillo/ai-agents#4733 (144 status checks, 16/16/16 review
          threads), cross-checked independently via raw `gh pr view --json`
          and `gh api graphql` calls that do not go through the script under
          test; exact match; pagination past 100 nodes verified
          deterministically (101 threads across 2 pages, cursor propagation
          asserted) and structurally consistent with the live 144-check
          PR; null and empty statusCheckRollup both yield [] / 0, confirmed
          deterministically and against live PR octocat/Hello-World#1 (empty
          rollup, 0 status checks, 30/30/30 review threads); malformed/
          missing GraphQL and REST shapes exit 3, confirmed by 17
          deterministic tests plus a live nonexistent-repository probe
          (exit 3); canonical and generated copies are byte-identical (diff
          clean, re-verified 2026-08-08); api-reference.md documents all six
          new fields with names and semantics matching the implementation.
Gap: None within issue #3912's scope.
Out-of-scope, nonblocking finding: `gh pr view`'s not-found error text does
          not contain "not found" against `gh` v2.97.0, so `_load_pr_data`
          exits 3 instead of the documented exit 2 for a genuinely
          nonexistent PR. Confirmed present identically on `main` before
          this branch's diff (pre-existing, introduced by #3912's original
          commit 30619adf3, unrelated to this branch's status-check/review-
          thread work). Not required or fixed here per explicit scope
          instruction; recommend filing a separate issue.
Result: PASS
```

## Status

**QA COMPLETE**

## Review Fix Validation

Two PR review findings were reproduced and fixed.

- Invalid JSON from a successful `gh pr view` call exits 3 without a traceback.
- A consumer-wiring test asserts the real `--json` field list includes `statusCheckRollup`.

Focused tests: 62 passed. Broader regression selection: 1337 passed.
Canonical and generated helpers remain byte-identical. Live PR #4733 output
matched independent GitHub status-check and review-thread counts.


## Infrastructure

No infrastructure gaps. `pytest`, `ruff`, `mypy`, and `gh` (v2.97.0) were all
available and used. `gh auth status` reports a stale/cosmetic token warning
in this environment, but live `gh` calls (issue view, PR view, GraphQL
queries) all succeeded without error throughout this evaluation.

## Test Results

### Deterministic Suite (`tests/test_get_pr_context.py`)

All 62 tests passed in 0.71s (re-run 2026-08-08). Coverage: 96% line
(169 stmts, 7 missed - none in issue-scoped code).

Issue #3912 acceptance-criteria tests, all [PASS]:

| Criterion | Test | Result |
|-----------|------|--------|
| Status checks returned + count | `test_basic_output`, `test_empty_status_checks_are_authoritative` | [PASS] |
| Null statusCheckRollup -> authoritative zero | `test_null_status_checks_are_authoritative` | [PASS] |
| Missing statusCheckRollup key -> exit 3 (not silent zero) | `test_missing_status_check_rollup_exits_3` | [PASS] |
| Malformed check shape -> exit 3 | `test_malformed_status_check_exits_3`, `test_object_status_check_rollup_exits_3` | [PASS] |
| Review-thread total/returned/unresolved/complete | `test_review_threads_count_unresolved`, `test_review_thread_count_reports_hidden_nodes` | [PASS] |
| Pagination past 100 threads | `test_review_threads_paginates_past_first_hundred` (101 threads across 2 pages, cursor propagation asserted) | [PASS] |
| Missing cursor mid-pagination -> exit 3 | `test_review_threads_missing_cursor_exits_3` | [PASS] |
| totalCount drifts across pages -> exit 3 | `test_review_threads_changed_total_exits_3` | [PASS] |
| Pagination cap exceeded -> exit 3 | `test_review_threads_page_limit_exits_3` | [PASS] |
| Repeated cursor / duplicate thread id -> exit 3 | `test_review_threads_repeated_cursor_exits_3`, `test_review_threads_duplicate_thread_exits_3`, `test_review_threads_duplicate_thread_in_page_exits_3` | [PASS] |
| GraphQL transport failure (RuntimeError/timeout) -> exit 3 | `test_review_threads_fetch_failure_exits_3`, `test_review_threads_timeout_exits_3` | [PASS] |
| Structural GraphQL shapes (`[]`, `{}`, `pullRequest: []`, `pullRequest: {}`) -> exit 3; `pullRequest: None` -> exit 2 | `test_review_threads_reject_structural_failures` (parametrized x5) | [PASS] |
| Generic API failure -> exit 3 | `test_api_failure_exits_3`, `test_api_failure_uses_stdout_when_stderr_empty` | [PASS] |
| Non-object PR response -> exit 3 | `test_non_object_pr_response_exits_3` | [PASS] |
| Auth failure -> exit 4 | `test_not_authenticated_exits_4` | [PASS] |
| Backward compatibility (old API shape missing new fields) | `test_missing_new_fields_handled_gracefully` | [PASS] |
| Mock fidelity vs canonical fixture | `test_mock_shape_matches_fixture` | [PASS] |

None of the passing tests exhibit the insufficient-test anti-patterns (no bare
regex-on-source-text assertions; every test calls `main()` and asserts on
`SystemExit.code` or the emitted JSON `Data` payload; external `subprocess.run`
and `gh_graphql` are mocked; error and edge-case paths are exercised).

Note: `test_pr_not_found_exits_2` exists in this file and passes, but it
tests pre-existing, out-of-scope behavior (see "Out-of-Scope Finding"
below) and is excluded from the issue #3912 acceptance-criteria table above.

### Broader Regression Suite

```
$ python -m pytest -k "github or pr_context or pr_review or review_thread" -q
1337 passed, 22938 deselected, 1 warning in 21.33s
```

No regressions. The one warning is an expected `UserWarning` emitted by
`review_threads.py`'s own cursor-missing diagnostic in a deliberate negative
test, not a failure.

### Mirror Parity (re-verified 2026-08-08)

```
$ diff .claude/skills/github/scripts/pr/get_pr_context.py \
       src/copilot-cli/skills/github/scripts/pr/get_pr_context.py
(no output - byte-identical)

$ diff .claude/skills/github/references/api-reference.md \
       src/copilot-cli/skills/github/references/api-reference.md
(no output - byte-identical)
```

`.claude/skills/` is the canonical source; `src/copilot-cli/skills/` is its
generated mirror per `scripts/validation/git_hook_policy.py:_GENERATED_MIRRORS`.
Documentation diff in `api-reference.md` (verified against `git diff main`)
adds exactly six rows describing `status_checks`, `status_check_total_count`,
`review_thread_total_count`, `review_thread_returned_count`,
`review_thread_unresolved_count`, and `review_thread_counts_complete`, with
field names and semantics matching the implementation.

### Static Analysis (re-verified 2026-08-08)

```
$ ruff check .claude/skills/github/scripts/pr/get_pr_context.py
All checks passed!

$ mypy .claude/skills/github/scripts/pr/get_pr_context.py
Success: no issues found in 1 source file
```

### Code Quality Gate Checklist

- [x] Cyclomatic complexity <= 10 per method (ruff C901 clean; all helpers are
  single-branch validators)
- [x] Nesting depth <= 3 levels
- [x] All public functions covered by tests
- [x] No suppressed warnings without justification
- [ ] No methods exceed 60 lines: `main()` is ~100 lines. **Pre-existing,
  out of scope**: `main()` was already ~112 lines in HEAD before this
  branch's diff; this branch's refactor extracted `_load_pr_data`,
  `_review_counts`, and `_status_checks` while adding 6 new dict-literal
  fields, netting a small reduction. Not a regression introduced by this
  branch; flagged for awareness, not blocking.

### Live GitHub Probes (independent, unmocked, re-run 2026-08-08)

Environment: `gh` v2.97.0. Live API calls succeeded throughout despite a
stale `gh auth status` warning in this sandbox.

**Probe 1: PR #4733 (`rjmurillo/ai-agents`)**, re-run 2026-08-08:

```
$ python .claude/skills/github/scripts/pr/get_pr_context.py \
    --owner rjmurillo --repo ai-agents --pull-request 4733 --output-format json
exit code: 0
status_check_total_count: 144
review_thread_total_count: 16
review_thread_returned_count: 16
review_thread_unresolved_count: 16
review_thread_counts_complete: true
mergeable: MERGEABLE
merge_state_status: BEHIND
```

Independently cross-checked against raw `gh` calls that do not go through the
script under test:

```
$ gh pr view 4733 --repo rjmurillo/ai-agents --json statusCheckRollup \
    --jq '.statusCheckRollup | length'
144   # matches status_check_total_count exactly

$ gh api graphql -f query='query { repository(owner:"rjmurillo", name:"ai-agents") {
    pullRequest(number:4733) { reviewThreads(first:100) { totalCount
    nodes { isResolved } } } } }' \
    --jq '{returned: (nodes|length), totalCount, unresolved: [nodes[]|select(.isResolved==false)]|length}'
{"returned":16,"totalCount":16,"unresolved":16}   # matches script output exactly
```

[PASS] Status-check count and review-thread total/returned/unresolved/complete
all match ground truth obtained independently of the script under test,
reproduced identically across both evaluation dates.

**Probe 2: `octocat/Hello-World` PR #1**, re-run 2026-08-08:

```
exit code: 0
status_checks: []
status_check_total_count: 0
review_thread_total_count: 30
review_thread_returned_count: 30
review_thread_unresolved_count: 30
review_thread_counts_complete: true
```

[PASS] Confirms the empty-rollup branch is authoritative zero on live data,
reproduced identically to the 2026-08-07 run.

**Probe 3: Nonexistent repository (`github/some-truly-nonexistent-repo-xyz123`)
PR #1**, re-run 2026-08-08:

```
$ python .claude/skills/github/scripts/pr/get_pr_context.py \
    --owner github --repo some-truly-nonexistent-repo-xyz123 --pull-request 1
Failed to get PR #1: GraphQL: Could not resolve to a Repository with the
name 'github/some-truly-nonexistent-repo-xyz123'. (repository)
exit code: 3
```

[PASS] Generic external-service failure correctly exits 3, reproduced
identically to the 2026-08-07 run.

## Out-of-Scope Finding (Nonblocking)

**Not a QA gate for issue #3912.** Preserved here as evidence for a future,
separately-filed issue, per explicit instruction not to combine unrelated
defects into this fix.

**Finding**: Real `gh pr view` (v2.97.0) never emits the substring `"not
found"` for a nonexistent PR; it emits `"Could not resolve to a PullRequest
with the number of N. (repository.pullRequest)"` with `rc=1`. `_load_pr_data`'s
`if "not found" in err_msg` check therefore never matches, and the script
falls through to `error_and_exit(..., 3)` instead of the documented exit 2.

```
$ python .claude/skills/github/scripts/pr/get_pr_context.py \
    --owner rjmurillo --repo ai-agents --pull-request 999999
Failed to get PR #999999: GraphQL: Could not resolve to a PullRequest with
the number of 999999. (repository.pullRequest)
exit code: 3   # documented contract expects exit code 2
```

**Confirmed pre-existing and unrelated to issue #3912**:

```
$ git show main:.claude/skills/github/scripts/pr/get_pr_context.py | grep -n '"not found"'
113:        if "not found" in err_msg:
```

The same string-literal check, with the same behavior, exists byte-for-byte
on `main` before this branch's diff. It was introduced by the original
#3912 commit `30619adf3` (an earlier, separate change), not by this branch's
status-check/review-thread work, and issue #3912's body, PRD, and reopening
comment never mention it. This branch neither introduces nor worsens the
defect.

**Recommendation**: File a new issue for the `gh pr view` not-found error
text drift, independent of #3912. Suggested fix: match on the GraphQL error
shape `gh` actually returns (e.g., a case-insensitive check for `"could not
resolve"` combined with `"pullrequest"`), and add a regression test using the
real `gh` error string quoted above instead of the synthetic `"not found"`
mock currently in `test_pr_not_found_exits_2`.

## Gaps Identified

None within issue #3912's scope.

## Recommendations

1. All issue #3912 acceptance criteria (status checks + count, review-thread
   total/returned/unresolved/complete, pagination past 100, null-rollup
   authoritative zero, malformed/missing response exit 3, mirror parity,
   docs) are verified by both deterministic tests and live GitHub probes and
   require no further action. Ready for PR.
2. File a separate issue for the out-of-scope PR-not-found exit-code defect
   documented above. Do not fold it into this branch.

## Recommended Handoff

**orchestrator**: Issue #3912 acceptance criteria fully met. All tests pass,
mirrors match, docs are accurate, and live probes confirm behavior against
real GitHub data. Ready for business validation / PR. The unrelated
PR-not-found exit-code defect is documented above as nonblocking, out-of-scope
evidence for a future issue and does not block this handoff.
