# Pester Testing Skills

**Extracted**: 2025-12-15
**Source**: ai-agents install scripts session - Pester test infrastructure

## Skill-Test-Pester-001: Discovery Phase Pattern

**Statement**: Pester 5.x evaluates code outside BeforeAll during Discovery; use BeforeAll for all variable initialization

**Context**: When writing Pester 5.x tests with shared variables

**Evidence**: 42 test failures in ai-agents until variables moved to BeforeAll

**Atomicity**: 96%

**Problem**:

```powershell
# WRONG - Variables assigned during Discovery phase
Describe "Test" {
    $Script:TestDir = Join-Path $env:TEMP "test"  # Evaluated during Discovery!
    
    It "should work" {
        Test-Path $Script:TestDir | Should -Be $true
    }
}
```

**Solution**:

```powershell
# CORRECT - Variables assigned in BeforeAll
Describe "Test" {
    BeforeAll {
        $Script:TestDir = Join-Path $env:TEMP "test-$(Get-Random)"
        New-Item -ItemType Directory -Path $Script:TestDir -Force | Out-Null
    }
    
    AfterAll {
        Remove-Item -Path $Script:TestDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    
    It "should work" {
        Test-Path $Script:TestDir | Should -Be $true
    }
}
```

---

## Skill-Test-Pester-002: -ForEach Migration Pattern

**Statement**: Replace foreach loops with -ForEach parameter on It blocks for Pester 5.x parameterized tests

**Context**: When migrating from Pester 4.x or using parameterized tests

**Evidence**: Tests using -ForEach @(...) { $_.Param } pattern succeeded

**Atomicity**: 94%

**Problem**:

```powershell
# WRONG - Traditional foreach not compatible with Pester 5.x
Describe "Config" {
    $environments = @("Claude", "Copilot", "VSCode")
    
    foreach ($env in $environments) {
        It "should have $env config" {
            $config[$env] | Should -Not -BeNullOrEmpty
        }
    }
}
```

**Solution**:

```powershell
# CORRECT - Use -ForEach parameter
Describe "Config" {
    It "should have <Env> config" -ForEach @(
        @{ Env = "Claude" }
        @{ Env = "Copilot" }
        @{ Env = "VSCode" }
    ) {
        $config[$Env] | Should -Not -BeNullOrEmpty
    }
}
```

---

## Skill-Test-Pester-003: Cross-Platform Path Assertions

**Statement**: Use regex with alternation ([\\/]) for path assertions in cross-platform PowerShell tests

**Context**: When tests need to work on both Windows and Unix

**Evidence**: Path separator mismatches resolved with flexible regex

**Atomicity**: 90%

**Problem**:

```powershell
# WRONG - Hardcoded path separator
It "should resolve path" {
    $result | Should -Be "C:\MyRepo\.github\agents"  # Fails on Unix
}
```

**Solution**:

```powershell
# CORRECT - Flexible path matching
It "should resolve path" {
    # Option 1: Use -Match with flexible separator
    $result | Should -Match "MyRepo[\\/]\.github[\\/]agents"
    
    # Option 2: Normalize before comparison
    $normalizedResult = $result -replace '[/\\]', [IO.Path]::DirectorySeparatorChar
    $normalizedExpected = "MyRepo/.github/agents" -replace '[/\\]', [IO.Path]::DirectorySeparatorChar
    $normalizedResult | Should -Match [regex]::Escape($normalizedExpected)
}
```

---

## Related Files

- Test Files: `scripts/tests/*.Tests.ps1`
- Test Runner: `build/scripts/Invoke-PesterTests.ps1`
- CI Workflow: `.github/workflows/pester-tests.yml`
- Retrospective: `.agents/retrospective/2025-12-15-install-scripts-session.md`
