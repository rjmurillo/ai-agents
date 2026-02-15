# Anti-Pattern-Status-001: Status Conflation

**Type**: HARMFUL
**Atomicity**: 92%
**Category**: PR Review
**Source**: 2025-12-24 Parallel PR Review Retrospective

## Statement

Conflating task completion with PR readiness causes premature COMPLETE status.

## Evidence

2025-12-24 Parallel PR Review: PR #300 marked COMPLETE when actually BLOCKED awaiting human response (12.5% misclassification rate).

## Why This Is Harmful

1. **False completion**: PR appears done but isn't mergeable
2. **Stale PRs**: Waiting PRs get forgotten
3. **User confusion**: Status doesn't reflect reality
4. **Missing follow-up**: Human responses never received

## Correct Pattern

See: `skill-pr-status-001` (Status Classification Decision Tree)

Use distinct states:
- COMPLETE: Ready for merge (CI passing, no blockers)
- BLOCKED: CI failing or merge conflicts
- AWAITING_HUMAN: Question asked, waiting for response
