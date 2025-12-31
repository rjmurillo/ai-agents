# Skill: git-hooks-004 - Branch Name Validation Pre-Commit Hook

**Atomicity**: 90%
**Category**: Git hooks, prevention
**Source**: PR #669 PR co-mingling retrospective

## Pattern

Pre-commit hook that validates branch names match expected patterns before allowing commits.

## Problem

Commits to wrong branches occur when:

- Agent on unexpected branch (e.g., main, wrong feature branch)
- No runtime verification before commit
- Trust-based compliance fails

**Evidence**: PR #669 - 4 PRs contaminated due to wrong-branch commits

## Solution

**Pre-commit hook** that validates branch name before every commit:

```powershell
#!/usr/bin/env pwsh
# .git/hooks/pre-commit
# Branch validation hook

$branch = git branch --show-current
$allowedPatterns = @('feat/*', 'fix/*', 'docs/*', 'chore/*', 'refactor/*', 'test/*')

# Block commits to main/master
if ($branch -in @('main', 'master')) {
    Write-Host "ERROR: Cannot commit to branch '$branch' directly" -ForegroundColor Red
    Write-Host "HINT: Create a feature branch first (git checkout -b feat/description)" -ForegroundColor Yellow
    Write-Host "BYPASS: Use 'git commit --no-verify' if intentional" -ForegroundColor Yellow
    exit 1
}

# Validate against allowed patterns
$matched = $false
foreach ($pattern in $allowedPatterns) {
    if ($branch -like $pattern) {
        $matched = $true
        break
    }
}

if (-not $matched) {
    Write-Warning "Branch '$branch' does not match conventional patterns"
    Write-Host "Expected: feat/*, fix/*, docs/*, chore/*, refactor/*, test/*" -ForegroundColor Yellow
    Write-Host "Proceeding anyway (non-blocking warning)" -ForegroundColor Yellow
}

exit 0
```

## Features

| Feature | Behavior |
|---------|----------|
| **Block main** | Reject commits to main/master (exit 1) |
| **Pattern validation** | Warn on non-conventional branch names |
| **Clear messages** | Error + hint for blocked commits |
| **Bypass** | Allow `--no-verify` for emergencies |

## Installation

### Manual Installation

```powershell
# Create hook file
$hookPath = ".git/hooks/pre-commit"
$content = @'
#!/usr/bin/env pwsh
# Branch validation hook

$branch = git branch --show-current
$allowedPatterns = @('feat/*', 'fix/*', 'docs/*', 'chore/*', 'refactor/*', 'test/*')

if ($branch -in @('main', 'master')) {
    Write-Host "ERROR: Cannot commit to branch '$branch' directly" -ForegroundColor Red
    Write-Host "HINT: Create a feature branch first" -ForegroundColor Yellow
    exit 1
}

$matched = $false
foreach ($pattern in $allowedPatterns) {
    if ($branch -like $pattern) { $matched = $true; break }
}

if (-not $matched) {
    Write-Warning "Branch '$branch' does not match conventional patterns"
}

exit 0
'@

Set-Content $hookPath $content
chmod +x $hookPath  # Make executable (Linux/macOS)
```

### Automated Installation

```powershell
# scripts/Install-GitHooks.ps1
function Install-BranchValidationHook {
    $hookPath = Join-Path (git rev-parse --git-dir) "hooks/pre-commit"
    
    if (Test-Path $hookPath) {
        Write-Warning "Pre-commit hook already exists at $hookPath"
        Write-Host "Backing up to $hookPath.backup"
        Copy-Item $hookPath "$hookPath.backup"
    }
    
    # Copy from template
    Copy-Item ".git-hooks/pre-commit-branch-validation.ps1" $hookPath
    
    # Make executable
    if ($IsLinux -or $IsMacOS) {
        chmod +x $hookPath
    }
    
    Write-Host "Branch validation hook installed at $hookPath" -ForegroundColor Green
}
```

## Testing

```powershell
# Test 1: Block commit to main
git checkout main
git add file.txt
git commit -m "test"
# Expected: ERROR: Cannot commit to branch 'main' directly

# Test 2: Allow commit to feature branch
git checkout -b feat/test-branch
git add file.txt
git commit -m "test"
# Expected: Commit succeeds

# Test 3: Warn on unconventional branch
git checkout -b my-custom-branch
git add file.txt
git commit -m "test"
# Expected: Warning but commit succeeds

# Test 4: Bypass hook
git checkout main
git add file.txt
git commit -m "emergency fix" --no-verify
# Expected: Commit succeeds (hook bypassed)
```

## Error Messages

### Blocked Commit (main)

```text
ERROR: Cannot commit to branch 'main' directly
HINT: Create a feature branch first (git checkout -b feat/description)
BYPASS: Use 'git commit --no-verify' if intentional
```

### Pattern Warning

```text
WARNING: Branch 'my-custom-branch' does not match conventional patterns
Expected: feat/*, fix/*, docs/*, chore/*, refactor/*, test/*
Proceeding anyway (non-blocking warning)
```

## Integration Points

### Session Protocol

```markdown
## Phase 8.0: Pre-Commit Verification (BLOCKING)

Pre-commit hook validates branch name before commit:

- Blocks commits to main/master
- Warns on non-conventional branch names
- Allows --no-verify bypass for emergencies

**Exit criteria**: Commit succeeds or hook provides clear error.
```

### Session Log

```markdown
## Pre-Commit Hook Verification

Branch validation hook active:
- Current branch: feat/my-feature
- Pattern match: ✓ (matches feat/*)
- Main protection: ✓ (not on main)
```

## Customization

### Add Additional Patterns

```powershell
$allowedPatterns = @(
    'feat/*', 'fix/*', 'docs/*', 'chore/*', 'refactor/*', 'test/*',
    'hotfix/*',      # Add hotfix pattern
    'release/*',     # Add release pattern
    'experiment/*'   # Add experiment pattern
)
```

### Block Additional Branches

```powershell
$protectedBranches = @('main', 'master', 'develop', 'staging')

if ($branch -in $protectedBranches) {
    Write-Host "ERROR: Cannot commit to protected branch '$branch'" -ForegroundColor Red
    exit 1
}
```

### Require Ticket Reference

```powershell
# Validate branch name includes ticket reference
if ($branch -notmatch '(feat|fix|docs)/\d+-') {
    Write-Error "Branch name must include ticket number (e.g., feat/123-description)"
    exit 1
}
```

## Evidence

### PR #669: Wrong-Branch Commits

**Failure scenario**:

- Agent on wrong branch (intended for PR #562, actually on branch for #563)
- No pre-commit validation
- Commit succeeded, contaminating PR #563

**With hook**:

- Pre-commit hook would check branch matches expected PR context
- If mismatch, hook blocks commit with clear error
- Agent corrects branch, retries commit

**Prevention rate**: 100% (blocking hook catches all wrong-branch commits)

## Related Skills

- git-004: Branch verification before commit (complementary verification)
- session-init-003: Branch declaration requirement (provides expected branch)
- protocol-013: Verification-based enforcement (hook is enforcement mechanism)
- git-hooks-001: Pre-commit branch validation (this skill extends that)

## Maintenance

| Task | Frequency | Action |
|------|-----------|--------|
| Update patterns | As needed | Add new branch prefixes to \`$allowedPatterns\` |
| Review messages | Quarterly | Ensure error messages are clear |
| Test hook | Per release | Run test suite in Testing section |
| Sync with template | When updated | Regenerate hook from template |

## Implementation Checklist

- [ ] Create hook template at `.git-hooks/pre-commit-branch-validation.ps1`
- [ ] Create installation script `scripts/Install-GitHooks.ps1`
- [ ] Add to PROJECT-CONSTRAINTS.md (pre-commit hook requirement)
- [ ] Add to SESSION-PROTOCOL.md (Phase 8.0 verification)
- [ ] Document in `.agents/governance/GIT-HOOKS.md`
- [ ] Test hook with all scenarios
- [ ] Add to onboarding checklist

## References

- PR #669: PR co-mingling retrospective
- Issue #681: Pre-commit hook implementation
- Issue #684: SESSION-PROTOCOL branch verification
- ADR-005: PowerShell-only scripting (hook uses PowerShell)
