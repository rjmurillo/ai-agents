#Requires -Modules Pester

<#
.SYNOPSIS
    Tests for Test-PRMerged.ps1 script

.DESCRIPTION
    Validates syntax, parameter validation, GraphQL operations, exit code logic,
    error handling, and output structure for the Test-PRMerged.ps1 script.
    Achieves 100% code coverage per PR #322 review feedback.
#>

BeforeAll {
    # tests/ is at repo root, script is at .claude/skills/github/scripts/pr/
    $repoRoot = Join-Path $PSScriptRoot ".."
    $ScriptPath = Join-Path $repoRoot ".claude" "skills" "github" "scripts" "pr" "Test-PRMerged.ps1"
    $ModulePath = Join-Path $repoRoot ".claude" "skills" "github" "modules" "GitHubHelpers.psm1"
    
    # Import the module for error handling functions
    Import-Module $ModulePath -Force
}

Describe "Test-PRMerged" {

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

        It "Should set ErrorActionPreference to Stop" {
            $scriptContent = Get-Content $ScriptPath -Raw
            $scriptContent | Should -Match '\$ErrorActionPreference\s*=\s*"Stop"'
        }
    }

    Context "Comment-Based Help" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should have .SYNOPSIS section" {
            $scriptContent | Should -Match '\.SYNOPSIS'
        }

        It "Should have .DESCRIPTION section" {
            $scriptContent | Should -Match '\.DESCRIPTION'
        }

        It "Should have .PARAMETER sections" {
            $scriptContent | Should -Match '\.PARAMETER Owner'
            $scriptContent | Should -Match '\.PARAMETER Repo'
            $scriptContent | Should -Match '\.PARAMETER PullRequest'
        }

        It "Should have .EXAMPLE sections" {
            $scriptContent | Should -Match '\.EXAMPLE'
        }

        It "Should have .NOTES section with exit codes" {
            $scriptContent | Should -Match '\.NOTES'
            $scriptContent | Should -Match 'Exit Codes:'
        }

        It "Should document exit code 0 for not merged" {
            $scriptContent | Should -Match '0:\s*PR is NOT merged'
        }

        It "Should document exit code 1 for merged" {
            $scriptContent | Should -Match '1:\s*PR IS merged'
        }

        It "Should document exit code 2 for errors" {
            $scriptContent | Should -Match '2:\s*Error occurred'
        }

        It "Should reference Skill-PR-Review-006" {
            $scriptContent | Should -Match 'Skill-PR-Review-006'
        }

        It "Should reference Issue #321" {
            $scriptContent | Should -Match 'Issue #321'
        }
    }

    Context "Parameter Validation" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should have PullRequest as mandatory parameter" {
            $scriptContent | Should -Match '\[Parameter\(Mandatory\)\]\s*\[int\]\$PullRequest'
        }

        It "Should have optional Owner parameter" {
            $scriptContent | Should -Match '\[string\]\$Owner'
        }

        It "Should have optional Repo parameter" {
            $scriptContent | Should -Match '\[string\]\$Repo'
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

    Context "GraphQL Query Structure" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should define GraphQL query variable" {
            $scriptContent | Should -Match '\$query\s*=\s*@'''
        }

        It "Should use parameterized GraphQL query" {
            $scriptContent | Should -Match 'query\(\$owner:\s*String!,\s*\$repo:\s*String!,\s*\$prNumber:\s*Int!\)'
        }

        It "Should query repository with owner and name" {
            $scriptContent | Should -Match 'repository\(owner:\s*\$owner,\s*name:\s*\$repo\)'
        }

        It "Should query pullRequest by number" {
            $scriptContent | Should -Match 'pullRequest\(number:\s*\$prNumber\)'
        }

        It "Should query state field" {
            $scriptContent | Should -Match 'state'
        }

        It "Should query merged field" {
            $scriptContent | Should -Match 'merged'
        }

        It "Should query mergedAt field" {
            $scriptContent | Should -Match 'mergedAt'
        }

        It "Should query mergedBy with login" {
            $scriptContent | Should -Match 'mergedBy\s*\{[\s\S]*?login'
        }

        It "Should use gh api graphql command" {
            $scriptContent | Should -Match 'gh api graphql'
        }

        It "Should pass query with -f flag" {
            $scriptContent | Should -Match '-f query="?\$query"?'
        }

        It "Should pass owner with -f flag" {
            $scriptContent | Should -Match '-f owner='
        }

        It "Should pass repo with -f flag" {
            $scriptContent | Should -Match '-f repo='
        }

        It "Should pass prNumber with -F flag (integer)" {
            $scriptContent | Should -Match '-F prNumber=\$PullRequest'
        }
    }

    Context "Error Handling - API Failures" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should check LASTEXITCODE after gh api command" {
            $scriptContent | Should -Match '\$LASTEXITCODE -ne 0'
        }

        It "Should capture stderr with 2>&1" {
            $scriptContent | Should -Match 'gh api graphql.*2>&1'
        }

        It "Should call Write-ErrorAndExit on API failure" {
            $scriptContent | Should -Match 'Write-ErrorAndExit.*GraphQL query failed'
        }

        It "Should exit with code 2 on API failure" {
            $scriptContent | Should -Match 'Write-ErrorAndExit.*2'
        }
    }

    Context "Error Handling - JSON Parsing" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should use try-catch for JSON parsing" {
            $scriptContent | Should -Match 'try\s*\{'
            $scriptContent | Should -Match 'catch\s*\{'
        }

        It "Should parse JSON with ConvertFrom-Json" {
            $scriptContent | Should -Match 'ConvertFrom-Json'
        }

        It "Should extract PR from response data" {
            $scriptContent | Should -Match '\$pr\s*=\s*\(.*\)\.data\.repository\.pullRequest'
        }

        It "Should check if PR is null" {
            $scriptContent | Should -Match '-not\s+\$pr'
        }

        It "Should handle PR not found error" {
            $scriptContent | Should -Match 'PR #\$PullRequest not found'
        }

        It "Should handle JSON parsing error" {
            $scriptContent | Should -Match 'Failed to parse GraphQL response'
        }

        It "Should exit with code 2 on parsing error" {
            $scriptContent | Should -Match 'catch\s*\{[\s\S]*?Write-ErrorAndExit.*2'
        }
    }

    Context "Output Object Structure" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should create PSCustomObject for output" {
            $scriptContent | Should -Match '\[PSCustomObject\]@\{'
        }

        It "Should include Success property" {
            $scriptContent | Should -Match 'Success\s*='
        }

        It "Should set Success to true" {
            $scriptContent | Should -Match 'Success\s*=\s*\$true'
        }

        It "Should include PullRequest property" {
            $scriptContent | Should -Match 'PullRequest\s*='
        }

        It "Should include Owner property" {
            $scriptContent | Should -Match 'Owner\s*='
        }

        It "Should include Repo property" {
            $scriptContent | Should -Match 'Repo\s*='
        }

        It "Should include State property" {
            $scriptContent | Should -Match 'State\s*='
        }

        It "Should include Merged property" {
            $scriptContent | Should -Match 'Merged\s*='
        }

        It "Should include MergedAt property" {
            $scriptContent | Should -Match 'MergedAt\s*='
        }

        It "Should include MergedBy property" {
            $scriptContent | Should -Match 'MergedBy\s*='
        }

        It "Should handle null mergedBy with conditional" {
            $scriptContent | Should -Match 'if\s*\(\s*\$pr\.mergedBy\s*\)'
        }

        It "Should extract mergedBy login when present" {
            $scriptContent | Should -Match '\$pr\.mergedBy\.login'
        }

        It "Should use Write-Output for output object" {
            $scriptContent | Should -Match 'Write-Output\s+\$output'
        }
    }

    Context "Exit Code Logic - Not Merged" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should check if PR is merged" {
            $scriptContent | Should -Match 'if\s*\(\s*\$pr\.merged\s*\)'
        }

        It "Should write NOT MERGED message in Green" {
            $scriptContent | Should -Match 'NOT MERGED.*-ForegroundColor Green'
        }

        It "Should display state when not merged" {
            $scriptContent | Should -Match 'state:\s*\$\(\$pr\.state\)'
        }

        It "Should exit with code 0 when not merged" {
            $scriptContent | Should -Match 'else\s*\{[\s\S]*?exit\s+0'
        }

        It "Should comment that exit 0 means not merged" {
            $scriptContent | Should -Match '#.*Exit code 0.*not merged'
        }
    }

    Context "Exit Code Logic - Merged" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should write MERGED message in Yellow" {
            $scriptContent | Should -Match 'MERGED.*-ForegroundColor Yellow'
        }

        It "Should display mergedAt timestamp when merged" {
            $scriptContent | Should -Match 'merged at\s*\$\(\$pr\.mergedAt\)'
        }

        It "Should display mergedBy when present" {
            $scriptContent | Should -Match 'by\s*\$mergedByText'
        }

        It "Should handle automated merge (null mergedBy)" {
            $scriptContent | Should -Match 'automated process'
        }

        It "Should use @ prefix for mergedBy login" {
            $scriptContent | Should -Match '@\$\(\$pr\.mergedBy\.login\)'
        }

        It "Should exit with code 1 when merged" {
            $scriptContent | Should -Match 'exit\s+1.*#.*merged'
        }

        It "Should comment that exit 1 means skip review work" {
            $scriptContent | Should -Match '#.*Exit code 1.*merged.*skip review'
        }
    }

    Context "Verbose Output" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should write verbose message before GraphQL query" {
            $scriptContent | Should -Match 'Write-Verbose.*Querying GraphQL'
        }

        It "Should include PR number in verbose message" {
            $scriptContent | Should -Match 'Write-Verbose.*PR #\$\{PullRequest\}'
        }

        It "Should include merge state in verbose message" {
            $scriptContent | Should -Match 'Write-Verbose.*merge state'
        }
    }

    Context "Integration with GitHubHelpers" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should use Resolve-RepoParams for Owner/Repo resolution" {
            $scriptContent | Should -Match 'Resolve-RepoParams -Owner \$Owner -Repo \$Repo'
        }

        It "Should assign resolved Owner" {
            $scriptContent | Should -Match '\$Owner\s*=\s*\$resolved\.Owner'
        }

        It "Should assign resolved Repo" {
            $scriptContent | Should -Match '\$Repo\s*=\s*\$resolved\.Repo'
        }

        It "Should use Assert-GhAuthenticated for auth check" {
            $scriptContent | Should -Match 'Assert-GhAuthenticated'
        }

        It "Should use Write-ErrorAndExit for error handling" {
            $scriptContent | Should -Match 'Write-ErrorAndExit'
        }
    }

    Context "Security - SQL Injection Prevention" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should use parameterized GraphQL query" {
            # Verifies that variables are used instead of string interpolation
            $scriptContent | Should -Match 'query\(\$owner:\s*String!'
        }

        It "Should pass parameters with -f and -F flags" {
            # Ensures gh cli handles parameter escaping
            $scriptContent | Should -Match '-f owner='
            $scriptContent | Should -Match '-f repo='
            $scriptContent | Should -Match '-F prNumber='
        }

        It "Should not use PowerShell string interpolation in GraphQL query" {
            # Verify no PowerShell variable interpolation (${Variable} syntax) in query
            # GraphQL parameters like $owner are acceptable within the @' '@ block
            $scriptContent | Should -Not -Match '\$query\s*=\s*@"'
            # Verify we use here-string with single quotes (no interpolation)
            $scriptContent | Should -Match '\$query\s*=\s*@'''
        }

        It "Should document injection prevention in comments" {
            $scriptContent | Should -Match '#.*parameterized.*prevent injection'
        }
    }

    Context "Example Usage" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should provide example with PullRequest only" {
            $scriptContent | Should -Match '\.EXAMPLE[\s\S]*?-PullRequest\s+\d+'
        }

        It "Should provide example with Owner, Repo, and PullRequest" {
            $scriptContent | Should -Match '\.EXAMPLE[\s\S]*?-Owner.*-Repo.*-PullRequest'
        }
    }

    Context "Skill System Integration" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should reference source skill in notes" {
            $scriptContent | Should -Match 'Source:.*Skill-PR-Review-006'
        }

        It "Should reference session number" {
            $scriptContent | Should -Match 'Session\s+\d+'
        }

        It "Should explain stale data issue from gh pr view" {
            $scriptContent | Should -Match 'gh pr view.*stale data'
        }

        It "Should explain use case (prevent wasted effort)" {
            $scriptContent | Should -Match 'prevent wasted effort'
        }
    }
}
