---
type: task
id: TASK-041
title: Delete the PR size ceilings outright
status: in-progress
priority: P1
complexity: S
related:
  - REQ-032
created: 2026-09-22
updated: 2026-09-22
author: plan
tags:
  - control-plane
  - adr-100
---

# TASK-041: Delete the PR size ceilings outright

Implements REQ-032. One PR, closes #5241.

## Milestones

Each milestone is one atomic commit. Order matters only where noted.

1. **Commit-count ceiling.** Remove `_check_commit_limit` and its call site in
   the pre-push path, and the `pr_commit_count` import in the hook policy
   module. Delete the commit-count classifier module and its tests. Remove the
   three `pr-validation.yml` steps (count check, add label, remove label).
   Delete the `needs-split` label script and its tests. Covers REQ-032 AC 1, 2.
2. **Atomic-commit ceiling.** Remove `check_atomic_commit`, its CLI handler,
   the `atomic-commit` lefthook job, and its tests. Covers AC 3.
3. **Scope ceiling.** Delete the scope script and the PR-base helper it alone
   uses, their tests, and the `scope-policy` and `branch-scope` lefthook jobs.
   Update the lefthook budget model job list. Covers AC 4, 5.
4. **Live documents.** Edit templates (not generated mirrors), then run the
   build so mirrors follow. Update CONTRIBUTING, scripts/AGENTS, project
   structure, governance constraints, gotchas, golden principles, failure
   modes, fail-open inventory, context entry points. Covers AC 6, 7, 9.
5. **ADR-100.** Record the owner decision, withdraw item 6 and the re-measure,
   set `implemented: true`, and stage a debate log. Covers AC 8.

## Risks

| Risk | Mitigation |
|------|------------|
| A shared test file asserts a deleted job name | Run the full suite, fix assertions that name deleted jobs only |
| Mirror drift | Edit templates, run the build, commit mirrors in the same commit |
| A deleted helper has a second caller | `git grep` each deleted symbol before deletion |

## Done

REQ-032 AC 1 to 10 pass. Full suite green.
