#Requires -Modules Pester

<#
.SYNOPSIS
    Tests for Get-PRReviewComments.ps1 script

.DESCRIPTION
    Validates syntax, parameter validation, and functionality for the Get-PRReviewComments.ps1 script.
    Tests both review comments and issue comments retrieval.
#>

BeforeAll {
    # Correct path: from test/claude/skills/github -> .claude/skills/github/scripts/pr
    $ScriptPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "scripts" "pr" "Get-PRReviewComments.ps1"
    $ModulePath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "modules" "GitHubCore.psm1"

    # Import the module for helper functions
    Import-Module $ModulePath -Force
}

Describe "Get-PRReviewComments" {

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

        It "Should be valid PowerShell syntax" {
            $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$errors)
            $errors | Should -BeNullOrEmpty
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

        It "Should have optional Author parameter" {
            $scriptContent | Should -Match '\[string\]\$Author'
        }

        It "Should have IncludeDiffHunk switch parameter" {
            $scriptContent | Should -Match '\[switch\]\$IncludeDiffHunk'
        }

        It "Should have IncludeIssueComments switch parameter" {
            $scriptContent | Should -Match '\[switch\]\$IncludeIssueComments'
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

    Context "API Endpoint Usage" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should fetch review comments from pulls endpoint" {
            $scriptContent | Should -Match 'repos/\$Owner/\$Repo/pulls/\$PullRequest/comments'
        }

        It "Should fetch issue comments from issues endpoint when IncludeIssueComments is set" {
            $scriptContent | Should -Match 'repos/\$Owner/\$Repo/issues/\$PullRequest/comments'
        }

        It "Should use Invoke-GhApiPaginated for review comments" {
            $scriptContent | Should -Match 'Invoke-GhApiPaginated.*pulls.*comments'
        }

        It "Should use Invoke-GhApiPaginated for issue comments" {
            $scriptContent | Should -Match 'Invoke-GhApiPaginated.*issues.*comments'
        }
    }

    Context "Comment Type Handling" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should set CommentType to Review for review comments" {
            $scriptContent | Should -Match 'CommentType\s*=\s*"Review"'
        }

        It "Should set CommentType to Issue for issue comments" {
            $scriptContent | Should -Match 'CommentType\s*=\s*"Issue"'
        }

        It "Should combine review and issue comments" {
            $scriptContent | Should -Match '\$allProcessedComments\s*=.*\$processedReviewComments.*\$processedIssueComments'
        }

        It "Should sort comments by CreatedAt" {
            $scriptContent | Should -Match 'Sort-Object.*CreatedAt'
        }
    }

    Context "Output Structure" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should include Success property in output" {
            $scriptContent | Should -Match 'Success\s*=\s*\$true'
        }

        It "Should include TotalComments property in output" {
            $scriptContent | Should -Match 'TotalComments\s*='
        }

        It "Should include ReviewCommentCount property in output" {
            $scriptContent | Should -Match 'ReviewCommentCount\s*='
        }

        It "Should include IssueCommentCount property in output" {
            $scriptContent | Should -Match 'IssueCommentCount\s*='
        }

        It "Should include AuthorSummary property in output" {
            $scriptContent | Should -Match 'AuthorSummary\s*='
        }

        It "Should include Comments array in output" {
            $scriptContent | Should -Match 'Comments\s*=.*\$allProcessedComments'
        }
    }

    Context "Comment Object Properties" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should include Id property" {
            $scriptContent | Should -Match 'Id\s*=\s*\$comment\.id'
        }

        It "Should include Author property" {
            $scriptContent | Should -Match 'Author\s*=\s*\$comment\.user\.login'
        }

        It "Should include AuthorType property" {
            $scriptContent | Should -Match 'AuthorType\s*=\s*\$comment\.user\.type'
        }

        It "Should include Body property" {
            $scriptContent | Should -Match 'Body\s*=\s*\$comment\.body'
        }

        It "Should include HtmlUrl property" {
            $scriptContent | Should -Match 'HtmlUrl\s*=\s*\$comment\.html_url'
        }

        It "Should include CreatedAt property" {
            $scriptContent | Should -Match 'CreatedAt\s*=\s*\$comment\.created_at'
        }

        It "Should include Path property for review comments" {
            $scriptContent | Should -Match 'Path\s*=\s*\$comment\.path'
        }

        It "Should include Line property for review comments" {
            $scriptContent | Should -Match 'Line\s*='
        }

        It "Should set Path to null for issue comments" {
            $scriptContent | Should -Match 'Path\s*=\s*\$null.*#.*Issue comments'
        }
    }

    Context "Author Filtering" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should filter review comments by Author when specified" {
            $scriptContent | Should -Match 'if\s*\(\$Author.*\$comment\.user\.login.*continue'
        }

        It "Should filter issue comments by Author when specified" {
            # The same filtering pattern appears for issue comments
            $matches = [regex]::Matches($scriptContent, 'if\s*\(\$Author.*\$comment\.user\.login.*continue')
            $matches.Count | Should -BeGreaterOrEqual 2
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

        It "Should document IncludeIssueComments parameter" {
            $scriptContent | Should -Match '\.PARAMETER\s+IncludeIssueComments'
        }

        It "Should have EXAMPLE showing IncludeIssueComments usage" {
            $scriptContent | Should -Match '\.EXAMPLE[\s\S]*-IncludeIssueComments'
        }

        It "Should mention issue comments in description" {
            $scriptContent | Should -Match 'issue comments'
        }

        It "Should mention AI Quality Gate as example of issue comment" {
            $scriptContent | Should -Match 'AI Quality Gate'
        }
    }

    Context "Conditional Issue Comment Fetching" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should only fetch issue comments when IncludeIssueComments is set" {
            $scriptContent | Should -Match 'if\s*\(\$IncludeIssueComments\)'
        }

        It "Should initialize processedIssueComments as empty array" {
            $scriptContent | Should -Match '\$processedIssueComments\s*=\s*@\(\)'
        }
    }

    Context "Output Messages" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should output comment count summary" {
            $scriptContent | Should -Match 'Write-Host.*comments.*-ForegroundColor\s+Cyan'
        }

        It "Should include issue count in summary when IncludeIssueComments is set" {
            $scriptContent | Should -Match 'issue.*comments'
        }
    }
}
