#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Validate-SkillFormat.ps1

.DESCRIPTION
    Tests the skill format validation functions that implement
    ADR-017 requirements:
    - One skill per file (no bundled skills)
    - Files must NOT use 'skill-' prefix (use {domain}-{description} format)

.NOTES
    Related: ADR-017, Issue #307, Issue #356
#>

BeforeAll {
    $script:ScriptPath = Join-Path $PSScriptRoot ".." "Validate-SkillFormat.ps1"
    $script:TestMemoriesPath = Join-Path $TestDrive ".serena" "memories"

    # Create test directory structure
    New-Item -ItemType Directory -Path $TestMemoriesPath -Force | Out-Null

    # Helper function to run the script and capture all output
    function Invoke-ValidationScript {
        param(
            [string]$Path,
            [switch]$CI,
            [string[]]$ChangedFiles
        )

        $params = @()
        if ($Path) { $params += "-Path", $Path }
        if ($CI) { $params += "-CI" }
        if ($ChangedFiles) { $params += "-ChangedFiles", ($ChangedFiles -join ",") }

        # Run in a new PowerShell process to get proper exit code
        $output = pwsh -NoProfile -Command "& '$script:ScriptPath' $($params -join ' '); exit `$LASTEXITCODE" 2>&1
        $exitCode = $LASTEXITCODE

        return @{
            Output = ($output | Out-String)
            ExitCode = $exitCode
        }
    }
}

Describe "Validate-SkillFormat.ps1" {

    AfterEach {
        # Clean up test files after each test
        Get-ChildItem -Path $TestMemoriesPath -Filter "*.md" -ErrorAction SilentlyContinue | Remove-Item -Force
    }

    Context "Prefix Validation - skill- prefix detection" {

        It "Rejects files starting with 'skill-'" {
            # Arrange: Create a file with invalid 'skill-' prefix
            $invalidFile = Join-Path $TestMemoriesPath "skill-test-example.md"
            Set-Content -Path $invalidFile -Value "# Test Content"

            # Act: Run validation in CI mode
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert: Should exit with code 1 (failure)
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "skill-test-example\.md"
        }

        It "Accepts files with valid domain prefix (pr-NNN-*)" {
            # Arrange: Create a file with valid domain prefix
            $validFile = Join-Path $TestMemoriesPath "pr-001-reviewer-enumeration.md"
            Set-Content -Path $validFile -Value "# Test Content"

            # Act: Run validation in CI mode
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert: Should exit with code 0 (success)
            $result.ExitCode | Should -Be 0
        }

        It "Accepts files with valid domain prefix (qa-NNN-*)" {
            # Arrange
            $validFile = Join-Path $TestMemoriesPath "qa-002-test-coverage.md"
            Set-Content -Path $validFile -Value "# Test Content"

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }

        It "Accepts files with valid domain prefix (security-NNN-*)" {
            # Arrange
            $validFile = Join-Path $TestMemoriesPath "security-003-input-validation.md"
            Set-Content -Path $validFile -Value "# Test Content"

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }

        It "Does not flag files with 'skill' in the middle of the name" {
            # Arrange: 'labeler-skill-training.md' should NOT match '^skill-'
            $validFile = Join-Path $TestMemoriesPath "labeler-skill-training.md"
            Set-Content -Path $validFile -Value "# Test Content"

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert: Should pass (skill is not at the start)
            $result.ExitCode | Should -Be 0
        }

        It "Rejects minimal 'skill-' prefix file" {
            # Arrange: Edge case - minimal valid match
            $invalidFile = Join-Path $TestMemoriesPath "skill-.md"
            Set-Content -Path $invalidFile -Value "# Test Content"

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert
            $result.ExitCode | Should -Be 1
        }

        It "Detects multiple prefix violations" {
            # Arrange: Multiple invalid files
            $invalidFile1 = Join-Path $TestMemoriesPath "skill-test-one.md"
            $invalidFile2 = Join-Path $TestMemoriesPath "skill-test-two.md"
            Set-Content -Path $invalidFile1 -Value "# Test 1"
            Set-Content -Path $invalidFile2 -Value "# Test 2"

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert: Should fail and report both violations
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "skill-test-one\.md"
            $result.Output | Should -Match "skill-test-two\.md"
        }
    }

    Context "Index File Exclusion" {

        It "Excludes skills-*-index.md files from validation" {
            # Arrange: Index files should be skipped entirely
            $indexFile = Join-Path $TestMemoriesPath "skills-labeler-index.md"
            Set-Content -Path $indexFile -Value "# Labeler Skills Index"

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert: Should pass (index files are excluded)
            $result.ExitCode | Should -Be 0
        }

        It "Excludes memory-index.md from validation" {
            # Arrange
            $indexFile = Join-Path $TestMemoriesPath "memory-index.md"
            Set-Content -Path $indexFile -Value "# Memory Index"

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }

        It "Validates non-index files while excluding index files" {
            # Arrange: Mix of index and regular files
            $indexFile = Join-Path $TestMemoriesPath "skills-security-index.md"
            $validFile = Join-Path $TestMemoriesPath "security-001-threat-model.md"
            Set-Content -Path $indexFile -Value "# Security Skills Index"
            Set-Content -Path $validFile -Value "# Threat Model"

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert: Should pass
            $result.ExitCode | Should -Be 0
        }
    }

    Context "CI vs Local Mode Behavior" {

        It "Exits with code 1 in CI mode when violations found" {
            # Arrange
            $invalidFile = Join-Path $TestMemoriesPath "skill-ci-test.md"
            Set-Content -Path $invalidFile -Value "# Test"

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert
            $result.ExitCode | Should -Be 1
        }

        It "Exits with code 0 in local mode when violations found (non-blocking)" {
            # Arrange
            $invalidFile = Join-Path $TestMemoriesPath "skill-local-test.md"
            Set-Content -Path $invalidFile -Value "# Test"

            # Act: Run WITHOUT -CI flag
            $result = Invoke-ValidationScript -Path $TestMemoriesPath

            # Assert: Local mode is non-blocking
            $result.ExitCode | Should -Be 0
        }

        It "Outputs warning in local mode" {
            # Arrange
            $invalidFile = Join-Path $TestMemoriesPath "skill-warning-test.md"
            Set-Content -Path $invalidFile -Value "# Test"

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath

            # Assert: Should show warning about non-blocking
            $result.Output | Should -Match "WARNING"
        }
    }

    Context "Bundled Format Detection" {

        It "Detects bundled skills (multiple ## Skill-* headers)" {
            # Arrange: File with multiple skill headers
            $bundledFile = Join-Path $TestMemoriesPath "bundled-skills.md"
            $bundledContent = @"
# Skills Bundle

## Skill-QA-001: First Skill

Content for first skill.

## Skill-QA-002: Second Skill

Content for second skill.
"@
            Set-Content -Path $bundledFile -Value $bundledContent

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "BUNDLED"
            $result.Output | Should -Match "2 skills"
        }

        It "Accepts single skill per file" {
            # Arrange: File with single skill header
            $singleFile = Join-Path $TestMemoriesPath "single-skill.md"
            $singleContent = @"
# Single Skill

## Skill-QA-001: Only One Skill

Content for the skill.
"@
            Set-Content -Path $singleFile -Value $singleContent

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }

        It "Accepts files without skill headers" {
            # Arrange: Regular memory file without skill headers
            $regularFile = Join-Path $TestMemoriesPath "regular-memory.md"
            Set-Content -Path $regularFile -Value "# Regular Memory`n`nSome content here."

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }
    }

    Context "Empty and Missing File Handling" {

        It "Handles empty directory gracefully" {
            # Arrange: Empty memories directory (cleared in AfterEach)
            # No files to create

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert: Should pass with message about no files
            $result.ExitCode | Should -Be 0
            $result.Output | Should -Match "No skill files found"
        }

        It "Handles empty file content gracefully" {
            # Arrange: Create empty file
            $emptyFile = Join-Path $TestMemoriesPath "empty-file.md"
            Set-Content -Path $emptyFile -Value ""

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert: Should pass (empty files have no violations)
            $result.ExitCode | Should -Be 0
        }
    }

    Context "Case Sensitivity" {

        It "Rejects Skill- prefix (PowerShell -match is case-insensitive)" {
            # Arrange: PowerShell's -match operator is case-insensitive by default
            $upperFile = Join-Path $TestMemoriesPath "Skill-uppercase.md"
            Set-Content -Path $upperFile -Value "# Test"

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert: Should match (PowerShell -match is case-insensitive)
            $result.ExitCode | Should -Be 1
        }

        It "Rejects SKILL- prefix (all caps)" {
            # Arrange
            $allCapsFile = Join-Path $TestMemoriesPath "SKILL-allcaps.md"
            Set-Content -Path $allCapsFile -Value "# Test"

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert: PowerShell -match is case-insensitive
            $result.ExitCode | Should -Be 1
        }
    }
}

Describe "Validate-SkillFormat.ps1 - ChangedFiles Parameter" {

    AfterEach {
        Get-ChildItem -Path $TestMemoriesPath -Filter "*.md" -ErrorAction SilentlyContinue | Remove-Item -Force
    }

    Context "CI Workflow Integration" {

        It "Processes only files specified in ChangedFiles array" {
            # Arrange: Create both valid and invalid files, but only pass valid to ChangedFiles
            $validFile = Join-Path $TestMemoriesPath "pr-001-valid.md"
            $invalidFile = Join-Path $TestMemoriesPath "skill-would-fail.md"
            Set-Content -Path $validFile -Value "# Valid"
            Set-Content -Path $invalidFile -Value "# Invalid"

            # Act: Run from TestDrive so relative paths resolve correctly
            $testDriveRoot = Split-Path (Split-Path $TestMemoriesPath -Parent) -Parent
            $output = pwsh -NoProfile -Command "Push-Location '$testDriveRoot'; & '$script:ScriptPath' -CI -ChangedFiles '.serena/memories/pr-001-valid.md'; `$code = `$LASTEXITCODE; Pop-Location; exit `$code" 2>&1
            $exitCode = $LASTEXITCODE

            # Assert: Should pass (only valid file checked, invalid file ignored)
            $exitCode | Should -Be 0
        }

        It "Excludes files outside .serena/memories/ directory" {
            # Arrange: Non-memory files should be filtered out
            $changedFiles = @("README.md", "src/test.ps1", ".github/workflows/ci.yml")

            # Act
            $output = pwsh -NoProfile -Command "& '$script:ScriptPath' -CI -ChangedFiles '$($changedFiles -join "','")'; exit `$LASTEXITCODE" 2>&1 | Out-String
            $exitCode = $LASTEXITCODE

            # Assert: Should pass with "No skill files" message
            $exitCode | Should -Be 0
            $output | Should -Match "No skill files in changed files list"
        }

        It "Handles deleted files gracefully (file in list but not on disk)" {
            # Arrange: Reference a file that doesn't exist
            $deletedFilePath = ".serena/memories/deleted-file.md"

            # Act: Script should handle missing files without error
            $output = pwsh -NoProfile -Command "& '$script:ScriptPath' -CI -ChangedFiles '$deletedFilePath'; exit `$LASTEXITCODE" 2>&1 | Out-String
            $exitCode = $LASTEXITCODE

            # Assert: Should pass (deleted files skipped via Get-Item -ErrorAction SilentlyContinue)
            $exitCode | Should -Be 0
        }

        It "Excludes index files from ChangedFiles validation" {
            # Arrange: Create an index file and pass it to ChangedFiles
            $indexFile = Join-Path $TestMemoriesPath "skills-test-index.md"
            Set-Content -Path $indexFile -Value "# Index"

            # Act: Run from TestDrive so relative paths resolve correctly
            $testDriveRoot = Split-Path (Split-Path $TestMemoriesPath -Parent) -Parent
            $output = pwsh -NoProfile -Command "Push-Location '$testDriveRoot'; & '$script:ScriptPath' -CI -ChangedFiles '.serena/memories/skills-test-index.md'; `$code = `$LASTEXITCODE; Pop-Location; exit `$code" 2>&1 | Out-String
            $exitCode = $LASTEXITCODE

            # Assert: Index files should be filtered out
            $exitCode | Should -Be 0
        }

        It "Detects violations in ChangedFiles" {
            # Arrange: Create an invalid file in TestDrive's .serena/memories
            $invalidFile = Join-Path $TestMemoriesPath "skill-invalid.md"
            Set-Content -Path $invalidFile -Value "# Invalid"

            # Act: Run from TestDrive so relative paths resolve correctly
            $testDriveRoot = Split-Path (Split-Path $TestMemoriesPath -Parent) -Parent
            $output = pwsh -NoProfile -Command "Push-Location '$testDriveRoot'; & '$script:ScriptPath' -CI -ChangedFiles '.serena/memories/skill-invalid.md'; `$code = `$LASTEXITCODE; Pop-Location; exit `$code" 2>&1 | Out-String
            $exitCode = $LASTEXITCODE

            # Assert
            $exitCode | Should -Be 1
            $output | Should -Match "skill-invalid\.md"
        }
    }
}

Describe "Validate-SkillFormat.ps1 - Bundled Detection Edge Cases" {

    AfterEach {
        Get-ChildItem -Path $TestMemoriesPath -Filter "*.md" -ErrorAction SilentlyContinue | Remove-Item -Force
    }

    Context "Multiple Skill Headers" {

        It "Detects 3+ skill headers in single file" {
            # Arrange: File with 3 skill headers
            $bundledFile = Join-Path $TestMemoriesPath "triple-bundled.md"
            $content = @"
# Triple Bundle

## Skill-QA-001: First

Content 1.

## Skill-QA-002: Second

Content 2.

## Skill-QA-003: Third

Content 3.
"@
            Set-Content -Path $bundledFile -Value $content

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "3 skills"
        }

        It "Handles mixed violations (bundled + skill- prefix)" {
            # Arrange: File that violates BOTH rules
            $mixedFile = Join-Path $TestMemoriesPath "skill-bundled-violation.md"
            $content = @"
# Mixed Violation

## Skill-QA-001: First

Content 1.

## Skill-QA-002: Second

Content 2.
"@
            Set-Content -Path $mixedFile -Value $content

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert: Should report both violations
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "BUNDLED"
            $result.Output | Should -Match "PREFIX"
        }
    }

    Context "Skill Header Regex Pattern" {

        It "Rejects h3 skill headers (### instead of ##)" {
            # Arrange: h3 headers should NOT be counted as skill headers
            $h3File = Join-Path $TestMemoriesPath "h3-headers.md"
            $content = @"
# Some Doc

### Skill-QA-001: Not a real skill header

Content.

### Skill-QA-002: Also not counted

More content.
"@
            Set-Content -Path $h3File -Value $content

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert: Should pass (h3 headers don't match regex)
            $result.ExitCode | Should -Be 0
        }

        It "Counts skill headers with single-digit numbers" {
            # Arrange: Skill-QA-1 should match the pattern
            $singleDigitFile = Join-Path $TestMemoriesPath "single-digit.md"
            $content = @"
# Single Digit

## Skill-QA-1: First

Content 1.

## Skill-QA-2: Second

Content 2.
"@
            Set-Content -Path $singleDigitFile -Value $content

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert: Should detect 2 bundled skills
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "2 skills"
        }
    }
}

Describe "Validate-SkillFormat.ps1 - Integration Tests" {

    AfterEach {
        # Clean up test files after each test
        Get-ChildItem -Path $TestMemoriesPath -Filter "*.md" -ErrorAction SilentlyContinue | Remove-Item -Force
    }

    Context "Real-world scenarios" {

        It "Passes validation on valid memory file set" {
            # Arrange: Create a realistic set of valid memory files
            $validFiles = @(
                "pr-001-reviewer-enumeration.md",
                "qa-007-test-isolation.md",
                "security-003-input-validation.md",
                "labeler-005-all-patterns-matcher.md",
                "skills-pr-review-index.md",
                "memory-index.md"
            )
            foreach ($file in $validFiles) {
                $path = Join-Path $TestMemoriesPath $file
                Set-Content -Path $path -Value "# $file`n`nContent here."
            }

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert
            $result.ExitCode | Should -Be 0
            $result.Output | Should -Match "PASSED"
        }

        It "Fails with clear output when legacy skill- files found" {
            # Arrange: Mix of valid and invalid files
            $validFile = Join-Path $TestMemoriesPath "pr-001-valid.md"
            $invalidFile = Join-Path $TestMemoriesPath "skill-legacy-format.md"
            Set-Content -Path $validFile -Value "# Valid"
            Set-Content -Path $invalidFile -Value "# Legacy format"

            # Act
            $result = Invoke-ValidationScript -Path $TestMemoriesPath -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "skill-legacy-format\.md"
            $result.Output | Should -Match "PREFIX"
        }
    }
}
