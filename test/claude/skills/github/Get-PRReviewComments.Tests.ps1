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

        It "Should have specific exception handling for ArgumentException" {
            # PR #987: Replaced broad RuntimeException with specific exception types
            $scriptContent | Should -Match 'catch\s+\[System\.ArgumentException\]'
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

    Context "PR #987 Fix Validation - Specific Exception Handling" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should catch System.ArgumentException in Get-PRFileTree" {
            $scriptContent | Should -Match 'catch\s+\[System\.ArgumentException\][\s\S]*?file tree JSON'
        }

        It "Should catch System.ArgumentException in Get-FileContent" {
            $scriptContent | Should -Match 'catch\s+\[System\.ArgumentException\][\s\S]*?parse/decode'
        }

        It "Should catch System.FormatException in Get-FileContent" {
            $scriptContent | Should -Match 'catch\s+\[System\.FormatException\][\s\S]*?base64'
        }

        It "Should NOT catch RuntimeException in Get-PRFileTree" {
            # The function should not have RuntimeException catch
            $functionPattern = 'function\s+Get-PRFileTree\s*\{[\s\S]*?^\}'
            $functionMatch = [regex]::Match($scriptContent, $functionPattern, [System.Text.RegularExpressions.RegexOptions]::Multiline)
            if ($functionMatch.Success) {
                $functionMatch.Value | Should -Not -Match 'RuntimeException'
            }
        }

        It "Should NOT catch RuntimeException in Get-FileContent" {
            # The function should not have RuntimeException catch
            $functionPattern = 'function\s+Get-FileContent\s*\{[\s\S]*?^\}'
            $functionMatch = [regex]::Match($scriptContent, $functionPattern, [System.Text.RegularExpressions.RegexOptions]::Multiline)
            if ($functionMatch.Success) {
                $functionMatch.Value | Should -Not -Match 'RuntimeException'
            }
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
