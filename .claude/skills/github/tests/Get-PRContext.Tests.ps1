#Requires -Modules Pester

<#
.SYNOPSIS
    Tests for Get-PRContext.ps1 script

.DESCRIPTION
    Validates syntax, parameter validation, and error handling for the Get-PRContext.ps1 script.
    Covers the scenarios identified in PR #79 retrospective.
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot ".." "scripts" "pr" "Get-PRContext.ps1"
    $ModulePath = Join-Path $PSScriptRoot ".." "modules" "GitHubHelpers.psm1"
    
    # Import the module for error handling functions
    Import-Module $ModulePath -Force
}

Describe "Get-PRContext" {

    Context "Syntax Validation" {
        It "Should exist as a file" {
            Test-Path $ScriptPath | Should -BeTrue
        }

        It "Should have .ps1 extension" {
            [System.IO.Path]::GetExtension($ScriptPath) | Should -Be ".ps1"
        }

        It "Should be readable" {
            { Get-Content $ScriptPath -Raw } | Should -Not -Throw
        }

        It "Should have CmdletBinding attribute" {
            $scriptContent = Get-Content $ScriptPath -Raw
            $scriptContent | Should -Match '\[CmdletBinding\(\)\]'
        }
    }

    Context "Parameter Validation" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should have PullRequest as mandatory parameter" {
            $scriptContent | Should -Match '\[Parameter\(Mandatory\)\].*\[int\]\$PullRequest'
        }

        It "Should have optional Owner parameter" {
            $scriptContent | Should -Match '\[string\]\$Owner'
        }

        It "Should have optional Repo parameter" {
            $scriptContent | Should -Match '\[string\]\$Repo'
        }

        It "Should have IncludeDiff switch parameter" {
            $scriptContent | Should -Match '\[switch\]\$IncludeDiff'
        }

        It "Should have IncludeChangedFiles switch parameter" {
            $scriptContent | Should -Match '\[switch\]\$IncludeChangedFiles'
        }

        It "Should have DiffStat switch parameter" {
            $scriptContent | Should -Match '\[switch\]\$DiffStat'
        }

        It "Should import GitHubHelpers module" {
            $scriptContent | Should -Match 'Import-Module.*GitHubHelpers\.psm1'
        }

        It "Should call Assert-GhAuthenticated" {
            $scriptContent | Should -Match 'Assert-GhAuthenticated'
        }

        It "Should call Resolve-RepoParams" {
            $scriptContent | Should -Match 'Resolve-RepoParams'
        }
    }

    Context "Error Handling" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should check LASTEXITCODE after gh pr view command" {
            # Verify script checks LASTEXITCODE after gh pr view
            $scriptContent | Should -Match '\$LASTEXITCODE -ne 0'
        }

        It "Should have error path for PR not found" {
            # Test the error message pattern for not found scenario
            # Looking for pattern where we check "not found" and call Write-ErrorAndExit with code 2
            $scriptContent | Should -Match 'not found'
            $scriptContent | Should -Match 'Write-ErrorAndExit.*2'
        }

        It "Should have error path for API error with exit code 3" {
            # Test the error message pattern for API error scenario
            $scriptContent | Should -Match 'Write-ErrorAndExit.*"Failed to get PR.*3'
        }

        It "Should check authentication before making API calls" {
            # Verify Assert-GhAuthenticated is called (which uses exit code 4)
            $scriptContent | Should -Match 'Assert-GhAuthenticated'
        }

        It "Should handle not found with specific exit code 2" {
            # Verify the not found pattern specifically uses exit code 2
            $scriptContent | Should -Match 'if.*not found.*Write-ErrorAndExit.*2'
        }
    }

    Context "Output Validation" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should create output object with required properties" {
            # Verify the output structure includes key properties
            $scriptContent | Should -Match 'Success\s*='
            $scriptContent | Should -Match 'Number\s*='
            $scriptContent | Should -Match 'Title\s*='
            $scriptContent | Should -Match 'Body\s*='
            $scriptContent | Should -Match 'State\s*='
            $scriptContent | Should -Match 'Author\s*='
            $scriptContent | Should -Match 'HeadBranch\s*='
            $scriptContent | Should -Match 'BaseBranch\s*='
        }

        It "Should support IncludeDiff parameter" {
            $scriptContent | Should -Match 'if.*\$IncludeDiff'
        }

        It "Should support IncludeChangedFiles parameter" {
            $scriptContent | Should -Match 'if.*\$IncludeChangedFiles'
        }

        It "Should support DiffStat parameter" {
            $scriptContent | Should -Match 'if.*\$DiffStat'
        }
    }

    Context "Integration with GitHubHelpers" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should use Resolve-RepoParams for Owner/Repo resolution" {
            $scriptContent | Should -Match 'Resolve-RepoParams -Owner \$Owner -Repo \$Repo'
        }

        It "Should use Assert-GhAuthenticated for auth check" {
            $scriptContent | Should -Match 'Assert-GhAuthenticated'
        }

        It "Should use Write-ErrorAndExit for error handling" {
            $scriptContent | Should -Match 'Write-ErrorAndExit'
        }
    }
}
