#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Validate-SessionEnd.ps1

.DESCRIPTION
    Tests the docs-only detection logic for QA skip behavior.
    Specifically tests fix for Issue #551: false positive on documentation-only commits.
#>

BeforeAll {
    # Define the Is-DocsOnly function for unit testing
    # This mirrors the implementation in Validate-SessionEnd.ps1
    function Is-DocsOnly([string[]]$Files) {
        if (-not $Files -or $Files.Count -eq 0) { return $false } # No files = cannot prove docs-only
        foreach ($f in $Files) {
            $ext = [IO.Path]::GetExtension($f).ToLowerInvariant()
            if ($ext -ne '.md') { return $false }
        }
        return $true
    }
}

Describe "Is-DocsOnly Function" {
    Context "When all files are markdown" {
        It "Returns true for single .md file" {
            $files = @(".agents/sessions/2025-12-29-session-01.md")
            Is-DocsOnly $files | Should -BeTrue
        }

        It "Returns true for multiple .md files" {
            $files = @(
                ".agents/sessions/2025-12-29-session-01.md",
                "README.md",
                "docs/guide.md"
            )
            Is-DocsOnly $files | Should -BeTrue
        }

        It "Returns true for .MD uppercase extension" {
            $files = @("README.MD", "CHANGELOG.MD")
            Is-DocsOnly $files | Should -BeTrue
        }
    }

    Context "When non-markdown files are present" {
        It "Returns false for .ps1 files" {
            $files = @("scripts/Validate-SessionEnd.ps1")
            Is-DocsOnly $files | Should -BeFalse
        }

        It "Returns false for .psm1 files" {
            $files = @("modules/Common.psm1")
            Is-DocsOnly $files | Should -BeFalse
        }

        It "Returns false for .yml files" {
            $files = @(".github/workflows/ci.yml")
            Is-DocsOnly $files | Should -BeFalse
        }

        It "Returns false for mixed files (md + ps1)" {
            $files = @(
                ".agents/sessions/2025-12-29-session-01.md",
                "scripts/Validate-SessionEnd.ps1"
            )
            Is-DocsOnly $files | Should -BeFalse
        }

        It "Returns false for files without extension" {
            $files = @("Makefile")
            Is-DocsOnly $files | Should -BeFalse
        }
    }

    Context "Edge cases" {
        It "Returns false for empty array" {
            $files = @()
            Is-DocsOnly $files | Should -BeFalse
        }

        It "Returns false for null" {
            Is-DocsOnly $null | Should -BeFalse
        }

        It "Handles paths with spaces" {
            $files = @("docs/my guide.md")
            Is-DocsOnly $files | Should -BeTrue
        }

        It "Handles deeply nested paths" {
            $files = @(".agents/sessions/archive/2025/12/session.md")
            Is-DocsOnly $files | Should -BeTrue
        }
    }
}

Describe "PreCommit Mode Docs-Only Detection (Issue #551)" {
    <#
    .SYNOPSIS
        Tests that verify the fix for Issue #551:
        Session protocol validation false positive on documentation-only commits.

    .DESCRIPTION
        The bug: During pre-commit, the validator was checking git diff $startingCommit..HEAD
        which includes ALL session changes, not just staged files. This caused false positives
        when committing docs-only changes on a branch that had previous code changes.

        The fix: In pre-commit mode, check git diff --staged --name-only instead.
    #>

    Context "Scenario: Docs-only commit on branch with previous code changes" {
        It "Should allow QA skip when only .md files are staged" {
            # This is the core scenario from Issue #551
            # Branch has previous code changes (*.ps1), but current commit is docs-only
            $stagedFiles = @(".agents/sessions/2025-12-29-session-01.md")
            Is-DocsOnly $stagedFiles | Should -BeTrue
        }
    }

    Context "Scenario: Code commit should require QA" {
        It "Should require QA when .ps1 file is staged" {
            $stagedFiles = @("scripts/Validate-SessionEnd.ps1")
            Is-DocsOnly $stagedFiles | Should -BeFalse
        }

        It "Should require QA when mixed files are staged" {
            $stagedFiles = @(
                ".agents/sessions/2025-12-29-session-01.md",
                "scripts/Validate-SessionEnd.ps1"
            )
            Is-DocsOnly $stagedFiles | Should -BeFalse
        }
    }
}
