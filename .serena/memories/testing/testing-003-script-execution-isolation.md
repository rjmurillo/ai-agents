# Skill-Testing-003: Script Execution Isolation in Pester Tests

**Statement**: When testing PowerShell scripts with main execution logic, extract only function definitions using regex to prevent script execution during test setup

**Context**: Writing Pester tests for PowerShell scripts (.ps1 files) that contain both function definitions and main execution logic

**Evidence**: Session 68 (2025-12-22): Generate-Skills.Tests.ps1 (script deleted in commit d7f2e08, replaced by validate-skill.py)
- Dot-sourcing (`. "$PSScriptRoot/../Generate-Skills.ps1"`) executed the main script logic
- Script looked for SKILL.md files and started processing during test setup
- Fix: Used regex to extract only function definitions before `# Main` comment
- Pattern: `$scriptContent -replace '(?s)# Main.*', ''`
- Result: Functions loaded without executing main logic

**Atomicity**: 93%

**Tag**: helpful (testing pattern)

**Impact**: 9/10 (prevents test pollution and unexpected side effects)

**Created**: 2025-12-22

**Validated**: 1 (Session 68)

**Pattern**:

```powershell
BeforeAll {
    # Read the script content
    $scriptContent = Get-Content "$PSScriptRoot/../YourScript.ps1" -Raw

    # Extract only function definitions (before "# Main" comment)
    $functionContent = $scriptContent -replace '(?s)# Main.*', ''

    # Execute only the function definitions
    Invoke-Expression $functionContent

    # Now functions are available for testing without executing main logic
}
```

**Alternative approaches**:

1. **Module extraction** (better for production):
   - Move functions to a .psm1 module
   - Script becomes thin wrapper calling module functions
   - Tests import module directly
   - Follows ADR-006 (Thin Workflows, Testable Modules)

2. **Guard clause** (quick fix):
   ```powershell
   # At top of script
   if ($PSCommandPath -and -not $PSScriptRoot) {
       # Running in test context, skip main execution
       return
   }
   ```

3. **Separate files** (cleanest):
   - Functions.psm1 (pure functions)
   - YourScript.ps1 (imports module, calls main function)
   - Tests import Functions.psm1

**When to use regex extraction**:
- Quick testing of existing scripts
- Legacy scripts not yet refactored to modules
- Scripts with clear "# Main" or similar comment delimiter

**When NOT to use**:
- New scripts (write as modules from start per ADR-006)
- Scripts without clear function/main separation
- Production code (prefer module extraction)

**Related**:
- ADR-006: Thin Workflows, Testable Modules
- pester-test-isolation-pattern
- skill-testing-002-test-first-development

**Anti-Pattern**: Dot-sourcing entire script files with main execution logic in Pester BeforeAll

## Related

- [testing-002-test-first-development](testing-002-test-first-development.md)
- [testing-004-coverage-pragmatism](testing-004-coverage-pragmatism.md)
- [testing-007-contract-testing](testing-007-contract-testing.md)
- [testing-008-entry-point-isolation](testing-008-entry-point-isolation.md)
- [testing-coverage-philosophy-integration](testing-coverage-philosophy-integration.md)
