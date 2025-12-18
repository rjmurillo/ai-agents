<#
.SYNOPSIS
    Common functions for AI review workflows.

.DESCRIPTION
    PowerShell module containing utility functions for AI-powered workflows:
    - Retry logic with exponential backoff
    - AI output parsing (verdicts, labels, milestones)
    - Markdown formatting (collapsible sections, verdict alerts)
    - Logging and environment validation

    For GitHub operations (PR comments, issue management, reactions, etc.),
    use the dedicated skill scripts in .claude/skills/github/ directly.

.NOTES
    Import this module in workflow scripts:
    Import-Module .github/scripts/AIReviewCommon.psm1

    For GitHub operations, use the skill scripts directly:
    - .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1
    - .claude/skills/github/scripts/issue/Post-IssueComment.ps1
    - .claude/skills/github/scripts/pr/Get-PRContext.ps1
    - .claude/skills/github/scripts/issue/Set-IssueLabels.ps1
    - .claude/skills/github/scripts/reactions/Add-CommentReaction.ps1
#>

#Requires -Version 7.0

$ErrorActionPreference = 'Stop'

#region Configuration

$script:AIReviewDir = if ($env:AI_REVIEW_DIR) { $env:AI_REVIEW_DIR } else { Join-Path $env:TEMP 'ai-review' }
$script:MaxRetries = if ($env:MAX_RETRIES) { [int]$env:MAX_RETRIES } else { 3 }
$script:RetryDelay = if ($env:RETRY_DELAY) { [int]$env:RETRY_DELAY } else { 30 }

#endregion

#region Initialization

function Initialize-AIReview {
    <#
    .SYNOPSIS
        Initialize working directory for AI review operations.

    .DESCRIPTION
        Creates the AI review working directory if it doesn't exist.

    .OUTPUTS
        System.String - The path to the AI review directory.

    .EXAMPLE
        $workDir = Initialize-AIReview
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param()

    if (-not (Test-Path $script:AIReviewDir)) {
        New-Item -ItemType Directory -Path $script:AIReviewDir -Force | Out-Null
    }
    Write-Verbose "AI Review working directory: $script:AIReviewDir"
    return $script:AIReviewDir
}

#endregion

#region Retry Logic

function Invoke-WithRetry {
    <#
    .SYNOPSIS
        Retry a command with exponential backoff.

    .DESCRIPTION
        Executes a script block and retries on failure with exponential backoff.

    .PARAMETER ScriptBlock
        The script block to execute.

    .PARAMETER MaxRetries
        Maximum number of retry attempts. Default is from configuration.

    .PARAMETER InitialDelay
        Initial delay in seconds between retries. Default is from configuration.

    .OUTPUTS
        The output of the successful script block execution.

    .EXAMPLE
        Invoke-WithRetry -ScriptBlock { gh pr view 123 } -MaxRetries 3

    .EXAMPLE
        Invoke-WithRetry { Invoke-WebRequest $url } -InitialDelay 5
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [scriptblock]$ScriptBlock,

        [Parameter()]
        [int]$MaxRetries = $script:MaxRetries,

        [Parameter()]
        [int]$InitialDelay = $script:RetryDelay
    )

    $delay = $InitialDelay
    for ($i = 1; $i -le $MaxRetries; $i++) {
        try {
            return & $ScriptBlock
        }
        catch {
            if ($i -eq $MaxRetries) {
                Write-Error "All $MaxRetries attempts failed. Last error: $_"
                throw
            }
            Write-Warning "Attempt $i/$MaxRetries failed, retrying in ${delay}s..."
            Start-Sleep -Seconds $delay
            $delay = $delay * 2
        }
    }
}

#endregion

#region Parsing Functions

function Get-Verdict {
    <#
    .SYNOPSIS
        Parse verdict from AI output.

    .DESCRIPTION
        Extracts verdict from AI-generated text using pattern matching.
        Tries explicit VERDICT: pattern first, then falls back to keyword detection.

    .PARAMETER Output
        The AI output text to parse.

    .OUTPUTS
        System.String - One of: PASS, WARN, REJECTED, CRITICAL_FAIL

    .EXAMPLE
        $verdict = Get-Verdict -Output $aiResponse
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory, ValueFromPipeline)]
        [AllowEmptyString()]
        [string]$Output
    )

    process {
        if ([string]::IsNullOrWhiteSpace($Output)) {
            return 'CRITICAL_FAIL'
        }

        # Try explicit VERDICT: pattern first
        if ($Output -match 'VERDICT:\s*([A-Z_]+)') {
            return $Matches[1]
        }

        # Fall back to keyword detection
        if ($Output -match 'CRITICAL_FAIL|critical failure|severe issue') {
            return 'CRITICAL_FAIL'
        }
        if ($Output -match 'REJECTED|reject|must fix|blocking') {
            return 'REJECTED'
        }
        if ($Output -match 'PASS|approved|looks good|no issues') {
            return 'PASS'
        }
        if ($Output -match 'WARN|warning|caution') {
            return 'WARN'
        }

        # No parseable verdict = failure mode
        return 'CRITICAL_FAIL'
    }
}

function Get-Labels {
    <#
    .SYNOPSIS
        Parse labels from AI output.

    .DESCRIPTION
        Extracts LABEL: entries from AI-generated text.

    .PARAMETER Output
        The AI output text to parse.

    .OUTPUTS
        System.String[] - Array of label strings.

    .EXAMPLE
        $labels = Get-Labels -Output $aiResponse
    #>
    [CmdletBinding()]
    [OutputType([string[]])]
    param(
        [Parameter(Mandatory, ValueFromPipeline)]
        [AllowEmptyString()]
        [string]$Output
    )

    process {
        if ([string]::IsNullOrWhiteSpace($Output)) {
            return @()
        }

        $labels = [System.Collections.Generic.List[string]]::new()
        $matches = [regex]::Matches($Output, 'LABEL:\s*(\S+)')
        foreach ($match in $matches) {
            $label = $match.Groups[1].Value
            if (-not [string]::IsNullOrWhiteSpace($label)) {
                $labels.Add($label)
            }
        }
        return $labels.ToArray()
    }
}

function Get-Milestone {
    <#
    .SYNOPSIS
        Parse milestone from AI output.

    .DESCRIPTION
        Extracts MILESTONE: entry from AI-generated text.

    .PARAMETER Output
        The AI output text to parse.

    .OUTPUTS
        System.String - The milestone string, or empty string if not found.

    .EXAMPLE
        $milestone = Get-Milestone -Output $aiResponse
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory, ValueFromPipeline)]
        [AllowEmptyString()]
        [string]$Output
    )

    process {
        if ([string]::IsNullOrWhiteSpace($Output)) {
            return ''
        }

        if ($Output -match 'MILESTONE:\s*(\S+)') {
            return $Matches[1]
        }
        return ''
    }
}

function Merge-Verdicts {
    <#
    .SYNOPSIS
        Aggregate multiple verdicts into a final verdict.

    .DESCRIPTION
        Combines multiple verdict values following priority rules:
        CRITICAL_FAIL/REJECTED > WARN > PASS

    .PARAMETER Verdicts
        Array of verdict strings to aggregate.

    .OUTPUTS
        System.String - The aggregated verdict.

    .EXAMPLE
        $final = Merge-Verdicts -Verdicts @('PASS', 'WARN', 'PASS')
        # Returns 'WARN'

    .EXAMPLE
        $final = Merge-Verdicts -Verdicts @('PASS', 'CRITICAL_FAIL', 'PASS')
        # Returns 'CRITICAL_FAIL'
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [string[]]$Verdicts
    )

    if ($Verdicts.Count -eq 0) {
        return 'PASS'
    }

    $final = 'PASS'

    foreach ($verdict in $Verdicts) {
        switch ($verdict) {
            { $_ -in 'CRITICAL_FAIL', 'REJECTED' } {
                return 'CRITICAL_FAIL'
            }
            'WARN' {
                if ($final -eq 'PASS') {
                    $final = 'WARN'
                }
            }
        }
    }

    return $final
}

#endregion

#region Formatting Functions

function Format-CollapsibleSection {
    <#
    .SYNOPSIS
        Format a collapsible details section for GitHub markdown.

    .DESCRIPTION
        Creates an HTML details/summary section for collapsible content.

    .PARAMETER Title
        The title shown in the summary element.

    .PARAMETER Content
        The content inside the collapsible section.

    .OUTPUTS
        System.String - The formatted HTML details section.

    .EXAMPLE
        $section = Format-CollapsibleSection -Title "View Details" -Content $details
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [string]$Title,

        [Parameter(Mandatory)]
        [string]$Content
    )

    return @"
<details>
<summary>$Title</summary>

$Content

</details>
"@
}

function Format-VerdictAlert {
    <#
    .SYNOPSIS
        Format a verdict using GitHub's markdown alert syntax.

    .DESCRIPTION
        Creates a GitHub alert block with appropriate severity level.
        Mapping:
          PASS         -> [!TIP]      (green)
          WARN/PARTIAL -> [!WARNING]  (yellow)
          CRITICAL_FAIL/REJECTED/FAIL -> [!CAUTION] (red)

    .PARAMETER Verdict
        The verdict value.

    .PARAMETER Message
        Optional message to include in the alert.

    .OUTPUTS
        System.String - The formatted alert block.

    .EXAMPLE
        $alert = Format-VerdictAlert -Verdict 'PASS' -Message 'All checks passed'
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [string]$Verdict,

        [Parameter()]
        [string]$Message
    )

    $alertType = Get-VerdictAlertType -Verdict $Verdict

    if ($Message) {
        return @"
> [!$alertType]
> **Verdict: $Verdict**
>
> $Message
"@
    }
    else {
        return @"
> [!$alertType]
> **Verdict: $Verdict**
"@
    }
}

function Get-VerdictAlertType {
    <#
    .SYNOPSIS
        Get the alert type for a verdict.

    .DESCRIPTION
        Maps verdict values to GitHub alert types.

    .PARAMETER Verdict
        The verdict value.

    .OUTPUTS
        System.String - The alert type: TIP, WARNING, CAUTION, or NOTE.

    .EXAMPLE
        $type = Get-VerdictAlertType -Verdict 'PASS'
        # Returns 'TIP'
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [string]$Verdict
    )

    switch ($Verdict) {
        'PASS' { return 'TIP' }
        { $_ -in 'WARN', 'PARTIAL' } { return 'WARNING' }
        { $_ -in 'CRITICAL_FAIL', 'REJECTED', 'FAIL' } { return 'CAUTION' }
        default { return 'NOTE' }
    }
}

function Get-VerdictExitCode {
    <#
    .SYNOPSIS
        Get exit code based on verdict.

    .DESCRIPTION
        Returns appropriate exit code for CI pipeline integration.

    .PARAMETER Verdict
        The verdict value.

    .OUTPUTS
        System.Int32 - Exit code: 1 for failures, 0 otherwise.

    .EXAMPLE
        exit (Get-VerdictExitCode -Verdict $finalVerdict)
    #>
    [CmdletBinding()]
    [OutputType([int])]
    param(
        [Parameter(Mandatory)]
        [string]$Verdict
    )

    switch ($Verdict) {
        { $_ -in 'CRITICAL_FAIL', 'REJECTED' } { return 1 }
        default { return 0 }
    }
}

#endregion

#region Logging Functions

function Write-Log {
    <#
    .SYNOPSIS
        Log message with timestamp.

    .DESCRIPTION
        Writes a timestamped message to the information stream.

    .PARAMETER Message
        The message to log.

    .EXAMPLE
        Write-Log "Starting review process"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0, ValueFromPipeline)]
        [string]$Message
    )

    process {
        $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
        Write-Information "[$timestamp] $Message" -InformationAction Continue
    }
}

function Write-LogError {
    <#
    .SYNOPSIS
        Log error message with timestamp.

    .DESCRIPTION
        Writes a timestamped error message to the error stream.

    .PARAMETER Message
        The error message to log.

    .EXAMPLE
        Write-LogError "Failed to post comment"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0, ValueFromPipeline)]
        [string]$Message
    )

    process {
        $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
        Write-Error "[$timestamp] ERROR: $Message"
    }
}

#endregion

#region Utility Functions

function Assert-EnvironmentVariables {
    <#
    .SYNOPSIS
        Check if required environment variables are set.

    .DESCRIPTION
        Validates that all specified environment variables exist and have values.

    .PARAMETER Names
        Array of environment variable names to check.

    .EXAMPLE
        Assert-EnvironmentVariables -Names @('GITHUB_TOKEN', 'PR_NUMBER')
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string[]]$Names
    )

    $missing = @()
    foreach ($name in $Names) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if ([string]::IsNullOrWhiteSpace($value)) {
            $missing += $name
        }
    }

    if ($missing.Count -gt 0) {
        throw "Missing required environment variables: $($missing -join ', ')"
    }
}

function Get-PRChangedFiles {
    <#
    .SYNOPSIS
        Get changed files in a PR matching a pattern.

    .DESCRIPTION
        Uses gh CLI to get the list of changed files in a PR,
        optionally filtered by a regex pattern.

    .PARAMETER PRNumber
        The PR number.

    .PARAMETER Pattern
        Optional regex pattern to filter files.

    .OUTPUTS
        System.String[] - Array of matching file paths.

    .EXAMPLE
        $mdFiles = Get-PRChangedFiles -PRNumber 123 -Pattern '\.md$'
    #>
    [CmdletBinding()]
    [OutputType([string[]])]
    param(
        [Parameter(Mandatory)]
        [int]$PRNumber,

        [Parameter()]
        [string]$Pattern = '.*'
    )

    try {
        $files = gh pr diff $PRNumber --name-only 2>$null
        if ($files) {
            return $files -split "`n" | Where-Object { $_ -match $Pattern }
        }
        return @()
    }
    catch {
        return @()
    }
}

function ConvertTo-JsonEscaped {
    <#
    .SYNOPSIS
        Escape string for JSON.

    .DESCRIPTION
        Properly escapes a string for JSON embedding.

    .PARAMETER InputString
        The string to escape.

    .OUTPUTS
        System.String - The JSON-escaped string.

    .EXAMPLE
        $escaped = ConvertTo-JsonEscaped -InputString 'Hello "World"'
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory, ValueFromPipeline)]
        [AllowEmptyString()]
        [string]$InputString
    )

    process {
        if ([string]::IsNullOrEmpty($InputString)) {
            return '""'
        }
        return $InputString | ConvertTo-Json
    }
}

function Format-MarkdownTableRow {
    <#
    .SYNOPSIS
        Format a table row for markdown.

    .DESCRIPTION
        Creates a pipe-delimited markdown table row.

    .PARAMETER Columns
        Array of column values.

    .OUTPUTS
        System.String - The formatted table row.

    .EXAMPLE
        $row = Format-MarkdownTableRow -Columns @('Col1', 'Col2', 'Col3')
        # Returns "| Col1 | Col2 | Col3 |"
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [string[]]$Columns
    )

    return "| $($Columns -join ' | ') |"
}

#endregion

#region GitHub Comment Functions

function Send-PRComment {
    <#
    .SYNOPSIS
        Post or update a PR comment idempotently.

    .DESCRIPTION
        Posts a new comment or updates an existing one based on a marker.
        The marker is added as an HTML comment for identification.

    .PARAMETER PRNumber
        The PR number.

    .PARAMETER CommentFile
        Path to the file containing the comment body.

    .PARAMETER Marker
        Unique marker to identify the comment for updates. Default: "AI-REVIEW"

    .EXAMPLE
        Send-PRComment -PRNumber 123 -CommentFile "/tmp/report.md" -Marker "AI-QUALITY-GATE"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [int]$PRNumber,

        [Parameter(Mandatory)]
        [string]$CommentFile,

        [Parameter()]
        [string]$Marker = "AI-REVIEW"
    )

    if (-not (Test-Path $CommentFile)) {
        Write-LogError "Comment file not found: $CommentFile"
        return $false
    }

    $commentContent = Get-Content $CommentFile -Raw
    $commentBody = "<!-- $Marker -->`n$commentContent"

    # Check for existing comment with this marker
    try {
        $comments = gh pr view $PRNumber --json comments -q ".comments[] | select(.body | contains(`"<!-- $Marker -->`")) | .databaseId" 2>$null
        $existingCommentId = ($comments -split "`n" | Select-Object -First 1)
    }
    catch {
        $existingCommentId = $null
    }

    if ($existingCommentId) {
        Write-Log "Updating existing comment (ID: $existingCommentId)"
        try {
            $repo = gh repo view --json nameWithOwner -q '.nameWithOwner' 2>$null
            if ($repo) {
                # Update via GitHub API using specific comment ID
                $commentBody | gh api --method PATCH "/repos/$repo/issues/comments/$existingCommentId" -F body=@- --silent 2>$null
                if ($LASTEXITCODE -ne 0) {
                    Write-Warning "Failed to update comment via API, creating new comment"
                    $commentBody | gh pr comment $PRNumber --body-file -
                }
            }
            else {
                Write-Warning "Could not determine repo, creating new comment"
                $commentBody | gh pr comment $PRNumber --body-file -
            }
        }
        catch {
            Write-Warning "Error updating comment: $_"
            $commentBody | gh pr comment $PRNumber --body-file -
        }
    }
    else {
        Write-Log "Creating new comment"
        $commentBody | gh pr comment $PRNumber --body-file -
    }

    return $LASTEXITCODE -eq 0
}

function Send-IssueComment {
    <#
    .SYNOPSIS
        Post a comment on an issue.

    .DESCRIPTION
        Posts a new comment on an issue with an optional marker for identification.

    .PARAMETER IssueNumber
        The issue number.

    .PARAMETER CommentFile
        Path to the file containing the comment body.

    .PARAMETER Marker
        Optional marker to add to the comment. Default: "AI-TRIAGE"

    .EXAMPLE
        Send-IssueComment -IssueNumber 123 -CommentFile "/tmp/triage.md" -Marker "AI-TRIAGE"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [int]$IssueNumber,

        [Parameter(Mandatory)]
        [string]$CommentFile,

        [Parameter()]
        [string]$Marker = "AI-TRIAGE"
    )

    if (-not (Test-Path $CommentFile)) {
        Write-LogError "Comment file not found: $CommentFile"
        return $false
    }

    $commentContent = Get-Content $CommentFile -Raw
    $commentBody = "<!-- $Marker -->`n$commentContent"

    Write-Log "Posting comment to issue #$IssueNumber"
    $commentBody | gh issue comment $IssueNumber --body-file -

    return $LASTEXITCODE -eq 0
}

function Get-VerdictEmoji {
    <#
    .SYNOPSIS
        Get the emoji for a verdict.

    .DESCRIPTION
        Maps verdict values to appropriate emojis for display.

    .PARAMETER Verdict
        The verdict value.

    .OUTPUTS
        System.String - The emoji for the verdict.

    .EXAMPLE
        $emoji = Get-VerdictEmoji -Verdict 'PASS'
        # Returns '✅'
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [string]$Verdict
    )

    switch ($Verdict) {
        'PASS' { return '✅' }
        'WARN' { return '⚠️' }
        { $_ -in 'CRITICAL_FAIL', 'REJECTED', 'FAIL' } { return '❌' }
        default { return '❔' }
    }
}

#endregion

#region Module Initialization

# Initialize on import
Initialize-AIReview | Out-Null

#endregion

# Export functions
Export-ModuleMember -Function @(
    # Initialization
    'Initialize-AIReview'
    # Retry logic
    'Invoke-WithRetry'
    # AI output parsing
    'Get-Verdict'
    'Get-Labels'
    'Get-Milestone'
    'Merge-Verdicts'
    # Markdown formatting
    'Format-CollapsibleSection'
    'Format-VerdictAlert'
    'Get-VerdictAlertType'
    'Get-VerdictExitCode'
    'Get-VerdictEmoji'
    # Logging
    'Write-Log'
    'Write-LogError'
    # Utilities
    'Assert-EnvironmentVariables'
    'Get-PRChangedFiles'
    'ConvertTo-JsonEscaped'
    'Format-MarkdownTableRow'
    # GitHub Comments
    'Send-PRComment'
    'Send-IssueComment'
)
