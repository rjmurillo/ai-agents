# Skill: Git-003 Staged Changes Guard

**Statement**: Check for staged changes before `git commit` to handle clean merge scenarios.

**Atomicity Score**: 95%
**Source**: Session 86 retrospective - PR maintenance fix
**Date**: 2025-12-24
**Validation Count**: 1 (Commit 910f907)
**Tag**: defensive-coding

## Pattern

```powershell
$null = git diff --cached --quiet 2>&1
if ($LASTEXITCODE -eq 0) {
    # No staged changes - skip commit
    Write-Log "Merge completed without needing commit" -Level INFO
}
else {
    # Staged changes exist - proceed with commit
    $null = git commit -m "Merge message" 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to commit merge"
    }
}
```

## When to Apply

- After conflict resolution with `--theirs` or `--ours`
- After auto-merge scenarios
- Any automated merge workflow
- Scripts that programmatically resolve conflicts

## Why This Works

`git diff --cached --quiet` returns:

- Exit code 0: No staged changes (index matches HEAD)
- Exit code 1: Staged changes exist

Without this check, `git commit` fails when:

1. Merge completed cleanly (no conflicts)
2. `--theirs`/`--ours` resolution resulted in no actual change
3. Files were already identical to target version

## Evidence

Commit 910f907 - PR maintenance workflow fix:

- Fixed false-positive failures in Resolve-PRConflicts
- Applied to both GitHub runner and local worktree code paths

## Related Skills

- skill-git-001-pre-commit-branch-validation: Branch name security
- skill-git-002-branch-recovery-procedure: Recovery from bad state
- skill-ci-001-fail-fast-infrastructure-failures: CI failure handling

## Related

- [git-004-branch-switch-file-verification](git-004-branch-switch-file-verification.md)
- [git-004-branch-verification-before-commit](git-004-branch-verification-before-commit.md)
- [git-branch-cleanup-pattern](git-branch-cleanup-pattern.md)
- [git-conflict-deleted-file](git-conflict-deleted-file.md)
- [git-conflict-resolution-workflow](git-conflict-resolution-workflow.md)
