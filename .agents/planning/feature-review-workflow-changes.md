# Feature Review Workflow Changes

**Date**: 2025-12-19
**ADR**: ADR-020-feature-request-review-step.md
**Status**: Draft - Pending Review

## Summary

This document specifies the workflow YAML changes required to implement the feature request review capability.

## File: `.github/workflows/ai-issue-triage.yml`

### Insert After Line 69 (after Parse Categorization Results step)

```yaml
      - name: Review Feature Request (Analyst Agent)
        id: review-feature
        if: steps.parse-categorize.outputs.category == 'enhancement'
        uses: ./.github/actions/ai-review
        with:
          agent: analyst
          context-type: issue
          issue-number: ${{ github.event.issue.number }}
          prompt-file: .github/prompts/issue-feature-review.md
          timeout-minutes: 3
          bot-pat: ${{ secrets.BOT_PAT }}
          copilot-token: ${{ secrets.COPILOT_GITHUB_TOKEN }}

      - name: Parse Feature Review Results
        id: parse-review
        if: steps.review-feature.outcome == 'success'
        shell: pwsh
        env:
          RAW_OUTPUT: ${{ steps.review-feature.outputs.findings }}
        run: |
          Import-Module .github/scripts/AIReviewCommon.psm1

          # Parse recommendation
          $recommendation = Get-FeatureReviewRecommendation -Output $env:RAW_OUTPUT

          # Parse suggested assignees (comma-separated)
          $assignees = Get-FeatureReviewAssignees -Output $env:RAW_OUTPUT

          # Parse suggested labels
          $labels = Get-FeatureReviewLabels -Output $env:RAW_OUTPUT

          echo "recommendation=$recommendation" >> $env:GITHUB_OUTPUT
          echo "assignees=$assignees" >> $env:GITHUB_OUTPUT
          echo "labels=$labels" >> $env:GITHUB_OUTPUT
```

### Modify Post Triage Summary Step

Add feature review results to the triage summary comment:

```yaml
        env:
          # ... existing env vars ...
          FEATURE_REVIEW: ${{ steps.parse-review.outputs.recommendation }}
          FEATURE_REVIEW_OUTPUT: ${{ steps.review-feature.outputs.findings }}
```

Add to PowerShell template:

```powershell
# Add feature review section if applicable
$featureRow = if ($env:FEATURE_REVIEW) {
  "| **Feature Review** | ``$($env:FEATURE_REVIEW)`` |"
} else {
  ""
}
```

And in the comment body, add after `$prdRow`:

```powershell
$featureRow
```

Add collapsible section for feature review details:

```powershell
$featureDetails = if ($env:FEATURE_REVIEW_OUTPUT) {
  @"

<details>
<summary>Feature Request Review</summary>

$($env:FEATURE_REVIEW_OUTPUT)

</details>
"@
} else {
  ""
}
```

## File: `.github/scripts/AIReviewCommon.psm1`

### Add New Functions

```powershell
<#
.SYNOPSIS
    Extracts the feature review recommendation from AI output.

.DESCRIPTION
    Parses the AI output to find the RECOMMENDATION line and extracts
    the recommendation value (PROCEED, DEFER, REQUEST_EVIDENCE,
    NEEDS_RESEARCH, or DECLINE).

.PARAMETER Output
    The raw AI output string to parse.

.OUTPUTS
    System.String. The recommendation value or "UNKNOWN" if not found.

.EXAMPLE
    $recommendation = Get-FeatureReviewRecommendation -Output $aiOutput
#>
function Get-FeatureReviewRecommendation {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Output
    )

    if ([string]::IsNullOrWhiteSpace($Output)) {
        return "UNKNOWN"
    }

    # Match RECOMMENDATION: followed by the value
    $pattern = 'RECOMMENDATION:\s*(PROCEED|DEFER|REQUEST_EVIDENCE|NEEDS_RESEARCH|DECLINE)'
    if ($Output -match $pattern) {
        return $Matches[1]
    }

    # Fallback: check for keywords in context
    if ($Output -match '\bPROCEED\b' -and $Output -notmatch '\bDECLINE\b') {
        return "PROCEED"
    }
    if ($Output -match '\bDECLINE\b') {
        return "DECLINE"
    }
    if ($Output -match '\bDEFER\b') {
        return "DEFER"
    }

    return "UNKNOWN"
}

<#
.SYNOPSIS
    Extracts suggested assignees from feature review AI output.

.DESCRIPTION
    Parses the Assignees line from the AI output and returns
    a comma-separated list of GitHub usernames.

.PARAMETER Output
    The raw AI output string to parse.

.OUTPUTS
    System.String. Comma-separated usernames or empty string.

.EXAMPLE
    $assignees = Get-FeatureReviewAssignees -Output $aiOutput
#>
function Get-FeatureReviewAssignees {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Output
    )

    if ([string]::IsNullOrWhiteSpace($Output)) {
        return ""
    }

    # Match Assignees: followed by value (handles markdown bold)
    $pattern = '\*{0,2}Assignees\*{0,2}:\s*(.+?)(?:\r?\n|$)'
    if ($Output -match $pattern) {
        $value = $Matches[1].Trim()

        # Skip "none suggested" type responses
        if ($value -match '^(none|no one|none suggested|n/a)') {
            return ""
        }

        # Extract @usernames or plain usernames
        $usernames = [regex]::Matches($value, '@?([a-zA-Z0-9][-a-zA-Z0-9]*)') |
            ForEach-Object { $_.Groups[1].Value } |
            Where-Object { $_ -notmatch '^(none|suggested|or)$' }

        return ($usernames -join ',')
    }

    return ""
}

<#
.SYNOPSIS
    Extracts suggested labels from feature review AI output.

.DESCRIPTION
    Parses the Labels line from the AI output and returns
    a comma-separated list of labels.

.PARAMETER Output
    The raw AI output string to parse.

.OUTPUTS
    System.String. Comma-separated labels or empty string.

.EXAMPLE
    $labels = Get-FeatureReviewLabels -Output $aiOutput
#>
function Get-FeatureReviewLabels {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Output
    )

    if ([string]::IsNullOrWhiteSpace($Output)) {
        return ""
    }

    # Match Labels: followed by value (handles markdown bold)
    $pattern = '\*{0,2}Labels\*{0,2}:\s*(.+?)(?:\r?\n|$)'
    if ($Output -match $pattern) {
        $value = $Matches[1].Trim()

        # Skip "none" type responses
        if ($value -match '^(none|no additional|n/a)') {
            return ""
        }

        # Extract backtick-wrapped labels or comma-separated values
        $labels = [regex]::Matches($value, '`([^`]+)`|([a-z][-a-z0-9:]+)') |
            ForEach-Object {
                if ($_.Groups[1].Success) { $_.Groups[1].Value }
                elseif ($_.Groups[2].Success) { $_.Groups[2].Value }
            } |
            Where-Object { $_ -and $_ -notmatch '^(none|or|and)$' }

        return ($labels -join ',')
    }

    return ""
}
```

### Export Functions

Add to the module's Export-ModuleMember (if using):

```powershell
Export-ModuleMember -Function @(
    # ... existing functions ...
    'Get-FeatureReviewRecommendation',
    'Get-FeatureReviewAssignees',
    'Get-FeatureReviewLabels'
)
```

## File: `.github/scripts/AIReviewCommon.Tests.ps1`

### Add Test Cases

```powershell
Describe 'Get-FeatureReviewRecommendation' {
    BeforeAll {
        Import-Module "$PSScriptRoot/AIReviewCommon.psm1" -Force
    }

    Context 'When output contains explicit RECOMMENDATION' {
        It 'Extracts PROCEED' {
            $output = "RECOMMENDATION: PROCEED`nRationale: Clear value"
            Get-FeatureReviewRecommendation -Output $output | Should -Be "PROCEED"
        }

        It 'Extracts DEFER' {
            $output = "RECOMMENDATION: DEFER`nRationale: Wrong timing"
            Get-FeatureReviewRecommendation -Output $output | Should -Be "DEFER"
        }

        It 'Extracts REQUEST_EVIDENCE' {
            $output = "RECOMMENDATION: REQUEST_EVIDENCE`nRationale: Need data"
            Get-FeatureReviewRecommendation -Output $output | Should -Be "REQUEST_EVIDENCE"
        }

        It 'Extracts NEEDS_RESEARCH' {
            $output = "RECOMMENDATION: NEEDS_RESEARCH"
            Get-FeatureReviewRecommendation -Output $output | Should -Be "NEEDS_RESEARCH"
        }

        It 'Extracts DECLINE' {
            $output = "RECOMMENDATION: DECLINE`nRationale: Out of scope"
            Get-FeatureReviewRecommendation -Output $output | Should -Be "DECLINE"
        }
    }

    Context 'When output is empty or malformed' {
        It 'Returns UNKNOWN for empty string' {
            Get-FeatureReviewRecommendation -Output "" | Should -Be "UNKNOWN"
        }

        It 'Returns UNKNOWN for whitespace' {
            Get-FeatureReviewRecommendation -Output "   " | Should -Be "UNKNOWN"
        }

        It 'Returns UNKNOWN when no recommendation found' {
            $output = "This is some text without a recommendation"
            Get-FeatureReviewRecommendation -Output $output | Should -Be "UNKNOWN"
        }
    }

    Context 'Fallback keyword detection' {
        It 'Detects PROCEED keyword in context' {
            $output = "I recommend we PROCEED with this feature"
            Get-FeatureReviewRecommendation -Output $output | Should -Be "PROCEED"
        }

        It 'Detects DECLINE keyword' {
            $output = "We should DECLINE this request"
            Get-FeatureReviewRecommendation -Output $output | Should -Be "DECLINE"
        }
    }
}

Describe 'Get-FeatureReviewAssignees' {
    BeforeAll {
        Import-Module "$PSScriptRoot/AIReviewCommon.psm1" -Force
    }

    Context 'When assignees are specified' {
        It 'Extracts single username' {
            $output = "**Assignees**: @rjmurillo"
            Get-FeatureReviewAssignees -Output $output | Should -Be "rjmurillo"
        }

        It 'Extracts multiple usernames' {
            $output = "**Assignees**: @user1, @user2, @user3"
            Get-FeatureReviewAssignees -Output $output | Should -Be "user1,user2,user3"
        }

        It 'Handles usernames without @ prefix' {
            $output = "Assignees: user1, user2"
            Get-FeatureReviewAssignees -Output $output | Should -Be "user1,user2"
        }
    }

    Context 'When no assignees suggested' {
        It 'Returns empty for "none suggested"' {
            $output = "**Assignees**: none suggested"
            Get-FeatureReviewAssignees -Output $output | Should -Be ""
        }

        It 'Returns empty for empty string' {
            Get-FeatureReviewAssignees -Output "" | Should -Be ""
        }
    }
}

Describe 'Get-FeatureReviewLabels' {
    BeforeAll {
        Import-Module "$PSScriptRoot/AIReviewCommon.psm1" -Force
    }

    Context 'When labels are specified' {
        It 'Extracts backtick-wrapped labels' {
            $output = "**Labels**: `enhancement`, `needs-design`"
            Get-FeatureReviewLabels -Output $output | Should -Be "enhancement,needs-design"
        }

        It 'Extracts plain labels' {
            $output = "Labels: priority:P1, area-workflows"
            Get-FeatureReviewLabels -Output $output | Should -Be "priority:P1,area-workflows"
        }
    }

    Context 'When no labels suggested' {
        It 'Returns empty for "none"' {
            $output = "**Labels**: none"
            Get-FeatureReviewLabels -Output $output | Should -Be ""
        }
    }
}
```

## Implementation Checklist

- [ ] ADR-020 reviewed and accepted
- [ ] Prompt file created: `.github/prompts/issue-feature-review.md`
- [ ] PowerShell functions added to `AIReviewCommon.psm1`
- [ ] Pester tests added to `AIReviewCommon.Tests.ps1`
- [ ] Tests passing locally: `Invoke-Pester`
- [ ] Workflow YAML updated
- [ ] Manual test with sample feature request issue
- [ ] Create issue on rjmurillo/ai-agents with design proposal

## Rollback Plan

If the feature causes issues:

1. Comment out the two new steps (`review-feature` and `parse-review`)
2. Remove feature review from triage summary template
3. Keep PowerShell functions (they are tested and harmless)

## Timeline

| Task | Effort | Owner |
|------|--------|-------|
| ADR review | 15 min | User |
| PowerShell functions | 1 hr | Implementer |
| Pester tests | 1 hr | Implementer |
| Workflow YAML | 30 min | Implementer |
| Manual testing | 30 min | QA |
| Issue creation | 15 min | Orchestrator |

**Total**: ~3.5 hours
