#Requires -Modules Pester

<#
.SYNOPSIS
    Tests for Close-PR.ps1 script

.DESCRIPTION
    Validates syntax, parameter validation, and error handling for the Close-PR.ps1 script.
    Covers parameter definitions, exit codes, and output schema validation.
#>

BeforeAll {
    # Correct path: from .github/tests/skills/github -> .claude/skills/github/scripts/pr
    $ScriptPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "scripts" "pr" "Close-PR.ps1"
    $ModulePath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "modules" "GitHubHelpers.psm1"
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

        It "Should have optional Comment parameter" {
            $scriptContent | Should -Match '\[string\]\$Comment'
        }

        It "Should have optional CommentFile parameter" {
            $scriptContent | Should -Match '\[string\]\$CommentFile'
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
            $scriptContent | Should -Match 'not found'
            $scriptContent | Should -Match 'Write-ErrorAndExit.*2'
        }

        It "Should have error path for API error with exit code 3" {
            $scriptContent | Should -Match 'Write-ErrorAndExit.*3'
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

        It "Should include State property in output object" {
            $scriptContent | Should -Match 'State\s*='
        }

        It "Should include Action property in output object" {
            $scriptContent | Should -Match 'Action\s*='
        }

        It "Should include Message property in output object" {
            $scriptContent | Should -Match 'Message\s*='
        }

        It "Should output JSON" {
            $scriptContent | Should -Match 'ConvertTo-Json'
        }
    }

    Context "Idempotency Behavior" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should check if PR is already closed" {
            $scriptContent | Should -Match 'state.*CLOSED'
        }

        It "Should check if PR is already merged" {
            $scriptContent | Should -Match 'state.*MERGED'
        }

        It "Should return success for already closed PR" {
            # Pattern: if already closed -> exit 0
            $scriptContent | Should -Match 'already[\s\S]*exit\s+0'
        }
    }

    Context "Comment Handling" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should validate CommentFile if provided" {
            $scriptContent | Should -Match 'Assert-ValidBodyFile'
        }

        It "Should read comment from file when CommentFile is used" {
            $scriptContent | Should -Match 'Get-Content.*CommentFile'
        }

        It "Should post comment before closing if provided" {
            $scriptContent | Should -Match 'gh pr comment'
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
