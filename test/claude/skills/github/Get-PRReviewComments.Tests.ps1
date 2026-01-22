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

        It "Should have GroupByDomain switch parameter" {
            $scriptContent | Should -Match '\[switch\]\$GroupByDomain'
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

        It "Should document GroupByDomain parameter" {
            $scriptContent | Should -Match '\.PARAMETER\s+GroupByDomain'
        }

        It "Should have EXAMPLE showing GroupByDomain usage" {
            $scriptContent | Should -Match '\.EXAMPLE[\s\S]*-GroupByDomain'
        }

        It "Should mention domain classification in description" {
            $scriptContent | Should -Match 'domain classification|Domain Classification'
        }
    }

    Context "Domain Classification Function" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should have Get-CommentDomain function" {
            $scriptContent | Should -Match 'function Get-CommentDomain'
        }

        It "Should classify security keywords" {
            # Test the classification logic by checking regex patterns
            $scriptContent | Should -Match 'cwe-\\d\+'
            $scriptContent | Should -Match 'vulnerability|injection|xss|sql|csrf'
            $scriptContent | Should -Match 'auth(entication|orization)?'
            $scriptContent | Should -Match 'secrets?|credentials?'
            $scriptContent | Should -Match 'toctou|symlink|traversal'
            $scriptContent | Should -Match 'sanitiz|escap'
        }

        It "Should classify bug keywords" {
            $scriptContent | Should -Match 'error|crash|exception|fail|null'
            $scriptContent | Should -Match 'race\\s\+condition|deadlock|memory\\s\+leak'
        }

        It "Should classify style keywords" {
            $scriptContent | Should -Match 'formatting|naming|indentation|whitespace|convention'
            $scriptContent | Should -Match 'prefer|consider|suggest'
        }

        It "Should classify summary patterns" {
            $scriptContent | Should -Match 'summary|overview|changes|walkthrough'
        }

        It "Should return security domain" {
            $scriptContent | Should -Match "return\s+[`"']security[`"']"
        }

        It "Should return bug domain" {
            $scriptContent | Should -Match "return\s+[`"']bug[`"']"
        }

        It "Should return style domain" {
            $scriptContent | Should -Match "return\s+[`"']style[`"']"
        }

        It "Should return summary domain" {
            $scriptContent | Should -Match "return\s+[`"']summary[`"']"
        }

        It "Should return general domain as default" {
            $scriptContent | Should -Match "return\s+[`"']general[`"']"
        }

        It "Should convert body to lowercase for case-insensitive matching" {
            $scriptContent | Should -Match '\.ToLower\(\)|\.toLower\(\)'
        }

        It "Should use word boundaries for auth keyword to avoid 'author' false positives" {
            $scriptContent | Should -Match '\\bauth'
        }

        It "Should use word boundaries for escap keyword to avoid false positives" {
            $scriptContent | Should -Match '\\bescap'
        }

        It "Should use specific bug patterns to reduce false positives" {
            # Should match "throws error", "error occurs", etc., not just "error"
            $scriptContent | Should -Match 'throws?\\s+error|error\\s+'
        }

        It "Should use multiline mode for summary detection" {
            $scriptContent | Should -Match '\(\?m\)'
        }
    }

    Context "Domain Property in Comment Objects" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should add Domain property to review comments" {
            $scriptContent | Should -Match 'Domain\s*=\s*Get-CommentDomain'
        }

        It "Should call Get-CommentDomain with comment body" {
            $scriptContent | Should -Match 'Get-CommentDomain\s+-Body\s+\$comment\.body'
        }

        It "Should have Domain property in PSCustomObject for review comments" {
            # Check that Domain appears after Body in review comment object
            $scriptContent | Should -Match 'Body\s*=[\s\S]{0,100}Domain\s*='
        }

        It "Should have Domain property in PSCustomObject for issue comments" {
            # There should be at least 2 occurrences (review + issue comments)
            $matches = [regex]::Matches($scriptContent, 'Domain\s*=\s*Get-CommentDomain')
            $matches.Count | Should -BeGreaterOrEqual 2
        }
    }

    Context "GroupByDomain Output" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should check for GroupByDomain parameter" {
            $scriptContent | Should -Match 'if\s*\(\$GroupByDomain\)'
        }

        It "Should group comments by Domain property" {
            $scriptContent | Should -Match 'Group-Object\s+-Property\s+Domain'
        }

        It "Should initialize Security group" {
            $scriptContent | Should -Match "Security\s*=\s*@\(\)"
        }

        It "Should initialize Bug group" {
            $scriptContent | Should -Match "Bug\s*=\s*@\(\)"
        }

        It "Should initialize Style group" {
            $scriptContent | Should -Match "Style\s*=\s*@\(\)"
        }

        It "Should initialize Summary group" {
            $scriptContent | Should -Match "Summary\s*=\s*@\(\)"
        }

        It "Should initialize General group" {
            $scriptContent | Should -Match "General\s*=\s*@\(\)"
        }

        It "Should capitalize domain names for grouped output" {
            $scriptContent | Should -Match 'ToTitleCase'
        }

        It "Should include TotalComments in grouped output" {
            $scriptContent | Should -Match '\.TotalComments\s*='
        }

        It "Should include DomainCounts in grouped output" {
            $scriptContent | Should -Match '\.DomainCounts\s*='
        }

        It "Should return early when GroupByDomain is used" {
            $scriptContent | Should -Match 'return' # After grouped output
        }
    }

    Context "Domain Distribution in Standard Output" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should include DomainCounts in standard output object" {
            $scriptContent | Should -Match 'DomainCounts\s*='
        }

        It "Should display domain distribution in console output" {
            $scriptContent | Should -Match 'Domains:'
        }

        It "Should use color coding for security domain" {
            $scriptContent | Should -Match "Red.*security|security.*Red"
        }

        It "Should use color coding for bug domain" {
            $scriptContent | Should -Match "Yellow.*bug|bug.*Yellow"
        }

        It "Should use color coding for style domain" {
            $scriptContent | Should -Match "Gray.*style|style.*Gray"
        }

        It "Should use color coding for general domain" {
            $scriptContent | Should -Match "Cyan.*general|general.*Cyan"
        }
    }

    Context "Get-CommentDomain Function Tests" {
        BeforeAll {
            # Extract and execute just the Get-CommentDomain function
            $scriptContent = Get-Content $ScriptPath -Raw
            $functionMatch = [regex]::Match($scriptContent, 'function Get-CommentDomain\s*{[\s\S]*?^}', [System.Text.RegularExpressions.RegexOptions]::Multiline)
            if ($functionMatch.Success) {
                Invoke-Expression $functionMatch.Value
            }
        }

        It "Should classify CWE identifier as security" {
            $result = Get-CommentDomain -Body "Potential Path Traversal (CWE-22) vulnerability"
            $result | Should -Be "security"
        }

        It "Should classify vulnerability keyword as security" {
            $result = Get-CommentDomain -Body "This code has a vulnerability in the authentication logic"
            $result | Should -Be "security"
        }

        It "Should classify XSS as security" {
            $result = Get-CommentDomain -Body "Potential XSS attack vector"
            $result | Should -Be "security"
        }

        It "Should NOT classify 'author' as security (word boundary test)" {
            $result = Get-CommentDomain -Body "The author should update the documentation"
            $result | Should -Not -Be "security"
        }

        It "Should classify 'authentication' as security" {
            $result = Get-CommentDomain -Body "Fix the authentication logic"
            $result | Should -Be "security"
        }

        It "Should classify error throws as bug" {
            $result = Get-CommentDomain -Body "This function throws error when given invalid input"
            $result | Should -Be "bug"
        }

        It "Should classify null pointer as bug" {
            $result = Get-CommentDomain -Body "Potential null pointer dereference"
            $result | Should -Be "bug"
        }

        It "Should NOT classify 'no error' as bug (false positive test)" {
            $result = Get-CommentDomain -Body "There is no error in this code"
            $result | Should -Not -Be "bug"
        }

        It "Should classify formatting as style" {
            $result = Get-CommentDomain -Body "Fix the formatting of this function"
            $result | Should -Be "style"
        }

        It "Should classify readability as style" {
            $result = Get-CommentDomain -Body "Improve readability by extracting this logic"
            $result | Should -Be "style"
        }

        It "Should classify CWE with 'consider' wording as security (security wins priority)" {
            $result = Get-CommentDomain -Body "Consider the CWE-79 vulnerability in this change"
            $result | Should -Be "security"
        }

        It "Should classify summary header as summary" {
            $result = Get-CommentDomain -Body "## Summary`nThis PR adds feature X"
            $result | Should -Be "summary"
        }

        It "Should classify overview header as summary" {
            $result = Get-CommentDomain -Body "### Overview`nChanges made in this PR"
            $result | Should -Be "summary"
        }

        It "Should classify summary header in middle of comment as summary (multiline test)" {
            $result = Get-CommentDomain -Body "Some intro text`n`n## Summary`nMain content"
            $result | Should -Be "summary"
        }

        It "Should return general for non-matching comment" {
            $result = Get-CommentDomain -Body "Great work on this feature!"
            $result | Should -Be "general"
        }

        It "Should return general for empty body" {
            $result = Get-CommentDomain -Body ""
            $result | Should -Be "general"
        }

        It "Should be case-insensitive" {
            $result = Get-CommentDomain -Body "POTENTIAL XSS ATTACK"
            $result | Should -Be "security"
        }

        It "Should prioritize security over other domains" {
            $result = Get-CommentDomain -Body "Fix this vulnerability (CWE-79) with better formatting"
            $result | Should -Be "security"
        }

        It "Should prioritize bug over style" {
            $result = Get-CommentDomain -Body "This crashes the application. Also fix formatting."
            $result | Should -Be "bug"
        }

        It "Should prioritize style over general" {
            $result = Get-CommentDomain -Body "Improve the naming convention for this variable"
            $result | Should -Be "style"
        }
    }

    Context "Backward Compatibility" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should still produce standard output when GroupByDomain not specified" {
            # Standard output object should still be created
            $scriptContent | Should -Match 'Success\s*=\s*\$true'
            $scriptContent | Should -Match 'TotalComments\s*='
            $scriptContent | Should -Match 'Comments\s*=.*\$allProcessedComments'
        }

        It "Should maintain existing output properties" {
            $scriptContent | Should -Match 'ReviewCommentCount\s*='
            $scriptContent | Should -Match 'IssueCommentCount\s*='
            $scriptContent | Should -Match 'AuthorSummary\s*='
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
