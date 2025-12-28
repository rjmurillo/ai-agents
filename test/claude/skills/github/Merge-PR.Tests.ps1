#Requires -Modules Pester

<#
.SYNOPSIS
    Tests for Merge-PR.ps1 script

.DESCRIPTION
    Validates syntax, parameter validation, and error handling for the Merge-PR.ps1 script.
    Covers parameter definitions, exit codes, merge strategies, and output schema validation.
#>

BeforeAll {
    # Correct path: from .github/tests/skills/github -> .claude/skills/github/scripts/pr
    $ScriptPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "scripts" "pr" "Merge-PR.ps1"
    $ModulePath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "modules" "GitHubHelpers.psm1"
}

Describe "Merge-PR" {

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

        It "Should have Strategy parameter with validation" {
            $scriptContent | Should -Match '\[ValidateSet\("merge",\s*"squash",\s*"rebase"\)\]'
        }

        It "Should have DeleteBranch switch parameter" {
            $scriptContent | Should -Match '\[switch\]\$DeleteBranch'
        }

        It "Should have Auto switch parameter" {
            $scriptContent | Should -Match '\[switch\]\$Auto'
        }

        It "Should have optional Subject parameter" {
            $scriptContent | Should -Match '\[string\]\$Subject'
        }

        It "Should have optional Body parameter" {
            $scriptContent | Should -Match '\[string\]\$Body'
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

        It "Should document exit code 6 for Not mergeable" {
            $scriptContent | Should -Match 'Exit Codes:.*6=Not mergeable'
        }

        It "Should check LASTEXITCODE after gh commands" {
            $scriptContent | Should -Match '\$LASTEXITCODE -ne 0'
        }

        It "Should have error path for PR not found with exit code 2" {
            $scriptContent | Should -Match 'not found'
            $scriptContent | Should -Match 'Write-ErrorAndExit.*2'
        }

        It "Should have error path for not mergeable with exit code 6" {
            $scriptContent | Should -Match 'not mergeable|cannot be merged'
            $scriptContent | Should -Match 'Write-ErrorAndExit.*6'
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

        It "Should include Strategy property in output object" {
            $scriptContent | Should -Match 'Strategy\s*='
        }

        It "Should include BranchDeleted property in output object" {
            $scriptContent | Should -Match 'BranchDeleted\s*='
        }

        It "Should include Message property in output object" {
            $scriptContent | Should -Match 'Message\s*='
        }

        It "Should output JSON" {
            $scriptContent | Should -Match 'ConvertTo-Json'
        }
    }

    Context "Merge Strategy Handling" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should default Strategy to merge" {
            $scriptContent | Should -Match '\$Strategy\s*=\s*"merge"'
        }

        It "Should build merge command with strategy flag" {
            $scriptContent | Should -Match '--\$Strategy'
        }

        It "Should support squash strategy" {
            $scriptContent | Should -Match 'squash'
        }

        It "Should support rebase strategy" {
            $scriptContent | Should -Match 'rebase'
        }
    }

    Context "Auto-Merge Behavior" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should add --auto flag when Auto switch is used" {
            $scriptContent | Should -Match '\$Auto[\s\S]*--auto'
        }

        It "Should set action to auto-merge-enabled when Auto is used" {
            $scriptContent | Should -Match 'auto-merge-enabled'
        }

        It "Should set state to PENDING when Auto is used" {
            $scriptContent | Should -Match 'PENDING'
        }
    }

    Context "Delete Branch Behavior" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should add --delete-branch flag when DeleteBranch switch is used" {
            $scriptContent | Should -Match '\$DeleteBranch[\s\S]*--delete-branch'
        }
    }

    Context "Idempotency Behavior" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should check if PR is already merged" {
            $scriptContent | Should -Match 'state.*MERGED'
        }

        It "Should return success for already merged PR" {
            # Pattern: if already merged -> exit 0
            $scriptContent | Should -Match 'already merged[\s\S]*exit\s+0'
        }

        It "Should error if PR is closed and not mergeable" {
            $scriptContent | Should -Match 'state.*CLOSED'
            $scriptContent | Should -Match 'closed and cannot be merged'
        }
    }

    Context "Custom Commit Message" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should support Subject parameter for commit subject" {
            $scriptContent | Should -Match '--subject.*\$Subject'
        }

        It "Should support Body parameter for commit body" {
            $scriptContent | Should -Match '--body.*\$Body'
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
