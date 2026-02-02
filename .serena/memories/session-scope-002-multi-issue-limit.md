# Skill-Session-Scope-002: Multi-Issue Limit

**Statement**: Limit sessions to 2 issues maximum to prevent context confusion

**Context**: At session start when planning work scope with multiple issues

**Evidence**: PR #669 co-mingling incident - working on 3+ issues caused branch confusion and wrong commits

**Atomicity**: 85% | **Impact**: 7/10

## Pattern

**Session Scope Decision Tree**:

1. **Single Issue**: Ideal, proceed normally
2. **Two Issues**: Acceptable if:
   - Issues are closely related (same domain)
   - Both use same branch OR separate worktrees
   - Session log explicitly tracks both
3. **Three+ Issues**: REJECT
   - Split into multiple sessions
   - Complete one fully before starting next

```markdown
# Session Log Header Example (2 issues)
## Issues in Scope
- #123: Primary issue (feat/issue-123)
- #124: Related dependency (same branch)

## Branch Strategy
- Single branch: feat/issue-123-and-124
- OR Worktree isolation: feat/issue-123 + feat/issue-124
```

## Anti-Pattern

```markdown
# WRONG: Too many issues in one session
## Issues in Scope
- #120: Add feature A
- #121: Fix bug B
- #122: Update docs C
- #123: Refactor D

# Problem: High risk of wrong-branch commits
```

## Related Skills

- [session-init-003-branch-declaration](session-init-003-branch-declaration.md): Explicit branch tracking
- [git-004-branch-verification-before-commit](git-004-branch-verification-before-commit.md): Per-commit protection
- [git-worktree-parallel](git-worktree-parallel.md): Isolation for multiple branches

## Related

- [session-109-export-analysis-findings](session-109-export-analysis-findings.md)
- [session-110-agent-upgrade](session-110-agent-upgrade.md)
- [session-111-investigation-allowlist](session-111-investigation-allowlist.md)
- [session-112-pr-712-review](session-112-pr-712-review.md)
- [session-113-pr-713-review](session-113-pr-713-review.md)
