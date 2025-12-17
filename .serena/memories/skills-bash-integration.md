# Skills: Bash Integration Patterns

## Overview

Atomic skills for bash script development and cross-language integration, extracted from PR #52 retrospective.

---

## Skill-Bash-Pattern-001: Pattern Discovery Protocol

**Statement**: Search file for 'AUTOFIX' before adding AUTO-FIX hook sections

**Context**: When extending `.githooks/pre-commit` with new AUTO-FIX behavior

**Evidence**: PR #52 Bug 1 - Added MCP sync without checking existing pattern at line 131

**Atomicity**: 95%

**Tags**: pre-commit, pattern-discovery, consistency

### Prevention Pattern

```bash
# Before adding new AUTO-FIX section:
# 1. Search for existing patterns
grep -n "AUTOFIX" .githooks/pre-commit

# 2. Review existing patterns and follow same structure
# 3. Wrap new section in AUTOFIX check

# ✅ Correct pattern
if [ "$AUTOFIX" = "1" ]; then
    # Auto-fix code here
fi
```

### Trigger: Pattern Discovery

- Adding new sections to bash scripts
- Implementing AUTO-FIX behavior in pre-commit hooks
- Extending existing validation scripts

---

## Skill-PowerShell-ExitCode-001: Script Scope Return Semantics

**Statement**: In PowerShell script scope use `exit` not `return`; `return` exits with code 0

**Context**: When PowerShell script is invoked from bash and exit codes matter

**Evidence**: PR #52 Bug 2 - Lines 88, 95, 105, 111 used `return $false` which exits code 0

**Atomicity**: 92%

**Tags**: exit-codes, bash-integration, cross-language

### Antipattern (DO NOT USE)

```powershell
# ❌ WRONG - return exits script with code 0, exit 1 is unreachable
if (-not (Test-Path $SourcePath)) {
    Write-Error "Source not found"
    if ($PassThru) { return $false }  # Exits with code 0!
    exit 1  # Never reached
}
```

### Correct Pattern

```powershell
# ✅ CORRECT - exit directly with explicit code
if (-not (Test-Path $SourcePath)) {
    Write-Error "Source not found"
    exit 1  # Always exits with explicit code
}
```

### Key Insight

- `return` in **function scope**: Returns value to caller, function exits
- `return` in **script scope**: Entire script exits with code 0 (regardless of value)
- `exit N` in **script scope**: Script exits with code N

### Trigger: PowerShell Exit Codes

- Writing PowerShell scripts that will be called from bash
- Implementing error handling in .ps1 files (not functions/modules)
- Any script where exit codes are checked by the caller

---

## Skill-Testing-Integration-001: Exit Code Contract Testing

**Statement**: Test PowerShell script exit codes with `$LASTEXITCODE` assertions when called from bash

**Context**: When writing Pester tests for PowerShell scripts invoked from bash hooks

**Evidence**: PR #52 Bug 2 - Exit code 0 vs non-zero not tested, allowing bug to pass

**Atomicity**: 90%

**Tags**: pester, exit-codes, integration-testing

### Test Pattern

```powershell
Describe "Exit Codes" {
    It "Returns non-zero on source not found" {
        # Use & operator to invoke script
        & $scriptPath -SourcePath "nonexistent.json" 2>&1 | Out-Null
        $LASTEXITCODE | Should -Not -Be 0
    }
    
    It "Returns non-zero on invalid JSON" {
        & $scriptPath -SourcePath $invalidJsonPath 2>&1 | Out-Null
        $LASTEXITCODE | Should -Not -Be 0
    }
    
    It "Returns 0 on success" {
        & $scriptPath -SourcePath $validSourcePath
        $LASTEXITCODE | Should -Be 0
    }
}
```

### Key Points

- Use `&` operator (call operator) to invoke scripts for proper exit code capture
- Redirect stderr with `2>&1 | Out-Null` to suppress error output in tests
- Test BOTH success (0) and failure (non-zero) paths
- Add to every PowerShell script that will be called from bash

### Trigger: Integration Testing

- Writing Pester tests for .ps1 scripts
- Scripts called from bash hooks
- Any cross-language integration point

---

## Skill-Integration-Contract-001: Cross-Language Exit Code Contract

**Statement**: Document bash-PowerShell exit code contract: 0 is success, non-zero failure

**Context**: When PowerShell script is designed to be called from bash

**Evidence**: PR #52 Bug 2 - Integration contract was implicit, caused silent failure masking

**Atomicity**: 88%

**Tags**: documentation, exit-codes, contracts

### Documentation Template

```powershell
<#
.NOTES
    EXIT CODES (Bash Integration Contract):
    0  - Success: Operation completed successfully
    1  - Error: Source file not found
    1  - Error: Invalid JSON in source
    1  - Error: Missing required key
    1  - Error: Security violation (symlink detected)
    
    When called from bash:
    - Exit code 0 = success (bash `$?` equals 0)
    - Exit code non-zero = failure (bash `$?` non-zero)
#>
```

### Bash Caller Pattern

```bash
# Check exit code after calling PowerShell
if pwsh -NoProfile -File "$SCRIPT" -PassThru 2>&1; then
    echo "Script succeeded"
else
    echo "Script failed with exit code $?"
fi
```

### Trigger: Contract Documentation

- Designing PowerShell scripts for bash consumption
- Documenting integration contracts
- Code review of cross-language boundaries

---

## Skill-Process-PreCommit-001: AUTO-FIX Section Checklist

**Statement**: Wrap AUTO-FIX sections in `if [ "$AUTOFIX" = "1" ]` check

**Context**: When adding new auto-fix functionality to pre-commit hooks

**Evidence**: PR #52 Bug 1 - MCP sync violated SKIP_AUTOFIX contract

**Atomicity**: 94%

**Tags**: pre-commit, autofix, consistency

### Checklist Before Adding AUTO-FIX Section

- [ ] Search for "AUTOFIX" in file: `grep -n "AUTOFIX" .githooks/pre-commit`
- [ ] Review existing AUTO-FIX patterns in the file
- [ ] Wrap new section in `if [ "$AUTOFIX" = "1" ]` check
- [ ] Add "skipped (auto-fix disabled)" message for SKIP_AUTOFIX case
- [ ] Verify exit code contract with any called scripts
- [ ] Test with `SKIP_AUTOFIX=1` to verify check-only mode

### Pattern

```bash
if [ -n "$STAGED_FILES_NEEDING_FIX" ]; then
    if [ "$AUTOFIX" = "1" ]; then
        echo "Auto-fixing files..."
        # Auto-fix logic here
    else
        echo "Auto-fix skipped (SKIP_AUTOFIX=1)."
    fi
fi
```

---

## Related Resources

- `.agents/retrospective/2025-12-17-PR52-cursor-bot-bugs.md` - Full retrospective
- `.serena/memories/pr-52-retrospective-learnings.md` - Self-contained retrospective
- `.serena/memories/git-hook-patterns.md` - Git hook patterns

## Success Metrics

- Pre-submission bug detection: Target >80%
- Bash pattern consistency: Zero violations in next 3 PRs
- Exit code testing: 100% coverage for bash-invoked scripts
- Documentation: All bash-PowerShell boundaries have explicit exit code contracts

---

*Last updated: 2025-12-17*
*Source: PR #52 Retrospective*
