<#
.SYNOPSIS
    Posts a reply to a GitHub PR review comment or creates a new PR comment.

.DESCRIPTION
    Generic script for posting replies to GitHub pull request comments using the GitHub API.
    Supports both:
    - In-thread replies to existing review comments
    - New top-level PR comments (issue comments)

    Designed for use with Claude Code agents and the pr-comment-responder workflow.

.PARAMETER Owner
    Repository owner (username or organization). If not specified, attempts to infer from git remote.

.PARAMETER Repo
    Repository name. If not specified, attempts to infer from git remote.

.PARAMETER PullRequest
    Pull request number (required).

.PARAMETER CommentId
    The ID of the review comment to reply to. If not provided, creates a top-level PR comment.

.PARAMETER Body
    The comment body text. Mutually exclusive with BodyFile.

.PARAMETER BodyFile
    Path to a file containing the comment body. Mutually exclusive with Body.

.PARAMETER CommentType
    Type of comment: "review" (in-thread reply) or "issue" (top-level PR comment).
    Default: "review" when CommentId is provided, "issue" otherwise.

.EXAMPLE
    # Reply to a review comment using inline body
    .\Post-PRCommentReply.ps1 -PullRequest 50 -CommentId 2625540786 -Body "Fixed in commit abc1234."

.EXAMPLE
    # Reply to a review comment using body from file
    .\Post-PRCommentReply.ps1 -Owner rjmurillo -Repo ai-agents -PullRequest 50 -CommentId 2625540786 -BodyFile reply.md

.EXAMPLE
    # Post a new top-level PR comment
    .\Post-PRCommentReply.ps1 -PullRequest 50 -Body "All review comments have been addressed."

.EXAMPLE
    # Post using current repo context (infers owner/repo from git)
    .\Post-PRCommentReply.ps1 -PullRequest 50 -CommentId 12345 -BodyFile .agents/pr-comments/PR-50/reply.md

.NOTES
    Requires GitHub CLI (gh) to be installed and authenticated.

    Exit Codes:
        0 - Success
        1 - Invalid parameters
        2 - File not found
        3 - GitHub API error
        4 - gh CLI not found or not authenticated

.LINK
    https://docs.github.com/en/rest/pulls/comments#create-a-reply-for-a-review-comment
    https://docs.github.com/en/rest/issues/comments#create-an-issue-comment
#>

[CmdletBinding(DefaultParameterSetName = 'BodyText')]
param(
    [Parameter()]
    [string]$Owner,

    [Parameter()]
    [string]$Repo,

    [Parameter(Mandatory = $true)]
    [int]$PullRequest,

    [Parameter()]
    [long]$CommentId,

    [Parameter(ParameterSetName = 'BodyText', Mandatory = $true)]
    [string]$Body,

    [Parameter(ParameterSetName = 'BodyFile', Mandatory = $true)]
    [string]$BodyFile,

    [Parameter()]
    [ValidateSet("review", "issue")]
    [string]$CommentType
)

#region Helper Functions

function Get-RepoInfo {
    <#
    .SYNOPSIS
        Extracts owner/repo from git remote URL
    #>
    try {
        $remoteUrl = git remote get-url origin 2>$null
        if ($remoteUrl -match 'github\.com[:/]([^/]+)/([^/.]+)') {
            return @{
                Owner = $Matches[1]
                Repo = $Matches[2] -replace '\.git$', ''
            }
        }
    }
    catch {
        # Ignore errors
    }
    return $null
}

function Test-GhAuthenticated {
    <#
    .SYNOPSIS
        Verifies GitHub CLI is installed and authenticated
    #>
    try {
        $null = gh auth status 2>&1
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Write-ErrorAndExit {
    param(
        [string]$Message,
        [int]$ExitCode
    )
    Write-Error $Message
    exit $ExitCode
}

#endregion

#region Validation

# Check gh CLI
if (-not (Test-GhAuthenticated)) {
    Write-ErrorAndExit "GitHub CLI (gh) is not installed or not authenticated. Run 'gh auth login' first." 4
}

# Infer owner/repo if not provided
if (-not $Owner -or -not $Repo) {
    $repoInfo = Get-RepoInfo
    if ($repoInfo) {
        if (-not $Owner) { $Owner = $repoInfo.Owner }
        if (-not $Repo) { $Repo = $repoInfo.Repo }
    }
    else {
        Write-ErrorAndExit "Could not infer repository info. Please provide -Owner and -Repo parameters." 1
    }
}

# Get body content
if ($BodyFile) {
    if (-not (Test-Path $BodyFile)) {
        Write-ErrorAndExit "Body file not found: $BodyFile" 2
    }
    $Body = Get-Content $BodyFile -Raw
}

if ([string]::IsNullOrWhiteSpace($Body)) {
    Write-ErrorAndExit "Comment body cannot be empty." 1
}

# Determine comment type
if (-not $CommentType) {
    $CommentType = if ($CommentId) { "review" } else { "issue" }
}

# Validate CommentId for review type
if ($CommentType -eq "review" -and -not $CommentId) {
    Write-ErrorAndExit "CommentId is required for review comment replies. Use -CommentType 'issue' for top-level comments." 1
}

#endregion

#region Post Comment

$result = $null

try {
    if ($CommentType -eq "review") {
        # Post in-thread reply to review comment
        Write-Verbose "Posting reply to review comment $CommentId on PR #$PullRequest in $Owner/$Repo"

        $result = gh api "repos/$Owner/$Repo/pulls/$PullRequest/comments" `
            -X POST `
            -f body=$Body `
            -F in_reply_to=$CommentId 2>&1
    }
    else {
        # Post top-level issue comment
        Write-Verbose "Posting top-level comment on PR #$PullRequest in $Owner/$Repo"

        $result = gh api "repos/$Owner/$Repo/issues/$PullRequest/comments" `
            -X POST `
            -f body=$Body 2>&1
    }

    if ($LASTEXITCODE -ne 0) {
        Write-ErrorAndExit "GitHub API error: $result" 3
    }

    # Parse and return result
    $response = $result | ConvertFrom-Json

    # Output success info
    $output = [PSCustomObject]@{
        Success     = $true
        CommentId   = $response.id
        HtmlUrl     = $response.html_url
        CreatedAt   = $response.created_at
        InReplyTo   = if ($CommentType -eq "review") { $CommentId } else { $null }
        CommentType = $CommentType
    }

    Write-Output $output

    # Also write to host for visibility in scripts
    Write-Host "Successfully posted $CommentType comment." -ForegroundColor Green
    Write-Host "URL: $($response.html_url)" -ForegroundColor Cyan
}
catch {
    Write-ErrorAndExit "Failed to post comment: $_" 3
}

#endregion
