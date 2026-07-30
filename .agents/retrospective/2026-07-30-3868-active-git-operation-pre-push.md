---
date: 2026-07-30
issue: 3868
scope: scripts/validation/git_hook_policy.py
---

## Retrospective: active Git operation pre-push guard

### Context

Issue #3868 reported wasted pre-push time when a worktree still had an active
merge. The pre-push chain reached expensive validation before any job explained
that `MERGE_HEAD` existed.

### What changed

The first pre-push policy command now checks active Git operation state before
branch, history, security, test, or lint work. It blocks merge, rebase, and
cherry-pick states. It lists unmerged paths when present and still blocks after
conflicts are resolved but before the final commit exists.

### Learnings captured

1. Pre-push guards for repository state need to run before history checks and
   before any push-range materialization. The value comes from failing in the
   first seconds, not from adding another late diagnostic.
2. `MERGE_HEAD` with no `git diff --diff-filter=U` output still represents an
   unfinished merge. A clean index is not enough evidence that the operation is
   complete.
3. Rebase and cherry-pick states need operation-specific wording. A generic
   conflict message would send the user to the wrong repair command.
