# Skill: Branch State Verification

## Statement

Verify current branch with `git branch --show-current` before making any file edits.

## Trigger

Before any file modification during PR comment response.

## Action

1. Run `git branch --show-current`
2. Confirm output matches expected PR branch
3. If mismatch, checkout correct branch before proceeding

## Concurrent Push Extension

Before every push, compare the PR's live `headRefOid` with the local commit that was last fetched or extended. Stop when they differ. A failed fetch or a missing expected remote ref also blocks the push. Pushing from a stale snapshot can recreate a branch that GitHub deleted after merge.

**Evidence**: PRs #3340, #3347, and #3348 had concurrent branch updates. SHA checks preserved those commits and prevented overwrite.

## Benefit

Prevents edits to wrong branch when branch checkouts fail silently with uncommitted changes.

## Evidence

- PR #488: Branch checkout failed silently due to uncommitted changes
- Learning documented: "Always verify current branch before making edits"

## Anti-Pattern

Assuming `git checkout` succeeded without verification.

## Related

- Read tool may trigger file watchers affecting branch state
- Explicitly verify state before and after Read operations

## Atomicity

**Score**: 95%

**Justification**: Single concept (branch verification). Highly actionable.

## Category

pr-comment-responder

## Created

2025-12-29

## Related

- [pr-comment-001-reviewer-signal-quality](pr-comment-001-reviewer-signal-quality.md)
- [pr-comment-002-security-domain-priority](pr-comment-002-security-domain-priority.md)
- [pr-comment-003-path-containment-layers](pr-comment-003-path-containment-layers.md)
- [pr-comment-004-bot-response-templates](pr-comment-004-bot-response-templates.md)
- [pr-comment-index](pr-comment-index.md)
