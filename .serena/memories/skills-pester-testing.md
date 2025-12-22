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

## Skill-Test-Pester-004: BeforeEach Cleanup for Test Isolation

**Statement**: Every Pester Context block creating files needs BeforeEach cleanup to prevent test pollution

**Context**: When writing file-based Pester tests with multiple It blocks

**Evidence**: PR #47 - Pattern Detection context missing BeforeEach caused cross-test file accumulation; cursor[bot] detected bug

**Atomicity**: 96%

**Tag**: helpful

**Impact**: 9/10

**Problem**:

```powershell
# WRONG - Missing BeforeEach causes test pollution
Context "Pattern Tests" {
    # No BeforeEach cleanup!
    
    It "Test 1" {
        Set-Content -Path "$TestDir\file1.md" -Value "..."
    }
    
    It "Test 2" {
        Set-Content -Path "$TestDir\file2.md" -Value "..."
        # This test now sees file1.md from Test 1!
        (Get-ChildItem $TestDir).Count | Should -Be 1  # FAILS - sees 2 files
    }
}
```

**Solution**:

```powershell
# CORRECT - BeforeEach cleanup ensures isolation
Context "Pattern Tests" {
    BeforeEach {
        # Clean test directory before EACH test
        Get-ChildItem -Path $TestDir -Recurse | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
    }
    
    It "Test 1" {
        Set-Content -Path "$TestDir\file1.md" -Value "..."
        (Get-ChildItem $TestDir).Count | Should -Be 1  # PASSES
    }
    
    It "Test 2" {
        Set-Content -Path "$TestDir\file2.md" -Value "..."
        (Get-ChildItem $TestDir).Count | Should -Be 1  # PASSES - isolated
    }
}
```

**Validation**: 1 (PR #47)

---

## Skill-Test-Pester-005: Test-First Development (95%)

**Statement**: Create Pester tests during implementation (not after) to validate correctness before commit, achieving 100% pass rates

**Context**: During implementation phase for PowerShell scripts/modules

**Evidence**: Session 21 created 13 tests alongside Check-SkillExists.ps1 → 100% pass rate on first run → high confidence before commit

**Atomicity**: 95%

- Single concept (test-first timing) ✓
- Specific approach (during, not after) ✓
- Actionable (write tests alongside code) ✓
- Measurable (100% pass rate) ✓
- Length: 16 words (-5%)

**Tag**: helpful

**Impact**: 8/10 - Validates implementation correctness during development

**Pattern**: Write test → Write code → Run test → Refactor → Commit (all tests passing)

**Evidence Details**:

- 13 Pester tests created alongside implementation
- All operations tested: pr, issue, reactions, label, milestone
- Parameters tested: -Operation, -Action, -ListAvailable
- 100% pass rate on first run (13/13 passed, 0 failed)

**Anti-Pattern**: Writing tests after implementation claims completion

**Validation**: 1 (Session 21: Check-SkillExists.ps1)

**Created**: 2025-12-18

---

## Skill-Test-Pester-006: Static Analysis Tests for PowerShell Scripts

**Statement**: Use regex-based Pester tests to validate PowerShell script structure (syntax, parameters, API patterns, outputs) without making API calls

**Context**: When testing PowerShell scripts that interact with external APIs where live API testing is slow or impractical

**Evidence**: PR #235 - 49 Pester tests validate Get-PRReviewComments.ps1 structure in 1.4s without GitHub API calls, catching regressions early

**Atomicity**: 96%

**Tag**: helpful (fast testing)

**Impact**: 9/10 (enables CI validation)

**Created**: 2025-12-22

**Problem**:

```powershell
# WRONG - Tests require live API calls (slow, flaky, rate-limited)
Describe "Get-PRReviewComments" {
    It "should fetch comments" {
        $result = Get-PRReviewComments -PullRequest 123 -Owner "org" -Repo "repo"
        $result.Count | Should -BeGreaterThan 0  # Requires live GitHub API
    }
}
# Problems: Slow (network latency), flaky (rate limits), requires auth
```

**Solution**:

```powershell
# CORRECT - Static analysis validates structure without API calls
Describe "Get-PRReviewComments.ps1 - Static Analysis" {
    BeforeAll {
        $ScriptPath = "$PSScriptRoot/../Get-PRReviewComments.ps1"
        $ScriptContent = Get-Content $ScriptPath -Raw
    }
    
    Context "Syntax Validation" {
        It "should have valid PowerShell syntax" {
            $errors = $null
            [System.Management.Automation.PSParser]::Tokenize($ScriptContent, [ref]$errors)
            $errors.Count | Should -Be 0
        }
    }
    
    Context "Parameter Declarations" {
        It "should have mandatory -PullRequest parameter" {
            $ScriptContent | Should -Match 'param\s*\([^)]*\[Parameter\(Mandatory\)\][^)]*\$PullRequest'
        }
        
        It "should have optional -IncludeIssueComments switch" {
            $ScriptContent | Should -Match '\[switch\]\$IncludeIssueComments'
        }
    }
    
    Context "API Endpoint Patterns" {
        It "should call review comments endpoint" {
            $ScriptContent | Should -Match 'repos/\$Owner/\$Repo/pulls/\$PullRequest/comments'
        }
        
        It "should conditionally call issue comments endpoint" {
            $ScriptContent | Should -Match 'if\s*\(\$IncludeIssueComments\)'
            $ScriptContent | Should -Match 'repos/\$Owner/\$Repo/issues/\$PullRequest/comments'
        }
    }
    
    Context "Output Structure" {
        It "should add CommentType discriminator field" {
            $ScriptContent | Should -Match 'Add-Member.*CommentType.*Review'
            $ScriptContent | Should -Match 'Add-Member.*CommentType.*Issue'
        }
    }
    
    Context "Help Documentation" {
        It "should have synopsis" {
            $ScriptContent | Should -Match '\.SYNOPSIS'
        }
        
        It "should document -IncludeIssueComments parameter" {
            $ScriptContent | Should -Match '\.PARAMETER\s+IncludeIssueComments'
        }
    }
}
```

**Why It Matters**:

Static analysis tests provide:
- **Speed** - Complete in seconds (49 tests in 1.4s vs minutes for live API)
- **Reliability** - No network dependency, rate limits, or auth issues
- **Early detection** - Catch structural regressions in CI before deployment
- **Comprehensive coverage** - Validate all code paths without complex mocking

**What to Test**:

| Category | Pattern | Example Regex |
|----------|---------|---------------|
| **Syntax** | Valid PowerShell | `PSParser::Tokenize` with zero errors |
| **Parameters** | Declarations | `\[Parameter\(Mandatory\)\].*\$ParamName` |
| **API Calls** | Endpoint patterns | `gh api repos/.*/pulls/` |
| **Conditionals** | Feature flags | `if\s*\(\$SwitchParam\)` |
| **Output** | Field additions | `Add-Member.*FieldName.*Value` |
| **Documentation** | Help blocks | `\.SYNOPSIS`, `\.PARAMETER` |

**Pattern**:

```powershell
# General static analysis test template
Describe "Script.ps1 - Static Analysis" {
    BeforeAll {
        $ScriptContent = Get-Content $PSScriptRoot/../Script.ps1 -Raw
    }
    
    It "should have valid syntax" {
        $errors = $null
        [System.Management.Automation.PSParser]::Tokenize($ScriptContent, [ref]$errors)
        $errors.Count | Should -Be 0
    }
    
    It "should declare expected parameters" {
        $ScriptContent | Should -Match '\$ParamName'
    }
    
    It "should call expected API endpoints" {
        $ScriptContent | Should -Match 'api-endpoint-pattern'
    }
}
```

**Anti-Pattern**:

```powershell
# Over-mocking live API calls (brittle, complex)
Mock Invoke-RestMethod { return @{ id = 1 } }
Mock ConvertFrom-Json { ... }
# Mocking is useful but shouldn't be the ONLY testing approach
```

**Validation**: 1 (PR #235 - 49 tests, 1.4s execution)

---

## Related Files

- Test Files: `scripts/tests/*.Tests.ps1`
- Test Runner: `build/scripts/Invoke-PesterTests.ps1`
- CI Workflow: `.github/workflows/pester-tests.yml`
- Retrospective: `.agents/retrospective/2025-12-15-install-scripts-session.md`
- Retrospective: `.agents/retrospective/2025-12-18-parallel-implementation-retrospective.md`
