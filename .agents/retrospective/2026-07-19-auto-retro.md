# Retrospective: Lefthook Migration

## Session Context

- **Date:** 2026-07-19
- **Branch:** `chore/lefthook-migration`
- **Completed at:** `ff63ed93ee`
- **Outcome:** Migration completed. Final code review found no issues, security
  approved the change, QA passed, and full validation passed.

### Work Items

- Replaced `.githooks` and its custom installer with Lefthook 2.1.10.
- Moved hook payloads into `scripts/hooks` and updated bootstrap behavior.
- Updated documentation, CI, tests, security classifiers, generated mirrors, and
  plugin versions.
- Removed legacy hook installation paths and stale references.
- Validated the complete migration after review-driven corrections.

## What Went Well

- Pinning Lefthook 2.1.10 gave the migration a stable upstream reference.
- Iterative security review found two successive classifier gaps. The first pass
  found `lefthook.yml`. The next pass found all 30 auto-discovered primary and
  local configuration filenames.
- Each review finding changed implementation and test coverage before approval.
- Final code review reported no findings. Security approved the resulting
  classifier coverage. QA and the full validation suite passed.
- Generated mirrors, documentation, bootstrap paths, and tests moved together.
  This prevented a mixed old and new hook workflow.

## What Could Improve

- The first security classifier updates followed known repository files instead
  of Lefthook's complete discovery behavior. This required two review cycles.
- The migration should have derived the filename inventory from the pinned
  upstream source before implementation and test design.
- A QA subagent ran `rm -rf` on unrelated sibling `pr3097-worktree`. The command
  targeted a scratch basename inside the repository without proving ownership.
- Git worktree metadata allowed restoration of all tracked files. Verification
  confirmed the original branch, HEAD, and zero tracked diff. Any prior
  untracked or ignored files remain unknowable and may be lost.

## Key Learnings

### Upstream-Derived Coverage

- **Learning:** Derive config coverage from the exact pinned upstream source.
- **Impact:** Review expanded coverage to all 30 upstream-discovered primary and
  local filenames.
- **Atomicity:** 100%

### Iterative Security Review

- **Learning:** Re-run security review after every classifier expansion.
- **Impact:** Two review rounds found successive gaps. The final review found
  none.
- **Atomicity:** 100%

### Owned Cleanup Paths

- **Learning:** Clean only absolute, owned temporary paths outside repository
  worktrees.
- **Impact:** Prevents recurrence of one cross-worktree deletion. Target zero
  cleanup escapes.
- **Atomicity:** 100%

### Limits of Git Restoration

- **Learning:** Treat Git restoration as incomplete when untracked files may have
  existed.
- **Impact:** Tracked diff returned to zero. Untracked and ignored recovery
  remained unprovable.
- **Atomicity:** 100%

## Failure Patterns

### Destructive Cleanup by Basename

- **Signal:** A cleanup command resolves a scratch basename inside a repository
  containing multiple worktrees.
- **Failure:** A QA subagent deleted unrelated sibling `pr3097-worktree` with
  `rm -rf`.
- **Root cause:** The cleanup step trusted a basename and skipped absolute-path,
  ownership, and repository-boundary checks.
- **Impact:** Tracked files were restored. Prior untracked and ignored files may
  be permanently lost.
- **Prevention rule:** Never clean scratch paths by basename inside a repository.
  Create scratch space under an absolute system temporary path. Require an
  ownership marker, resolve the target, and abort unless it is outside every
  repository and worktree before deletion.

### Incomplete Security Classifier Inventory

- **Signal:** Classifier tests cover files present in the repository but lack an
  inventory tied to the pinned tool version.
- **Failure:** Initial coverage omitted `lefthook.yml`, then omitted Lefthook's
  wider auto-discovered configuration filename set.
- **Root cause:** Implementation followed local examples instead of discovery
  logic from pinned upstream source.
- **Impact:** Two review cycles were required before security approval.
- **Prevention rule:** Extract accepted configuration names from the pinned
  upstream source, record the source version, and test the full inventory.

## Actionable Next Steps

1. Add a QA cleanup guard that accepts only absolute system temporary paths with
   an ownership marker. Reject repository and worktree targets before deletion.
2. Add destructive-action instructions to QA prompts: no basename cleanup and no
   deletion outside a task-owned temporary root.
3. Keep the upstream-derived Lefthook filename inventory tied to version 2.1.10.
   Re-derive and review it whenever the pinned version changes.
4. Preserve iterative security review after classifier changes. Approval requires
   zero known inventory gaps and tests for every accepted filename.
