<#
.SYNOPSIS
    Tests whether a GitHub event is authorized to invoke Claude Code.

.DESCRIPTION
    Validates GitHub webhook events against authorization rules:
    - Checks for @claude mention in event body/title
    - Validates author association (MEMBER, OWNER, COLLABORATOR)
    - Allows specific bot accounts (dependabot, renovate, github-actions)

    Provides audit logging to GitHub Actions summary for security compliance.

    Per ADR-006, this script extracts complex conditional logic from workflow YAML
    to enable testing, debugging, and proper error handling.

.PARAMETER EventName
    GitHub event name (issue_comment, pull_request_review_comment, pull_request_review, issues)

.PARAMETER Actor
    GitHub actor triggering the event (e.g., username or bot name)

.PARAMETER AuthorAssociation
    Author's association with the repository (MEMBER, OWNER, COLLABORATOR, etc.)

.PARAMETER CommentBody
    Body text of a comment (for issue_comment and pull_request_review_comment events)

.PARAMETER ReviewBody
    Body text of a review (for pull_request_review events)

.PARAMETER IssueBody
    Body text of an issue (for issues events)

.PARAMETER IssueTitle
    Title of an issue (for issues events)

.OUTPUTS
    System.String
    Returns "true" if authorized, "false" if not authorized

.EXAMPLE
    Test-ClaudeAuthorization.ps1 -EventName "issue_comment" -Actor "octocat" -AuthorAssociation "MEMBER" -CommentBody "Hey @claude, can you help?"

    Returns "true" because MEMBER is authorized and @claude is mentioned

.EXAMPLE
    Test-ClaudeAuthorization.ps1 -EventName "issues" -Actor "external-user" -AuthorAssociation "CONTRIBUTOR" -IssueBody "Feature request"

    Returns "false" because no @claude mention

.NOTES
    This script logs all authorization attempts to GitHub Actions summary for audit trail.
    Exit code 0 indicates success (result in stdout), non-zero indicates script error.

    Error Handling:
    - All errors use Write-Error with -ErrorId for categorization
    - Script exits 1 on any error condition
    - Missing required parameters cause immediate failure
    - Regex matching errors are caught and logged

    Audit Logging:
    - Writes to GITHUB_STEP_SUMMARY when available
    - Logging failures do not block authorization (continue execution)
    - Includes timestamp, event details, decision, and reasoning

    Security:
    - Validates input length to prevent regex DoS (1MB max)
    - Case-sensitive @claude matching with negative lookahead pattern
    - All parameters validated before processing

    Configuration:
    - Bot allowlist must be synchronized with .github/workflows/claude.yml
    - Update both locations when modifying allowed bots
    - See lines 87-88 for bot list definition
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('issue_comment', 'pull_request_review_comment', 'pull_request_review', 'issues')]
    [string]$EventName,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$Actor,

    [Parameter()]
    [string]$AuthorAssociation = '',

    [Parameter()]
    [string]$CommentBody = '',

    [Parameter()]
    [string]$ReviewBody = '',

    [Parameter()]
    [string]$IssueBody = '',

    [Parameter()]
    [string]$IssueTitle = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

try {
    # Authorization configuration (single source of truth)
    $allowedAssociations = @('MEMBER', 'OWNER', 'COLLABORATOR')
    $allowedBots = @('dependabot[bot]', 'renovate[bot]', 'github-actions[bot]')

    # Extract body content based on event type
    $body = switch ($EventName) {
        'issue_comment' {
            if ([string]::IsNullOrWhiteSpace($CommentBody)) {
                Write-Error "Missing required CommentBody for issue_comment event" -ErrorId 'MissingRequiredParameter'
                exit 1
            }
            $CommentBody
        }
        'pull_request_review_comment' {
            if ([string]::IsNullOrWhiteSpace($CommentBody)) {
                Write-Error "Missing required CommentBody for pull_request_review_comment event" -ErrorId 'MissingRequiredParameter'
                exit 1
            }
            $CommentBody
        }
        'pull_request_review' {
            if ([string]::IsNullOrWhiteSpace($ReviewBody)) {
                Write-Error "Missing required ReviewBody for pull_request_review event" -ErrorId 'MissingRequiredParameter'
                exit 1
            }
            $ReviewBody
        }
        'issues' {
            # For issues events, check both body and title
            if ([string]::IsNullOrWhiteSpace($IssueBody) -and [string]::IsNullOrWhiteSpace($IssueTitle)) {
                Write-Error "Missing required IssueBody or IssueTitle for issues event - authorization will fail without @claude mention" -ErrorId 'MissingRequiredParameter'
                exit 1
            }
            "$IssueBody $IssueTitle"
        }
        default {
            # NOTE: Unreachable due to [ValidateSet] on $EventName parameter
            # Kept for defensive programming in case validation is removed
            Write-Error "Unexpected event type: $EventName" -ErrorId 'UnexpectedEventType'
            exit 1
        }
    }

    # Check for @claude mention (required for all events)
    # Validate input length to prevent regex DoS
    $maxBodyLength = 1MB
    if ($body.Length -gt $maxBodyLength) {
        Write-Warning "Event body exceeds maximum length ($maxBodyLength bytes), truncating for mention check"
        $body = $body.Substring(0, $maxBodyLength)
    }

    # Use case-sensitive match with negative lookahead to ensure word boundary
    # Pattern: @claude not followed by a word character (prevents @claudette, @claude123, @claude_bot, etc.)
    try {
        $hasMention = -not [string]::IsNullOrWhiteSpace($body) -and $body -cmatch '@claude(?!\w)'
    }
    catch {
        Write-Error "Failed to check for @claude mention: $_" -ErrorId 'RegexMatchFailed'
        exit 1
    }

    # Log authorization attempt for audit trail
    Write-Host "Authorization Check Details:"
    Write-Host "  Event: $EventName"
    Write-Host "  Actor: $Actor"
    Write-Host "  Author Association: $AuthorAssociation"
    Write-Host "  Has @claude Mention: $hasMention"

    # Determine authorization
    $isAuthorized = $false
    $authReason = ''

    if (-not $hasMention) {
        $authReason = "No @claude mention found in event body/title"
        Write-Host "Result: Not authorized - $authReason"
    }
    elseif ($allowedBots -contains $Actor) {
        $isAuthorized = $true
        $authReason = "Authorized via bot allowlist: $Actor"
        Write-Host "Result: Authorized - $authReason"
    }
    elseif ($allowedAssociations -contains $AuthorAssociation) {
        $isAuthorized = $true
        $authReason = "Authorized via author association: $AuthorAssociation"
        Write-Host "Result: Authorized - $authReason"
    }
    else {
        $authReason = "Access denied: Actor=$Actor is not in bot allowlist, Association=$AuthorAssociation is not in allowed list"
        Write-Host "Result: Not authorized - $authReason"
    }

    # Write audit log to GitHub Actions summary (if running in GitHub Actions)
    if ($env:GITHUB_STEP_SUMMARY) {
        try {
            $timestamp = Get-Date -Format 'o'
            $summary = @"
## Claude Authorization Check

| Property | Value |
|----------|-------|
| **Event Type** | $EventName |
| **Actor** | $Actor |
| **Author Association** | $AuthorAssociation |
| **Has @claude Mention** | $hasMention |
| **Authorized** | $isAuthorized |
| **Reason** | $authReason |
| **Timestamp** | $timestamp |

### Authorization Rules

**Allowed Author Associations**: $($allowedAssociations -join ', ')
**Allowed Bots**: $($allowedBots -join ', ')

### Security Note

GitHub may deprecate `author_association` from webhook payloads in the future.
This implementation will need to be updated when that deprecation takes effect.

"@
            Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value $summary -ErrorAction Stop
        }
        catch {
            Write-Warning "Failed to write to GitHub Actions summary: $_"
            # Continue execution - audit logging failure shouldn't block authorization
        }
    }

    # Return result (true/false as lowercase string for GitHub Actions)
    Write-Output $isAuthorized.ToString().ToLower()
    exit 0
}
catch {
    $errorDetails = @{
        Message = $_.Exception.Message
        EventName = $EventName
        Actor = $Actor
        AuthorAssociation = $AuthorAssociation
        StackTrace = $_.ScriptStackTrace
    }

    Write-Error "Authorization check failed: $($errorDetails | ConvertTo-Json -Compress)" -ErrorId 'AuthorizationCheckFailed'
    Write-Host "Error Details: Event=$EventName, Actor=$Actor, Association=$AuthorAssociation"

    # Log error to summary if available
    if ($env:GITHUB_STEP_SUMMARY) {
        try {
            $errorSummary = @"
## Claude Authorization Check - ERROR

**Error**: $($_.Exception.Message)
**Event**: $EventName
**Actor**: $Actor
**Association**: $AuthorAssociation
**Timestamp**: $(Get-Date -Format 'o')

Authorization check failed. Review workflow logs for details.
"@
            Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value $errorSummary -ErrorAction Stop
        }
        catch {
            Write-Warning "Failed to write error summary: $_"
        }
    }

    exit 1
}
