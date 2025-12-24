#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Validate-SkillFormat.ps1

.DESCRIPTION
    Tests the skill format validation functionality for ADR-017 atomic format requirements.
    Validates detection of bundled skills (multiple ## Skill-* headers in one file).

.NOTES
    Related: ADR-017, Issue #307
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot ".." "scripts" "Validate-SkillFormat.ps1"

    # Create temp directory for test data
    $testRoot = Join-Path ([System.IO.Path]::GetTempPath()) "validate-skill-format-tests-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
    New-Item -Path $testRoot -ItemType Directory -Force | Out-Null

    # Helper to create test memory structure
    function New-TestMemoryStructure {
        param(
            [string]$BasePath,
            [hashtable]$Structure
        )

        foreach ($file in $Structure.Keys) {
            $filePath = Join-Path $BasePath $file
            $Structure[$file] | Set-Content -Path $filePath -Encoding UTF8
        }
    }

    # Helper to clean up test directory
    function Remove-TestMemoryStructure {
        param([string]$BasePath)
        if (Test-Path $BasePath) {
            Remove-Item -Path $BasePath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    # Helper to run script and capture output as string
    function Invoke-SkillFormatValidation {
        param(
            [string]$Path,
            [switch]$CI,
            [switch]$StagedOnly
        )

        $splatParams = @{}
        if ($Path) { $splatParams['Path'] = $Path }
        if ($CI) { $splatParams['CI'] = $true }
        if ($StagedOnly) { $splatParams['StagedOnly'] = $true }

        $output = & $scriptPath @splatParams *>&1
        # Convert InformationRecord objects to strings
        $output | ForEach-Object { $_.ToString() } | Out-String
    }
}

AfterAll {
    # Clean up test root
    if (Test-Path $testRoot) {
        Remove-Item -Path $testRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe "Validate-SkillFormat" {
    BeforeEach {
        # Create fresh test directory for each test
        $testMemoryPath = Join-Path $testRoot "memories-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
        New-Item -Path $testMemoryPath -ItemType Directory -Force | Out-Null
    }

    AfterEach {
        # Clean up test directory
        if (Test-Path $testMemoryPath) {
            Remove-Item -Path $testMemoryPath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Context "When memory path does not exist" {
        It "Exits gracefully with non-existent path" {
            { & $scriptPath -Path "/non/existent/path" } | Should -Not -Throw
        }

        It "Returns exit code 0 for non-existent path (no files to check)" {
            & $scriptPath -Path "/non/existent/path" 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "When no skill files exist" {
        It "Exits with code 0 when directory is empty" {
            & $scriptPath -Path $testMemoryPath 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 0
        }

        It "Reports no skill files found" {
            $result = Invoke-SkillFormatValidation -Path $testMemoryPath
            $result | Should -Match "No skill files found"
        }
    }

    Context "When only index files exist" {
        BeforeEach {
            $testStructure = @{
                "skills-test-index.md" = @"
| Keywords | File |
|----------|------|
| alpha beta | test-skill |
"@
                "skills-another-index.md" = @"
| Keywords | File |
|----------|------|
| gamma delta | another-skill |
"@
                "memory-index.md" = @"
| Domain | File |
|--------|------|
| test | skills-test-index |
"@
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Skips index files and reports no skill files to validate" {
            $result = Invoke-SkillFormatValidation -Path $testMemoryPath
            $result | Should -Match "No skill files found"
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "When validating atomic format files (PASS cases)" {
        BeforeEach {
            $testStructure = @{
                "test-skill-one.md" = @"
# Skill-Test-001: Test Skill One

**Statement**: This is a test skill statement.

**Context**: Testing context

**Evidence**: Session test evidence

**Atomicity**: 95% | **Impact**: 8/10

## Pattern

Test pattern here.
"@
                "test-skill-two.md" = @"
# Skill-Test-002: Test Skill Two

**Statement**: Another test skill statement.

**Context**: Another testing context

**Evidence**: More test evidence

**Atomicity**: 90% | **Impact**: 7/10

## Pattern

Another test pattern.

## Anti-Pattern

What not to do.
"@
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Passes validation for atomic format files" {
            & $scriptPath -Path $testMemoryPath 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 0
        }

        It "Reports PASSED status" {
            $result = Invoke-SkillFormatValidation -Path $testMemoryPath
            $result | Should -Match "PASSED"
        }
    }

    Context "When validating files with zero skill headers" {
        BeforeEach {
            $testStructure = @{
                "regular-memory.md" = @"
# Regular Memory File

This is not a skill file. It has no skill headers.

## Some Section

Content here.
"@
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Passes validation for files without skill headers" {
            & $scriptPath -Path $testMemoryPath 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "When validating bundled format files (FAIL cases)" {
        BeforeEach {
            $testStructure = @{
                "bundled-skills.md" = @"
# Bundled Skills File

## Skill-Test-001: First Skill

**Statement**: First skill statement.

## Skill-Test-002: Second Skill

**Statement**: Second skill statement.

## Skill-Test-003: Third Skill

**Statement**: Third skill statement.
"@
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Detects bundled format with multiple skill headers" {
            $result = Invoke-SkillFormatValidation -Path $testMemoryPath
            $result | Should -Match "BUNDLED"
        }

        It "Reports the number of skills in bundled file" {
            $result = Invoke-SkillFormatValidation -Path $testMemoryPath
            $result | Should -Match "contains 3 skills"
        }

        It "Returns exit code 0 in non-CI mode (warning only)" {
            Invoke-SkillFormatValidation -Path $testMemoryPath | Out-Null
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "When using -CI flag" {
        BeforeEach {
            $testStructure = @{
                "bundled-skills.md" = @"
# Bundled Skills

## Skill-CI-001: First

Content

## Skill-CI-002: Second

Content
"@
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Returns exit code 1 in CI mode for bundled files" {
            Invoke-SkillFormatValidation -Path $testMemoryPath -CI | Out-Null
            $LASTEXITCODE | Should -Be 1
        }

        It "Reports FAILED status in CI mode" {
            $result = Invoke-SkillFormatValidation -Path $testMemoryPath -CI
            $result | Should -Match "FAILED"
        }
    }

    Context "When using -CI flag with valid files" {
        BeforeEach {
            $testStructure = @{
                "atomic-skill.md" = @"
# Skill-Atomic-001: Single Skill

**Statement**: Just one skill.

**Context**: Test

**Evidence**: Test

**Atomicity**: 100% | **Impact**: 10/10
"@
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Returns exit code 0 in CI mode for valid files" {
            & $scriptPath -Path $testMemoryPath -CI 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "When mixing atomic and bundled files" {
        BeforeEach {
            $testStructure = @{
                "atomic-good.md" = @"
# Skill-Mix-001: Good Skill

**Statement**: Single skill.
"@
                "bundled-bad.md" = @"
# Multiple Skills

## Skill-Mix-002: First

Content

## Skill-Mix-003: Second

Content
"@
                "another-good.md" = @"
# Skill-Mix-004: Another Good

**Statement**: Another single skill.
"@
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Detects the bundled file among atomic files" {
            $result = Invoke-SkillFormatValidation -Path $testMemoryPath
            $result | Should -Match "bundled-bad.md"
        }

        It "Reports only the bundled file, not atomic files" {
            $result = Invoke-SkillFormatValidation -Path $testMemoryPath
            $result | Should -Not -Match "atomic-good.md"
            $result | Should -Not -Match "another-good.md"
        }
    }

    Context "When validating skill header regex patterns" {
        BeforeEach {
            $testStructure = @{
                "edge-case-headers.md" = @"
# Various Header Formats

## Skill-ABC-001: Uppercase Category

Content

## Skill-abc-002: Lowercase Category

Content
"@
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Detects skill headers with uppercase category" {
            $result = Invoke-SkillFormatValidation -Path $testMemoryPath
            $result | Should -Match "2 skills"
        }

        It "Matches skill headers case-insensitively for category" {
            $result = Invoke-SkillFormatValidation -Path $testMemoryPath
            $result | Should -Match "BUNDLED"
        }
    }

    Context "When file contains non-skill headers similar to skill format" {
        BeforeEach {
            $testStructure = @{
                "false-positive-check.md" = @"
# Skill-Test-001: Real Skill

This file has one real skill header.

## Not a skill header

## Skill-like but not matching: Missing number

## Skill-Test: No number at end

### Skill-Test-002: Wrong heading level (###)

Regular content here.
"@
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Only counts headers matching exact pattern (## Skill-[A-Za-z]+-[0-9]+:)" {
            & $scriptPath -Path $testMemoryPath 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 0
        }

        It "Does not flag as bundled when only one valid skill header exists" {
            $result = Invoke-SkillFormatValidation -Path $testMemoryPath
            $result | Should -Not -Match "BUNDLED"
        }
    }

    Context "When file is empty or has no content" {
        BeforeEach {
            $testStructure = @{
                "empty-file.md" = ""
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Handles empty files gracefully" {
            { & $scriptPath -Path $testMemoryPath } | Should -Not -Throw
        }

        It "Does not flag empty files as bundled" {
            $result = Invoke-SkillFormatValidation -Path $testMemoryPath
            $result | Should -Not -Match "BUNDLED"
        }
    }

    Context "When -StagedOnly flag is used" {
        It "Exits with code 0 when no staged files exist" {
            # This test runs in a git repo but with no staged memory files
            & $scriptPath -StagedOnly 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 0
        }

        It "Reports no staged files message" {
            $result = Invoke-SkillFormatValidation -StagedOnly
            $result | Should -Match "No skill files staged|Skipping"
        }
    }

    Context "When -StagedOnly flag is used with staged files" {
        BeforeAll {
            # Create a temporary git repo for testing staged files
            $stagedTestRoot = Join-Path ([System.IO.Path]::GetTempPath()) "staged-test-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
            New-Item -Path $stagedTestRoot -ItemType Directory -Force | Out-Null
            Push-Location $stagedTestRoot

            # Initialize git repo
            git init --quiet 2>&1 | Out-Null
            git config user.email "test@test.com" 2>&1 | Out-Null
            git config user.name "Test" 2>&1 | Out-Null

            # Create .serena/memories structure
            New-Item -Path ".serena/memories" -ItemType Directory -Force | Out-Null
        }

        AfterAll {
            Pop-Location
            if (Test-Path $stagedTestRoot) {
                Remove-Item -Path $stagedTestRoot -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Processes staged bundled skill files and detects issues" {
            # Create a bundled skill file
            $bundledContent = @"
# Multiple Skills

## Skill-Staged-001: First

Content

## Skill-Staged-002: Second

Content
"@
            Set-Content -Path ".serena/memories/staged-bundled.md" -Value $bundledContent

            # Stage the file
            git add ".serena/memories/staged-bundled.md" 2>&1 | Out-Null

            # Run validation on staged files
            $result = & $scriptPath -StagedOnly *>&1 | ForEach-Object { $_.ToString() } | Out-String
            $result | Should -Match "BUNDLED|staged-bundled.md|2 skills"
        }

        It "Processes staged atomic skill files and passes" {
            # Clean staging area and remove previous test files
            git reset HEAD 2>&1 | Out-Null
            Remove-Item -Path ".serena/memories/staged-bundled.md" -Force -ErrorAction SilentlyContinue

            # Create an atomic skill file
            $atomicContent = @"
# Skill-Staged-003: Atomic Skill

**Statement**: This is an atomic skill.

**Context**: Testing context

**Evidence**: Test evidence

**Atomicity**: 100% | **Impact**: 10/10
"@
            Set-Content -Path ".serena/memories/staged-atomic.md" -Value $atomicContent

            # Stage the file
            git add ".serena/memories/staged-atomic.md" 2>&1 | Out-Null

            # Run validation on staged files
            $result = & $scriptPath -StagedOnly *>&1 | ForEach-Object { $_.ToString() } | Out-String
            $result | Should -Match "PASSED"
        }

        It "Ignores index files in staged changes" {
            # Clean staging area and remove previous test files
            git reset HEAD 2>&1 | Out-Null
            Remove-Item -Path ".serena/memories/staged-bundled.md" -Force -ErrorAction SilentlyContinue
            Remove-Item -Path ".serena/memories/staged-atomic.md" -Force -ErrorAction SilentlyContinue

            # Create an index file (should be skipped)
            $indexContent = @"
| Keywords | File |
|----------|------|
| test | test-file |
"@
            Set-Content -Path ".serena/memories/skills-test-index.md" -Value $indexContent

            # Stage the index file
            git add ".serena/memories/skills-test-index.md" 2>&1 | Out-Null

            # Run validation - should report no skill files (index files are skipped)
            $result = & $scriptPath -StagedOnly *>&1 | ForEach-Object { $_.ToString() } | Out-String
            # When index files are staged but filtered out, it reports "No skill files found"
            $result | Should -Match "No skill files"
        }
    }

    Context "When validating output messages" {
        BeforeEach {
            $testStructure = @{
                "multiple-bundled.md" = @"
## Skill-Msg-001: First

Content

## Skill-Msg-002: Second

Content

## Skill-Msg-003: Third

Content

## Skill-Msg-004: Fourth

Content
"@
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Shows ADR-017 reference in error message" {
            $result = Invoke-SkillFormatValidation -Path $testMemoryPath
            $result | Should -Match "ADR-017"
        }

        It "Shows instruction to split bundled skills" {
            $result = Invoke-SkillFormatValidation -Path $testMemoryPath
            $result | Should -Match "Split bundled skills"
        }

        It "Shows exact count of skills in bundled file" {
            $result = Invoke-SkillFormatValidation -Path $testMemoryPath
            $result | Should -Match "4 skills"
        }
    }

    Context "When summary section reports results" {
        BeforeEach {
            $testStructure = @{
                "bundled-one.md" = @"
## Skill-Sum-001: A

Content

## Skill-Sum-002: B

Content
"@
                "bundled-two.md" = @"
## Skill-Sum-003: C

Content

## Skill-Sum-004: D

Content
"@
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Lists all bundled files in summary" {
            $result = Invoke-SkillFormatValidation -Path $testMemoryPath
            $result | Should -Match "bundled-one.md"
            $result | Should -Match "bundled-two.md"
        }

        It "Shows bundled format detected header" {
            $result = Invoke-SkillFormatValidation -Path $testMemoryPath
            $result | Should -Match "Bundled Format Detected"
        }
    }
}
