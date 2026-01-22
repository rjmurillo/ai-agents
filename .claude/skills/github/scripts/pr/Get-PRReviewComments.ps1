<#
.SYNOPSIS
    Gets all comments for a GitHub Pull Request with pagination and domain classification.

.DESCRIPTION
    Retrieves PR review comments (code-level) and optionally issue comments (PR-level)
    with full pagination support. Each comment is classified into a domain (security,
    bug, style, summary, or general) based on keyword matching for priority-based triage.

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

.PARAMETER GroupByDomain
    If specified, returns comments grouped by domain (Security, Bug, Style, Summary, General)
    instead of a flat array. Enables priority-based triage workflows where security comments
    can be processed first, followed by bugs, then style suggestions.

.EXAMPLE
    .\Get-PRReviewComments.ps1 -PullRequest 50
    Gets all review comments for PR #50 with domain classification.

.EXAMPLE
    .\Get-PRReviewComments.ps1 -PullRequest 50 -IncludeIssueComments
    Gets both review and issue comments with domain classification.

.EXAMPLE
    .\Get-PRReviewComments.ps1 -PullRequest 908 -GroupByDomain
    Returns comments grouped by domain for security-first processing:
    @{
        Security = @(... CWE, vulnerability comments ...)
        Bug = @(... error, crash comments ...)
        Style = @(... formatting, naming comments ...)
        Summary = @(... bot summary comments ...)
        General = @(... other comments ...)
    }

.EXAMPLE
    .\Get-PRReviewComments.ps1 -PullRequest 50 -Author "cursor[bot]"
    Gets only comments from cursor[bot] with domain classification.

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 2=Not found, 3=API error, 4=Not authenticated
    
    Domain Classification:
    - Security: CWE identifiers, vulnerability, injection, XSS, SQL, CSRF, auth, secrets, credentials
    - Bug: error, crash, exception, fail, null, undefined, race condition, deadlock, memory leak
    - Style: formatting, naming, indentation, whitespace, convention, prefer, consider, suggest
    - Summary: Bot-generated summaries (CodeRabbit, Copilot) with markdown headers
    - General: Default for comments not matching other patterns
    
    Integration: Used by pr-comment-responder skill for priority-based comment triage.
    Pattern: Similar to Update-ReviewerSignalStats.ps1 severity detection.
    
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
    [switch]$GroupByDomain
)

#region Helper Functions

<#
.SYNOPSIS
    Classifies a comment into a domain based on keyword matching.

.DESCRIPTION
    Scans comment body for security, bug, style, or summary patterns.
    Returns the first matching domain or "general" as default.
    
    Security keywords include CWE identifiers, vulnerability terms, and injection patterns.
    This prioritization ensures security-critical issues are identified first.

.PARAMETER Body
    The comment body text to classify.

.OUTPUTS
    String domain: "security", "bug", "style", "summary", or "general"
#>
function Get-CommentDomain {
    param([string]$Body)
    
    if ([string]::IsNullOrWhiteSpace($Body)) {
        return "general"
    }
    
    $bodyLower = $Body.ToLower()
    
    # Security: CWE identifiers, vulnerabilities, injection attacks, auth issues
    # Priority: Security issues must be detected first due to criticality
    # CRITICAL: Use word boundaries for "auth" to avoid matching "author", "authority"
    if ($bodyLower -match 'cwe-\d+|vulnerability|vulnerabilities|injection|xss|sql|csrf|\bauth(?:entication|orization|enticat|orized)?\b|secrets?|credentials?|toctou|symlink|traversal|sanitiz|\bescap(?:e|ing)\b') {
        return "security"
    }

    # Bug: Runtime errors, crashes, null/undefined references, concurrency issues
    # Use more specific patterns to reduce false positives (e.g., "no error" matching "error")
    if ($bodyLower -match 'throws?\s+error|error\s+(?:occurs?|occurred|happens?|when|while)|\bcrash(?:es|ed|ing)?\b|\bexception(?:s)?\b|\bfail(?:ed|s|ure|ing)\b|null\s+(?:pointer|reference|ref)\b|undefined\s+(?:behavior|reference|variable)\b|race\s+condition|deadlock|memory\s+leak') {
        return "bug"
    }

    # Style: Formatting, naming conventions, code style suggestions
    # Use more specific patterns to avoid false positives (e.g., "Consider the security implications")
    if ($bodyLower -match 'formatting|naming|indentation|whitespace|convention|code\s*style|stylistic|readability|cleanup|refactor|refactoring') {
        return "style"
    }

    # Summary: Bot-generated summary patterns (CodeRabbit, Copilot)
    # Detect markdown headers at the start of any line (not just comment start)
    if ($bodyLower -match '(?m)^\s*#{1,3}\s*(?:summary|overview|changes|walkthrough)') {
        return "summary"
    }
    
    # Default: General comments that don't match specific patterns
    return "general"
}

#endregion

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

Write-Verbose "Fetching review comments for PR #$PullRequest"

# Fetch review comments (code-level comments on specific lines/files)
$reviewComments = Invoke-GhApiPaginated -Endpoint "repos/$Owner/$Repo/pulls/$PullRequest/comments"

$processedReviewComments = @(foreach ($comment in $reviewComments) {
    if ($Author -and $comment.user.login -ne $Author) { continue }

    [PSCustomObject]@{
        Id          = $comment.id
        CommentType = "Review"
        Author      = $comment.user.login
        AuthorType  = $comment.user.type
        Path        = $comment.path
        Line = if ($comment.line) { $comment.line } else { $comment.original_line }
        Side        = $comment.side
        Body        = $comment.body
        Domain      = Get-CommentDomain -Body $comment.body
        CreatedAt   = $comment.created_at
        UpdatedAt   = $comment.updated_at
        InReplyToId = $comment.in_reply_to_id
        IsReply     = $null -ne $comment.in_reply_to_id
        DiffHunk = if ($IncludeDiffHunk) { $comment.diff_hunk } else { $null }
        HtmlUrl     = $comment.html_url
        CommitId    = $comment.commit_id
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
            Id          = $comment.id
            CommentType = "Issue"
            Author      = $comment.user.login
            AuthorType  = $comment.user.type
            Path        = $null  # Issue comments are not on specific files
            Line        = $null  # Issue comments are not on specific lines
            Side        = $null
            Body        = $comment.body
            Domain      = Get-CommentDomain -Body $comment.body
            CreatedAt   = $comment.created_at
            UpdatedAt   = $comment.updated_at
            InReplyToId = $null  # Issue comments don't have reply threading like review comments
            IsReply     = $false
            DiffHunk    = $null
            HtmlUrl     = $comment.html_url
            CommitId    = $null
        }
    })
}

# Combine all comments
$allProcessedComments = @($processedReviewComments) + @($processedIssueComments)

# Sort by creation date
$allProcessedComments = $allProcessedComments | Sort-Object -Property CreatedAt

# Calculate domain distribution (SHARED - used by both grouped and standard output)
$domainGroups = $allProcessedComments | Group-Object -Property Domain
$domainCounts = @{}
foreach ($group in $domainGroups) {
    $domainCounts[$group.Name] = $group.Count
}

# Group by domain if requested
if ($GroupByDomain) {
    # Initialize all domains with empty arrays
    $groupedOutput = @{
        Security = @()
        Bug = @()
        Style = @()
        Summary = @()
        General = @()
    }

    # Populate with actual comments
    foreach ($group in $domainGroups) {
        $capitalizedDomain = (Get-Culture).TextInfo.ToTitleCase($group.Name)
        $groupedOutput[$capitalizedDomain] = @($group.Group)
    }

    # Build capitalized domain counts for metadata
    $capitalizedDomainCounts = @{}
    foreach ($key in $domainCounts.Keys) {
        $capitalizedKey = (Get-Culture).TextInfo.ToTitleCase($key)
        $capitalizedDomainCounts[$capitalizedKey] = $domainCounts[$key]
    }

    # Add metadata (fix: handle empty comments correctly)
    $groupedOutput.TotalComments = if ($allProcessedComments) { @($allProcessedComments).Count } else { 0 }
    $groupedOutput.DomainCounts = $capitalizedDomainCounts

    Write-Output $groupedOutput

    # Console summary for grouped output
    $domainSummaryParts = @()
    foreach ($domain in @('Security', 'Bug', 'Style', 'Summary', 'General')) {
        $count = if ($capitalizedDomainCounts.ContainsKey($domain)) { $capitalizedDomainCounts[$domain] } else { 0 }
        $domainSummaryParts += "$domain($count)"
    }
    $groupedSummary = "PR #$($PullRequest): Grouped by domain: " + ($domainSummaryParts -join ', ')
    Write-Host $groupedSummary -ForegroundColor Cyan

    return
}

# Standard output mode
$authorGroups = @($allProcessedComments) | Group-Object -Property Author

$reviewCount = @($processedReviewComments).Count
$issueCount = @($processedIssueComments).Count

$output = [PSCustomObject]@{
    Success            = $true
    PullRequest        = $PullRequest
    Owner              = $Owner
    Repo               = $Repo
    TotalComments      = @($allProcessedComments).Count
    ReviewCommentCount = $reviewCount
    IssueCommentCount  = $issueCount
    TopLevelCount      = (@($allProcessedComments) | Where-Object { -not $_.IsReply }).Count
    ReplyCount         = (@($allProcessedComments) | Where-Object { $_.IsReply }).Count
    AuthorSummary      = @($authorGroups | ForEach-Object { [PSCustomObject]@{ Author = $_.Name; Count = $_.Count } })
    DomainCounts       = $domainCounts
    Comments           = @($allProcessedComments)
}

Write-Output $output

$reviewText = if ($reviewCount -eq 1) { "review comment" } else { "review comments" }
$commentSummary = "PR #$($PullRequest): $reviewCount $reviewText"
if ($IncludeIssueComments) {
    $issueText = if ($issueCount -eq 1) { "issue comment" } else { "issue comments" }
    $commentSummary += " + $issueCount $issueText"
}

# Add domain distribution with color coding
$domainSummaryParts = @()
foreach ($domain in @('security', 'bug', 'style', 'summary', 'general')) {
    $count = if ($domainCounts.ContainsKey($domain)) { $domainCounts[$domain] } else { 0 }
    if ($count -gt 0) {
        $capitalizedDomain = (Get-Culture).TextInfo.ToTitleCase($domain)
        $domainSummaryParts += "$capitalizedDomain($count)"
    }
}
if ($domainSummaryParts.Count -gt 0) {
    $commentSummary += " | Domains: " + ($domainSummaryParts -join ', ')
}

Write-Host $commentSummary -ForegroundColor Cyan

# Color-coded domain summary (one line per domain with count > 0)
foreach ($domain in @('security', 'bug', 'style', 'summary', 'general')) {
    $count = if ($domainCounts.ContainsKey($domain)) { $domainCounts[$domain] } else { 0 }
    if ($count -gt 0) {
        $color = switch ($domain) {
            'security' { 'Red' }
            'bug' { 'Yellow' }
            'style' { 'Gray' }
            'summary' { 'DarkGray' }
            'general' { 'Cyan' }
            default    { 'White' }
        }
        $capitalizedDomain = (Get-Culture).TextInfo.ToTitleCase($domain)
        Write-Host "  $capitalizedDomain`: $count" -ForegroundColor $color
    }
}
