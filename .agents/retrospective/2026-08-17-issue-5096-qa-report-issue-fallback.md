# Retrospective: QA report issue-number fallback, and a stale memory shipped with it

## Session Info

- **Date**: 2026-08-17 (work spans 2026-08-15 through 2026-08-17, session 14713)
- **Task Type**: Bug fix, CI infrastructure, plus a documentation-accuracy defect
  found while closing the same PR out.
- **Outcome**: Success. PR #5107, branch `fix/issue-5096-qa-report-issue-fallback`.

## What Happened

Issue #5096 was one of three churn reports filed against PR #5087 (issue
#5074, the merge-resolver rename rule) after that PR merged. `Check QA Report
Exists` resolved a QA report by globbing `.agents/qa/*pr-{pr_number}*.md`
only, and a PR number does not exist until the PR is opened, so the first
push of every code PR failed the gate. `scripts/ci/check_pr_qa_report.py`
gained a fallback: when no PR-numbered report exists, fetch the PR body,
extract linked issue numbers, and glob `.agents/qa/*issue-{n}*.md` for each.

## Root Cause, Part 1: The Gate

The original fallback design tried linked issues in numeric order. That is
wrong whenever a PR both closes one issue and references another,
lower-numbered one: PR #5107 itself hit this live. Its body carried `Refs
#5074` and `Fixes #5096`; numeric order tried `#5074` first and matched
`pr-5087-issue-5074-merge-resolver-rename-rule.md`, a report PR #5087 left on
`main` after its squash merge. That report's `qaCommit` was a branch commit
unreachable from `main`, so the ancestry check failed a PR whose own report
was valid (run 31906948410). The fix ranks closing keywords (`Closes`,
`Fixes`, `Resolves`) ahead of bare `Refs`, tries body-appearance order within
each tier, and adds a `PR_TOKEN` filter that skips any candidate report whose
filename carries a `pr-<digits>` token for a *different* PR.

## Root Cause, Part 2: The Memory That Documented the Wrong Contract

`.serena/memories/ci/ci-qa-report-may-be-named-for-the-issue-not-the-pr.md`
was written from the original design and never updated when the ordering
changed. It shipped in the same diff that implemented the tiering fix,
stating the fallback issues were "deduplicated and sorted numerically" and
never mentioning the `PR_TOKEN` filter at all. This is FM-9
(Confident-Incorrectness Recurrence, `.agents/governance/FAILURE-MODES.md`):
the memory made a "matches the code" style claim about the contract without
re-reading the code after the code changed. It is exactly the shape
`.claude/rules/canonical-source-mirror.md` exists to prevent, applied to a
Serena memory instead of a docstring. Caught by a spec-validation pass (run
31985055511) before merge, not by a human re-reading the memory against the
diff.

## Fix

- `scripts/ci/check_pr_qa_report.py`: `_linked_issues` buckets matches into
  closing-keyword and bare-ref tiers instead of a single numerically-sorted
  set; `_find_issue_qa_report` takes the PR number and skips any candidate
  report bound to a different PR by filename.
- `tests/ci/test_pr_validation_workflow.py`: 30 new/rewritten tests, including
  a discriminating case that would pass under the old numeric-order
  implementation and fails under it once restored (mutation-verified: 1 test
  kill for the `PR_TOKEN` filter, 3 for the tiering).
- The memory file: corrected to describe tiered ordering and the `PR_TOKEN`
  filter, with the live #5107 failure cited as the reason the original design
  changed, so the next reader sees why numeric order was wrong instead of
  inheriting the same imagined contract.

## Lessons

1. A discriminating test case is the only real proof a fix works: the input
   has to be one on which the old and new implementations disagree. PR
   #5107's own `Validate PR` run supplied that case for free once the fix was
   live, because the PR's own body carried both a `Refs` and a `Fixes`
   keyword in the vulnerable order.
2. A memory or comment that describes another file's contract is a claim,
   not a note. `.claude/rules/canonical-source-mirror.md`'s obligation to
   quote the canonical source verbatim binds a Serena memory exactly as hard
   as it binds a docstring: both get read by a future session that trusts
   them over re-deriving from the code.
3. Shipping the code fix and the memory describing it in the same diff does
   not make the memory correct by proximity. The memory was written from the
   design intent at the start of the session and the implementation changed
   twice (numeric sort to appearance-order-per-tier, then the addition of the
   `PR_TOKEN` filter) without a corresponding memory pass. Treat "does the
   memory in this diff still match the code in this diff" as its own
   checklist item before closing a PR that ships both.

## Remediation

- This PR (#5107) is the remediation for issue #5096.
- The memory correction lands in this same PR rather than a follow-up, per
  the canonical-source-mirror rule's preference for fixing the imagined
  contract before it reaches a reviewer who trusts it.
