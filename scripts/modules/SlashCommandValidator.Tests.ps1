#!/usr/bin/env pwsh

<#
.SYNOPSIS
    Pester tests for SlashCommandValidator.psm1

.DESCRIPTION
    Tests for the Invoke-SlashCommandValidation function that validates
    all slash command files in .claude/commands/
#>

BeforeAll {
    # Import the module under test
    $modulePath = Join-Path $PSScriptRoot 'SlashCommandValidator.psm1'
    Import-Module $modulePath -Force

    # Create mock validation script that will be called by the module
    $mockScriptDir = Join-Path $TestDrive '.claude' 'skills' 'slashcommandcreator' 'scripts'
    New-Item -ItemType Directory -Path $mockScriptDir -Force | Out-Null

    $mockScriptPath = Join-Path $mockScriptDir 'Validate-SlashCommand.ps1'

    # Create a simple mock script that returns based on a control file
    $mockScriptContent = @'
param(
    [Parameter(Mandatory=$false)]
    [string]$Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $Path) {
    Write-Error "Path parameter is required"
    exit 1
}

# Check if there's a failure marker file for this specific file
$fileName = Split-Path -Leaf $Path
$failMarker = Join-Path $env:TEMP "fail-$fileName"

if (Test-Path $failMarker) {
    Remove-Item $failMarker -Force
    exit 1
} else {
    exit 0
}
'@
    $mockScriptContent | Out-File -FilePath $mockScriptPath -Encoding utf8
}

Describe 'Invoke-SlashCommandValidation' {
    BeforeEach {
        # Create test directory structure
        $testCommandsDir = Join-Path $TestDrive '.claude' 'commands'
        New-Item -ItemType Directory -Path $testCommandsDir -Force | Out-Null

        # Store original location
        $script:originalLocation = Get-Location

        # Change to TestDrive to simulate repo root
        Set-Location $TestDrive

        # Clean up any old fail markers
        Get-ChildItem -Path $env:TEMP -Filter "fail-*.md" -ErrorAction SilentlyContinue | Remove-Item -Force
    }

    AfterEach {
        # Restore original location
        Set-Location $script:originalLocation

        # Clean up fail markers
        Get-ChildItem -Path $env:TEMP -Filter "fail-*.md" -ErrorAction SilentlyContinue | Remove-Item -Force
    }

    Context 'Empty commands directory' {
        It 'Should return 0 when no slash command files exist' {
            # Arrange: Empty .claude/commands directory already created in BeforeEach

            # Act
            $result = Invoke-SlashCommandValidation

            # Assert
            $result | Should -Be 0
        }

        It 'Should output message about no files found' {
            # Arrange: Empty directory

            # Act
            $output = Invoke-SlashCommandValidation *>&1

            # Assert
            $output -join ' ' | Should -Match 'No slash command files found'
        }
    }

    Context 'Single file validation' {
        It 'Should return 0 when single file passes validation' {
            # Arrange
            $validFile = Join-Path $testCommandsDir 'test-valid.md'
            '---
description: Use when testing
---' | Out-File -FilePath $validFile -Encoding utf8

            # Act
            $result = Invoke-SlashCommandValidation

            # Assert
            $result | Should -Be 0
        }

        It 'Should return 1 when single file fails validation' {
            # Arrange
            $invalidFile = Join-Path $testCommandsDir 'test-invalid.md'
            'No frontmatter' | Out-File -FilePath $invalidFile -Encoding utf8

            # Mark this file to fail
            'fail' | Out-File -FilePath (Join-Path $env:TEMP 'fail-test-invalid.md') -Encoding utf8

            # Act
            $result = Invoke-SlashCommandValidation

            # Assert
            $result | Should -Be 1
        }
    }

    Context 'Multiple file validation' {
        It 'Should return 0 when all files pass validation' {
            # Arrange
            $file1 = Join-Path $testCommandsDir 'test1.md'
            $file2 = Join-Path $testCommandsDir 'test2.md'
            '---
description: Test 1
---' | Out-File -FilePath $file1 -Encoding utf8
            '---
description: Test 2
---' | Out-File -FilePath $file2 -Encoding utf8

            # Act
            $result = Invoke-SlashCommandValidation

            # Assert
            $result | Should -Be 0
        }

        It 'Should return 1 when any file fails validation' {
            # Arrange
            $file1 = Join-Path $testCommandsDir 'test1.md'
            $file2 = Join-Path $testCommandsDir 'test2.md'
            $file3 = Join-Path $testCommandsDir 'test3.md'
            '---
description: Test 1
---' | Out-File -FilePath $file1 -Encoding utf8
            'No frontmatter' | Out-File -FilePath $file2 -Encoding utf8
            '---
description: Test 3
---' | Out-File -FilePath $file3 -Encoding utf8

            # Mark file2 to fail
            'fail' | Out-File -FilePath (Join-Path $env:TEMP 'fail-test2.md') -Encoding utf8

            # Act
            $result = Invoke-SlashCommandValidation

            # Assert
            $result | Should -Be 1
        }

        It 'Should list all failed files in output' {
            # Arrange
            $file1 = Join-Path $testCommandsDir 'failed1.md'
            $file2 = Join-Path $testCommandsDir 'failed2.md'
            'No frontmatter' | Out-File -FilePath $file1 -Encoding utf8
            'No frontmatter' | Out-File -FilePath $file2 -Encoding utf8

            # Mark both to fail
            'fail' | Out-File -FilePath (Join-Path $env:TEMP 'fail-failed1.md') -Encoding utf8
            'fail' | Out-File -FilePath (Join-Path $env:TEMP 'fail-failed2.md') -Encoding utf8

            # Act
            $output = Invoke-SlashCommandValidation *>&1

            # Assert
            $output -join ' ' | Should -Match 'failed1\.md'
            $output -join ' ' | Should -Match 'failed2\.md'
            $output -join ' ' | Should -Match '2 file\(s\) failed'
        }
    }

    Context 'Nested directory support' {
        It 'Should validate files in subdirectories (recursive)' {
            # Arrange
            $subDir = Join-Path $testCommandsDir 'namespace'
            New-Item -ItemType Directory -Path $subDir -Force | Out-Null

            $rootFile = Join-Path $testCommandsDir 'root.md'
            $nestedFile = Join-Path $subDir 'nested.md'
            '---
description: Root command
---' | Out-File -FilePath $rootFile -Encoding utf8
            '---
description: Nested command
---' | Out-File -FilePath $nestedFile -Encoding utf8

            # Act
            $output = Invoke-SlashCommandValidation *>&1

            # Assert
            $output -join ' ' | Should -Match 'Found 2 slash command'
            $output -join ' ' | Should -Match 'root.md'
            $output -join ' ' | Should -Match 'nested.md'
        }
    }

    Context 'Exit code behavior' {
        It 'Should return 0 when all validations pass' {
            # Arrange
            $file = Join-Path $testCommandsDir 'test.md'
            '---
description: Test
---' | Out-File -FilePath $file -Encoding utf8

            # Act
            $result = Invoke-SlashCommandValidation

            # Assert
            $result | Should -Be 0
        }

        It 'Should return 1 when any validation fails' {
            # Arrange
            $file = Join-Path $testCommandsDir 'test.md'
            'No frontmatter' | Out-File -FilePath $file -Encoding utf8

            # Mark to fail
            'fail' | Out-File -FilePath (Join-Path $env:TEMP 'fail-test.md') -Encoding utf8

            # Act
            $result = Invoke-SlashCommandValidation

            # Assert
            $result | Should -Be 1
        }
    }

    Context 'Output messages' {
        It 'Should output file count when files found' {
            # Arrange
            $file1 = Join-Path $testCommandsDir 'test1.md'
            $file2 = Join-Path $testCommandsDir 'test2.md'
            '---
description: Test 1
---' | Out-File -FilePath $file1 -Encoding utf8
            '---
description: Test 2
---' | Out-File -FilePath $file2 -Encoding utf8

            # Act
            $output = Invoke-SlashCommandValidation *>&1

            # Assert
            $output -join ' ' | Should -Match 'Found 2 slash command file\(s\)'
        }

        It 'Should output success message when all pass' {
            # Arrange
            $file = Join-Path $testCommandsDir 'test.md'
            '---
description: Test
---' | Out-File -FilePath $file -Encoding utf8

            # Act
            $output = Invoke-SlashCommandValidation *>&1

            # Assert
            $output -join ' ' | Should -Match '\[PASS\].*All slash commands passed'
        }

        It 'Should output failure message when any fail' {
            # Arrange
            $file = Join-Path $testCommandsDir 'test.md'
            'No frontmatter' | Out-File -FilePath $file -Encoding utf8

            # Mark to fail
            'fail' | Out-File -FilePath (Join-Path $env:TEMP 'fail-test.md') -Encoding utf8

            # Act
            $output = Invoke-SlashCommandValidation *>&1

            # Assert
            $output -join ' ' | Should -Match '\[FAIL\].*VALIDATION FAILED'
        }
    }
}
