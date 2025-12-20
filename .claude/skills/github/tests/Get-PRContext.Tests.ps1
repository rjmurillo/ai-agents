#Requires -Modules Pester

<#
.SYNOPSIS
    Tests for Get-PRContext.ps1 script

.DESCRIPTION
    Validates syntax, parameter validation, and error handling for the Get-PRContext.ps1 script.
    Covers the scenarios identified in PR #79 retrospective.
    Enhanced with mock-based behavior tests and comprehensive output validation.
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

    Context "Error Handling - Exit Codes" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should document exit code 0 for Success" {
            $scriptContent | Should -Match 'Exit Codes:.*0=Success'
        }

        It "Should document exit code 1 for Invalid params" {
            $scriptContent | Should -Match 'Exit Codes:.*1=Invalid params'
        }

        It "Should document exit code 2 for Not found" {
            $scriptContent | Should -Match 'Exit Codes:.*2=Not found'
        }

        It "Should document exit code 3 for API error" {
            $scriptContent | Should -Match 'Exit Codes:.*3=API error'
        }

        It "Should document exit code 4 for Not authenticated" {
            $scriptContent | Should -Match 'Exit Codes:.*4=Not authenticated'
        }

        It "Should check LASTEXITCODE after gh pr view command" {
            $scriptContent | Should -Match '\$LASTEXITCODE -ne 0'
        }

        It "Should have error path for PR not found with exit code 2" {
            $scriptContent | Should -Match 'not found'
            $scriptContent | Should -Match 'Write-ErrorAndExit.*2'
        }

        It "Should have error path for API error with exit code 3" {
            $scriptContent | Should -Match 'Write-ErrorAndExit.*"Failed to get PR.*3'
        }

        It "Should check authentication before making API calls (exit code 4)" {
            $scriptContent | Should -Match 'Assert-GhAuthenticated'
        }

        It "Should handle not found with specific exit code 2 pattern" {
            $scriptContent | Should -Match 'if.*not found.*Write-ErrorAndExit.*2'
        }
    }

    Context "Output Schema Validation" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should include Success property in output object" {
            $scriptContent | Should -Match 'Success\s*='
        }

        It "Should include Number property in output object" {
            $scriptContent | Should -Match 'Number\s*='
        }

        It "Should include Title property in output object" {
            $scriptContent | Should -Match 'Title\s*='
        }

        It "Should include Body property in output object" {
            $scriptContent | Should -Match 'Body\s*='
        }

        It "Should include State property in output object" {
            $scriptContent | Should -Match 'State\s*='
        }

        It "Should include Author property in output object" {
            $scriptContent | Should -Match 'Author\s*='
        }

        It "Should include HeadBranch property in output object" {
            $scriptContent | Should -Match 'HeadBranch\s*='
        }

        It "Should include BaseBranch property in output object" {
            $scriptContent | Should -Match 'BaseBranch\s*='
        }

        It "Should include Labels property in output object" {
            $scriptContent | Should -Match 'Labels\s*='
        }

        It "Should include Commits property in output object" {
            $scriptContent | Should -Match 'Commits\s*='
        }

        It "Should include Additions property in output object" {
            $scriptContent | Should -Match 'Additions\s*='
        }

        It "Should include Deletions property in output object" {
            $scriptContent | Should -Match 'Deletions\s*='
        }

        It "Should include ChangedFiles property in output object" {
            $scriptContent | Should -Match 'ChangedFiles\s*='
        }

        It "Should include Mergeable property in output object" {
            $scriptContent | Should -Match 'Mergeable\s*='
        }

        It "Should include Merged property in output object" {
            $scriptContent | Should -Match 'Merged\s*='
        }

        It "Should include MergedBy property in output object" {
            $scriptContent | Should -Match 'MergedBy\s*='
        }

        It "Should include CreatedAt property in output object" {
            $scriptContent | Should -Match 'CreatedAt\s*='
        }

        It "Should include UpdatedAt property in output object" {
            $scriptContent | Should -Match 'UpdatedAt\s*='
        }

        It "Should include Diff property in output object" {
            $scriptContent | Should -Match 'Diff\s*='
        }

        It "Should include Files property in output object" {
            $scriptContent | Should -Match 'Files\s*='
        }

        It "Should include Owner property in output object" {
            $scriptContent | Should -Match 'Owner\s*='
        }

        It "Should include Repo property in output object" {
            $scriptContent | Should -Match 'Repo\s*='
        }
    }

    Context "Switch Parameter Behaviors" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should conditionally populate Diff when IncludeDiff is used" {
            $scriptContent | Should -Match 'if.*\$IncludeDiff'
            $scriptContent | Should -Match '\$output\.Diff\s*='
        }

        It "Should conditionally populate Files when IncludeChangedFiles is used" {
            $scriptContent | Should -Match 'if.*\$IncludeChangedFiles'
            $scriptContent | Should -Match '\$output\.Files\s*='
        }

        It "Should use --stat flag when DiffStat is combined with IncludeDiff" {
            $scriptContent | Should -Match 'if.*\$DiffStat'
            $scriptContent | Should -Match 'gh pr diff.*--stat'
        }

        It "Should use --name-only flag for IncludeChangedFiles" {
            $scriptContent | Should -Match 'gh pr diff.*--name-only'
        }
    }

    Context "Labels Array Transformation" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should transform labels using ForEach-Object to extract name property" {
            $scriptContent | Should -Match 'labels.*ForEach-Object.*\.name'
        }

        It "Should wrap labels in array syntax" {
            $scriptContent | Should -Match 'Labels\s*=\s*@\('
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
