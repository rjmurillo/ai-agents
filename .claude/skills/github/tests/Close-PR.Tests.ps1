#Requires -Modules Pester

<#
.SYNOPSIS
    Tests for Close-PR.ps1 script

.DESCRIPTION
    Validates syntax, parameter validation, and error handling for the Close-PR.ps1 script.
    Covers basic functionality and edge cases for closing GitHub Pull Requests.
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot ".." "scripts" "pr" "Close-PR.ps1"
    $ModulePath = Join-Path $PSScriptRoot ".." "modules" "GitHubHelpers.psm1"

    # Import the module for error handling functions
    Import-Module $ModulePath -Force
}

Describe "Close-PR" {

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

        It "Should have optional DeleteBranch switch parameter" {
            $scriptContent | Should -Match '\[switch\]\$DeleteBranch'
        }

        It "Should have optional Comment parameter" {
            $scriptContent | Should -Match '\[string\]\$Comment'
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

        It "Should document exit code 2 for PR not found" {
            $scriptContent | Should -Match 'Exit Codes:.*2=PR not found'
        }

        It "Should document exit code 3 for API error" {
            $scriptContent | Should -Match 'Exit Codes:.*3=API error'
        }

        It "Should document exit code 4 for Not authenticated" {
            $scriptContent | Should -Match 'Exit Codes:.*4=Not authenticated'
        }
    }

    Context "Core Functionality" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should use gh pr close command" {
            $scriptContent | Should -Match "'pr'.*'close'"
        }

        It "Should check LASTEXITCODE after gh command" {
            $scriptContent | Should -Match '\$LASTEXITCODE -ne 0'
        }

        It "Should handle not found error" {
            $scriptContent | Should -Match 'not found'
        }

        It "Should support delete-branch flag" {
            $scriptContent | Should -Match "'--delete-branch'"
        }
    }

    Context "Comment Posting" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should check if Comment is provided" {
            $scriptContent | Should -Match 'IsNullOrWhiteSpace\(\$Comment\)'
        }

        It "Should use Post-PRCommentReply script for comments" {
            $scriptContent | Should -Match 'Post-PRCommentReply\.ps1'
        }

        It "Should continue if comment posting fails" {
            $scriptContent | Should -Match 'Continue anyway'
        }
    }

    Context "GitHub Actions Integration" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should check for GITHUB_OUTPUT environment variable" {
            $scriptContent | Should -Match '\$env:GITHUB_OUTPUT'
        }

        It "Should output success status" {
            $scriptContent | Should -Match 'success=true'
        }

        It "Should output PR number" {
            $scriptContent | Should -Match 'pr=\$PullRequest'
        }

        It "Should output branch_deleted status" {
            $scriptContent | Should -Match 'branch_deleted='
        }
    }

    Context "Mock-based Behavior Tests" {
        BeforeAll {
            # Mock the module functions and gh CLI
            Mock -CommandName 'gh' -MockWith {
                $global:LASTEXITCODE = 0
                return ""
            }

            Mock -CommandName 'Assert-GhAuthenticated' -MockWith { }
            Mock -CommandName 'Resolve-RepoParams' -MockWith {
                return @{ Owner = 'test'; Repo = 'repo' }
            }
            Mock -CommandName 'Write-Host' -MockWith { }
        }

        It "Should require PullRequest parameter" {
            { & $ScriptPath } | Should -Throw
        }
    }
}
