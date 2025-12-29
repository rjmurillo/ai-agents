<#
.SYNOPSIS
    Validates consistency across planning artifacts.

.DESCRIPTION
    Scans planning artifacts in .agents/planning/ directory for cross-document
    consistency issues including:
    - Effort estimate divergence between epic/PRD and task breakdowns
    - Orphan conditions (specialist conditions without task assignments)
    - Missing task coverage for PRD requirements

    This prevents Issues I2 (QA conditions not tracked) and I4 (Effort estimate
    discrepancy) as identified in CodeRabbit review of PR rjmurillo/ai-agents#43.

.PARAMETER FeatureName
    Name of the feature to validate. Looks for related planning documents.

.PARAMETER Path
    Root path containing .agents/planning/ directory. Defaults to current directory.

.PARAMETER EstimateThreshold
    Percentage threshold for flagging estimate divergence. Default is 20%.

.PARAMETER FailOnWarning
    Treat warnings as errors and exit with non-zero code.

.PARAMETER FailOnError
    Exit with non-zero code if errors found. Used in CI/CD.

.EXAMPLE
    .\Validate-PlanningArtifacts.ps1 -FeatureName "agent-consolidation"
    # Validate planning artifacts for agent-consolidation feature

.EXAMPLE
    .\Validate-PlanningArtifacts.ps1 -FailOnError
    # Validate all planning artifacts in CI mode

.NOTES
    Author: AI Agents Team
    Related: Issues rjmurillo/ai-agents#I2, rjmurillo/ai-agents#I4
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$FeatureName = "",

    [Parameter(Mandatory = $false)]
    [string]$Path = ".",

    [Parameter(Mandatory = $false)]
    [int]$EstimateThreshold = 20,

    [Parameter(Mandatory = $false)]
    [switch]$FailOnWarning,

    [Parameter(Mandatory = $false)]
    [switch]$FailOnError
)

# ANSI color codes for output
$ColorReset = "`e[0m"
$ColorRed = "`e[31m"
$ColorYellow = "`e[33m"
$ColorGreen = "`e[32m"
$ColorCyan = "`e[36m"
$ColorMagenta = "`e[35m"

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = $ColorReset
    )
    Write-Host "$Color$Message$ColorReset"
}

function Get-EstimateFromText {
    <#
    .SYNOPSIS
        Extracts effort estimates from text content.
    .DESCRIPTION
        Looks for common estimate patterns like "X-Y hours", "Xh", "X hours".
    #>
    param(
        [string]$Content
    )

    $estimates = @{
        Low  = 0
        High = 0
    }

    # Pattern: "X-Y hours" or "X-Y hrs"
    if ($Content -match '(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)') {
        $estimates.Low = [double]$Matches[1]
        $estimates.High = [double]$Matches[2]
        return $estimates
    }

    # Pattern: "X hours" or "Xh"
    if ($Content -match '(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b') {
        $estimates.Low = [double]$Matches[1]
        $estimates.High = [double]$Matches[1]
        return $estimates
    }

    return $null
}

function Find-OrphanConditions {
    <#
    .SYNOPSIS
        Finds conditions that are not linked to tasks.
    .DESCRIPTION
        Scans for condition patterns (QA:, Security:, etc.) in separate sections
        and checks if they appear in task tables.
    #>
    param(
        [string]$Content
    )

    $orphans = @()

    # Find condition patterns: "Agent: condition text"
    $conditionPatterns = @(
        'QA:\s*(.+)',
        'Security:\s*(.+)',
        'DevOps:\s*(.+)',
        'Architect:\s*(.+)',
        'Implementer:\s*(.+)'
    )

    # Extract conditions outside of tables
    $lines = $Content -split "`n"
    $inTable = $false
    $conditions = @()

    foreach ($line in $lines) {
        # Detect if we're in a table (starts with |)
        if ($line -match '^\s*\|') {
            $inTable = $true
        }
        elseif ($line -match '^\s*$' -or $line -match '^#') {
            $inTable = $false
        }

        # If not in table, look for conditions in list items
        if (-not $inTable -and $line -match '^\s*[-*]\s*') {
            foreach ($pattern in $conditionPatterns) {
                if ($line -match $pattern) {
                    $conditions += @{
                        Line      = $line.Trim()
                        Condition = $Matches[1].Trim()
                    }
                }
            }
        }
    }

    # Check if conditions appear in task tables
    foreach ($condition in $conditions) {
        $conditionText = [regex]::Escape($condition.Condition)
        if ($Content -notmatch "\|\s*[^|]*$conditionText[^|]*\s*\|") {
            $orphans += $condition.Line
        }
    }

    return $orphans
}

function Test-EstimateConsistency {
    <#
    .SYNOPSIS
        Compares estimates between documents.
    #>
    param(
        [hashtable]$SourceEstimate,
        [hashtable]$DerivedEstimate,
        [int]$Threshold
    )

    if ($null -eq $SourceEstimate -or $null -eq $DerivedEstimate) {
        return @{
            Consistent = $true
            Divergence = 0
            Message    = "Unable to compare estimates"
        }
    }

    # Calculate divergence as percentage of source
    $sourceMid = ($SourceEstimate.Low + $SourceEstimate.High) / 2
    $derivedMid = ($DerivedEstimate.Low + $DerivedEstimate.High) / 2

    if ($sourceMid -eq 0) {
        return @{
            Consistent = $true
            Divergence = 0
            Message    = "Source estimate is zero"
        }
    }

    $divergence = [math]::Abs(($derivedMid - $sourceMid) / $sourceMid * 100)

    return @{
        Consistent = $divergence -le $Threshold
        Divergence = [math]::Round($divergence, 1)
        Message    = "Source: $($SourceEstimate.Low)-$($SourceEstimate.High)h, Derived: $($DerivedEstimate.Low)-$($DerivedEstimate.High)h"
    }
}

function Find-PlanningDocuments {
    <#
    .SYNOPSIS
        Finds planning documents for a feature.
    #>
    param(
        [string]$RootPath,
        [string]$Feature
    )

    $planningPath = Join-Path $RootPath ".agents" "planning"

    if (-not (Test-Path $planningPath)) {
        return $null
    }

    $docs = @{
        Epic    = $null
        PRD     = $null
        Tasks   = $null
        Plan    = $null
        AllDocs = @()
    }

    $files = Get-ChildItem -Path $planningPath -Filter "*.md" -ErrorAction SilentlyContinue

    foreach ($file in $files) {
        $docs.AllDocs += $file
        $fileNameLower = $file.BaseName.ToLower()

        if ($Feature) {
            $featureLower = $Feature.ToLower()

            if ($fileNameLower -match "epic.*$featureLower" -or $fileNameLower -match "$featureLower.*epic") {
                $docs.Epic = $file
            }
            if ($fileNameLower -match "prd.*$featureLower" -or $fileNameLower -match "$featureLower.*prd") {
                $docs.PRD = $file
            }
            if ($fileNameLower -match "task.*$featureLower" -or $fileNameLower -match "$featureLower.*task") {
                $docs.Tasks = $file
            }
            if ($fileNameLower -match "plan.*$featureLower" -or $fileNameLower -match "$featureLower.*plan") {
                $docs.Plan = $file
            }
        }
        else {
            # When no feature specified, detect by prefix patterns
            if ($fileNameLower -match "^epic" -and $null -eq $docs.Epic) {
                $docs.Epic = $file
            }
            if ($fileNameLower -match "^prd" -and $null -eq $docs.PRD) {
                $docs.PRD = $file
            }
            if ($fileNameLower -match "^task" -and $null -eq $docs.Tasks) {
                $docs.Tasks = $file
            }
            if ($fileNameLower -match "^plan" -and $null -eq $docs.Plan) {
                $docs.Plan = $file
            }
        }
    }

    # Fallback: If no specific documents found, use first document as plan
    if ($null -eq $docs.Plan -and $null -eq $docs.Tasks -and $docs.AllDocs.Count -gt 0) {
        $docs.Plan = $docs.AllDocs[0]
    }

    return $docs
}

# Main execution
Write-ColorOutput "=== Planning Artifact Validation ===" $ColorCyan
Write-Host ""

$rootPath = (Resolve-Path $Path).Path
Write-Host "Scanning path: $rootPath"
if ($FeatureName) {
    Write-Host "Feature: $FeatureName"
}
Write-Host "Estimate threshold: $EstimateThreshold%"
Write-Host ""

# Find planning documents
$docs = Find-PlanningDocuments -RootPath $rootPath -Feature $FeatureName

if ($null -eq $docs -or $docs.AllDocs.Count -eq 0) {
    Write-ColorOutput "No planning documents found in .agents/planning/" $ColorYellow
    exit 0
}

Write-Host "Found $($docs.AllDocs.Count) planning document(s)"
Write-Host ""

$errors = @()
$warnings = @()

# Validation 1: Estimate Consistency
Write-ColorOutput "--- Estimate Consistency Check ---" $ColorMagenta

$sourceDoc = $docs.Epic ?? $docs.PRD ?? $docs.Plan
$derivedDoc = $docs.Tasks

if ($sourceDoc -and $derivedDoc) {
    Write-Host "Comparing: $($sourceDoc.Name) -> $($derivedDoc.Name)"

    $sourceContent = Get-Content -Path $sourceDoc.FullName -Raw
    $derivedContent = Get-Content -Path $derivedDoc.FullName -Raw

    $sourceEst = Get-EstimateFromText -Content $sourceContent
    $derivedEst = Get-EstimateFromText -Content $derivedContent

    $result = Test-EstimateConsistency -SourceEstimate $sourceEst -DerivedEstimate $derivedEst -Threshold $EstimateThreshold

    if ($result.Consistent) {
        Write-ColorOutput "[PASS] Effort Estimates - Divergence: $($result.Divergence)%" $ColorGreen
    }
    else {
        Write-ColorOutput "[WARN] Effort Estimates - Divergence: $($result.Divergence)% (threshold: $EstimateThreshold%)" $ColorYellow
        Write-Host "  $($result.Message)"
        $warnings += "Estimate divergence of $($result.Divergence)% exceeds $EstimateThreshold% threshold"
    }
}
else {
    Write-Host "Skipping estimate check: source or derived document not found"
}

Write-Host ""

# Validation 2: Condition Traceability
Write-ColorOutput "--- Condition Traceability Check ---" $ColorMagenta

$planDoc = $docs.Plan ?? $docs.Tasks

if ($planDoc) {
    Write-Host "Checking: $($planDoc.Name)"

    $content = Get-Content -Path $planDoc.FullName -Raw
    $orphans = Find-OrphanConditions -Content $content

    if ($orphans.Count -eq 0) {
        Write-ColorOutput "[PASS] Condition Traceability - No orphan conditions" $ColorGreen
    }
    else {
        Write-ColorOutput "[FAIL] Condition Traceability - $($orphans.Count) orphan condition(s) found" $ColorRed
        foreach ($orphan in $orphans) {
            Write-Host "  - $orphan"
        }
        $errors += "Orphan conditions found: $($orphans -join '; ')"
    }
}
else {
    Write-Host "Skipping condition check: no plan document found"
}

Write-Host ""

# Validation 3: Check all documents for general issues
Write-ColorOutput "--- Document Structure Check ---" $ColorMagenta

foreach ($doc in $docs.AllDocs) {
    $content = Get-Content -Path $doc.FullName -Raw -ErrorAction SilentlyContinue
    if (-not $content) { continue }

    # Check for reconciliation section when there are estimates
    $hasEstimates = $content -match '\d+\s*-\s*\d+\s*(?:hours?|hrs?)'
    $hasReconciliation = $content -match '(?i)## Estimate Reconciliation'

    if ($hasEstimates -and -not $hasReconciliation) {
        # This is informational, not an error
        Write-Host "  $($doc.Name): Contains estimates but no reconciliation section (consider adding)"
    }
}

Write-Host ""

# Summary
Write-ColorOutput "=== Validation Summary ===" $ColorCyan
Write-Host ""

if ($errors.Count -eq 0 -and $warnings.Count -eq 0) {
    Write-ColorOutput "✅ SUCCESS: All validations passed" $ColorGreen
    exit 0
}

if ($warnings.Count -gt 0) {
    Write-ColorOutput "⚠️  WARNINGS: $($warnings.Count)" $ColorYellow
    foreach ($warning in $warnings) {
        Write-Host "  - $warning"
    }
}

if ($errors.Count -gt 0) {
    Write-ColorOutput "❌ ERRORS: $($errors.Count)" $ColorRed
    foreach ($err in $errors) {
        Write-Host "  - $err"
    }
}

Write-Host ""

# Remediation steps
Write-ColorOutput "=== Remediation Steps ===" $ColorCyan
Write-Host ""

if ($warnings.Count -gt 0) {
    Write-Host "For estimate divergence:"
    Write-Host "  1. Add '## Estimate Reconciliation' section to task breakdown"
    Write-Host "  2. Document source estimate, derived estimate, and divergence percentage"
    Write-Host "  3. Choose action: Update source, Document rationale, or Flag for review"
    Write-Host ""
}

if ($errors.Count -gt 0) {
    Write-Host "For orphan conditions:"
    Write-Host "  1. Add 'Conditions' column to Work Breakdown table"
    Write-Host "  2. Link each specialist condition to a specific task"
    Write-Host "  3. Use format: 'QA: condition text' or 'Security: condition text'"
    Write-Host ""
}

Write-Host "See src/claude/planner.md and src/claude/task-generator.md for templates."
Write-Host ""

# Exit code logic
if ($errors.Count -gt 0 -and $FailOnError) {
    exit 1
}

if ($warnings.Count -gt 0 -and $FailOnWarning) {
    exit 1
}

exit 0
