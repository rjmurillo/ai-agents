#Requires -Modules Pester

<#
.SYNOPSIS
    Tests for Resolve-PRReviewThread.ps1 script

.DESCRIPTION
    Validates syntax, parameter validation, and behavior for the Resolve-PRReviewThread.ps1 script.
    This script resolves PR review threads to unblock PR merging.
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot ".." "scripts" "pr" "Resolve-PRReviewThread.ps1"
}

Describe "Resolve-PRReviewThread" {

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

        It "Should parse without syntax errors" {
            $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$errors)
            $errors.Count | Should -Be 0
        }

        It "Should have CmdletBinding attribute" {
            $scriptContent = Get-Content $ScriptPath -Raw
            $scriptContent | Should -Match '\[CmdletBinding'
        }
    }

    Context "Parameter Validation" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should have ThreadId parameter for single thread resolution" {
            $scriptContent | Should -Match '\[string\]\$ThreadId'
        }

        It "Should have PullRequest parameter for resolving all threads" {
            $scriptContent | Should -Match '\[int\]\$PullRequest'
        }

        It "Should have All switch parameter" {
            $scriptContent | Should -Match '\[switch\]\$All'
        }

        It "Should have ThreadId as mandatory in Single parameter set" {
            $scriptContent | Should -Match "ParameterSetName\s*=\s*'Single'"
        }

        It "Should have PullRequest as mandatory in All parameter set" {
            $scriptContent | Should -Match "ParameterSetName\s*=\s*'All'"
        }

        It "Should set default parameter set to Single" {
            $scriptContent | Should -Match "DefaultParameterSetName\s*=\s*'Single'"
        }
    }

    Context "GraphQL Mutation Structure" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should use resolveReviewThread mutation" {
            $scriptContent | Should -Match 'resolveReviewThread'
        }

        It "Should pass threadId in mutation input" {
            $scriptContent | Should -Match 'threadId.*\$Id'
        }

        It "Should request isResolved in response" {
            $scriptContent | Should -Match 'isResolved'
        }

        It "Should use gh api graphql for mutation" {
            $scriptContent | Should -Match 'gh api graphql -f query='
        }
    }

    Context "Error Handling" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should set ErrorActionPreference to Stop" {
            $scriptContent | Should -Match "\`$ErrorActionPreference\s*=\s*'Stop'"
        }

        It "Should check LASTEXITCODE after gh api calls" {
            $scriptContent | Should -Match '\$LASTEXITCODE -ne 0'
        }

        It "Should use Write-Warning for non-fatal errors" {
            $scriptContent | Should -Match 'Write-Warning'
        }

        It "Should throw on critical failures" {
            $scriptContent | Should -Match 'throw'
        }

        It "Should return exit code based on success" {
            $scriptContent | Should -Match 'exit\s*\('
        }
    }

    Context "Single Thread Resolution" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should have Resolve-SingleThread helper function" {
            $scriptContent | Should -Match 'function Resolve-SingleThread'
        }

        It "Should return boolean from Resolve-SingleThread" {
            $scriptContent | Should -Match 'return \$true'
            $scriptContent | Should -Match 'return \$false'
        }

        It "Should output success message when thread is resolved" {
            $scriptContent | Should -Match "Write-Host.*Resolved thread"
        }
    }

    Context "Bulk Thread Resolution" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should have Get-UnresolvedThreads helper function" {
            $scriptContent | Should -Match 'function Get-UnresolvedThreads'
        }

        It "Should query reviewThreads from repository" {
            $scriptContent | Should -Match 'reviewThreads'
        }

        It "Should filter to only unresolved threads" {
            $scriptContent | Should -Match 'Where-Object.*-not.*isResolved'
        }

        It "Should loop through unresolved threads" {
            $scriptContent | Should -Match 'foreach.*\$thread.*\$unresolvedThreads'
        }

        It "Should track resolved and failed counts" {
            $scriptContent | Should -Match '\$resolved\+\+'
            $scriptContent | Should -Match '\$failed\+\+'
        }

        It "Should output summary with counts" {
            $scriptContent | Should -Match 'Summary.*resolved.*failed'
        }

        It "Should return JSON with results" {
            $scriptContent | Should -Match 'ConvertTo-Json'
        }
    }

    Context "Output Format" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should output TotalUnresolved in JSON result" {
            $scriptContent | Should -Match 'TotalUnresolved\s*='
        }

        It "Should output Resolved count in JSON result" {
            $scriptContent | Should -Match 'Resolved\s*=\s*\$resolved'
        }

        It "Should output Failed count in JSON result" {
            $scriptContent | Should -Match 'Failed\s*=\s*\$failed'
        }

        It "Should output Success boolean in JSON result" {
            $scriptContent | Should -Match 'Success\s*='
        }
    }

    Context "Help Documentation" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should have SYNOPSIS" {
            $scriptContent | Should -Match '\.SYNOPSIS'
        }

        It "Should have DESCRIPTION" {
            $scriptContent | Should -Match '\.DESCRIPTION'
        }

        It "Should have PARAMETER documentation for ThreadId" {
            $scriptContent | Should -Match '\.PARAMETER\s+ThreadId'
        }

        It "Should have PARAMETER documentation for PullRequest" {
            $scriptContent | Should -Match '\.PARAMETER\s+PullRequest'
        }

        It "Should have PARAMETER documentation for All" {
            $scriptContent | Should -Match '\.PARAMETER\s+All'
        }

        It "Should have EXAMPLE for single thread resolution" {
            $scriptContent | Should -Match '\.EXAMPLE[\s\S]*?ThreadId'
        }

        It "Should have EXAMPLE for bulk resolution" {
            $scriptContent | Should -Match '\.EXAMPLE[\s\S]*?-All'
        }
    }
}
