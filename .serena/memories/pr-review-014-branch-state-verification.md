# Skill: Branch State Verification

## Statement

Verify current branch with `git branch --show-current` before making any file edits.

## Trigger

Before any file modification during PR comment response.

## Action

1. Run `git branch --show-current`
2. Confirm output matches expected PR branch
3. If mismatch, checkout correct branch before proceeding

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

- [pr-156-review-findings](pr-156-review-findings.md)
- [pr-320c2b3-refactoring-analysis](pr-320c2b3-refactoring-analysis.md)
- [pr-52-retrospective-learnings](pr-52-retrospective-learnings.md)
- [pr-52-symlink-retrospective](pr-52-symlink-retrospective.md)
- [pr-753-remediation-learnings](pr-753-remediation-learnings.md)
