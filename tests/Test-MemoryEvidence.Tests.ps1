#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Test-MemoryEvidence function in Validate-Session.ps1

.DESCRIPTION
    Tests the ADR-007 Memory Evidence validation (E2 enforcement mechanism).
    Validates that the Evidence column for memory-related rows contains actual
    memory names that exist in .serena/memories/.
#>

BeforeAll {
    # Import the consolidated session validation module to get the Test-MemoryEvidence function
    $modulePath = Join-Path $PSScriptRoot ".." "scripts" "modules" "SessionValidation.psm1"
    Import-Module $modulePath -Force

    # Create test memory directory
    $TestRoot = Join-Path $TestDrive "test-repo"
    $MemoriesDir = Join-Path $TestRoot ".serena" "memories"
    New-Item -ItemType Directory -Path $MemoriesDir -Force | Out-Null

    # Create some test memory files
    "# Memory Index`nTest content" | Out-File (Join-Path $MemoriesDir "memory-index.md")
    "# PR Review Skills`nTest content" | Out-File (Join-Path $MemoriesDir "skills-pr-review-index.md")
    "# Codebase Structure`nTest content" | Out-File (Join-Path $MemoriesDir "codebase-structure.md")
}

Describe "Test-MemoryEvidence" {
    Context "Valid evidence" {
        It "Passes with valid memory names in evidence" {
            $rows = @(
                @{ Req = 'MUST'; Step = 'Read memory-index, load task-relevant memories'; Status = 'x'; Evidence = 'memory-index, skills-pr-review-index' }
            )
            $result = Test-MemoryEvidence -SessionRows $rows -RepoRoot $TestRoot
            $result.IsValid | Should -Be $true
            $result.MemoriesFound | Should -Contain 'memory-index'
            $result.MemoriesFound | Should -Contain 'skills-pr-review-index'
        }

        It "Passes with single memory name" {
            $rows = @(
                @{ Req = 'MUST'; Step = 'Read memory-index, load task-relevant memories'; Status = 'x'; Evidence = 'memory-index' }
            )
            $result = Test-MemoryEvidence -SessionRows $rows -RepoRoot $TestRoot
            $result.IsValid | Should -Be $true
            $result.MemoriesFound.Count | Should -Be 1
        }

        It "Extracts memory names from narrative evidence" {
            $rows = @(
                @{ Req = 'MUST'; Step = 'Read memory-index, load task-relevant memories'; Status = 'x'; Evidence = 'Read memory-index and skills-pr-review-index for PR review context' }
            )
            $result = Test-MemoryEvidence -SessionRows $rows -RepoRoot $TestRoot
            $result.IsValid | Should -Be $true
            $result.MemoriesFound | Should -Contain 'memory-index'
            $result.MemoriesFound | Should -Contain 'skills-pr-review-index'
        }
    }

    Context "Placeholder detection" {
        It "Fails on empty evidence" {
            $rows = @(
                @{ Req = 'MUST'; Step = 'Read memory-index, load task-relevant memories'; Status = 'x'; Evidence = '' }
            )
            $result = Test-MemoryEvidence -SessionRows $rows -RepoRoot $TestRoot
            $result.IsValid | Should -Be $false
            $result.ErrorMessage | Should -Match 'placeholder'
        }

        It "Fails on template placeholder text" {
            $rows = @(
                @{ Req = 'MUST'; Step = 'Read memory-index, load task-relevant memories'; Status = 'x'; Evidence = 'List memories loaded' }
            )
            $result = Test-MemoryEvidence -SessionRows $rows -RepoRoot $TestRoot
            $result.IsValid | Should -Be $false
            $result.ErrorMessage | Should -Match 'placeholder'
        }

        It "Fails on bracketed placeholder" {
            $rows = @(
                @{ Req = 'MUST'; Step = 'Read memory-index, load task-relevant memories'; Status = 'x'; Evidence = '[memories]' }
            )
            $result = Test-MemoryEvidence -SessionRows $rows -RepoRoot $TestRoot
            $result.IsValid | Should -Be $false
            $result.ErrorMessage | Should -Match 'placeholder'
        }

        It "Fails on dashes placeholder" {
            $rows = @(
                @{ Req = 'MUST'; Step = 'Read memory-index, load task-relevant memories'; Status = 'x'; Evidence = '---' }
            )
            $result = Test-MemoryEvidence -SessionRows $rows -RepoRoot $TestRoot
            $result.IsValid | Should -Be $false
            $result.ErrorMessage | Should -Match 'placeholder'
        }
    }

    Context "Invalid memory names" {
        It "Fails when no valid memory names found" {
            $rows = @(
                @{ Req = 'MUST'; Step = 'Read memory-index, load task-relevant memories'; Status = 'x'; Evidence = 'yes done completed' }
            )
            $result = Test-MemoryEvidence -SessionRows $rows -RepoRoot $TestRoot
            $result.IsValid | Should -Be $false
            $result.ErrorMessage | Should -Match 'valid memory names'
        }

        It "Fails when referenced memory does not exist" {
            $rows = @(
                @{ Req = 'MUST'; Step = 'Read memory-index, load task-relevant memories'; Status = 'x'; Evidence = 'memory-index, nonexistent-memory' }
            )
            $result = Test-MemoryEvidence -SessionRows $rows -RepoRoot $TestRoot
            $result.IsValid | Should -Be $false
            $result.MissingMemories | Should -Contain 'nonexistent-memory'
            $result.ErrorMessage | Should -Match 'nonexistent-memory'
        }
    }

    Context "Edge cases" {
        It "Passes when no memory-index row exists (template issue, not evidence issue)" {
            $rows = @(
                @{ Req = 'MUST'; Step = 'Initialize Serena'; Status = 'x'; Evidence = 'Tool output present' }
            )
            $result = Test-MemoryEvidence -SessionRows $rows -RepoRoot $TestRoot
            $result.IsValid | Should -Be $true
        }

        It "Handles case-insensitive memory names" {
            $rows = @(
                @{ Req = 'MUST'; Step = 'Read memory-index, load task-relevant memories'; Status = 'x'; Evidence = 'Memory-Index, Skills-PR-Review-Index' }
            )
            $result = Test-MemoryEvidence -SessionRows $rows -RepoRoot $TestRoot
            $result.IsValid | Should -Be $true
        }

        It "Deduplicates repeated memory names" {
            $rows = @(
                @{ Req = 'MUST'; Step = 'Read memory-index, load task-relevant memories'; Status = 'x'; Evidence = 'memory-index, memory-index, memory-index' }
            )
            $result = Test-MemoryEvidence -SessionRows $rows -RepoRoot $TestRoot
            $result.IsValid | Should -Be $true
            $result.MemoriesFound.Count | Should -Be 1
        }
    }
}
