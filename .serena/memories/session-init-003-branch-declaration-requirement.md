# Skill: session-init-003 - Branch Declaration Requirement

**Atomicity**: 82%
**Category**: Session initialization, awareness
**Source**: PR #669 PR co-mingling retrospective

## Pattern

Require explicit branch declaration in session log header to improve agent awareness and enable verification.

## Problem

Without branch declaration:

- Agent unaware of current branch context
- No audit trail of branch usage
- Cannot verify branch hasn't changed mid-session
- Handoffs lack branch information

**Evidence**: PR #669 - Sessions lacked branch context, leading to wrong-branch commits

## Solution

**Mandatory branch field** in session log header:

```markdown
# Session NNN: [Title]

**Date**: YYYY-MM-DD
**Agent**: [agent-name]
**Branch**: [REQUIRED - output of 'git branch --show-current']
**PR**: #NNN (if applicable)

## Objective
[...]
```

### Session Initialization

```powershell
# During session start (Phase 1)
$branch = git branch --show-current
$sessionLog = ".agents/sessions/$(Get-Date -Format 'yyyy-MM-dd')-session-$NN.md"

# Populate template with branch
$content = @"
# Session $NN: [Title]

**Date**: $(Get-Date -Format 'yyyy-MM-dd')
**Agent**: [agent-name]
**Branch**: $branch
**PR**: #[if applicable]

## Objective
[...]
"@

Set-Content $sessionLog $content
```

## Benefits

| Benefit | Impact |
|---------|--------|
| Branch awareness | Agent knows current context |
| Audit trail | Branch usage documented in session log |
| Verification enabled | Can check branch hasn't changed |
| Handoff context | Next session knows expected branch |
| Protocol enforcement | Validate-SessionEnd can verify field |

## Implementation

### Session Protocol (Phase 1)

```markdown
## Phase 1.0: Branch Verification (BLOCKING)

Before ANY other action, verify and declare the current branch:

```bash
# REQUIRED: Verify current branch
git branch --show-current

# REQUIRED: Declare in session log
```

Document in session log header:
**Branch**: [output from git branch --show-current]

**Exit criteria**: Branch name documented in session log header.

```

### Validate-SessionEnd.ps1

```powershell
function Test-BranchDeclaration {
    param([string]$SessionLogPath)
    
    $log = Get-Content $SessionLogPath -Raw
    
    # Check for branch declaration
    if ($log -notmatch '\*\*Branch\*\*:\s+(.+)') {
        Write-Error "Session log missing required branch declaration"
        return $false
    }
    
    $declaredBranch = $Matches[1].Trim()
    $currentBranch = git branch --show-current
    
    # Warn if branch changed during session
    if ($declaredBranch -ne $currentBranch) {
        Write-Warning "Branch changed during session: declared=$declaredBranch, current=$currentBranch"
        
        # Check if change was documented
        if ($log -notmatch "Branch switch.*$currentBranch") {
            Write-Error "Undocumented branch switch detected"
            return $false
        }
    }
    
    return $true
}
```

### Template

Create/update: `.agents/templates/session-log.md`

```markdown
# Session {N}: {Title}

**Date**: {YYYY-MM-DD}
**Agent**: {agent-name}
**Branch**: {REQUIRED - git branch --show-current}
**PR**: #{number} (if applicable)

## Objective

{Description of work scope}

## Session Context

[Context from previous sessions, if any]

## Actions

[Session work log]

## Outcomes

[Results, commits, decisions]
```

## Validation

### At Session Start

```powershell
# Verify branch declaration exists
$log = Get-Content $sessionLog -Raw
if ($log -notmatch '\*\*Branch\*\*:') {
    throw "Session log missing branch declaration"
}
```

### At Session End

```powershell
# Validate-SessionEnd.ps1
$errors = @()

# Check branch declaration
if ($sessionLog -notmatch '\*\*Branch\*\*:\s+(.+)') {
    $errors += "Missing branch declaration"
}

# Check branch consistency
$declaredBranch = $Matches[1].Trim()
$currentBranch = git branch --show-current
if ($declaredBranch -ne $currentBranch) {
    # Warn but don't fail (branch switch may be intentional)
    Write-Warning "Branch mismatch: declared=$declaredBranch, current=$currentBranch"
}

return $errors.Count -eq 0
```

## Evidence

### PR #669: Missing Branch Context

**Failure mode**:

- Session logs had no branch declaration
- Agent switched between branches for different PRs
- No audit trail of which branch was used when
- Remediation couldn't determine intent from logs

**Outcome**:

- 4 PRs with cross-contamination
- Manual review of all commits required
- ~3 hours remediation time

**Lesson**: Branch declaration provides audit trail for remediation and prevents confusion

## Related Skills

- git-004: Branch verification before commit (uses this field)
- protocol-013: Verification-based enforcement (this is an example)
- session-scope-002: Limit sessions to 2 issues (reduces branch switching)
- protocol-012: Branch handoffs (relies on this field)

## Testing

```powershell
# Test 1: Session log with branch declaration
$log = @"
# Session 110

**Branch**: feat/test-branch
"@
# Should pass validation

# Test 2: Session log without branch declaration
$log = @"
# Session 110

**Date**: 2025-12-30
"@
# Should fail validation

# Test 3: Branch switch during session
$log = @"
# Session 110

**Branch**: feat/original

## Actions

Branch switch: feat/original -> feat/other (for dependency work)
"@
# Should pass (documented switch)

# Test 4: Undocumented branch switch
git checkout -b feat/original
# Session log declares feat/original
git checkout feat/other
# Validate-SessionEnd runs
# Should warn about mismatch, fail if undocumented
```

## Implementation Checklist

- [ ] Create/update session log template with branch field
- [ ] Add Phase 1.0 to SESSION-PROTOCOL (branch declaration)
- [ ] Add Test-BranchDeclaration to Validate-SessionEnd.ps1
- [ ] Update agent prompts to populate branch field
- [ ] Document in AGENT-INSTRUCTIONS.md

## References

- PR #669: PR co-mingling retrospective
- Issue #684: SESSION-PROTOCOL branch verification
- Issue #685: Session log template update
- ADR-XXX: Session log requirements (to be created)
