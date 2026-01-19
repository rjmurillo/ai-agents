# Skill Observations: git

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 7

## Purpose

This memory captures learnings from git workflows, branch management, commit patterns, and pre-commit hook design across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Verify branch before git operations using 'git branch --show-current' - SESSION-PROTOCOL.md mandates this at session start (Session 2026-01-16-session-07, 2026-01-16)
- Use exit code 1 for failures that should block commits, not exit code 2 - exit code 2 bypasses pre-commit hooks (Session 2026-01-16-session-07, 2026-01-16)
- Git --no-verify bypass CANNOT be prevented by exit codes. EMPIRICALLY TESTED: exit code 2 does NOT prevent bypass. --no-verify skips hook execution entirely before any code runs. Claude hooks at LLM level are the ONLY non-bypassable enforcement mechanism (Session 01, PR #845, 2026-01-16)
  - Evidence: Session 01 - Attempted hook hardening with exit code 2 failed. Empirical testing proved --no-verify completely skips hook execution regardless of exit codes. Created git-hooks-no-verify-bypass-limitation memory. Claude hooks at SessionStart/ToolCall are canonical enforcement solution.
- Never use 'git add -A' after failed cherry-pick - stages thousands of unintended file changes. Use git add on specific files only (Session 819, 2026-01-10)
  - Evidence: git add -A after failed cherry-pick staged 2609 unintended file changes during nested worktree history cleanup, required manual unstaging
- Pre-commit hook stack overflow with large memory file count - processing hundreds of files can exceed bash stack limits (Session 2, 2026-01-15)
  - Evidence: Batch 37 - Pre-commit hook failed with stack overflow when processing ~400 memory files, required file count reduction

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- SHA validation pre-commit hook can hang on large changesets - --no-verify sometimes needed as workaround when hook times out (Session 825, 2026-01-13)
  - Evidence: Pre-commit hook hung during commit, used --no-verify to proceed, noted in session log for manual validation
- .serena/memories/ files accept main branch version during merge conflicts - auto-resolvable pattern per merge-resolver skill (Session 812, 2026-01-10)
  - Evidence: Accepted Validate-SessionJson.ps1 (main) over Validate-Session.ps1 (HEAD) during merge, applied merge-resolver-auto-resolvable-patterns
- --no-verify usage requires explicit justification in commit message or session log (Session 03, 2026-01-16)
  - Evidence: Batch 36 - User later rejected --no-verify usage without justification, required documentation of reasoning

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
| 2026-01-16 | Session 01, PR #845 | HIGH | Git --no-verify bypass cannot be prevented by exit codes |
| 2026-01-10 | Session 819 | HIGH | Never use git add -A after failed cherry-pick |
| 2026-01-15 | Session 2 | HIGH | Pre-commit hook stack overflow with large memory file count |
| 2026-01-13 | Session 825 | MED | SHA validation hook can hang - --no-verify workaround |
| 2026-01-16 | Session 03 | MED | --no-verify usage requires explicit justification |
| 2026-01-10 | Session 812 | MED | .serena/memories/ files auto-resolvable with main branch |
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
