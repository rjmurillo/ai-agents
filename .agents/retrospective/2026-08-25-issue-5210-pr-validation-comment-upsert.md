# Issue #5210: PR validation comment upsert retrospective

Date: 2026-08-25

## Evidence

- [Issue #5210](https://github.com/rjmurillo/ai-agents/issues/5210): defines the stale-validation-comment bug
- [PR #5281](https://github.com/rjmurillo/ai-agents/pull/5281): delivers the fix
- Commit `f3600fdeb`: `fix(ci): pass --update-if-exists to the PR validation comment poster`
- `.github/workflows/pr-validation.yml`: workflow file modified to add the flag
- `tests/ci/test_pr_validation_workflow.py::test_post_pr_comment_step_updates_the_existing_comment_in_place`: mutation-tested wiring assertion (see "What went well" below)

## What we did

Fixed the bug in Issue #5210: `pr-validation.yml`'s "Post PR Comment" step called
`post_issue_comment.py` without `--update-if-exists`, so the script took its
write-once idempotency path once a `PR-VALIDATION`-marked comment existed. A
fixed PR kept showing its first failing verdict forever, because every later
run recomputed the report correctly and then hit the "already exists.
Skipping." branch. The fix is a one-line workflow change
(`.github/workflows/pr-validation.yml`) adding the flag, already the documented
switch to the update path in `post_issue_comment.py` and already used
identically by `ai-spec-validation.yml`.

The issue also named a second caller of the same script,
`investigation-claim-backstop.yml`, and required an explicit decision rather
than a silent default. That step only runs `if: failure()` and never re-posts
once the PR is fixed, so it has no stale-PASS-shown-as-FAIL failure mode to
correct; left it write-once and documented the reasoning in a YAML comment
next to the step.

Commit: `f3600fdeb` `fix(ci): pass --update-if-exists to the PR validation comment poster`

## What went well

- `post_issue_comment.py` already had a correct, fully unit-tested
  `--update-if-exists` upsert path (`TestMainIdempotency` in
  `tests/test_post_issue_comment.py`). The defect was purely in wiring, not in
  the script, which kept the fix to one workflow line.
- Added a mutation control for the new workflow-wiring test
  (`tests/ci/test_pr_validation_workflow.py::test_post_pr_comment_step_updates_the_existing_comment_in_place`):
  reverted only the workflow file with `git stash push --
  .github/workflows/pr-validation.yml`, confirmed the test fails on the
  pre-fix workflow, then restored the fix. Confirms the test actually
  discriminates fixed from broken, per `.claude/rules/testing.md` SHOULD-10.
- Extended `tests/test_post_issue_comment.py` with two cases the acceptance
  criteria specifically asked for: one asserting the comment BODY sent to
  `update_issue_comment` actually changes to the new report (not just that the
  call returns 0, since the original bug also printed `Success: True`), and one
  proving a byte-identical re-run still updates in place rather than creating a
  duplicate comment.
- `scripts/validation/pre_pr.py` (57/57) and the security agent both cleared
  the change before push; the security review flagged two pre-existing LOW
  findings in `post_issue_comment.py`'s marker-matching logic (no comment-author
  check), out of scope for this fix and not introduced by it.

## What went wrong / friction

- The local clone was shallow (`git fetch --depth=<n>` from an earlier
  operation), which failed `push-ref-staleness` in the pre-push hook with
  "push validation requires complete Git history." Fixed with `git fetch
  --unshallow origin`.
- The pre-push `retrospective-policy` gate
  (`scripts/validation/git_hook_policy.py retrospective`) requires either a
  same-day file under `.agents/retrospective/` or session-log evidence. No
  session log exists for this session, per `.claude/rules/session-logs.md`
  ("session log creation is discontinued"), so the only remaining path is this
  retrospective file. `run_retrospective.py --since "4 hours ago"` populated
  the auto-generated skeleton's "Work Items" section with unrelated content
  (a pip-audit pin bump, an unrelated setup-uv test fix) that does not belong
  to this session's actual diff; rewrote the file by hand instead of trusting
  the auto-populated section verbatim.

## Learnings

1. When a workflow calls a script that already has a documented idempotency
   flag, check whether every caller of that script passes it consistently
   before assuming the bug is in the script.
2. A wiring-only bug (a missing CLI flag in a workflow YAML step) needs a
   mutation-tested wiring assertion, not just unit coverage of the script it
   calls; the unit tests here already existed and did not catch the missing
   flag because nothing asserted the workflow actually passed it.
3. `run_retrospective.py`'s `--since` evidence gathering can surface work
   items from unrelated recent commits on the branch; do not commit its
   auto-populated "Work Items" section without checking it against the
   actual diff being retrospected.

## Failure Mode Classification

Matches FM-9, Confident-Incorrectness Recurrence
(`.agents/governance/FAILURE-MODES.md`): `run_retrospective.py --since "4
hours ago"` populated the "Work Items" section from partial signal (a
wall-clock-windowed `git log` scan), and that section named commits unrelated
to this session's actual diff (a pip-audit pin bump, an unrelated setup-uv
test fix, from other work on the same branch inside the window). Committing
that section verbatim, without cross-checking it against `git status` and the
real diff, would have shipped a retrospective narrating work this session did
not do. No existing class other than FM-9 fits, so no new class or ADR is
proposed per `.claude/rules/retros.md` MUST-2.

Caught before commit, not after multi-round correction, so impact is Low: one
session, one file, corrected pre-push. Evidence is this retrospective's own
"What went wrong / friction" section above; there is no separate incident
file because nothing shipped incorrect.

## Remediation

| Action | Status |
|---|---|
| Add `--update-if-exists` flag to `pr-validation.yml` comment poster step | Applied: commit `f3600fdeb` |
| Document `investigation-claim-backstop.yml` write-once decision in a YAML comment next to the step | Applied: commit `f3600fdeb` |
| Add a mutation-tested workflow wiring assertion (`tests/ci/test_pr_validation_workflow.py::test_post_pr_comment_step_updates_the_existing_comment_in_place`) | Applied: verified against a revert-only control |
| Extend `test_post_issue_comment.py` with body-verification and duplicate-prevention tests | Applied: `TestMainIdempotency` |
| Cross-check `run_retrospective.py`'s auto-generated "Work Items" against the actual session diff before committing | Done this session: caught and rewrote by hand before commit |
| File an issue to scope `run_retrospective.py --since` to the current branch's own commits (or the session's actual diff) instead of a wall-clock window that can span unrelated concurrent work on the same branch | Not filed. Single-session friction with no repeat evidence yet; revisit if this recurs in a future retrospective |
