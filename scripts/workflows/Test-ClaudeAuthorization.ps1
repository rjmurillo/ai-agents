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
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('issue_comment', 'pull_request_review_comment', 'pull_request_review', 'issues')]
    [string]$EventName,

    [Parameter(Mandatory)]
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
                Write-Warning "Expected comment body for issue_comment event"
            }
            $CommentBody
        }
        'pull_request_review_comment' {
            if ([string]::IsNullOrWhiteSpace($CommentBody)) {
                Write-Warning "Expected comment body for pull_request_review_comment event"
            }
            $CommentBody
        }
        'pull_request_review' {
            if ([string]::IsNullOrWhiteSpace($ReviewBody)) {
                Write-Warning "Expected review body for pull_request_review event"
            }
            $ReviewBody
        }
        'issues' {
            # For issues events, check both body and title
            if ([string]::IsNullOrWhiteSpace($IssueBody) -and [string]::IsNullOrWhiteSpace($IssueTitle)) {
                Write-Warning "Expected issue body or title for issues event"
            }
            "$IssueBody $IssueTitle"
        }
        default {
            Write-Error "Unexpected event type: $EventName" -ErrorId 'UnexpectedEventType'
            exit 1
        }
    }

    # Check for @claude mention (required for all events)
    # Use case-sensitive match with lookahead to ensure exact @claude match (not @claudette)
    # Pattern: @claude not followed by a word character (letter/digit/_)
    $hasMention = -not [string]::IsNullOrWhiteSpace($body) -and $body -cmatch '@claude(?!\w)'

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

GitHub announced in August 2025 that `author_association` will be deprecated from webhook payloads.
This implementation will need to be updated when that deprecation takes effect.

"@
        Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value $summary
    }

    # Return result (true/false as lowercase string for GitHub Actions)
    Write-Output $isAuthorized.ToString().ToLower()
    exit 0
}
catch {
    Write-Error "Authorization check failed: $_" -ErrorId 'AuthorizationCheckFailed'

    # Log error to summary if available
    if ($env:GITHUB_STEP_SUMMARY) {
        $errorSummary = @"
## Claude Authorization Check - ERROR

**Error**: $($_.Exception.Message)
**Timestamp**: $(Get-Date -Format 'o')

Authorization check failed. Review workflow logs for details.
"@
        Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value $errorSummary
    }

    exit 1
}
