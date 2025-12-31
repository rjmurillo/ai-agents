#Requires -Modules Pester

<#
.SYNOPSIS
    Tests for Get-PullRequests.ps1 script

.DESCRIPTION
    Validates syntax, parameter validation, and error handling for the Get-PullRequests.ps1 script.
    Covers parameter definitions, exit codes, filter options, and output schema validation.
#>

BeforeAll {
    # Correct path: from test/claude/skills/github -> .claude/skills/github/scripts/pr
    $ScriptPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "scripts" "pr" "Get-PullRequests.ps1"
    $ModulePath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "modules" "GitHubCore.psm1"
}

Describe "Get-PullRequests" {

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

        It "Should have optional Owner parameter" {
            $scriptContent | Should -Match '\[string\]\$Owner'
        }

        It "Should have optional Repo parameter" {
            $scriptContent | Should -Match '\[string\]\$Repo'
        }

        It "Should have State parameter with validation" {
            $scriptContent | Should -Match '\[ValidateSet\("open",\s*"closed",\s*"merged",\s*"all"\)\]'
        }

        It "Should default State to open" {
            $scriptContent | Should -Match '\[string\]\$State\s*=\s*"open"'
        }

        It "Should have optional Label parameter" {
            $scriptContent | Should -Match '\[string\]\$Label'
        }

        It "Should have optional Author parameter" {
            $scriptContent | Should -Match '\[string\]\$Author'
        }

        It "Should have optional Base parameter" {
            $scriptContent | Should -Match '\[string\]\$Base'
        }

        It "Should have optional Head parameter" {
            $scriptContent | Should -Match '\[string\]\$Head'
        }

        It "Should have Limit parameter with range validation" {
            $scriptContent | Should -Match '\[ValidateRange\(1,\s*1000\)\]'
        }

        It "Should default Limit to 30" {
            $scriptContent | Should -Match '\[int\]\$Limit\s*=\s*30'
        }

        It "Should import GitHubCore module" {
            $scriptContent | Should -Match 'Import-Module.*GitHubCore\.psm1'
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
            $scriptContent | Should -Match 'Exit Codes:[\s\S]*0\s*-\s*Success'
        }

        It "Should document exit code 1 for Invalid parameters" {
            $scriptContent | Should -Match 'Exit Codes:[\s\S]*1\s*-\s*Invalid parameters'
        }

        It "Should document exit code 3 for API error" {
            $scriptContent | Should -Match 'Exit Codes:[\s\S]*3\s*-\s*API error'
        }

        It "Should document exit code 4 for Not authenticated" {
            $scriptContent | Should -Match 'Exit Codes:[\s\S]*4\s*-\s*Not authenticated'
        }

        It "Should check LASTEXITCODE after gh pr list command" {
            $scriptContent | Should -Match '\$LASTEXITCODE -ne 0'
        }

        It "Should have error path for API error with exit code 3" {
            $scriptContent | Should -Match 'Write-ErrorAndExit.*"Failed to list PRs.*3'
        }
    }

    Context "Output Schema Validation" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should include number property in output object" {
            $scriptContent | Should -Match 'number\s*='
        }

        It "Should include title property in output object" {
            $scriptContent | Should -Match 'title\s*='
        }

        It "Should include head property in output object" {
            $scriptContent | Should -Match 'head\s*='
        }

        It "Should include base property in output object" {
            $scriptContent | Should -Match 'base\s*='
        }

        It "Should include state property in output object" {
            $scriptContent | Should -Match 'state\s*='
        }

        It "Should output JSON" {
            $scriptContent | Should -Match 'ConvertTo-Json'
        }

        It "Should use -AsArray for consistent JSON output" {
            $scriptContent | Should -Match 'ConvertTo-Json.*-AsArray'
        }
    }

    Context "Filter Handling" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should apply --state flag for state filter" {
            $scriptContent | Should -Match '--state'
        }

        It "Should apply --label flag for label filter" {
            $scriptContent | Should -Match '--label'
        }

        It "Should support comma-separated labels" {
            $scriptContent | Should -Match '\$Label\s*-split.*,'
        }

        It "Should apply --author flag for author filter" {
            $scriptContent | Should -Match '--author'
        }

        It "Should apply --base flag for base branch filter" {
            $scriptContent | Should -Match '--base'
        }

        It "Should apply --head flag for head branch filter" {
            $scriptContent | Should -Match '--head'
        }

        It "Should apply --limit flag for result limit" {
            $scriptContent | Should -Match '--limit'
        }
    }

    Context "Merged State Handling" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should handle merged state specially" {
            $scriptContent | Should -Match 'State\s*-eq\s*"merged"'
        }

        It "Should query closed PRs when filtering for merged" {
            $scriptContent | Should -Match 'merged.*closed'
        }

        It "Should filter results by MERGED state" {
            $scriptContent | Should -Match '\.state\s*-eq\s*"MERGED"'
        }
    }

    Context "Integration with GitHubCore" {
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

    Context "CLI Usage Examples" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should have example for default usage" {
            $scriptContent | Should -Match '\.EXAMPLE[\s\S]*Get-PullRequests\.ps1[\r\n]'
        }

        It "Should have example for state and limit" {
            $scriptContent | Should -Match '\.EXAMPLE[\s\S]*-State\s+all\s+-Limit'
        }

        It "Should have example for label filtering" {
            $scriptContent | Should -Match '\.EXAMPLE[\s\S]*-Label'
        }

        It "Should have example for author and base filtering" {
            $scriptContent | Should -Match '\.EXAMPLE[\s\S]*-Author.*-Base'
        }

        It "Should have example for head branch filtering" {
            $scriptContent | Should -Match '\.EXAMPLE[\s\S]*-Head'
        }
    }
}
