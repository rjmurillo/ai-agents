# Skill: Skill-QA-007-Pre-Push-Worktree-Isolation-Verification

**Atomicity Score**: 89%
**Source**: lawe (QA agent) - Sessions 40-41 retrospective
**Date**: 2025-12-20
**Validation Count**: 1 (Sessions 40-41 incident)

## Definition

QA must verify worktree isolation BEFORE accepting any push to remote. Prevents agents from accidentally pushing to shared branches or main.

## Verification Checks

### Check 1: Branch Name Pattern

```
Pattern: (feat|fix|audit|chore|docs)/*
Failure: Branch does not match isolation pattern
```

### Check 2: Not on Shared/Main Branch

```
Forbidden: main, master, copilot/add-copilot-context-synthesis, develop
Failure: Currently on shared/main branch
Action: Create isolated branch first
```

### Check 3: Worktree Exists (if in worktree mode)

```
Pattern: worktree-{ROLE}-*
Verification: git worktree list --porcelain
Warning: No worktree found matching pattern
```

### Check 4: Single Feature Commits

```
Action: Extract issue numbers from commits
Expected: Maximum 1 unique issue number
Warning: Multiple issues detected in commits
```

## When to Use

- MUST run before: `git push`
- Called by: QA validation gate (Phase 5 in SESSION-PROTOCOL.md)
- Part of: Pre-push verification checklist

## Implementation Pattern

```powershell
# Conceptual verification (not external script - memory-first)
$branch = git branch --show-current
if ($branch -notmatch "^(feat|fix|audit|chore|docs)\/") {
    # FAIL: Branch does not match isolation pattern
}
if ($branch -in @("main", "master", "copilot/add-copilot-context-synthesis")) {
    # FAIL: On shared/main branch
}
```

## Result

- Boolean pass/fail
- Machine-parseable output
- Blocking if failed

## Evidence

Sessions 40-41: First push to shared branch went unchallenged. No QA gate required worktree verification BEFORE push. Violation discovered after 4+ commits accumulated.

## Why 89% Atomicity

- Solves: Prevents agents from pushing to shared branches
- Specific: Checks 4 concrete criteria
- Testable: Returns boolean, machine-parseable output
- Reusable: Works for any agent, any worktree pattern
- Limitation: Doesn't enforce Session log creation (separate skill needed)
