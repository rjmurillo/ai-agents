# Retrospective: PR #3557 Validation Module Resolution

## Date: 2026-07-27

## Objective

Resolve dead and unwired validators for issue #3360.

## Learnings Captured

### Pattern: Hook gate triggered by unrelated file changes

The `adr-review-policy` hook fires on `SESSION-PROTOCOL.md` changes even when
the change is a trivial reference update (dead script name replacement). Fix:
separate documentation cleanup of gated files from the functional commit.

### Pattern: Governance schema documentation lags behind validator implementation

The traceability governance schema documented `NNN` (numeric-only) ID suffixes
while real repo IDs use alphanumeric (`a02`, `001`). The validator was already
correct; only the schema doc lagged. Both must update atomically.

### Pattern: Merge conflicts from main accumulate on long-lived branches

The PR was CONFLICTING because main advanced beyond its last merge commit. A
second merge-from-main resolved this cleanly with the ort strategy.

## Outcome

- 5 review threads addressed
- All 3 validators resolved: consistency (deleted), traceability (wired),
  hook_contracts (already wired by PR #3381)
- 14830 tests passing, 0 failures
