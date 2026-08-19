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

## Correction 2026-08-18 (Issue #5139)

A second Copilot review round on PR #5103, raised after this retrospective
landed, found four factual errors below. Per `.claude/rules/retros.md`
MUST-1, this landed retro is not edited in place; this section corrects it.

1. **FM-10 classification (Root Cause section) was wrong.** FM-10
   (`.agents/governance/FAILURE-MODES.md` lines 315-330) is defined by "the
   execution succeeds; the failure is invisible" and "the call site has no
   way to know the operation didn't actually do what its name claims." The
   `always()` bug is the opposite shape: the aggregator's failure is loudly
   VISIBLE, as a required red check run on the PR head. Nothing was
   suppressed or hidden; a real signal (cancellation) was misclassified as a
   different real signal (failure), and both were surfaced. None of the 11
   classes currently in `FAILURE-MODES.md` describes "two non-equivalent
   upstream states collapsed onto one boolean guard, each surfaced
   correctly as far as the guard can tell." Per retros.md MUST-2, a class
   that does not exist requires a linked ADR proposing it; that is an
   architecture decision needing sign-off per `AGENTS.md`'s "Ask First:
   Architecture | New ADRs" boundary, not something this documentation-only
   PR does unilaterally. Filing that ADR is a follow-up, not completed here.
   The closest existing class, FM-4 (False Completion Markers), also does
   not fit: FM-4 is about an agent's own success narration, not a CI gate's
   verdict logic. Read the Root Cause section's FM-10 citation as retracted;
   the mechanism it describes (a guard clause conflating two distinct
   states) is still accurate, only the taxonomy citation was wrong.

2. **Cancelled-vs-skipped conclusion (Fix section) was wrong.** "it skips
   when the run itself is cancelled. A skipped job publishes no check run"
   is true only for a job that has not yet started. `if:` is evaluated
   once, before a job starts; a job already running when the whole-run
   cancellation lands is force-terminated with conclusion `cancelled`, not
   `skipped`. Verified against a real superseded run on PR #5103 (run
   `31896264033`): overall conclusion `cancelled`, both its "Run Python
   Tests" and "Main failure alert" jobs `cancelled`, not `skipped`. The
   fix's actual guarantee holds either way: `cancelled` and `skipped` are
   both non-`success`/non-`failure`, so branch protection still does not
   merge on a false green, and neither is the red `failure` `always()`
   produced.

3. **Test count (Fix section, "33 tests") was stale.** The suite gained a
   test (`test_sweep_catches_a_reusable_workflow_call_aggregator`, added in
   an earlier review-fix round) before this retro was written; the count at
   the retro's own reference point was 34, not 33.

4. **Unowned follow-up (Remediation section) is now owned.** The
   `codeql-analysis.yml::check-blocking-issues` follow-up, listed as "Worth
   its own issue," is tracked by issue #5104.

## Correction 2026-08-18, round 2 (PR #5141 review)

A Copilot review round on PR #5141, the fix for the four items above, found
that item 1 was left without an owner and that item 2's replacement claim
was itself wrong. Per retros.md MUST-1, this appends rather than edits the
round-1 correction above.

1. **FM-10 replacement is now tracked.** Round 1 said "filing that ADR is a
   follow-up, not completed here" with no issue number, which a reviewer
   correctly read as leaving the retrospective's MUST-2 obligation
   unresolved and unowned. Issue #5145 tracks proposing a new
   `FAILURE-MODES.md` class (or an explicit decision that none is
   warranted) for this failure's shape: a boolean guard conflating two
   non-equivalent upstream states, with the result surfaced loudly rather
   than suppressed.

2. **Round 1's "cancelled-vs-skipped" replacement mechanism was itself
   wrong.** Round 1 wrote: "`if:` is evaluated once, before a job starts; a
   job already running when the whole-run cancellation lands is
   force-terminated with conclusion `cancelled`, not `skipped`, since `if:`
   is not re-evaluated mid-run." That is backwards. GitHub's workflow
   cancellation reference states directly: "To cancel the workflow run, the
   server re-evaluates `if` conditions for all currently running jobs. If
   the condition evaluates to `true`, the job will not get canceled." A
   running job's `!cancelled()` flips to false under that re-evaluation,
   and the job is cancelled BECAUSE of the re-evaluation, not despite `if:`
   never being re-evaluated. The observed conclusion (`cancelled`, verified
   on run `31896264033`) and the practical guarantee (a guarded job never
   concludes the red `failure` `always()` produced) are unchanged; only the
   stated mechanism was wrong, twice in a row, before this correction.
