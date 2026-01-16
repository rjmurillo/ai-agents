# Skill Observations: git

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 1

## Purpose

This memory captures learnings from git workflows, branch management, commit patterns, and pre-commit hook design across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Verify branch before git operations using 'git branch --show-current' - SESSION-PROTOCOL.md mandates this at session start (Session 2026-01-16-session-07, 2026-01-16)
- Use exit code 1 for failures that should block commits, not exit code 2 - exit code 2 bypasses pre-commit hooks (Session 2026-01-16-session-07, 2026-01-16)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

## Edge Cases (MED confidence)

These are scenarios to handle:

- High ratio of fix: to feat: commits indicates insufficient upfront testing/validation before merge - add platform testing matrix to CI (Session 2026-01-16-session-07, 2026-01-16)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Verify branch before git operations |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Use exit code 1 for blocking failures, not exit code 2 |
| 2026-01-16 | 2026-01-16-session-07 | MED | High fix: ratio indicates insufficient upfront testing |

## Related

- [git-003-staged-changes-guard](git-003-staged-changes-guard.md)
- [git-004-branch-switch-file-verification](git-004-branch-switch-file-verification.md)
- [git-004-branch-verification-before-commit](git-004-branch-verification-before-commit.md)
- [git-branch-cleanup-pattern](git-branch-cleanup-pattern.md)
- [git-conflict-deleted-file](git-conflict-deleted-file.md)
- [git-conflict-resolution-workflow](git-conflict-resolution-workflow.md)
- [git-hooks-002-branch-recovery-procedure](git-hooks-002-branch-recovery-procedure.md)
- [git-hooks-004-branch-name-validation](git-hooks-004-branch-name-validation.md)
- [git-hooks-autofix](git-hooks-autofix.md)
- [git-hooks-categories](git-hooks-categories.md)
- [git-hooks-cross-language](git-hooks-cross-language.md)
- [git-hooks-fix-hook-errors-never-bypass](git-hooks-fix-hook-errors-never-bypass.md)
- [git-hooks-no-verify-bypass-limitation](git-hooks-no-verify-bypass-limitation.md)
- [git-hooks-pre-commit-session-gap-796](git-hooks-pre-commit-session-gap-796.md)
- [git-hooks-session-validation](git-hooks-session-validation.md)
- [git-hooks-toctou](git-hooks-toctou.md)
- [git-merge-preflight](git-merge-preflight.md)
- [git-observations](git-observations.md)
- [git-worktree-cleanup](git-worktree-cleanup.md)
- [git-worktree-parallel](git-worktree-parallel.md)
- [git-worktree-worktrunk-hooks](git-worktree-worktrunk-hooks.md)
