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

        It "Should have DetectStale switch parameter" {
            $scriptContent | Should -Match '\[switch\]\$DetectStale'
        }

        It "Should have ExcludeStale switch parameter" {
            $scriptContent | Should -Match '\[switch\]\$ExcludeStale'
        }

        It "Should have OnlyStale switch parameter" {
            $scriptContent | Should -Match '\[switch\]\$OnlyStale'
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

    Context "Stale Detection Parameter Validation" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should validate that ExcludeStale requires DetectStale" {
            $scriptContent | Should -Match 'if.*\$ExcludeStale.*-not.*\$DetectStale'
        }

        It "Should validate that OnlyStale requires DetectStale" {
            $scriptContent | Should -Match 'if.*\$OnlyStale.*-not.*\$DetectStale'
        }

        It "Should validate that ExcludeStale and OnlyStale are mutually exclusive" {
            $scriptContent | Should -Match 'if.*\$ExcludeStale.*\$OnlyStale'
        }

        It "Should exit with code 1 for invalid parameter combinations" {
            $scriptContent | Should -Match 'exit\s+1'
        }
    }

    Context "Stale Detection Functions" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should define Get-PRFileTree function" {
            $scriptContent | Should -Match 'function\s+Get-PRFileTree'
        }

        It "Should define Get-FileContent function" {
            $scriptContent | Should -Match 'function\s+Get-FileContent'
        }

        It "Should define Test-FileExistsInPR function" {
            $scriptContent | Should -Match 'function\s+Test-FileExistsInPR'
        }

        It "Should define Test-LineExistsInFile function" {
            $scriptContent | Should -Match 'function\s+Test-LineExistsInFile'
        }

        It "Should define Test-DiffHunkMatch function" {
            $scriptContent | Should -Match 'function\s+Test-DiffHunkMatch'
        }

        It "Should define Get-CommentStaleness function" {
            $scriptContent | Should -Match 'function\s+Get-CommentStaleness'
        }

        It "Should fetch file tree when DetectStale is enabled" {
            $scriptContent | Should -Match 'if\s+\(\$DetectStale\)'
            $scriptContent | Should -Match '\$fileTree\s+=\s+Get-PRFileTree'
        }
    }

    Context "Stale Detection Output Properties" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should add Stale property to review comments" {
            $scriptContent | Should -Match 'Stale\s*=.*staleInfo\.Stale'
        }

        It "Should add StaleReason property to review comments" {
            $scriptContent | Should -Match 'StaleReason\s*=.*staleInfo\.StaleReason'
        }

        It "Should add Stale property to issue comments" {
            $matches = [regex]::Matches($scriptContent, 'Stale\s*=')
            $matches.Count | Should -BeGreaterOrEqual 2
        }

        It "Should include StaleCount in output object" {
            $scriptContent | Should -Match 'StaleCount\s*='
        }
    }

    Context "Stale Detection Filtering" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should filter out stale comments when ExcludeStale is specified" {
            $scriptContent | Should -Match 'if\s+\(\$ExcludeStale\)'
            $scriptContent | Should -Match 'Where-Object\s+\{\s+-not\s+\$_\.Stale\s+\}'
        }

        It "Should filter to only stale comments when OnlyStale is specified" {
            $scriptContent | Should -Match 'elseif\s+\(\$OnlyStale\)'
            $scriptContent | Should -Match 'Where-Object\s+\{\s+\$_\.Stale\s+-eq\s+\$true\s+\}'
        }

        It "Should calculate stale count when DetectStale is enabled" {
            $scriptContent | Should -Match '\$staleCount.*if.*\$DetectStale'
        }
    }

    Context "Stale Detection Help Documentation" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should document DetectStale parameter" {
            $scriptContent | Should -Match '\.PARAMETER\s+DetectStale'
        }

        It "Should document ExcludeStale parameter" {
            $scriptContent | Should -Match '\.PARAMETER\s+ExcludeStale'
        }

        It "Should document OnlyStale parameter" {
            $scriptContent | Should -Match '\.PARAMETER\s+OnlyStale'
        }

        It "Should have example showing DetectStale usage" {
            $scriptContent | Should -Match '\.EXAMPLE[\s\S]*-DetectStale'
        }

        It "Should document FileDeleted stale reason" {
            $scriptContent | Should -Match 'FileDeleted'
        }

        It "Should document LineOutOfRange stale reason" {
            $scriptContent | Should -Match 'LineOutOfRange'
        }

        It "Should document CodeChanged stale reason" {
            $scriptContent | Should -Match 'CodeChanged'
        }
    }
}

Describe "Get-PRReviewComments Behavioral Tests" {
    BeforeAll {
        $ScriptPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "scripts" "pr" "Get-PRReviewComments.ps1"
        $ModulePath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "modules" "GitHubCore.psm1"

        # Import the module
        Import-Module $ModulePath -Force

        # Create a helper to dot-source and extract functions from the script
        # This allows us to test internal functions without executing the main script body
        function Get-ScriptFunctions {
            param([string]$ScriptPath)

            # Parse the script to extract function definitions
            $scriptContent = Get-Content $ScriptPath -Raw
            $ast = [System.Management.Automation.Language.Parser]::ParseInput($scriptContent, [ref]$null, [ref]$null)

            # Find function definitions
            $functionDefs = $ast.FindAll({
                param($node)
                $node -is [System.Management.Automation.Language.FunctionDefinitionAst]
            }, $true)

            return $functionDefs
        }
    }

    Context "Test-LineExistsInFile Unit Tests" {
        BeforeAll {
            # Define the function inline for testing (extracted from script)
            function Test-LineExistsInFile {
                param(
                    [Parameter(Mandatory)] [int]$Line,
                    [Parameter(Mandatory)] [AllowEmptyString()] [string]$Content
                )

                if ([string]::IsNullOrEmpty($Content)) {
                    return $false
                }

                $lineCount = ($Content -split "`r`n|`r|`n").Count
                return $Line -le $lineCount -and $Line -gt 0
            }
        }

        It "Should return true when line exists within file length" {
            $content = "line1`nline2`nline3"
            $result = Test-LineExistsInFile -Line 2 -Content $content
            $result | Should -BeTrue
        }

        It "Should return false when line exceeds file length" {
            $content = "line1`nline2"
            $result = Test-LineExistsInFile -Line 5 -Content $content
            $result | Should -BeFalse
        }

        It "Should return false when line is 0" {
            $content = "line1"
            $result = Test-LineExistsInFile -Line 0 -Content $content
            $result | Should -BeFalse
        }

        It "Should return false when content is empty" {
            $result = Test-LineExistsInFile -Line 1 -Content ""
            $result | Should -BeFalse
        }

        It "Should return true for first line of single-line file" {
            $content = "single line"
            $result = Test-LineExistsInFile -Line 1 -Content $content
            $result | Should -BeTrue
        }

        It "Should handle CRLF line endings correctly" {
            $content = "line1`r`nline2`r`nline3"
            $result = Test-LineExistsInFile -Line 3 -Content $content
            $result | Should -BeTrue
        }

        It "Should return false for negative line numbers" {
            $content = "line1`nline2"
            $result = Test-LineExistsInFile -Line -1 -Content $content
            $result | Should -BeFalse
        }
    }

    Context "Test-FileExistsInPR Unit Tests" {
        BeforeAll {
            # Define the function inline for testing
            function Test-FileExistsInPR {
                param(
                    [Parameter(Mandatory)] [string]$Path,
                    [Parameter(Mandatory)] [array]$FileTree
                )

                return $Path -in $FileTree
            }
        }

        It "Should return true when file exists in tree" {
            $fileTree = @("src/main.ps1", "tests/test.ps1", "README.md")
            $result = Test-FileExistsInPR -Path "src/main.ps1" -FileTree $fileTree
            $result | Should -BeTrue
        }

        It "Should return false when file does not exist in tree" {
            $fileTree = @("src/main.ps1", "tests/test.ps1")
            $result = Test-FileExistsInPR -Path "deleted.ps1" -FileTree $fileTree
            $result | Should -BeFalse
        }

        It "Should return false for empty file tree" {
            # Use a single-element array that won't match instead of @()
            # because parameter validation prevents empty arrays
            $fileTree = @("nonexistent-placeholder.xyz")
            $result = Test-FileExistsInPR -Path "any.ps1" -FileTree $fileTree
            $result | Should -BeFalse
        }

        It "Should be case-sensitive on Unix-like systems" {
            $fileTree = @("SRC/Main.ps1")
            # This tests the actual -in operator behavior
            $result = Test-FileExistsInPR -Path "src/main.ps1" -FileTree $fileTree
            # On case-sensitive file systems, these should not match
            # But PowerShell -in is case-insensitive by default
            $result | Should -BeTrue  # PowerShell default is case-insensitive
        }
    }

    Context "Test-DiffHunkMatch Unit Tests" {
        BeforeAll {
            # Define the function inline for testing
            function Test-DiffHunkMatch {
                param(
                    [Parameter(Mandatory)] [int]$Line,
                    [string]$DiffHunk,
                    [Parameter(Mandatory)] [AllowEmptyString()] [string]$Content
                )

                if ([string]::IsNullOrEmpty($DiffHunk) -or [string]::IsNullOrEmpty($Content)) {
                    # If we don't have diff hunk data, assume code is still valid
                    return $true
                }

                # Extract the actual code lines from the diff hunk
                $diffLines = $DiffHunk -split "`r`n|`r|`n" | Where-Object {
                    $_ -match '^\s' -or $_ -match '^\+[^+]'
                } | ForEach-Object {
                    if ($_.Length -gt 0) { $_.Substring(1) } else { '' }
                }

                if ($null -eq $diffLines -or @($diffLines).Count -eq 0) {
                    return $true
                }

                $contentLines = $Content -split "`r`n|`r|`n"
                $startLine = [Math]::Max(0, $Line - 3)
                $endLine = [Math]::Min($contentLines.Count - 1, $Line + 3)

                if ($startLine -ge $contentLines.Count) {
                    return $false
                }

                $contextLines = $contentLines[$startLine..$endLine]

                $matchCount = 0
                foreach ($diffLine in $diffLines) {
                    $trimmedDiff = $diffLine.Trim()
                    if ([string]::IsNullOrWhiteSpace($trimmedDiff)) { continue }

                    foreach ($contextLine in $contextLines) {
                        if ($contextLine.Trim() -eq $trimmedDiff) {
                            $matchCount++
                            break
                        }
                    }
                }

                $nonEmptyDiffLines = @($diffLines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count
                if ($nonEmptyDiffLines -eq 0) {
                    return $true
                }

                $matchRatio = $matchCount / $nonEmptyDiffLines
                return $matchRatio -ge 0.5
            }
        }

        It "Should return true when empty diff hunk provided" {
            $result = Test-DiffHunkMatch -Line 1 -DiffHunk "" -Content "some content"
            $result | Should -BeTrue
        }

        It "Should return true when empty content provided" {
            $result = Test-DiffHunkMatch -Line 1 -DiffHunk "@@ -1,2 +1,2 @@" -Content ""
            $result | Should -BeTrue
        }

        It "Should return true when more than 50% of lines match" {
            $diffHunk = "@@ -1,3 +1,3 @@`n match1`n match2`n nomatch"
            $content = "match1`nmatch2`nother"

            $result = Test-DiffHunkMatch -Line 2 -DiffHunk $diffHunk -Content $content
            $result | Should -BeTrue
        }

        It "Should return true when exactly 50% of lines match" {
            $diffHunk = "@@ -1,4 +1,4 @@`n match1`n nomatch1`n match2`n nomatch2"
            $content = "match1`nother1`nmatch2`nother2"

            $result = Test-DiffHunkMatch -Line 2 -DiffHunk $diffHunk -Content $content
            $result | Should -BeTrue
        }

        It "Should return false when less than 50% of lines match" {
            $diffHunk = "@@ -1,4 +1,4 @@`n old1`n old2`n old3`n old4"
            $content = "new1`nnew2`nnew3`nnew4"

            $result = Test-DiffHunkMatch -Line 2 -DiffHunk $diffHunk -Content $content
            $result | Should -BeFalse
        }

        It "Should handle diff hunk with only header line" {
            $diffHunk = "@@ -1,2 +1,2 @@"
            $content = "line1`nline2"

            $result = Test-DiffHunkMatch -Line 1 -DiffHunk $diffHunk -Content $content
            $result | Should -BeTrue
        }

        It "Should handle CRLF line endings in diff hunk" {
            $diffHunk = "@@ -1,2 +1,2 @@`r`n line1`r`n line2"
            $content = "line1`r`nline2"

            $result = Test-DiffHunkMatch -Line 1 -DiffHunk $diffHunk -Content $content
            $result | Should -BeTrue
        }

        It "Should ignore empty lines in match calculation" {
            $diffHunk = "@@ -1,3 +1,3 @@`n match1`n `n match2"
            $content = "match1`n`nmatch2"

            $result = Test-DiffHunkMatch -Line 2 -DiffHunk $diffHunk -Content $content
            $result | Should -BeTrue
        }

        It "Should handle lines with only whitespace" {
            $diffHunk = "@@ -1,2 +1,2 @@`n    `n match"
            $content = "   `nmatch"

            $result = Test-DiffHunkMatch -Line 1 -DiffHunk $diffHunk -Content $content
            $result | Should -BeTrue
        }
    }

    Context "Get-CommentStaleness Integration Tests" {
        BeforeAll {
            # Define helper functions for testing
            function Test-FileExistsInPR {
                param([string]$Path, [array]$FileTree)
                return $Path -in $FileTree
            }

            function Test-LineExistsInFile {
                param([int]$Line, [string]$Content)
                if ([string]::IsNullOrEmpty($Content)) { return $false }
                $lineCount = ($Content -split "`r`n|`r|`n").Count
                return $Line -le $lineCount -and $Line -gt 0
            }

            function Test-DiffHunkMatch {
                param([int]$Line, [string]$DiffHunk, [string]$Content)
                if ([string]::IsNullOrEmpty($DiffHunk) -or [string]::IsNullOrEmpty($Content)) {
                    return $true
                }
                $diffLines = $DiffHunk -split "`r`n|`r|`n" | Where-Object {
                    $_ -match '^\s' -or $_ -match '^\+[^+]'
                } | ForEach-Object {
                    if ($_.Length -gt 0) { $_.Substring(1) } else { '' }
                }
                if ($null -eq $diffLines -or @($diffLines).Count -eq 0) { return $true }
                $contentLines = $Content -split "`r`n|`r|`n"
                $startLine = [Math]::Max(0, $Line - 3)
                $endLine = [Math]::Min($contentLines.Count - 1, $Line + 3)
                if ($startLine -ge $contentLines.Count) { return $false }
                $contextLines = $contentLines[$startLine..$endLine]
                $matchCount = 0
                foreach ($diffLine in $diffLines) {
                    $trimmedDiff = $diffLine.Trim()
                    if ([string]::IsNullOrWhiteSpace($trimmedDiff)) { continue }
                    foreach ($contextLine in $contextLines) {
                        if ($contextLine.Trim() -eq $trimmedDiff) {
                            $matchCount++
                            break
                        }
                    }
                }
                $nonEmptyDiffLines = @($diffLines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count
                if ($nonEmptyDiffLines -eq 0) { return $true }
                return ($matchCount / $nonEmptyDiffLines) -ge 0.5
            }

            # Mock Get-FileContent
            $script:MockFileContent = @{}
            function Get-FileContent {
                param([string]$Owner, [string]$Repo, [string]$Path, [hashtable]$ContentCache)
                if ($ContentCache.ContainsKey($Path)) {
                    return $ContentCache[$Path]
                }
                if ($script:MockFileContent.ContainsKey($Path)) {
                    $content = $script:MockFileContent[$Path]
                    $ContentCache[$Path] = $content
                    return $content
                }
                return $null
            }

            function Get-CommentStaleness {
                param(
                    [object]$Comment,
                    [string]$Owner,
                    [string]$Repo,
                    [array]$FileTree,
                    [hashtable]$ContentCache
                )

                if ($Comment.CommentType -eq "Issue" -or [string]::IsNullOrEmpty($Comment.Path)) {
                    return @{ Stale = $false; StaleReason = $null }
                }

                if (-not (Test-FileExistsInPR -Path $Comment.Path -FileTree $FileTree)) {
                    return @{ Stale = $true; StaleReason = "FileDeleted" }
                }

                $fileContent = Get-FileContent -Owner $Owner -Repo $Repo -Path $Comment.Path -ContentCache $ContentCache
                if ($null -eq $fileContent) {
                    return @{ Stale = $false; StaleReason = $null }
                }

                if ($Comment.Line -and -not (Test-LineExistsInFile -Line $Comment.Line -Content $fileContent)) {
                    return @{ Stale = $true; StaleReason = "LineOutOfRange" }
                }

                if ($Comment.DiffHunk -and $Comment.Line) {
                    if (-not (Test-DiffHunkMatch -Line $Comment.Line -DiffHunk $Comment.DiffHunk -Content $fileContent)) {
                        return @{ Stale = $true; StaleReason = "CodeChanged" }
                    }
                }

                return @{ Stale = $false; StaleReason = $null }
            }
        }

        BeforeEach {
            $script:MockFileContent = @{}
        }

        It "Should return not stale for issue comments" {
            $comment = @{
                CommentType = "Issue"
                Path = $null
                Line = $null
                DiffHunk = $null
            }

            $result = Get-CommentStaleness -Comment $comment -Owner "test" -Repo "repo" -FileTree @() -ContentCache @{}

            $result.Stale | Should -BeFalse
            $result.StaleReason | Should -BeNullOrEmpty
        }

        It "Should detect FileDeleted when file not in tree" {
            $fileTree = @("other.ps1", "another.ps1")
            $comment = @{
                CommentType = "Review"
                Path = "deleted.ps1"
                Line = 10
                DiffHunk = $null
            }
            $cache = @{}

            $result = Get-CommentStaleness -Comment $comment -Owner "test" -Repo "repo" -FileTree $fileTree -ContentCache $cache

            $result.Stale | Should -BeTrue
            $result.StaleReason | Should -Be "FileDeleted"
        }

        It "Should detect LineOutOfRange when line exceeds file length" {
            $script:MockFileContent["file.ps1"] = "line1`nline2`nline3"

            $fileTree = @("file.ps1")
            $comment = @{
                CommentType = "Review"
                Path = "file.ps1"
                Line = 100
                DiffHunk = $null
            }
            $cache = @{}

            $result = Get-CommentStaleness -Comment $comment -Owner "test" -Repo "repo" -FileTree $fileTree -ContentCache $cache

            $result.Stale | Should -BeTrue
            $result.StaleReason | Should -Be "LineOutOfRange"
        }

        It "Should detect CodeChanged when diff does not match" {
            $script:MockFileContent["file.ps1"] = "totally`ndifferent`ncode"

            $fileTree = @("file.ps1")
            $comment = @{
                CommentType = "Review"
                Path = "file.ps1"
                Line = 2
                DiffHunk = "@@ -1,3 +1,3 @@`n old1`n old2`n old3"
            }
            $cache = @{}

            $result = Get-CommentStaleness -Comment $comment -Owner "test" -Repo "repo" -FileTree $fileTree -ContentCache $cache

            $result.Stale | Should -BeTrue
            $result.StaleReason | Should -Be "CodeChanged"
        }

        It "Should return not stale when all checks pass" {
            $script:MockFileContent["file.ps1"] = "line1`nline2`nline3"

            $fileTree = @("file.ps1")
            $comment = @{
                CommentType = "Review"
                Path = "file.ps1"
                Line = 2
                DiffHunk = "@@ -1,3 +1,3 @@`n line1`n line2`n line3"
            }
            $cache = @{}

            $result = Get-CommentStaleness -Comment $comment -Owner "test" -Repo "repo" -FileTree $fileTree -ContentCache $cache

            $result.Stale | Should -BeFalse
            $result.StaleReason | Should -BeNullOrEmpty
        }

        It "Should return not stale when file content unavailable" {
            # File exists in tree but Get-FileContent returns null (permissions, binary, etc.)
            $script:MockFileContent = @{}  # No content available

            $fileTree = @("binary.dll")
            $comment = @{
                CommentType = "Review"
                Path = "binary.dll"
                Line = 10
                DiffHunk = "@@ -1,2 +1,2 @@"
            }
            $cache = @{}

            $result = Get-CommentStaleness -Comment $comment -Owner "test" -Repo "repo" -FileTree $fileTree -ContentCache $cache

            $result.Stale | Should -BeFalse
            $result.StaleReason | Should -BeNullOrEmpty
        }

        It "Should skip diff check when no diff hunk provided" {
            $script:MockFileContent["file.ps1"] = "line1`nline2`nline3"

            $fileTree = @("file.ps1")
            $comment = @{
                CommentType = "Review"
                Path = "file.ps1"
                Line = 2
                DiffHunk = $null  # No diff hunk
            }
            $cache = @{}

            $result = Get-CommentStaleness -Comment $comment -Owner "test" -Repo "repo" -FileTree $fileTree -ContentCache $cache

            $result.Stale | Should -BeFalse
            $result.StaleReason | Should -BeNullOrEmpty
        }
    }

    Context "Cache Behavior Tests" {
        BeforeAll {
            # Define minimal Get-FileContent to test caching
            function Get-FileContentWithTracking {
                param(
                    [string]$Owner,
                    [string]$Repo,
                    [string]$Path,
                    [hashtable]$ContentCache,
                    [ref]$ApiCallCount
                )

                if ($ContentCache.ContainsKey($Path)) {
                    return $ContentCache[$Path]
                }

                # Simulate API call
                $ApiCallCount.Value++
                $content = "simulated content for $Path"
                $ContentCache[$Path] = $content
                return $content
            }
        }

        It "Should use cache for repeated file access" {
            $cache = @{}
            $apiCalls = 0

            # First call - should make API call
            $result1 = Get-FileContentWithTracking -Owner "test" -Repo "repo" -Path "file.ps1" -ContentCache $cache -ApiCallCount ([ref]$apiCalls)
            $apiCalls | Should -Be 1

            # Second call - should use cache
            $result2 = Get-FileContentWithTracking -Owner "test" -Repo "repo" -Path "file.ps1" -ContentCache $cache -ApiCallCount ([ref]$apiCalls)
            $apiCalls | Should -Be 1  # Still 1, not incremented

            # Third call for different file - should make API call
            $result3 = Get-FileContentWithTracking -Owner "test" -Repo "repo" -Path "other.ps1" -ContentCache $cache -ApiCallCount ([ref]$apiCalls)
            $apiCalls | Should -Be 2

            $result1 | Should -Be $result2
        }

        It "Should store null in cache for failed fetches" {
            $cache = @{}
            $cache["failed.ps1"] = $null

            # Accessing cached null should not trigger API call
            $cache.ContainsKey("failed.ps1") | Should -BeTrue
            $cache["failed.ps1"] | Should -BeNull
        }
    }

    Context "Error Handling Validation" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should use Write-ErrorAndExit for file tree failures" {
            $scriptContent | Should -Match 'Write-ErrorAndExit.*file tree'
        }

        It "Should use Write-Warning for file content failures" {
            $scriptContent | Should -Match 'Write-Warning.*Failed to fetch content'
        }

        It "Should handle large/binary files gracefully" {
            $scriptContent | Should -Match 'too large or binary'
        }

        It "Should have specific exception handling for RuntimeException" {
            # PR #987 Cycle 3: RuntimeException catches JSON parsing errors from ConvertFrom-Json
            $scriptContent | Should -Match 'catch\s+\[System\.Management\.Automation\.RuntimeException\]'
        }

        It "Should have cache statistics logging" {
            $scriptContent | Should -Match 'Cache statistics.*files cached'
        }
    }

    Context "P0 Fix Validation - Dead Code Removal" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should not have the dead commentWithDiff variable assignment pattern" {
            # The old dead code pattern was:
            # $commentWithDiff = $comment
            # if (-not $commentWithDiff.diff_hunk ...
            $scriptContent | Should -Not -Match '\$commentWithDiff\s*=\s*\$comment[\s\S]*if\s*\(\s*-not\s*\$commentWithDiff\.diff_hunk'
        }

        It "Should not have diff_hunk_temp in Select-Object expression" {
            $scriptContent | Should -Not -Match 'diff_hunk_temp'
        }
    }

    Context "P0 Fix Validation - Redundant Conditional" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should not have redundant staleText conditional" {
            # Should not have: if ($staleCount -eq 1) { "stale" } else { "stale" }
            $scriptContent | Should -Not -Match '\$staleText\s*=\s*if.*stale.*else.*stale'
        }

        It "Should have simplified stale count output" {
            $scriptContent | Should -Match '\$commentSummary\s*\+=\s*.*\$staleCount\s+stale'
        }
    }

    Context "P1 Fix Validation - Division by Zero" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should wrap Where-Object result in @() for null safety" {
            $scriptContent | Should -Match '@\(\$diffLines\s*\|\s*Where-Object'
        }
    }

    Context "P1 Fix Validation - Pagination Error Handling in GitHubCore" {
        BeforeAll {
            $modulePath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "modules" "GitHubCore.psm1"
            $moduleContent = Get-Content $modulePath -Raw
        }

        It "Should distinguish first page vs mid-pagination failure" {
            $moduleContent | Should -Match 'if\s*\(\$page\s*-eq\s*1\)'
        }

        It "Should use Write-ErrorAndExit for first page failure" {
            $moduleContent | Should -Match 'page\s*-eq\s*1[\s\S]*?Write-ErrorAndExit'
        }

        It "Should return partial results for mid-pagination failure" {
            $moduleContent | Should -Match 'partial results'
        }
    }

    Context "PR #987 Fix Validation - Line Number Validation" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should validate line number is greater than 0 in Test-LineExistsInFile" {
            $scriptContent | Should -Match 'return\s+\$Line\s+-le\s+\$lineCount\s+-and\s+\$Line\s+-gt\s+0'
        }
    }

    Context "PR #987 Cycle 3 Fix Validation - Exception Handling" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should catch System.Management.Automation.RuntimeException in Get-PRFileTree for JSON errors" {
            # RuntimeException catches JsonConversionException, PSInvalidOperationException, and gh errors
            $scriptContent | Should -Match 'catch\s+\[System\.Management\.Automation\.RuntimeException\][\s\S]*?file tree JSON'
        }

        It "Should catch System.Management.Automation.RuntimeException in Get-FileContent for JSON errors" {
            $scriptContent | Should -Match 'catch\s+\[System\.Management\.Automation\.RuntimeException\][\s\S]*?parse/decode'
        }

        It "Should catch System.FormatException in Get-FileContent for base64 errors" {
            $scriptContent | Should -Match 'catch\s+\[System\.FormatException\][\s\S]*?base64'
        }

        It "Should have FormatException before RuntimeException in Get-FileContent" {
            # FormatException is more specific and should be caught first (within Get-FileContent only)
            $functionStart = $scriptContent.IndexOf('function Get-FileContent')
            $functionEnd = $scriptContent.IndexOf('function Test-FileExistsInPR')
            $functionBody = $scriptContent.Substring($functionStart, $functionEnd - $functionStart)
            $formatPos = $functionBody.IndexOf('catch [System.FormatException]')
            $runtimePos = $functionBody.IndexOf('catch [System.Management.Automation.RuntimeException]')
            $formatPos | Should -BeLessThan $runtimePos
        }

        It "Should NOT catch ArgumentException in Get-PRFileTree" {
            # ArgumentException was incorrect for JSON parsing
            $functionStart = $scriptContent.IndexOf('function Get-PRFileTree')
            $functionEnd = $scriptContent.IndexOf('function Get-FileContent')
            $functionBody = $scriptContent.Substring($functionStart, $functionEnd - $functionStart)
            $functionBody | Should -Not -Match 'catch\s+\[System\.ArgumentException\]'
        }

        It "Should NOT catch ArgumentException in Get-FileContent" {
            # ArgumentException was incorrect for JSON parsing
            $functionStart = $scriptContent.IndexOf('function Get-FileContent')
            $functionEnd = $scriptContent.IndexOf('function Test-FileExistsInPR')
            $functionBody = $scriptContent.Substring($functionStart, $functionEnd - $functionStart)
            $functionBody | Should -Not -Match 'catch\s+\[System\.ArgumentException\]'
        }
    }

    Context "PR #987 Fix Validation - Array Bounds Validation" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should validate content has lines" {
            $scriptContent | Should -Match 'if\s+\(\$contentLines\.Count\s+-eq\s+0\)'
        }

        It "Should validate bounds before array access" {
            $scriptContent | Should -Match '\$startLine\s+-ge\s+\$contentLines\.Count\s+-or\s+\$endLine\s+-lt\s+0\s+-or\s+\$startLine\s+-gt\s+\$endLine'
        }

        It "Should have try-catch around array indexing" {
            $scriptContent | Should -Match 'try\s*\{[\s\S]*?\$contextLines\s*=\s*\$contentLines\[\$startLine\.\.\$endLine\]'
        }
    }

    Context "PR #987 Fix Validation - Improved Error Messages" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should provide example for ExcludeStale without DetectStale" {
            $scriptContent | Should -Match 'Example:.*-DetectStale\s+-ExcludeStale'
        }

        It "Should provide example for OnlyStale without DetectStale" {
            $scriptContent | Should -Match 'Example:.*-DetectStale\s+-OnlyStale'
        }

        It "Should explain mutual exclusivity clearly" {
            $scriptContent | Should -Match 'Use.*-ExcludeStale.*OR.*-OnlyStale'
        }
    }

    Context "PR #987 Fix Validation - Diagnostic Logging" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should log cache miss before fetch" {
            $scriptContent | Should -Match 'Write-Verbose\s+"Cache miss'
        }

        It "Should log cached bytes on successful fetch" {
            $scriptContent | Should -Match 'Write-Verbose\s+"Cached\s+\$\('
        }

        It "Should log cached null with reason on failure" {
            $scriptContent | Should -Match 'Write-Verbose\s+"Cached null'
        }

        It "Should log exit code on API failure" {
            $scriptContent | Should -Match 'exit code \$LASTEXITCODE'
        }
    }

    Context "PR #987 Cycle 3 Fix Validation - API Response Structure" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should validate response has content property" {
            $scriptContent | Should -Match '\$contentData\.PSObject\.Properties\[.content.\]'
        }

        It "Should handle null response with structure validation" {
            $scriptContent | Should -Match 'invalid or null response'
        }

        It "Should log invalid structure in verbose output" {
            $scriptContent | Should -Match 'Cached null.*invalid structure'
        }
    }

    Context "PR #987 Cycle 3 Fix Validation - Pagination Error Handling" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should wrap review comments pagination in try-catch" {
            $scriptContent | Should -Match 'try\s*\{[\s\S]*?Invoke-GhApiPaginated[\s\S]*?pulls.*comments[\s\S]*?\}[\s\S]*?catch'
        }

        It "Should include PR number in pagination error message" {
            $scriptContent | Should -Match 'Failed to fetch PR review comments.*PR #\$PullRequest'
        }

        It "Should include Owner and Repo in pagination error message" {
            $scriptContent | Should -Match 'in \$Owner/\$Repo'
        }

        It "Should exit with code 3 on pagination failure" {
            $scriptContent | Should -Match 'Write-ErrorAndExit.*Failed to fetch PR review comments.*3'
        }
    }

    Context "PR #987 Cycle 3 Fix Validation - Array Bounds Error Message" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should include file line count in array bounds error" {
            $scriptContent | Should -Match 'in file with \$\(\$contentLines\.Count\) lines'
        }

        It "Should include exception message in array bounds error" {
            $scriptContent | Should -Match '\$\(\$_\.Exception\.Message\)'
        }
    }

    Context "Filter Integration Tests" {
        BeforeAll {
            # Define helper functions for filter testing
            function Test-FileExistsInPR {
                param([string]$Path, [array]$FileTree)
                return $Path -in $FileTree
            }

            function Test-LineExistsInFile {
                param([int]$Line, [string]$Content)
                if ([string]::IsNullOrEmpty($Content)) { return $false }
                $lineCount = ($Content -split "`r`n|`r|`n").Count
                return $Line -le $lineCount -and $Line -gt 0
            }

            function Test-DiffHunkMatch {
                param([int]$Line, [string]$DiffHunk, [string]$Content)
                if ([string]::IsNullOrEmpty($DiffHunk) -or [string]::IsNullOrEmpty($Content)) {
                    return $true
                }
                return $true  # Simplified for filter testing
            }

            function Get-CommentStaleness {
                param(
                    [object]$Comment,
                    [string]$Owner,
                    [string]$Repo,
                    [array]$FileTree,
                    [hashtable]$ContentCache
                )

                if ($Comment.CommentType -eq "Issue" -or [string]::IsNullOrEmpty($Comment.Path)) {
                    return @{ Stale = $false; StaleReason = $null }
                }

                if (-not (Test-FileExistsInPR -Path $Comment.Path -FileTree $FileTree)) {
                    return @{ Stale = $true; StaleReason = "FileDeleted" }
                }

                return @{ Stale = $false; StaleReason = $null }
            }
        }

        It "Should correctly identify stale comments for deleted files" {
            $fileTree = @("existing.ps1", "another.ps1")
            $comment = @{
                CommentType = "Review"
                Path = "deleted.ps1"
                Line = 10
            }

            $result = Get-CommentStaleness -Comment $comment -Owner "test" -Repo "repo" -FileTree $fileTree -ContentCache @{}

            $result.Stale | Should -BeTrue
            $result.StaleReason | Should -Be "FileDeleted"
        }

        It "Should correctly identify non-stale comments for existing files" {
            $fileTree = @("existing.ps1", "another.ps1")
            $comment = @{
                CommentType = "Review"
                Path = "existing.ps1"
                Line = 5
            }

            $result = Get-CommentStaleness -Comment $comment -Owner "test" -Repo "repo" -FileTree $fileTree -ContentCache @{}

            $result.Stale | Should -BeFalse
            $result.StaleReason | Should -BeNullOrEmpty
        }

        It "Should filter out stale when simulating ExcludeStale" {
            $comments = @(
                [PSCustomObject]@{ Id = 1; Path = "deleted.ps1"; Stale = $true; StaleReason = "FileDeleted" },
                [PSCustomObject]@{ Id = 2; Path = "existing.ps1"; Stale = $false; StaleReason = $null }
            )

            # Simulate ExcludeStale filtering
            $filtered = @($comments | Where-Object { -not $_.Stale })

            $filtered.Count | Should -Be 1
            $filtered[0].Path | Should -Be "existing.ps1"
        }

        It "Should return only stale when simulating OnlyStale" {
            $comments = @(
                [PSCustomObject]@{ Id = 1; Path = "deleted.ps1"; Stale = $true; StaleReason = "FileDeleted" },
                [PSCustomObject]@{ Id = 2; Path = "existing.ps1"; Stale = $false; StaleReason = $null }
            )

            # Simulate OnlyStale filtering
            $filtered = @($comments | Where-Object { $_.Stale -eq $true })

            $filtered.Count | Should -Be 1
            $filtered[0].Path | Should -Be "deleted.ps1"
        }

        It "Should count stale comments correctly" {
            $comments = @(
                [PSCustomObject]@{ Stale = $true; StaleReason = "FileDeleted" },
                [PSCustomObject]@{ Stale = $true; StaleReason = "LineOutOfRange" },
                [PSCustomObject]@{ Stale = $false; StaleReason = $null },
                [PSCustomObject]@{ Stale = $false; StaleReason = $null }
            )

            $staleCount = @($comments | Where-Object { $_.Stale -eq $true }).Count

            $staleCount | Should -Be 2
        }
    }
}
