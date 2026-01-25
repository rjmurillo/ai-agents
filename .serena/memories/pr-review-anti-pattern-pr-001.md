# Anti-Pattern-PR-001: Assuming PR Enumeration Complete

**Type**: HARMFUL
**Atomicity**: 95%
**Category**: PR Review
**Source**: 2025-12-24 Parallel PR Review Retrospective

## Statement

Assuming `gh pr list` output is complete without verification causes systematic detection failures.

## Evidence

2025-12-24 Parallel PR Review: PR #336 missed in initial enumeration (12.5% detection failure rate). User intervention required: "Why do you keep missing PR 336?"

## Why This Is Harmful

1. **Silent failures**: Missing PRs go unnoticed until user feedback
2. **Trust erosion**: User must verify agent's work
3. **Wasted effort**: Re-processing required after discovery
4. **Systematic gap**: Not random—specific filter conditions cause misses

## Correct Pattern

See: `skill-pr-enum-001` (PR Enumeration Verification Gate)

Always cross-check filtered enumeration against total open PRs before proceeding.

## Related

- [pr-156-review-findings](pr-156-review-findings.md)
- [pr-320c2b3-refactoring-analysis](pr-320c2b3-refactoring-analysis.md)
- [pr-52-retrospective-learnings](pr-52-retrospective-learnings.md)
- [pr-52-symlink-retrospective](pr-52-symlink-retrospective.md)
- [pr-753-remediation-learnings](pr-753-remediation-learnings.md)
