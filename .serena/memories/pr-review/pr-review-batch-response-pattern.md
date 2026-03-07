# PR Review Batch Response Pattern

## Pattern

Collect all PR review comments and address them together in a single commit for clean history and efficient resolution.

## Problem

Responding to PR comments one-at-a-time creates:

- Noisy commit history (many small "fix review comment" commits)
- Difficult code archaeology (changes spread across commits)
- Inefficient workflow (context switching per comment)
- Harder to revert if needed (must revert multiple commits)

## Solution

**When PR review contains multiple comments**:

1. Read all comments first (don't start fixing immediately)
2. Categorize by type (documentation, code, tests, typos)
3. Implement all fixes together
4. Create single commit: `fix: address PR review feedback`
5. Reply to each comment thread explaining the fix
6. Link to the single commit in replies

## Evidence

**Session 826** (2026-01-13): PR #895 received 8 review comments from `copilot-pull-request-reviewer`. All 8 were addressed in single commit `bce23f0`:

```
commit bce23f0
Author: Claude
Date:   2026-01-13

fix: address PR review feedback (8 comments)

- Updated ADR-040 file count (18 → 54)
- Fixed session log naming reference
- Added YAML compatibility rationale
- [5 more fixes...]
```

**Result**: Clean history, easy to review, all threads resolved efficiently.

## Benefits

| Metric | One-commit-per-comment | Batch Response |
|--------|------------------------|----------------|
| Commits in history | 8 commits | 1 commit |
| Context switches | 8 switches | 1 switch |
| Reviewer re-review effort | High (8 commits) | Low (1 commit) |
| Revert complexity | Must revert 8 | Revert 1 |
| Commit message clarity | Varies | Consolidated |

## Exception Cases

**When to use multiple commits**:

- Unrelated concerns (e.g., bug fix + feature request)
- Large refactoring + documentation changes
- Critical security fix + non-critical improvements

## Impact

- **Atomicity**: 90%
- **Domain**: pr-review
- **Time Savings**: ~30% reduction in review resolution time
- **History Clarity**: Easier git archaeology

## Implementation

Add to PR review workflow:
```markdown
When review comments received:
1. [ ] Read all comments without starting fixes
2. [ ] Group by category (code, docs, tests)
3. [ ] Implement all fixes
4. [ ] Single commit: "fix: address PR review feedback"
5. [ ] Reply to each thread with explanation
```

## Related

- [[pr-review-007-ci-verification]] - CI checks before review
- [[pr-comment-004-bot-response-templates]] - Comment reply templates
- [[git-004-branch-verification-before-commit]] - Pre-commit validation

## Source

- Session: 826 (2026-01-13)
- Retrospective: `.agents/retrospective/2026-01-13-fix-tools-frontmatter-retrospective.md`
- Learning: L3 (Phase 4, Lines 540-548)
- Commit: bce23f0 (8 comments in 1 commit)
