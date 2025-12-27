<#
.SYNOPSIS
    Tests for Resolve-PRReviewThread.ps1

.DESCRIPTION
    Pester tests covering syntax validation, parameter handling, GraphQL operations,
    and error handling for the PR review thread resolution script.
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot '..' 'scripts' 'pr' 'Resolve-PRReviewThread.ps1'
    $ScriptContent = Get-Content -Path $ScriptPath -Raw
}

Describe 'Resolve-PRReviewThread.ps1' {
    Context 'Script Syntax' {
        It 'Should be valid PowerShell' {
            $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$errors)
            $errors | Should -BeNullOrEmpty
        }

        It 'Should have comment-based help' {
            $ScriptContent | Should -Match '\.SYNOPSIS'
            $ScriptContent | Should -Match '\.DESCRIPTION'
            $ScriptContent | Should -Match '\.PARAMETER'
            $ScriptContent | Should -Match '\.EXAMPLE'
        }

        It 'Should have EXAMPLE for single thread resolution' {
            # Using [\s\S]*? to match across newlines
            $ScriptContent | Should -Match '\.EXAMPLE[\s\S]*?-ThreadId'
        }

        It 'Should have EXAMPLE for bulk resolution' {
            # Using [\s\S]*? to match across newlines
            $ScriptContent | Should -Match '\.EXAMPLE[\s\S]*?-PullRequest[\s\S]*?-All'
        }
    }

    Context 'Parameter Definitions' {
        BeforeAll {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $paramBlock = $ast.ParamBlock
        }

        It 'Should define ThreadId parameter' {
            $ScriptContent | Should -Match '\[string\]\$ThreadId'
        }

        It 'Should define PullRequest parameter' {
            $ScriptContent | Should -Match '\[int\]\$PullRequest'
        }

        It 'Should define All switch parameter' {
            $ScriptContent | Should -Match '\[switch\]\$All'
        }

        It 'Should have Single parameter set' {
            $ScriptContent | Should -Match "ParameterSetName\s*=\s*'Single'"
        }

        It 'Should have All parameter set' {
            $ScriptContent | Should -Match "ParameterSetName\s*=\s*'All'"
        }

        It 'Should set Single as default parameter set' {
            $ScriptContent | Should -Match "DefaultParameterSetName\s*=\s*'Single'"
        }
    }

    Context 'GraphQL Operations' {
        It 'Should use resolveReviewThread mutation' {
            $ScriptContent | Should -Match 'resolveReviewThread\s*\(\s*input:'
        }

        It 'Should query reviewThreads for bulk resolution' {
            $ScriptContent | Should -Match 'reviewThreads\s*\(\s*first:'
        }

        It 'Should check isResolved status' {
            $ScriptContent | Should -Match 'isResolved'
        }

        It 'Should use gh api graphql command' {
            $ScriptContent | Should -Match 'gh api graphql'
        }

        It 'Should handle GraphQL response parsing' {
            $ScriptContent | Should -Match 'ConvertFrom-Json'
        }
    }

    Context 'GraphQL Injection Prevention (ADR-015)' {
        # Security tests verifying GraphQL variables are used instead of string interpolation

        It 'Should use GraphQL variable for threadId in mutation' {
            # The mutation should use $threadId variable, not string interpolation
            $ScriptContent | Should -Match 'mutation\s*\(\s*\$threadId:\s*ID!\s*\)'
        }

        It 'Should pass threadId as -f parameter to gh api graphql' {
            # The threadId should be passed via -f flag, not interpolated
            $ScriptContent | Should -Match '-f\s+threadId='
        }

        It 'Should use GraphQL variables for owner and name in query' {
            # The query should use $owner and $name variables
            $ScriptContent | Should -Match 'query\s*\(\s*\$owner:\s*String!'
            $ScriptContent | Should -Match '\$name:\s*String!'
        }

        It 'Should use GraphQL variable for prNumber in query' {
            # The query should use $prNumber variable
            $ScriptContent | Should -Match '\$prNumber:\s*Int!'
        }

        It 'Should pass owner, name, prNumber as parameters to gh api graphql' {
            # Values should be passed via -f/-F flags
            $ScriptContent | Should -Match '-f\s+owner='
            $ScriptContent | Should -Match '-f\s+name='
            $ScriptContent | Should -Match '-F\s+prNumber='
        }

        It 'Should NOT use string interpolation in GraphQL mutations' {
            # Ensure we don't have patterns like threadId: "$Id" (vulnerable to injection)
            $ScriptContent | Should -Not -Match 'threadId:\s*"\$Id"'
        }

        It 'Should NOT use string interpolation in GraphQL queries' {
            # Ensure we don't have patterns like owner: "$($repo.owner.login)" (vulnerable)
            $ScriptContent | Should -Not -Match 'owner:\s*"\$\(\$repo\.owner'
            $ScriptContent | Should -Not -Match 'name:\s*"\$\(\$repo\.name'
        }

        It 'Should include ADR-015 compliance comment' {
            $ScriptContent | Should -Match 'ADR-015'
        }
    }

    Context 'Error Handling' {
        It 'Should set ErrorActionPreference to Stop' {
            $ScriptContent | Should -Match "\`$ErrorActionPreference\s*=\s*'Stop'"
        }

        It 'Should check LASTEXITCODE after gh commands' {
            $ScriptContent | Should -Match '\$LASTEXITCODE\s*-ne\s*0'
        }

        It 'Should use Write-Warning for failures' {
            $ScriptContent | Should -Match 'Write-Warning'
        }

        It 'Should return boolean from Resolve-ReviewThread' {
            $ScriptContent | Should -Match 'return\s+\$true'
            $ScriptContent | Should -Match 'return\s+\$false'
        }
    }

    Context 'Output and Reporting' {
        It 'Should output colored status messages' {
            $ScriptContent | Should -Match '-ForegroundColor\s+Green'
            $ScriptContent | Should -Match '-ForegroundColor\s+Yellow'
            $ScriptContent | Should -Match '-ForegroundColor\s+Cyan'
        }

        It 'Should output JSON summary for bulk resolution' {
            $ScriptContent | Should -Match 'ConvertTo-Json'
        }

        It 'Should track resolved and failed counts' {
            $ScriptContent | Should -Match '\$resolved'
            $ScriptContent | Should -Match '\$failed'
        }

        It 'Should output summary with counts' {
            $ScriptContent | Should -Match 'Summary:'
        }
    }

    Context 'PowerShell Syntax Patterns' {
        It 'Should use brace syntax for variable in string with hash' {
            # Critical: #$PullRequest is a comment, ${PullRequest} is correct
            $ScriptContent | Should -Match '#\$\{PullRequest\}'
        }

        It 'Should NOT have bare #$PullRequest pattern' {
            # This would be interpreted as a comment
            $ScriptContent | Should -Not -Match '#\$PullRequest[^}]'
        }
    }

    Context 'Function Definitions' {
        It 'Should define Resolve-ReviewThread function' {
            $ScriptContent | Should -Match 'function\s+Resolve-ReviewThread'
        }

        It 'Should define Get-UnresolvedReviewThreads function' {
            $ScriptContent | Should -Match 'function\s+Get-UnresolvedReviewThreads'
        }

        It 'Should have proper parameter in Resolve-ReviewThread' {
            $ScriptContent | Should -Match 'Resolve-ReviewThread\s*\{[\s\S]*?param\s*\(\s*\[string\]\s*\$Id\s*\)'
        }

        It 'Should have proper parameter in Get-UnresolvedReviewThreads' {
            $ScriptContent | Should -Match 'Get-UnresolvedReviewThreads\s*\{[\s\S]*?param\s*\(\s*\[int\]\s*\$PR\s*\)'
        }
    }

    Context 'Repository Info Retrieval' {
        It 'Should get repo info using gh repo view' {
            $ScriptContent | Should -Match 'gh repo view --json owner,name'
        }

        It 'Should access owner.login' {
            $ScriptContent | Should -Match '\$repo\.owner\.login'
        }

        It 'Should access repo name' {
            $ScriptContent | Should -Match '\$repo\.name'
        }
    }

    Context 'Thread Processing' {
        It 'Should filter for unresolved threads' {
            $ScriptContent | Should -Match 'Where-Object\s*\{[\s\S]*?-not\s+\$_\.isResolved'
        }

        It 'Should iterate through unresolved threads' {
            $ScriptContent | Should -Match 'foreach\s*\(\s*\$thread\s+in\s+\$unresolvedThreads\s*\)'
        }

        It 'Should access thread comments for author info' {
            $ScriptContent | Should -Match '\$thread\.comments\.nodes\[0\]'
        }
    }

    Context 'Exit Codes' {
        It 'Should exit with 0 on success' {
            $ScriptContent | Should -Match 'exit\s+0'
        }

        It 'Should exit with 1 on failure via ternary' {
            # Uses ternary: exit ($success ? 0 : 1) or exit ($failed -eq 0 ? 0 : 1)
            $ScriptContent | Should -Match '\?\s*0\s*:\s*1\s*\)'
        }

        It 'Should use ternary for exit code based on success' {
            $ScriptContent | Should -Match '\?\s*0\s*:\s*1'
        }
    }

    Context 'Help Documentation Quality' {
        It 'Should document ThreadId parameter' {
            $ScriptContent | Should -Match '\.PARAMETER\s+ThreadId'
        }

        It 'Should document PullRequest parameter' {
            $ScriptContent | Should -Match '\.PARAMETER\s+PullRequest'
        }

        It 'Should document All parameter' {
            $ScriptContent | Should -Match '\.PARAMETER\s+All'
        }

        It 'Should mention PRRT prefix in ThreadId description' {
            $ScriptContent | Should -Match 'PRRT_'
        }

        It 'Should explain branch protection in description' {
            $ScriptContent | Should -Match 'branch[\s\S]*?protection|resolved[\s\S]*?before[\s\S]*?merging'
        }
    }
}
