#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Gets bot comments that need action based on lifecycle state analysis.

.DESCRIPTION
    Implements a state machine to determine which comments truly need attention.
    Analyzes eyes reactions, reply count, reply content, and thread resolution.

    LIFECYCLE STATE MACHINE:
      State 1: NEW (needs immediate action)
        - Condition: 0 eyes AND 0 replies AND thread unresolved
        - Action: Add eyes + post reply

      State 2: ACKNOWLEDGED (needs response)
        - Condition: >0 eyes AND 0 replies AND thread unresolved
        - Action: Post reply

      State 3: IN_DISCUSSION (needs analysis of reply text)
        - Condition: >0 eyes AND >0 replies AND thread unresolved
        - Sub-states (analyze reply text):
          - WONT_FIX: Reply contains "won't fix", "out of scope", "future PR" -> Resolve thread
          - FIX_DESCRIBED: Reply describes fix but no commit hash -> Add commit to reply
          - FIX_COMMITTED: Reply has commit hash -> Resolve thread
          - NEEDS_CLARIFICATION: Reply asks questions -> Wait for response

      State 4: RESOLVED
        - Condition: Thread resolved (for ReviewComments)
        - For IssueComments: No thread resolution mechanism

    FILTERING:
      -OnlyUnaddressed includes: NEW, ACKNOWLEDGED, IN_DISCUSSION
      Excludes: RESOLVED and IN_DISCUSSION with WONT_FIX sub-state (no action needed)

    See: .agents/architecture/bot-author-feedback-protocol.md

.PARAMETER Owner
    Repository owner. Auto-detected from git remote if not specified.

.PARAMETER Repo
    Repository name. Auto-detected from git remote if not specified.

.PARAMETER PullRequest
    Pull request number.

.PARAMETER BotOnly
    If specified (default: true), returns only bot comments.
    Set to $false to include all unaddressed comments regardless of author type.

.PARAMETER OnlyUnaddressed
    If specified (default: true), returns only comments needing action.
    Set to $false to include all comments with full lifecycle state info.

.EXAMPLE
    # Quick check: Are there unaddressed comments?
    $result = ./Get-UnaddressedComments.ps1 -PullRequest 365
    if ($result.TotalCount -gt 0) { Write-Host "$($result.TotalCount) comments need attention" }

.EXAMPLE
    # Get comments by lifecycle state
    $result = ./Get-UnaddressedComments.ps1 -PullRequest 365
    $result.LifecycleStateCounts  # @{NEW=2; ACKNOWLEDGED=1; IN_DISCUSSION=3; RESOLVED=5}

.EXAMPLE
    # Get IN_DISCUSSION sub-state breakdown
    $result = ./Get-UnaddressedComments.ps1 -PullRequest 365
    $result.DiscussionSubStateCounts  # @{WONT_FIX=1; FIX_DESCRIBED=1; FIX_COMMITTED=0; NEEDS_CLARIFICATION=1}

.EXAMPLE
    # Get all comments including resolved (for audit)
    ./Get-UnaddressedComments.ps1 -PullRequest 365 -OnlyUnaddressed:$false

.EXAMPLE
    # Include all authors (not just bots)
    ./Get-UnaddressedComments.ps1 -PullRequest 365 -BotOnly:$false

.NOTES
    Depends on Get-UnresolvedReviewThreads for thread resolution status.

    OUTPUT FORMAT:
    Returns PSCustomObject with:
    - Success: bool
    - TotalCount: int (unaddressed comment count when OnlyUnaddressed, else all)
    - LifecycleStateCounts: @{NEW=N; ACKNOWLEDGED=N; IN_DISCUSSION=N; RESOLVED=N}
    - DiscussionSubStateCounts: @{WONT_FIX=N; FIX_DESCRIBED=N; FIX_COMMITTED=N; NEEDS_CLARIFICATION=N}
    - DomainCounts: @{security=N; bug=N; style=N; summary=N; general=N}
    - AuthorSummary: @(@{Author="name"; Count=N}, ...)
    - Comments: Array of enriched comment objects with:
      - Id, Author, AuthorType, Path, Line, Body, Domain
      - CreatedAt, HtmlUrl, IsReply, InReplyToId
      - LifecycleState: NEW, ACKNOWLEDGED, IN_DISCUSSION, RESOLVED
      - DiscussionSubState: WONT_FIX, FIX_DESCRIBED, FIX_COMMITTED, NEEDS_CLARIFICATION (when IN_DISCUSSION)
      - ReplyCount: Number of replies to this comment
      - NeedsAction: bool indicating if action is required

    EXIT CODES:
    0  - Success: Comments retrieved successfully (implicit)

    See: ADR-035 Exit Code Standardization

.OUTPUTS
    PSCustomObject with TotalCount, LifecycleStateCounts, DomainCounts, AuthorSummary, and Comments array.
    Returns object with TotalCount=0 and empty Comments when all bot comments are addressed.
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,
    [Parameter(Mandatory)]
    [int]$PullRequest,
    [switch]$BotOnly = $true,
    [switch]$OnlyUnaddressed = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Import shared module
Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1") -Force

#region Lifecycle State Detection

function Get-DiscussionSubState {
    <#
    .SYNOPSIS
        Analyzes reply text to determine discussion sub-state.
    .DESCRIPTION
        Scans reply content for keywords indicating resolution path:
        - WONT_FIX: Contains "won't fix", "wontfix", "out of scope", "follow-up PR", "future"
        - FIX_COMMITTED: Contains commit hash pattern (7+ hex chars)
        - FIX_DESCRIBED: Describes a fix without commit reference
        - NEEDS_CLARIFICATION: Asks questions or requests info
    #>
    param(
        [string[]]$ReplyBodies
    )

    if ($null -eq $ReplyBodies -or $ReplyBodies.Count -eq 0) {
        return $null
    }

    # Join all reply bodies for analysis (most recent reply has priority)
    $combinedText = ($ReplyBodies | Select-Object -Last 3) -join "`n"
    $textLower = $combinedText.ToLower()

    # Check for "won't fix" indicators (highest priority, means no action needed)
    if ($textLower -match "won'?t\s*fix|wontfix|out\s+of\s+scope|follow-?up\s+pr|future\s+pr|defer|deferred|tracked\s+in|separate\s+issue") {
        return "WONT_FIX"
    }

    # Check for commit hash (indicates fix was committed)
    # Pattern: "commit [hash]", "fixed in [hash]", or standalone 7+ char hex preceded by word boundary
    if ($combinedText -match 'commit\s+[0-9a-fA-F]{7,40}|fixed\s+in\s+[0-9a-fA-F]{7,40}|\b[0-9a-fA-F]{7,40}\b') {
        return "FIX_COMMITTED"
    }

    # Check for clarification requests (questions being asked)
    if ($textLower -match '\?\s*$|can\s+you\s+clarify|what\s+do\s+you\s+mean|could\s+you\s+explain|not\s+sure\s+I\s+understand|need\s+more\s+context') {
        return "NEEDS_CLARIFICATION"
    }

    # Check for fix description without commit (mentions fixing, updating, changing)
    if ($textLower -match 'will\s+fix|fixing|updated|changed|modified|addressed|implemented|added|removed') {
        return "FIX_DESCRIBED"
    }

    # Default: needs clarification if we have replies but cannot categorize
    return "NEEDS_CLARIFICATION"
}

function Get-CommentLifecycleState {
    <#
    .SYNOPSIS
        Determines the lifecycle state of a comment.
    .DESCRIPTION
        Implements the state machine:
        - NEW: 0 eyes AND 0 replies AND unresolved
        - ACKNOWLEDGED: >0 eyes AND 0 replies AND unresolved
        - IN_DISCUSSION: >0 eyes AND >0 replies AND unresolved
        - RESOLVED: thread is resolved
    #>
    param(
        [int]$EyesCount,
        [int]$ReplyCount,
        [bool]$IsThreadResolved
    )

    if ($IsThreadResolved) {
        return "RESOLVED"
    }

    if ($EyesCount -eq 0) {
        return "NEW"
    }

    if ($ReplyCount -eq 0) {
        return "ACKNOWLEDGED"
    }

    return "IN_DISCUSSION"
}

function Test-CommentNeedsAction {
    <#
    .SYNOPSIS
        Determines if a comment needs action based on state.
    .DESCRIPTION
        Returns true for: NEW, ACKNOWLEDGED, IN_DISCUSSION (except WONT_FIX sub-state)
        Returns false for: RESOLVED, IN_DISCUSSION with WONT_FIX
    #>
    param(
        [string]$LifecycleState,
        [string]$DiscussionSubState
    )

    switch ($LifecycleState) {
        "RESOLVED" { return $false }
        "NEW" { return $true }
        "ACKNOWLEDGED" { return $true }
        "IN_DISCUSSION" {
            # WONT_FIX means no action needed (decision made to defer)
            # FIX_COMMITTED also needs no action (just needs thread resolution)
            if ($DiscussionSubState -eq "WONT_FIX" -or $DiscussionSubState -eq "FIX_COMMITTED") {
                return $false
            }
            return $true
        }
        default { return $true }
    }
}

#endregion

#region Domain Classification (reused from Get-PRReviewComments)

function Get-CommentDomain {
    <#
    .SYNOPSIS
        Classifies a comment into a domain based on keyword matching.
    #>
    param([string]$Body)

    if ([string]::IsNullOrWhiteSpace($Body)) {
        return "general"
    }

    $bodyLower = $Body.ToLower()

    # Security: CWE identifiers, vulnerabilities, injection attacks, auth issues
    if ($bodyLower -match 'cwe-\d+|vulnerability|vulnerabilities|injection|xss|sql|csrf|\bauth(?:entication|orization|enticat|orized)?\b|secrets?|credentials?|toctou|symlink|traversal|sanitiz|\bescap(?:e|ing)\b') {
        return "security"
    }

    # Bug: Runtime errors, crashes, null/undefined references, concurrency issues
    if ($bodyLower -match 'throws?\s+error|error\s+(?:occurs?|occurred|happens?|when|while)|\bcrash(?:es|ed|ing)?\b|\bexception(?:s)?\b|\bfail(?:ed|s|ure|ing)\b|null\s+(?:pointer|reference|ref)\b|undefined\s+(?:behavior|reference|variable)\b|race\s+condition|deadlock|memory\s+leak') {
        return "bug"
    }

    # Style: Formatting, naming conventions, code style suggestions
    if ($bodyLower -match 'formatting|naming|indentation|whitespace|convention|code\s*style|stylistic|readability|cleanup|refactor|refactoring') {
        return "style"
    }

    # Summary: Bot-generated summary patterns (CodeRabbit, Copilot)
    if ($bodyLower -match '(?m)^\s*#{1,3}\s*(?:summary|overview|changes|walkthrough)') {
        return "summary"
    }

    return "general"
}

#endregion

#region Main Logic

# Guard: Only execute main logic when run directly, not when dot-sourced for testing
if ($MyInvocation.InvocationName -eq '.') {
    return
}

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

Write-Verbose "Fetching comments for PR #$PullRequest"

# Fetch all review comments
try {
    $rawComments = Invoke-GhApiPaginated -Endpoint "repos/$Owner/$Repo/pulls/$PullRequest/comments"
}
catch {
    Write-Error "Failed to fetch PR review comments for PR #$PullRequest in $Owner/$Repo. Error: $_"
    exit 3
}

# Early exit if no comments
if ($null -eq $rawComments -or $rawComments.Count -eq 0) {
    $emptyResult = [PSCustomObject]@{
        Success = $true
        PullRequest = $PullRequest
        Owner = $Owner
        Repo = $Repo
        TotalCount = 0
        LifecycleStateCounts = @{ NEW = 0; ACKNOWLEDGED = 0; IN_DISCUSSION = 0; RESOLVED = 0 }
        DiscussionSubStateCounts = @{ WONT_FIX = 0; FIX_DESCRIBED = 0; FIX_COMMITTED = 0; NEEDS_CLARIFICATION = 0 }
        DomainCounts = @{ security = 0; bug = 0; style = 0; summary = 0; general = 0 }
        AuthorSummary = @()
        Comments = @()
    }
    Write-Output $emptyResult
    Write-Host "PR #$PullRequest`: 0 comments needing action" -ForegroundColor Cyan
    exit 0
}

# Query unresolved threads for lifecycle state detection
$unresolvedThreads = Get-UnresolvedReviewThreads -Owner $Owner -Repo $Repo -PullRequest $PullRequest

# Extract comment IDs from unresolved threads
$unresolvedCommentIds = @()
foreach ($thread in $unresolvedThreads) {
    $firstComment = $thread.comments.nodes | Select-Object -First 1
    if ($null -ne $firstComment -and $null -ne $firstComment.databaseId) {
        $unresolvedCommentIds += $firstComment.databaseId
    }
}

# Build reply lookup: parentCommentId -> array of reply bodies
# This lets us count replies and analyze reply content for each root comment
$replyLookup = @{}
$replyCountLookup = @{}
foreach ($comment in $rawComments) {
    # Safe property access: in_reply_to_id may not exist on all comments
    $replyToId = if ($comment.PSObject.Properties['in_reply_to_id']) { $comment.in_reply_to_id } else { $null }
    if ($null -ne $replyToId) {
        if (-not $replyLookup.ContainsKey($replyToId)) {
            $replyLookup[$replyToId] = @()
            $replyCountLookup[$replyToId] = 0
        }
        $replyLookup[$replyToId] += $comment.body
        $replyCountLookup[$replyToId]++
    }
}

# Filter and transform comments
$allProcessedComments = @()
foreach ($comment in $rawComments) {
    # Skip replies, we only want root comments (thread starters)
    # Safe property access: in_reply_to_id may not exist
    $inReplyToId = if ($comment.PSObject.Properties['in_reply_to_id']) { $comment.in_reply_to_id } else { $null }
    if ($null -ne $inReplyToId) {
        continue
    }

    # Apply bot filter if specified
    if ($BotOnly -and $comment.user.type -ne 'Bot') {
        continue
    }

    # Gather state inputs
    $eyesCount = if ($comment.reactions.eyes) { $comment.reactions.eyes } else { 0 }
    $replyCount = if ($replyCountLookup.ContainsKey($comment.id)) { $replyCountLookup[$comment.id] } else { 0 }
    $isThreadResolved = -not ($unresolvedCommentIds -contains $comment.id)

    # Determine lifecycle state
    $lifecycleState = Get-CommentLifecycleState -EyesCount $eyesCount -ReplyCount $replyCount -IsThreadResolved $isThreadResolved

    # Determine discussion sub-state if IN_DISCUSSION
    $discussionSubState = $null
    if ($lifecycleState -eq "IN_DISCUSSION") {
        $replyBodies = if ($replyLookup.ContainsKey($comment.id)) { $replyLookup[$comment.id] } else { @() }
        $discussionSubState = Get-DiscussionSubState -ReplyBodies $replyBodies
    }

    # Determine if action is needed
    $needsAction = Test-CommentNeedsAction -LifecycleState $lifecycleState -DiscussionSubState $discussionSubState

    $allProcessedComments += [PSCustomObject]@{
        Id = $comment.id
        Author = $comment.user.login
        AuthorType = $comment.user.type
        Path = $comment.path
        Line = if ($comment.line) { $comment.line } else { $comment.original_line }
        Body = $comment.body
        Domain = Get-CommentDomain -Body $comment.body
        CreatedAt = $comment.created_at
        UpdatedAt = $comment.updated_at
        HtmlUrl = $comment.html_url
        InReplyToId = $null  # Root comments have no parent
        IsReply = $false
        LifecycleState = $lifecycleState
        DiscussionSubState = $discussionSubState
        EyesCount = $eyesCount
        ReplyCount = $replyCount
        IsThreadResolved = $isThreadResolved
        NeedsAction = $needsAction
    }
}

# Apply OnlyUnaddressed filter
# Explicit array handling to ensure .Count property exists
$filteredComments = if ($OnlyUnaddressed) {
    $allProcessedComments | Where-Object { $_.NeedsAction }
} else {
    $allProcessedComments
}
# Force array even if result is null or single item
$outputComments = @($filteredComments)

# Calculate lifecycle state counts (from all processed, not filtered)
$lifecycleStateCounts = @{ NEW = 0; ACKNOWLEDGED = 0; IN_DISCUSSION = 0; RESOLVED = 0 }
$discussionSubStateCounts = @{ WONT_FIX = 0; FIX_DESCRIBED = 0; FIX_COMMITTED = 0; NEEDS_CLARIFICATION = 0 }
foreach ($c in $allProcessedComments) {
    $lifecycleStateCounts[$c.LifecycleState]++
    if ($c.LifecycleState -eq "IN_DISCUSSION" -and $null -ne $c.DiscussionSubState) {
        $discussionSubStateCounts[$c.DiscussionSubState]++
    }
}

# Calculate domain counts (from output comments)
$domainGroups = $outputComments | Group-Object -Property Domain
$domainCounts = @{ security = 0; bug = 0; style = 0; summary = 0; general = 0 }
foreach ($group in $domainGroups) {
    if ($null -ne $group.Name -and $domainCounts.ContainsKey($group.Name)) {
        $domainCounts[$group.Name] = $group.Count
    }
}

# Calculate author summary (from output comments)
$authorGroups = @($outputComments) | Group-Object -Property Author
$authorSummary = @($authorGroups | Where-Object { $null -ne $_.Name } | ForEach-Object { [PSCustomObject]@{ Author = $_.Name; Count = $_.Count } })

# Build output
$output = [PSCustomObject]@{
    Success = $true
    PullRequest = $PullRequest
    Owner = $Owner
    Repo = $Repo
    TotalCount = $outputComments.Count
    LifecycleStateCounts = $lifecycleStateCounts
    DiscussionSubStateCounts = $discussionSubStateCounts
    DomainCounts = $domainCounts
    AuthorSummary = $authorSummary
    Comments = @($outputComments)
}

Write-Output $output

# Console summary with lifecycle state breakdown
$stateParts = @()
foreach ($state in @('NEW', 'ACKNOWLEDGED', 'IN_DISCUSSION')) {
    if ($lifecycleStateCounts[$state] -gt 0) {
        $stateParts += "$state($($lifecycleStateCounts[$state]))"
    }
}
$stateSummary = if ($stateParts.Count -gt 0) { " | $($stateParts -join ', ')" } else { "" }

$actionableCount = @($allProcessedComments | Where-Object { $_.NeedsAction }).Count
Write-Host "PR #$PullRequest`: $actionableCount comments needing action$stateSummary" -ForegroundColor Cyan

#endregion
