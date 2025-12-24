#Requires -Modules Pester

<#
.SYNOPSIS
    Tests for Get-PRReviewThreads.ps1 script

.DESCRIPTION
    Validates syntax, parameter validation, and error handling for the Get-PRReviewThreads.ps1 script.
    Covers parameter definitions, exit codes, GraphQL operations, and output schema validation.
#>

BeforeAll {
    # Correct path: from .github/tests/skills/github -> .claude/skills/github/scripts/pr
    $ScriptPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "scripts" "pr" "Get-PRReviewThreads.ps1"
    $ModulePath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "modules" "GitHubHelpers.psm1"
}

Describe "Get-PRReviewThreads" {

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

        It "Should be valid PowerShell" {
            $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$errors)
            $errors | Should -BeNullOrEmpty
        }

        It "Should have CmdletBinding attribute" {
            $scriptContent = Get-Content $ScriptPath -Raw
            $scriptContent | Should -Match '\[CmdletBinding\(\)\]'
        }

        It "Should have comment-based help" {
            $scriptContent = Get-Content $ScriptPath -Raw
            $scriptContent | Should -Match '\.SYNOPSIS'
            $scriptContent | Should -Match '\.DESCRIPTION'
            $scriptContent | Should -Match '\.PARAMETER'
            $scriptContent | Should -Match '\.EXAMPLE'
            $scriptContent | Should -Match '\.NOTES'
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

        It "Should have UnresolvedOnly switch parameter" {
            $scriptContent | Should -Match '\[switch\]\$UnresolvedOnly'
        }

        It "Should have IncludeComments switch parameter" {
            $scriptContent | Should -Match '\[switch\]\$IncludeComments'
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

        It "Should check LASTEXITCODE after gh commands" {
            $scriptContent | Should -Match '\$LASTEXITCODE -ne 0'
        }

        It "Should have error path for PR not found with exit code 2" {
            $scriptContent | Should -Match 'Could not resolve|not found'
            $scriptContent | Should -Match 'Write-ErrorAndExit.*2'
        }

        It "Should have error path for API error with exit code 3" {
            $scriptContent | Should -Match 'Write-ErrorAndExit.*3'
        }
    }

    Context "GraphQL Operations" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should use gh api graphql command" {
            $scriptContent | Should -Match 'gh api graphql'
        }

        It "Should query reviewThreads" {
            $scriptContent | Should -Match 'reviewThreads\s*\('
        }

        It "Should query isResolved status" {
            $scriptContent | Should -Match 'isResolved'
        }

        It "Should query isOutdated status" {
            $scriptContent | Should -Match 'isOutdated'
        }

        It "Should query path and line information" {
            $scriptContent | Should -Match 'path'
            $scriptContent | Should -Match '\bline\b'
        }

        It "Should query comments with author info" {
            $scriptContent | Should -Match 'comments[\s\S]*author[\s\S]*login'
        }

        It "Should handle GraphQL response parsing" {
            $scriptContent | Should -Match 'ConvertFrom-Json'
        }

        It "Should include diffSide in query" {
            $scriptContent | Should -Match 'diffSide'
        }
    }

    Context "Output Schema Validation" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should include Success property in output object" {
            $scriptContent | Should -Match 'Success\s*='
        }

        It "Should include PullRequest property in output object" {
            $scriptContent | Should -Match 'PullRequest\s*='
        }

        It "Should include Owner property in output object" {
            $scriptContent | Should -Match 'Owner\s*='
        }

        It "Should include Repo property in output object" {
            $scriptContent | Should -Match 'Repo\s*='
        }

        It "Should include TotalThreads property in output object" {
            $scriptContent | Should -Match 'TotalThreads\s*='
        }

        It "Should include ResolvedCount property in output object" {
            $scriptContent | Should -Match 'ResolvedCount\s*='
        }

        It "Should include UnresolvedCount property in output object" {
            $scriptContent | Should -Match 'UnresolvedCount\s*='
        }

        It "Should include Threads array property in output object" {
            $scriptContent | Should -Match 'Threads\s*='
        }

        It "Should output JSON with depth" {
            $scriptContent | Should -Match 'ConvertTo-Json\s+-Depth'
        }
    }

    Context "Thread Output Schema" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should include ThreadId in thread output" {
            $scriptContent | Should -Match 'ThreadId\s*='
        }

        It "Should include IsResolved in thread output" {
            $scriptContent | Should -Match 'IsResolved\s*='
        }

        It "Should include IsOutdated in thread output" {
            $scriptContent | Should -Match 'IsOutdated\s*='
        }

        It "Should include Path in thread output" {
            $scriptContent | Should -Match 'Path\s*='
        }

        It "Should include Line in thread output" {
            $scriptContent | Should -Match 'Line\s*='
        }

        It "Should include CommentCount in thread output" {
            $scriptContent | Should -Match 'CommentCount\s*='
        }

        It "Should include FirstCommentId in thread output" {
            $scriptContent | Should -Match 'FirstCommentId\s*='
        }

        It "Should include FirstCommentAuthor in thread output" {
            $scriptContent | Should -Match 'FirstCommentAuthor\s*='
        }

        It "Should include FirstCommentBody in thread output" {
            $scriptContent | Should -Match 'FirstCommentBody\s*='
        }
    }

    Context "Filtering Behavior" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should filter for unresolved threads when UnresolvedOnly is used" {
            $scriptContent | Should -Match 'UnresolvedOnly[\s\S]*Where-Object[\s\S]*-not.*isResolved'
        }

        It "Should include all comments when IncludeComments is used" {
            $scriptContent | Should -Match 'IncludeComments[\s\S]*comments'
        }
    }

    Context "Summary Output" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should display colored summary output" {
            $scriptContent | Should -Match 'Write-Host.*-ForegroundColor\s+Cyan'
        }

        It "Should display thread counts" {
            $scriptContent | Should -Match 'Total:'
            $scriptContent | Should -Match 'Resolved:'
            $scriptContent | Should -Match 'Unresolved:'
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

    Context "Notes Documentation" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should document GraphQL API usage" {
            $scriptContent | Should -Match 'GraphQL API'
        }

        It "Should explain thread structure vs flat comments" {
            $scriptContent | Should -Match 'thread[\s\S]*Get-PRReviewComments'
        }
    }
}
