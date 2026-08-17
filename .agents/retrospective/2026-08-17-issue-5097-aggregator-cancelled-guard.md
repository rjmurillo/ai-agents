# Retrospective: aggregator jobs report FAILURE on a cancelled run

## Session Info

- **Date**: 2026-08-17 (work spans 2026-08-15 through 2026-08-17, session 14714)
- **Task Type**: Bug fix, CI infrastructure
- **Outcome**: Success. PR #5103, branch `fix/issue-5097-aggregator-cancelled-guard`.

## What Happened

Issue #5097 was one of three churn reports filed against PR #5087 (issue #5074,
the merge-resolver rename rule) after that PR merged. `Validate PR` runs kept
going red on pushes that were themselves superseded seconds later by a newer
push. Five result-aggregator jobs across four workflows
(`pytest.yml::test-result`, `pytest.yml::main-failure-alert`,
`cli-smoke.yml::smoke-result`, `installed-plugin-hook-guard.yml::guard-result`,
`test-codeql-integration.yml::aggregate-results`) carried
`if: always()`. GitHub's own `cancel-in-progress` concurrency setting cancels a
superseded run, but `always()` still executes the aggregator step, its
dependencies report `cancelled`, and the aggregator's own `!= 'success'` check
converts that into a published `failure` check run on the pull request head.

## Root Cause

`if: always()` was applied to make an aggregator report a real failure when a
dependency legitimately failed or was skipped (the #2347 fix this pattern
descends from). It over-corrected: it also runs, and therefore also fails,
when the *run itself* was cancelled, which is not a failure of anything the
aggregator is supposed to be grading. The aggregator's logic has no way to
distinguish "a dependency failed" from "this whole run was superseded," so it
launders a `cancelled` state into a `failure` state without surfacing that the
run never actually evaluated.

This is FM-10 (Silent Defaults and Guard-Clause Suppression,
`.agents/governance/FAILURE-MODES.md`), not the FM-4 (False Completion
Markers) it produces downstream: the mechanism is a guard clause
(`always()`) that suppresses the distinction between "graded and failed" and
"never graded," and the visible symptom (a red required check on a PR whose
latest push is actually fine) is what looks like a false failure marker to
anyone watching the PR.

## Fix

Replaced `always()` with the vendor-recommended `!cancelled()` on the five
aggregator jobs. `!cancelled()` still runs (and can still fail) when a
dependency reports `failure` or `skipped`, preserving the #2347 behavior, but
it skips when the run itself is cancelled. A skipped job publishes no check
run, and a skipped check is not a success, so branch protection keeps waiting
on the newer, non-cancelled run instead of merging on a false green or
blocking on a false red.

Audited every `.github/workflows/*.yml` job carrying both `needs` and
`always()` (24 total): 7 consume a dependency result on a PR head and are the
fixed shape, 2 were already guarded by #2347's `always() && !cancelled()`
spelling, and the rest are `schedule`/`workflow_dispatch`-only or read
artifacts rather than `needs.<job>.result`, so they sit outside this fix's
shape.

`tests/workflows/test_aggregator_cancellation_guard.py` (33 tests) pins the
fix per job with a repository-wide sweep asserting no unguarded
result-consuming aggregator remains, plus a mutation control that restores
`always()` on one job and confirms exactly the three tests naming that job
fail. Two pre-existing tests that pinned the old `always()` contract
(`test_pytest_xdist_parallelism.py::test_aggregate_runs_when_path_detection_fails`,
`test_plugin_hook_guard_aggregate.py::test_guard_result_runs_even_when_dependencies_fail`)
were flipped in the same diff, not deleted, per the mirror obligation.

## Lessons

1. `always()` and `!cancelled()` are not interchangeable despite both reading
   as "run no matter what." `always()` also fires on cancellation; the vendor
   docs name `!cancelled()` as the replacement for exactly this reason. A
   Serena memory (`ci/ci-infrastructure-aggregate-job-always-pattern.md`) had
   previously told future sessions to write `always()` on aggregate jobs; it
   was corrected in this diff rather than left to mislead the next reader.
2. A cancelled run and a failed run are different signals, and any aggregator
   that cannot tell them apart will eventually launder one into the other.
   The general form of the fix, not just this instance, is to make the
   distinguishing case (cancelled vs. failed vs. skipped) an explicit branch
   rather than relying on a single boolean guard to cover all three.
3. A gate that audits `if: always()` usage repository-wide, not just the
   reported instance, catches the sibling jobs before they generate their own
   issue reports. Five jobs shared this defect; only one had a filed issue.

## Remediation

- This PR (#5103) is the remediation for issue #5097.
- Follow-up named in the QA report: `codeql-analysis.yml::check-blocking-issues`
  keeps `always()`; it is outside this fix's shape (reads SARIF, not
  `needs.<job>.result`) but a cancelled run can still leave it red on missing
  artifacts. Worth its own issue.
- Follow-up: `ai-pr-quality-gate.yml::aggregate` and
  `ai-session-protocol.yml::aggregate` keep the redundant
  `always() && !cancelled()` spelling from #2347. Cosmetic, deliberately out
  of scope here.
