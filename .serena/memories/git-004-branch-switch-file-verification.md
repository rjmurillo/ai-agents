# Skill: git-004 - Branch Verification Before Commit

**Atomicity**: 92%
**Category**: Git operations, verification
**Source**: PR #669 PR co-mingling retrospective

## Pattern

Verify the current branch before EVERY commit to prevent cross-PR contamination.

## Problem

Agents commit to the wrong branch when:

- Multiple PRs active in single session
- Branch switches during session
- Trust-based compliance (agent "should remember")

**Failure impact**: 4 PRs contaminated, ~3 hours remediation (PR #669)

## Solution

Verification-based enforcement at commit time:

```bash
# BEFORE every git commit
CURRENT_BRANCH=$(git branch --show-current)
EXPECTED_BRANCH="[from session log or environment]"

if [ "$CURRENT_BRANCH" != "$EXPECTED_BRANCH" ]; then
    echo "ERROR: Branch mismatch (current: $CURRENT_BRANCH, expected: $EXPECTED_BRANCH)"
    exit 1
fi

# Proceed with commit
git commit -m "..."
```

## Integration Points

### Session Protocol (Phase 1)

```markdown
## Phase 1.0: Branch Verification (BLOCKING)

Before ANY other action:

```bash
git branch --show-current  # Output MUST appear in transcript
```

Document in session log header:
**Branch**: [output from git branch --show-current]

```

### Pre-Commit Hook

```powershell
#!/usr/bin/env pwsh
# .git/hooks/pre-commit

$current = git branch --show-current
$expected = $env:SESSION_BRANCH  # Set during session init

if ($current -ne $expected) {
    Write-Error "Branch mismatch: $current != $expected"
    exit 1
}
```

### Agent Workflow

```powershell
# Before implementer commits changes
$branch = git branch --show-current
Write-Host "Committing to branch: $branch"

# Verify matches session context
if ($branch -ne $sessionLog.Branch) {
    throw "Branch mismatch detected"
}
```

## Evidence

**PR #669**: 4 PRs affected by wrong-branch commits

- PRs #562, #563, #564, #565 all received commits intended for other PRs
- Remediation required cherry-picking ~15 commits
- Delay: ~12 hours in merge queue
- Root cause: No branch verification before commits

## Related Skills

- protocol-013: Verification-based enforcement
- session-init-003: Branch declaration requirement
- git-hooks-004: Pre-commit branch validation
- git-003: Staged changes guard

## Testing

```powershell
# Test 1: Verify branch check before commit
git checkout -b feat/test-1
git add file.txt
# Should verify current branch is feat/test-1
git commit -m "test"

# Test 2: Detect branch mismatch
git checkout feat/test-2  # Switch branch
# Attempt commit without updating session context
# Should fail with branch mismatch error
```

## Implementation Checklist

- [ ] Add Phase 1.0 to SESSION-PROTOCOL (branch verification)
- [ ] Add Phase 8.0 to SESSION-PROTOCOL (pre-commit re-verification)
- [ ] Create pre-commit hook (git-hooks-004)
- [ ] Update session log template (session-init-003)
- [ ] Document in AGENT-INSTRUCTIONS.md

## References

- PR #669: PR co-mingling retrospective
- Issue #684: SESSION-PROTOCOL branch verification
- Issue #681: Pre-commit hook implementation
- ADR-XXX: Verification-based enforcement (to be created)

## Related

- [git-003-staged-changes-guard](git-003-staged-changes-guard.md)
- [git-004-branch-verification-before-commit](git-004-branch-verification-before-commit.md)
- [git-branch-cleanup-pattern](git-branch-cleanup-pattern.md)
- [git-conflict-deleted-file](git-conflict-deleted-file.md)
- [git-conflict-resolution-workflow](git-conflict-resolution-workflow.md)
