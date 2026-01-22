<#
.SYNOPSIS
    Gets all comments for a GitHub Pull Request with pagination and stale comment detection.

.DESCRIPTION
    Retrieves PR review comments (code-level) and optionally issue comments (PR-level)
    with full pagination support. Can detect stale comments that reference deleted files,
    out-of-range lines, or changed code.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER PullRequest
    PR number (required).

.PARAMETER Author
    Optional filter by author login name.

.PARAMETER IncludeDiffHunk
    If specified, includes the diff context for each review comment.

.PARAMETER IncludeIssueComments
    If specified, also fetches issue comments (top-level PR comments like AI Quality Gate).
    These are comments posted via /issues/{n}/comments API, not code-level review comments.

.PARAMETER DetectStale
    If specified, analyzes each review comment to determine if it references deleted files,
    out-of-range lines, or changed code. Adds Stale and StaleReason properties to comments.

    Stale reasons:
    - FileDeleted: Comment references a file that no longer exists in HEAD
    - LineOutOfRange: Comment line number exceeds current file length
    - CodeChanged: Diff hunk context no longer matches current code

.PARAMETER ExcludeStale
    If specified with -DetectStale, filters out stale comments from results.
    Cannot be used with -OnlyStale.

.PARAMETER OnlyStale
    If specified with -DetectStale, returns only stale comments.
    Cannot be used with -ExcludeStale. Useful for PR cleanup.

.EXAMPLE
    .\Get-PRReviewComments.ps1 -PullRequest 50
    Get all review comments for PR #50

.EXAMPLE
    .\Get-PRReviewComments.ps1 -PullRequest 50 -IncludeIssueComments
    Get all review and issue comments for PR #50

.EXAMPLE
    .\Get-PRReviewComments.ps1 -PullRequest 50 -Author "cursor[bot]"
    Get only comments from cursor[bot] for PR #50

.EXAMPLE
    .\Get-PRReviewComments.ps1 -PullRequest 908 -DetectStale
    Detect stale comments on PR #908 and include Stale/StaleReason properties

.EXAMPLE
    .\Get-PRReviewComments.ps1 -PullRequest 908 -DetectStale -ExcludeStale
    Get active comments only, excluding stale ones (recommended for response workflow)

.EXAMPLE
    .\Get-PRReviewComments.ps1 -PullRequest 908 -DetectStale -OnlyStale
    Get only stale comments for cleanup and resolution

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 2=Not found, 3=API error, 4=Not authenticated

    Stale Detection Performance:
    - Makes 1 API call to fetch file tree (cached for all comments)
    - Makes 1 API call per unique file path (cached)
    - Use -Verbose to see cache hit statistics

    See: ADR-035 Exit Code Standardization
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)] [int]$PullRequest,
    [string]$Author,
    [switch]$IncludeDiffHunk,
    [switch]$IncludeIssueComments,
    [switch]$DetectStale,
    [switch]$ExcludeStale,
    [switch]$OnlyStale
)

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1") -Force

# Validate parameter combinations
if ($ExcludeStale -and -not $DetectStale) {
    Write-Error "-ExcludeStale filters stale comments, but stale detection is disabled. Add -DetectStale to enable detection."
    Write-Host "Example: Get-PRReviewComments.ps1 -PullRequest $PullRequest -DetectStale -ExcludeStale" -ForegroundColor Yellow
    exit 1
}
if ($OnlyStale -and -not $DetectStale) {
    Write-Error "-OnlyStale returns only stale comments, but stale detection is disabled. Add -DetectStale to enable detection."
    Write-Host "Example: Get-PRReviewComments.ps1 -PullRequest $PullRequest -DetectStale -OnlyStale" -ForegroundColor Yellow
    exit 1
}
if ($ExcludeStale -and $OnlyStale) {
    Write-Error "-ExcludeStale and -OnlyStale are mutually exclusive."
    Write-Host "Use -DetectStale -ExcludeStale to hide stale, OR -DetectStale -OnlyStale to show only stale." -ForegroundColor Yellow
    exit 1
}

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

#region Stale Detection Helper Functions

function Get-PRFileTree {
    <#
    .SYNOPSIS
        Fetches and caches the file tree for the PR's HEAD commit.
    #>
    param(
        [Parameter(Mandatory)] [string]$Owner,
        [Parameter(Mandatory)] [string]$Repo
    )

    Write-Verbose "Fetching file tree for HEAD"
    try {
        $treeData = gh api "repos/$Owner/$Repo/git/trees/HEAD?recursive=1" 2>&1 | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorAndExit "Failed to fetch file tree from GitHub API. Cannot perform stale detection. Error: $treeData" 3
        }

        # Validate response structure
        if ($null -eq $treeData -or $null -eq $treeData.tree) {
            Write-ErrorAndExit "GitHub API returned invalid file tree structure. Cannot perform stale detection." 3
        }

        return $treeData.tree | Where-Object { $_.type -eq "blob" } | ForEach-Object { $_.path }
    }
    catch [System.ArgumentException] {
        # Specific: JSON parsing failed from ConvertFrom-Json
        Write-ErrorAndExit "Failed to parse file tree JSON from GitHub API: $_" 3
    }
    # Let unexpected errors propagate for debugging
}

function Get-FileContent {
    <#
    .SYNOPSIS
        Fetches and caches file content from HEAD.
    #>
    param(
        [Parameter(Mandatory)] [string]$Owner,
        [Parameter(Mandatory)] [string]$Repo,
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [hashtable]$ContentCache
    )

    if ($ContentCache.ContainsKey($Path)) {
        Write-Verbose "Cache hit for $Path"
        return $ContentCache[$Path]
    }

    Write-Verbose "Cache miss - fetching content for $Path"
    try {
        $encodedPath = [System.Uri]::EscapeDataString($Path)
        $contentData = gh api "repos/$Owner/$Repo/contents/$encodedPath`?ref=HEAD" 2>&1 | ConvertFrom-Json

        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Failed to fetch content for file '$Path' from GitHub API (exit code $LASTEXITCODE). Skipping line/diff checks. Error: $contentData"
            Write-Verbose "Cached null for $Path (API failure)"
            $ContentCache[$Path] = $null
            return $null
        }

        # Validate response exists
        if ($null -eq $contentData) {
            Write-Warning "GitHub API returned null response for file '$Path'. Skipping line/diff checks."
            Write-Verbose "Cached null for $Path (null response)"
            $ContentCache[$Path] = $null
            return $null
        }

        # Handle large files or binary files that don't have base64 content
        if ([string]::IsNullOrEmpty($contentData.content)) {
            Write-Verbose "File content not available via contents API (too large or binary): $Path"
            Write-Verbose "Cached null for $Path (no content)"
            $ContentCache[$Path] = $null
            return $null
        }

        # Decode base64 content
        $decodedContent = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($contentData.content))
        $ContentCache[$Path] = $decodedContent
        Write-Verbose "Cached $($decodedContent.Length) bytes for $Path"
        return $decodedContent
    }
    catch [System.ArgumentException] {
        # Specific: JSON parsing or base64 decode failed
        Write-Warning "Failed to parse/decode content for file '$Path': $_"
        Write-Verbose "Cached null for $Path (parse error)"
        $ContentCache[$Path] = $null
        return $null
    }
    catch [System.FormatException] {
        # Specific: Base64 decode format error
        Write-Warning "File '$Path' contains invalid base64 content. Likely binary or corrupted."
        Write-Verbose "Cached null for $Path (base64 error)"
        $ContentCache[$Path] = $null
        return $null
    }
    # Let unexpected errors propagate for debugging
}

function Test-FileExistsInPR {
    <#
    .SYNOPSIS
        Checks if a file exists in the PR's current HEAD.
    #>
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [array]$FileTree
    )

    return $Path -in $FileTree
}

function Test-LineExistsInFile {
    <#
    .SYNOPSIS
        Checks if a line number exists in the current file content.
    #>
    param(
        [Parameter(Mandatory)] [int]$Line,
        [Parameter(Mandatory)] [string]$Content
    )

    if ([string]::IsNullOrEmpty($Content)) {
        return $false
    }

    $lineCount = ($Content -split "`r`n|`r|`n").Count
    return $Line -le $lineCount -and $Line -gt 0
}

function Test-DiffHunkMatch {
    <#
    .SYNOPSIS
        Checks if the diff hunk context still matches the current file content.
    #>
    param(
        [Parameter(Mandatory)] [int]$Line,
        [string]$DiffHunk,
        [Parameter(Mandatory)] [string]$Content
    )

    if ([string]::IsNullOrEmpty($DiffHunk) -or [string]::IsNullOrEmpty($Content)) {
        # If we don't have diff hunk data, assume code is still valid (conservative approach to avoid false positives)
        return $true
    }

    # Extract the actual code lines from the diff hunk (lines starting with ' ' or '+')
    $diffLines = $DiffHunk -split "`r`n|`r|`n" | Where-Object {
        $_ -match '^\s' -or $_ -match '^\+[^+]'
    } | ForEach-Object {
        # Remove the diff marker (first character)
        if ($_.Length -gt 0) { $_.Substring(1) } else { '' }
    }

    if ($diffLines.Count -eq 0) {
        return $true
    }

    # Get the corresponding lines from the current content
    $contentLines = $Content -split "`r`n|`r|`n"

    # Validate content has lines
    if ($contentLines.Count -eq 0) {
        Write-Verbose "Content has no lines for comparison"
        return $false
    }

    $startLine = [Math]::Max(0, $Line - 3)
    $endLine = [Math]::Min($contentLines.Count - 1, $Line + 3)

    # Validate bounds before array access
    if ($startLine -ge $contentLines.Count -or $endLine -lt 0 -or $startLine -gt $endLine) {
        Write-Verbose "Line $Line is out of range for file with $($contentLines.Count) lines"
        return $false
    }

    try {
        $contextLines = $contentLines[$startLine..$endLine]
    }
    catch {
        Write-Warning "Array indexing failed for lines $startLine..$endLine`: $_"
        return $false
    }

    # Fuzzy match: Check if any diff line appears in the context
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

    # Consider it matching if at least 50% of non-empty diff lines are found
    # Wrap in @() for null safety when Where-Object returns nothing
    $nonEmptyDiffLines = @($diffLines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count
    if ($nonEmptyDiffLines -eq 0) {
        return $true
    }

    $matchRatio = $matchCount / $nonEmptyDiffLines
    return $matchRatio -ge 0.5
}

function Get-CommentStaleness {
    <#
    .SYNOPSIS
        Determines if a comment is stale and returns the staleness reason.
    #>
    param(
        [Parameter(Mandatory)] [object]$Comment,
        [Parameter(Mandatory)] [string]$Owner,
        [Parameter(Mandatory)] [string]$Repo,
        [Parameter(Mandatory)] [array]$FileTree,
        [Parameter(Mandatory)] [hashtable]$ContentCache
    )

    # Skip issue comments (they don't have file/line context)
    if ($Comment.CommentType -eq "Issue" -or [string]::IsNullOrEmpty($Comment.Path)) {
        return @{ Stale = $false; StaleReason = $null }
    }

    # Check 1: File existence
    if (-not (Test-FileExistsInPR -Path $Comment.Path -FileTree $FileTree)) {
        return @{ Stale = $true; StaleReason = "FileDeleted" }
    }

    # Check 2: Line range
    $fileContent = Get-FileContent -Owner $Owner -Repo $Repo -Path $Comment.Path -ContentCache $ContentCache
    if ($null -eq $fileContent) {
        # File exists in tree but couldn't fetch content (permissions, binary, etc.)
        Write-Verbose "Could not fetch content for $($Comment.Path), skipping line/diff checks"
        return @{ Stale = $false; StaleReason = $null }
    }

    if ($Comment.Line -and -not (Test-LineExistsInFile -Line $Comment.Line -Content $fileContent)) {
        return @{ Stale = $true; StaleReason = "LineOutOfRange" }
    }

    # Check 3: Diff context
    if ($Comment.DiffHunk -and $Comment.Line) {
        if (-not (Test-DiffHunkMatch -Line $Comment.Line -DiffHunk $Comment.DiffHunk -Content $fileContent)) {
            return @{ Stale = $true; StaleReason = "CodeChanged" }
        }
    }

    return @{ Stale = $false; StaleReason = $null }
}

#endregion

Write-Verbose "Fetching review comments for PR #$PullRequest"

# Initialize caches if stale detection is enabled
$fileTree = @()
$contentCache = @{}
if ($DetectStale) {
    $fileTree = Get-PRFileTree -Owner $Owner -Repo $Repo
    Write-Verbose "File tree loaded with $($fileTree.Count) files"
}

# Fetch review comments (code-level comments on specific lines/files)
$reviewComments = Invoke-GhApiPaginated -Endpoint "repos/$Owner/$Repo/pulls/$PullRequest/comments"

$processedReviewComments = @(foreach ($comment in $reviewComments) {
        if ($Author -and $comment.user.login -ne $Author) { continue }

        # Determine staleness if requested
        $staleInfo = if ($DetectStale) {
            Get-CommentStaleness -Comment @{
                CommentType = "Review"
                Path = $comment.path
                Line = if ($comment.line) { $comment.line } else { $comment.original_line }
                DiffHunk = $comment.diff_hunk
            } -Owner $Owner -Repo $Repo -FileTree $fileTree -ContentCache $contentCache
        } else {
            @{ Stale = $null; StaleReason = $null }
        }

        [PSCustomObject]@{
            Id = $comment.id
            CommentType = "Review"
            Author = $comment.user.login
            AuthorType = $comment.user.type
            Path = $comment.path
            Line = if ($comment.line) { $comment.line } else { $comment.original_line }
            Side = $comment.side
            Body = $comment.body
            CreatedAt = $comment.created_at
            UpdatedAt = $comment.updated_at
            InReplyToId = $comment.in_reply_to_id
            IsReply = $null -ne $comment.in_reply_to_id
            DiffHunk = if ($IncludeDiffHunk) { $comment.diff_hunk } else { $null }
            HtmlUrl = $comment.html_url
            CommitId = $comment.commit_id
            Stale = $staleInfo.Stale
            StaleReason = $staleInfo.StaleReason
        }
    })

# Fetch issue comments (top-level PR comments) if requested
$processedIssueComments = @()
if ($IncludeIssueComments) {
    Write-Verbose "Fetching issue comments for PR #$PullRequest"
    $issueComments = Invoke-GhApiPaginated -Endpoint "repos/$Owner/$Repo/issues/$PullRequest/comments"

    $processedIssueComments = @(foreach ($comment in $issueComments) {
            if ($Author -and $comment.user.login -ne $Author) { continue }

            [PSCustomObject]@{
                Id = $comment.id
                CommentType = "Issue"
                Author = $comment.user.login
                AuthorType = $comment.user.type
                Path = $null  # Issue comments are not on specific files
                Line = $null  # Issue comments are not on specific lines
                Side = $null
                Body = $comment.body
                CreatedAt = $comment.created_at
                UpdatedAt = $comment.updated_at
                InReplyToId = $null  # Issue comments don't have reply threading like review comments
                IsReply = $false
                DiffHunk = $null
                HtmlUrl = $comment.html_url
                CommitId = $null
                Stale = if ($DetectStale) { $false } else { $null }  # Issue comments are never stale
                StaleReason = $null
            }
        })
}

# Combine all comments
$allProcessedComments = @($processedReviewComments) + @($processedIssueComments)

# Apply filtering if requested
if ($DetectStale) {
    # Log cache statistics for performance monitoring
    $uniqueFiles = @($allProcessedComments | Where-Object { $_.Path } | Select-Object -ExpandProperty Path -Unique).Count
    $cachedFiles = $contentCache.Keys.Count
    Write-Verbose "Cache statistics: $cachedFiles files cached for $uniqueFiles unique file paths in comments"

    if ($ExcludeStale) {
        Write-Verbose "Filtering out stale comments"
        $allProcessedComments = @($allProcessedComments | Where-Object { -not $_.Stale })
    }
    elseif ($OnlyStale) {
        Write-Verbose "Filtering to only stale comments"
        $allProcessedComments = @($allProcessedComments | Where-Object { $_.Stale -eq $true })
    }
}

# Sort by creation date
$allProcessedComments = $allProcessedComments | Sort-Object -Property CreatedAt

$authorGroups = @($allProcessedComments) | Group-Object -Property Author

# Count stale comments if detection was enabled
$staleCount = if ($DetectStale) {
    @($processedReviewComments + $processedIssueComments | Where-Object { $_.Stale -eq $true }).Count
} else {
    0
}

$reviewCount = @($processedReviewComments).Count
$issueCount = @($processedIssueComments).Count

$output = [PSCustomObject]@{
    Success = $true
    PullRequest = $PullRequest
    Owner = $Owner
    Repo = $Repo
    TotalComments = @($allProcessedComments).Count
    ReviewCommentCount = $reviewCount
    IssueCommentCount = $issueCount
    TopLevelCount = (@($allProcessedComments) | Where-Object { -not $_.IsReply }).Count
    ReplyCount = (@($allProcessedComments) | Where-Object { $_.IsReply }).Count
    StaleCount = $staleCount
    AuthorSummary = @($authorGroups | ForEach-Object { [PSCustomObject]@{ Author = $_.Name; Count = $_.Count } })
    Comments = @($allProcessedComments)
}

Write-Output $output

$reviewText = if ($reviewCount -eq 1) { "review comment" } else { "review comments" }
$commentSummary = "PR #$($PullRequest): $reviewCount $reviewText"
if ($IncludeIssueComments) {
    $issueText = if ($issueCount -eq 1) { "issue comment" } else { "issue comments" }
    $commentSummary += " + $issueCount $issueText"
}
if ($DetectStale -and $staleCount -gt 0) {
    $commentSummary += " ($staleCount stale)"
}
Write-Host $commentSummary -ForegroundColor Cyan
if ($DetectStale -and $staleCount -gt 0) {
    Write-Host "  Stale comments detected - use -ExcludeStale to filter them out" -ForegroundColor Gray
}
