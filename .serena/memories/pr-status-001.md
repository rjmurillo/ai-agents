# Status Classification Decision Tree

**Atomicity**: 90%
**Category**: PR Review
**Source**: 2025-12-24 Parallel PR Review Retrospective

## Statement

Check for blocking human responses before marking PR COMPLETE; use AWAITING_HUMAN if found.

## Context

Before assigning final status to PR after comment processing. Prevents premature closure when human response needed.

## Evidence

2025-12-24 Parallel PR Review: PR #300 marked COMPLETE when actually BLOCKED awaiting human response (12.5% misclassification). Decision tree needed: COMPLETE vs BLOCKED vs AWAITING_HUMAN.

## Decision Tree

```text
1. Check CI status:
   - Any failures? → BLOCKED
   
2. Check comment threads:
   - Any unresolved agent questions needing human input? → AWAITING_HUMAN
   - Any open review threads requiring action? → Check if blocking
   
3. If CI passing AND no blocking human responses → COMPLETE

Default: Conservative (AWAITING_HUMAN) over optimistic (COMPLETE)
```

## Status States

| State | Definition | Next Action |
|-------|------------|-------------|
| COMPLETE | All comments addressed, CI passing, no blockers | Ready for merge |
| BLOCKED | CI failing or merge conflicts | Fix blockers |
| AWAITING_HUMAN | Question asked, waiting for human response | Wait or ping reviewer |

## Related

- [pr-156-review-findings](pr-156-review-findings.md)
- [pr-308-devops-review](pr-308-devops-review.md)
- [pr-320c2b3-refactoring-analysis](pr-320c2b3-refactoring-analysis.md)
- [pr-52-retrospective-learnings](pr-52-retrospective-learnings.md)
- [pr-52-symlink-retrospective](pr-52-symlink-retrospective.md)
