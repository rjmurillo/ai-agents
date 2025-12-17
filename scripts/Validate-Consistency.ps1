<#
.SYNOPSIS
    Validates cross-document consistency for agent-generated artifacts.

.DESCRIPTION
    Implements the validation procedure defined in .agents/governance/consistency-protocol.md.
    Checks scope alignment, coverage, naming conventions, cross-references, and task status.

.PARAMETER Feature
    Name of the feature to validate (e.g., "user-authentication").
    Will look for EPIC-*-[feature].md, prd-[feature].md, tasks-[feature].md

.PARAMETER All
    Validate all features found in .agents/ directories.

.PARAMETER Checkpoint
    Which checkpoint to validate: 1 (Pre-Critic) or 2 (Post-Implementation).
    Default: 1

.PARAMETER Format
    Output format: "console", "markdown", or "json".
    Default: "console"

.PARAMETER CI
    CI mode - returns non-zero exit code on failures.

.PARAMETER Path
    Base path to scan. Default: current directory.

.EXAMPLE
    .\Validate-Consistency.ps1 -Feature "user-authentication"

.EXAMPLE
    .\Validate-Consistency.ps1 -All -CI

.EXAMPLE
    .\Validate-Consistency.ps1 -Feature "auth" -Format "markdown"
#>

[CmdletBinding(DefaultParameterSetName = 'Feature')]
param(
    [Parameter(ParameterSetName = 'Feature', Mandatory = $true)]
    [string]$Feature,

    [Parameter(ParameterSetName = 'All', Mandatory = $true)]
    [switch]$All,

    [Parameter()]
    [ValidateSet(1, 2)]
    [int]$Checkpoint = 1,

    [Parameter()]
    [ValidateSet("console", "markdown", "json")]
    [string]$Format = "console",

    [Parameter()]
    [switch]$CI,

    [Parameter()]
    [string]$Path = "."
)

#region Color Output
$ColorReset = "`e[0m"
$ColorRed = "`e[31m"
$ColorYellow = "`e[33m"
$ColorGreen = "`e[32m"
$ColorCyan = "`e[36m"
$ColorMagenta = "`e[35m"

function Write-ColorOutput {
    param([string]$Message, [string]$Color = $ColorReset)
    if ($Format -eq "console") {
        Write-Host "${Color}${Message}${ColorReset}"
    }
}
#endregion

#region Validation Functions

function Test-NamingConvention {
    <#
    .SYNOPSIS
        Validates file naming against conventions from naming-conventions.md
    #>
    param(
        [string]$FilePath,
        [string]$ExpectedPattern
    )

    $fileName = Split-Path -Leaf $FilePath

    $patterns = @{
        'epic'    = '^EPIC-\d{3}-[\w-]+\.md$'
        'adr'     = '^ADR-\d{3}-[\w-]+\.md$'
        'prd'     = '^prd-[\w-]+\.md$'
        'tasks'   = '^tasks-[\w-]+\.md$'
        'plan'    = '^\d{3}-[\w-]+-plan\.md$|^(implementation-plan|plan)-[\w-]+\.md$'
        'tm'      = '^TM-\d{3}-[\w-]+\.md$'
    }

    if ($patterns.ContainsKey($ExpectedPattern)) {
        # Use case-sensitive matching (-cmatch)
        return $fileName -cmatch $patterns[$ExpectedPattern]
    }

    return $true  # Unknown pattern, skip validation
}

function Find-FeatureArtifacts {
    <#
    .SYNOPSIS
        Finds all artifacts related to a feature name
    #>
    param(
        [string]$FeatureName,
        [string]$BasePath
    )

    $artifacts = @{
        Epic = $null
        PRD = $null
        Tasks = $null
        Plan = $null
    }

    $agentsPath = Join-Path $BasePath ".agents"

    # Find Epic
    $epicPath = Join-Path $agentsPath "roadmap"
    if (Test-Path $epicPath) {
        $epic = Get-ChildItem -Path $epicPath -Filter "EPIC-*-*$FeatureName*.md" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($epic) { $artifacts.Epic = $epic.FullName }
    }

    # Find PRD
    $planningPath = Join-Path $agentsPath "planning"
    if (Test-Path $planningPath) {
        $prd = Get-ChildItem -Path $planningPath -Filter "prd-*$FeatureName*.md" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($prd) { $artifacts.PRD = $prd.FullName }

        $tasks = Get-ChildItem -Path $planningPath -Filter "tasks-*$FeatureName*.md" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($tasks) { $artifacts.Tasks = $tasks.FullName }

        $plan = Get-ChildItem -Path $planningPath -Filter "*plan*$FeatureName*.md" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($plan) { $artifacts.Plan = $plan.FullName }
    }

    return $artifacts
}

function Get-AllFeatures {
    <#
    .SYNOPSIS
        Discovers all features from existing artifacts
    #>
    param([string]$BasePath)

    $features = @()
    $planningPath = Join-Path $BasePath ".agents/planning"

    if (Test-Path $planningPath) {
        # Extract feature names from prd-*.md files
        Get-ChildItem -Path $planningPath -Filter "prd-*.md" -ErrorAction SilentlyContinue | ForEach-Object {
            $name = $_.BaseName -replace '^prd-', ''
            if ($name -and $name -notin $features) {
                $features += $name
            }
        }

        # Also check tasks-*.md
        Get-ChildItem -Path $planningPath -Filter "tasks-*.md" -ErrorAction SilentlyContinue | ForEach-Object {
            $name = $_.BaseName -replace '^tasks-', ''
            if ($name -and $name -notin $features) {
                $features += $name
            }
        }
    }

    return $features
}

function Test-ScopeAlignment {
    <#
    .SYNOPSIS
        Validates that PRD scope aligns with Epic outcomes
    #>
    param(
        [string]$EpicPath,
        [string]$PRDPath
    )

    $result = @{
        Passed = $true
        Issues = @()
    }

    if (-not $EpicPath -or -not (Test-Path $EpicPath)) {
        $result.Issues += "Epic file not found"
        return $result  # Not a failure if epic doesn't exist
    }

    if (-not $PRDPath -or -not (Test-Path $PRDPath)) {
        $result.Passed = $false
        $result.Issues += "PRD file not found"
        return $result
    }

    $epicContent = Get-Content -Path $EpicPath -Raw
    $prdContent = Get-Content -Path $PRDPath -Raw

    # Check if PRD references the epic
    $epicName = Split-Path -Leaf $EpicPath
    if ($prdContent -notmatch [regex]::Escape($epicName) -and $prdContent -notmatch 'EPIC-\d{3}') {
        $result.Issues += "PRD does not reference parent Epic"
    }

    # Extract success criteria from epic
    if ($epicContent -match '(?s)### Success Criteria(.+?)(?=###|$)') {
        $criteria = $Matches[1]
        $criteriaCount = ([regex]::Matches($criteria, '- \[[ x]\]')).Count
        if ($criteriaCount -gt 0) {
            # Check PRD has corresponding requirements
            if ($prdContent -match '(?s)## Requirements(.+?)(?=##|$)') {
                $requirements = $Matches[1]
                $reqCount = ([regex]::Matches($requirements, '(?m)- \[[ x]\]|^\d+\.|^-\s')).Count
                if ($reqCount -lt $criteriaCount) {
                    $result.Issues += "PRD has fewer requirements ($reqCount) than Epic success criteria ($criteriaCount)"
                }
            }
        }
    }

    if ($result.Issues.Count -gt 0) {
        $result.Passed = $false
    }

    return $result
}

function Test-RequirementCoverage {
    <#
    .SYNOPSIS
        Validates that all PRD requirements have corresponding tasks
    #>
    param(
        [string]$PRDPath,
        [string]$TasksPath
    )

    $result = @{
        Passed = $true
        Issues = @()
        RequirementCount = 0
        TaskCount = 0
    }

    if (-not $PRDPath -or -not (Test-Path $PRDPath)) {
        return $result  # Skip if no PRD
    }

    if (-not $TasksPath -or -not (Test-Path $TasksPath)) {
        $result.Passed = $false
        $result.Issues += "Tasks file not found for PRD"
        return $result
    }

    $prdContent = Get-Content -Path $PRDPath -Raw
    $tasksContent = Get-Content -Path $TasksPath -Raw

    # Count requirements in PRD (look for checkbox lists or numbered items)
    $reqMatches = [regex]::Matches($prdContent, '(?m)^[\s]*[-*]\s+\[[ x]\]|^[\s]*\d+\.\s+')
    $result.RequirementCount = $reqMatches.Count

    # Count tasks
    $taskMatches = [regex]::Matches($tasksContent, '(?m)^[\s]*[-*]\s+\[[ x]\]|^###\s+Task')
    $result.TaskCount = $taskMatches.Count

    if ($result.TaskCount -lt $result.RequirementCount) {
        $result.Passed = $false
        $result.Issues += "Fewer tasks ($($result.TaskCount)) than requirements ($($result.RequirementCount))"
    }

    return $result
}

function Test-CrossReferences {
    <#
    .SYNOPSIS
        Validates that cross-references point to existing files
    #>
    param(
        [string]$FilePath,
        [string]$BasePath
    )

    $result = @{
        Passed = $true
        Issues = @()
        References = @()
    }

    if (-not $FilePath -or -not (Test-Path $FilePath)) {
        return $result
    }

    $content = Get-Content -Path $FilePath -Raw
    $fileDir = Split-Path -Parent $FilePath

    # Find markdown links: [text](path)
    $linkMatches = [regex]::Matches($content, '\[([^\]]+)\]\(([^)]+)\)')

    foreach ($match in $linkMatches) {
        $linkPath = $match.Groups[2].Value

        # Skip URLs and anchors
        if ($linkPath -match '^https?://' -or $linkPath -match '^#') {
            continue
        }

        # Remove anchor from path
        $linkPath = $linkPath -replace '#.*$', ''

        if ($linkPath) {
            $result.References += $linkPath

            # Resolve relative path
            $fullPath = if ([System.IO.Path]::IsPathRooted($linkPath)) {
                $linkPath
            } else {
                Join-Path $fileDir $linkPath
            }

            if (-not (Test-Path $fullPath)) {
                $result.Passed = $false
                $result.Issues += "Broken reference: $linkPath"
            }
        }
    }

    return $result
}

function Test-TaskCompletion {
    <#
    .SYNOPSIS
        Validates task completion status for Checkpoint 2
    #>
    param([string]$TasksPath)

    $result = @{
        Passed = $true
        Issues = @()
        Total = 0
        Completed = 0
        P0Incomplete = @()
        P1Incomplete = @()
    }

    if (-not $TasksPath -or -not (Test-Path $TasksPath)) {
        return $result
    }

    $content = Get-Content -Path $TasksPath -Raw
    $lines = $content -split "`n"

    $currentPriority = "P2"

    foreach ($line in $lines) {
        # Detect priority sections
        if ($line -match '##.*P0|Priority:\s*P0|### P0') {
            $currentPriority = "P0"
        } elseif ($line -match '##.*P1|Priority:\s*P1|### P1') {
            $currentPriority = "P1"
        } elseif ($line -match '##.*P2|Priority:\s*P2|### P2') {
            $currentPriority = "P2"
        }

        # Count tasks
        if ($line -match '^\s*[-*]\s+\[([x ])\]\s+(.+)$') {
            $result.Total++
            $isComplete = $Matches[1] -eq 'x'
            $taskName = $Matches[2].Trim()

            if ($isComplete) {
                $result.Completed++
            } else {
                if ($currentPriority -eq "P0") {
                    $result.P0Incomplete += $taskName
                } elseif ($currentPriority -eq "P1") {
                    $result.P1Incomplete += $taskName
                }
            }
        }
    }

    if ($result.P0Incomplete.Count -gt 0) {
        $result.Passed = $false
        $result.Issues += "P0 tasks incomplete: $($result.P0Incomplete.Count)"
    }

    return $result
}

function Test-NamingConventions {
    <#
    .SYNOPSIS
        Validates all artifact naming conventions
    #>
    param([hashtable]$Artifacts)

    $result = @{
        Passed = $true
        Issues = @()
    }

    $checks = @(
        @{ Path = $Artifacts.Epic; Type = 'epic'; Name = 'Epic' }
        @{ Path = $Artifacts.PRD; Type = 'prd'; Name = 'PRD' }
        @{ Path = $Artifacts.Tasks; Type = 'tasks'; Name = 'Tasks' }
        @{ Path = $Artifacts.Plan; Type = 'plan'; Name = 'Plan' }
    )

    foreach ($check in $checks) {
        if ($check.Path -and (Test-Path $check.Path)) {
            if (-not (Test-NamingConvention -FilePath $check.Path -ExpectedPattern $check.Type)) {
                $result.Passed = $false
                $fileName = Split-Path -Leaf $check.Path
                $result.Issues += "$($check.Name) naming violation: $fileName"
            }
        }
    }

    return $result
}

#endregion

#region Main Validation Logic

function Invoke-FeatureValidation {
    param(
        [string]$FeatureName,
        [string]$BasePath,
        [int]$CheckpointNum
    )

    $validation = @{
        Feature = $FeatureName
        Checkpoint = $CheckpointNum
        Passed = $true
        Artifacts = @{}
        Results = @{}
        Issues = @()
    }

    # Find artifacts
    $artifacts = Find-FeatureArtifacts -FeatureName $FeatureName -BasePath $BasePath
    $validation.Artifacts = $artifacts

    # Run Checkpoint 1 validations
    if ($CheckpointNum -ge 1) {
        # Scope Alignment
        $scopeResult = Test-ScopeAlignment -EpicPath $artifacts.Epic -PRDPath $artifacts.PRD
        $validation.Results['ScopeAlignment'] = $scopeResult
        if (-not $scopeResult.Passed) {
            $validation.Passed = $false
            $validation.Issues += $scopeResult.Issues
        }

        # Requirement Coverage
        $coverageResult = Test-RequirementCoverage -PRDPath $artifacts.PRD -TasksPath $artifacts.Tasks
        $validation.Results['RequirementCoverage'] = $coverageResult
        if (-not $coverageResult.Passed) {
            $validation.Passed = $false
            $validation.Issues += $coverageResult.Issues
        }

        # Naming Conventions
        $namingResult = Test-NamingConventions -Artifacts $artifacts
        $validation.Results['NamingConventions'] = $namingResult
        if (-not $namingResult.Passed) {
            $validation.Passed = $false
            $validation.Issues += $namingResult.Issues
        }

        # Cross-References (check all artifacts)
        $refIssues = @()
        foreach ($artifactPath in $artifacts.Values) {
            if ($artifactPath) {
                $refResult = Test-CrossReferences -FilePath $artifactPath -BasePath $BasePath
                if (-not $refResult.Passed) {
                    $refIssues += $refResult.Issues
                }
            }
        }
        $validation.Results['CrossReferences'] = @{ Passed = ($refIssues.Count -eq 0); Issues = $refIssues }
        if ($refIssues.Count -gt 0) {
            $validation.Passed = $false
            $validation.Issues += $refIssues
        }
    }

    # Run Checkpoint 2 validations
    if ($CheckpointNum -ge 2) {
        $taskResult = Test-TaskCompletion -TasksPath $artifacts.Tasks
        $validation.Results['TaskCompletion'] = $taskResult
        if (-not $taskResult.Passed) {
            $validation.Passed = $false
            $validation.Issues += $taskResult.Issues
        }
    }

    return $validation
}

#endregion

#region Output Formatting

function Format-ConsoleOutput {
    param([array]$Validations)

    Write-ColorOutput "=== Consistency Validation ===" $ColorCyan
    Write-ColorOutput ""

    $totalPassed = 0
    $totalFailed = 0

    foreach ($v in $Validations) {
        $status = if ($v.Passed) { "${ColorGreen}PASS${ColorReset}" } else { "${ColorRed}FAIL${ColorReset}" }
        Write-ColorOutput "Feature: $($v.Feature) - $status"

        if ($v.Artifacts.Epic) { Write-ColorOutput "  Epic: $(Split-Path -Leaf $v.Artifacts.Epic)" $ColorMagenta }
        if ($v.Artifacts.PRD) { Write-ColorOutput "  PRD: $(Split-Path -Leaf $v.Artifacts.PRD)" $ColorMagenta }
        if ($v.Artifacts.Tasks) { Write-ColorOutput "  Tasks: $(Split-Path -Leaf $v.Artifacts.Tasks)" $ColorMagenta }

        foreach ($checkName in $v.Results.Keys) {
            $check = $v.Results[$checkName]
            $checkStatus = if ($check.Passed) { "${ColorGreen}[PASS]${ColorReset}" } else { "${ColorRed}[FAIL]${ColorReset}" }
            Write-ColorOutput "  $checkStatus $checkName"

            if (-not $check.Passed -and $check.Issues) {
                foreach ($issue in $check.Issues) {
                    Write-ColorOutput "    - $issue" $ColorYellow
                }
            }
        }

        if ($v.Passed) { $totalPassed++ } else { $totalFailed++ }
        Write-ColorOutput ""
    }

    Write-ColorOutput "=== Summary ===" $ColorCyan
    Write-ColorOutput "Passed: $totalPassed" $ColorGreen
    if ($totalFailed -gt 0) {
        Write-ColorOutput "Failed: $totalFailed" $ColorRed
    }

    return $totalFailed
}

function Format-MarkdownOutput {
    param([array]$Validations)

    $sb = [System.Text.StringBuilder]::new()

    [void]$sb.AppendLine("# Consistency Validation Report")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("**Date**: $(Get-Date -Format 'yyyy-MM-dd HH:mm')")
    [void]$sb.AppendLine("**Checkpoint**: $Checkpoint")
    [void]$sb.AppendLine("")

    foreach ($v in $Validations) {
        $status = if ($v.Passed) { "PASSED" } else { "FAILED" }
        [void]$sb.AppendLine("## Feature: $($v.Feature)")
        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("**Status**: $status")
        [void]$sb.AppendLine("")

        [void]$sb.AppendLine("### Artifacts")
        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("| Artifact | Path | Found |")
        [void]$sb.AppendLine("|----------|------|-------|")

        $artifactTypes = @('Epic', 'PRD', 'Tasks', 'Plan')
        foreach ($type in $artifactTypes) {
            $path = $v.Artifacts[$type]
            $found = if ($path -and (Test-Path $path)) { "Yes" } else { "No" }
            $displayPath = if ($path) { Split-Path -Leaf $path } else { "-" }
            [void]$sb.AppendLine("| $type | $displayPath | $found |")
        }

        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("### Validation Results")
        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("| Check | Status | Issues |")
        [void]$sb.AppendLine("|-------|--------|--------|")

        foreach ($checkName in $v.Results.Keys) {
            $check = $v.Results[$checkName]
            $checkStatus = if ($check.Passed) { "PASS" } else { "FAIL" }
            $issues = if ($check.Issues) { $check.Issues -join "; " } else { "-" }
            [void]$sb.AppendLine("| $checkName | $checkStatus | $issues |")
        }

        [void]$sb.AppendLine("")
    }

    return $sb.ToString()
}

function Format-JsonOutput {
    param([array]$Validations)

    $output = @{
        timestamp = (Get-Date -Format 'o')
        checkpoint = $Checkpoint
        validations = $Validations
        summary = @{
            total = $Validations.Count
            passed = ($Validations | Where-Object { $_.Passed }).Count
            failed = ($Validations | Where-Object { -not $_.Passed }).Count
        }
    }

    return $output | ConvertTo-Json -Depth 10
}

#endregion

#region Main Execution

Write-ColorOutput "=== Consistency Validation ===" $ColorCyan
Write-ColorOutput "Path: $Path" $ColorMagenta
Write-ColorOutput "Checkpoint: $Checkpoint" $ColorMagenta
Write-ColorOutput ""

$validations = @()

if ($All) {
    $features = Get-AllFeatures -BasePath $Path
    Write-ColorOutput "Found $($features.Count) feature(s)" $ColorMagenta
    Write-ColorOutput ""

    foreach ($f in $features) {
        $validation = Invoke-FeatureValidation -FeatureName $f -BasePath $Path -CheckpointNum $Checkpoint
        $validations += $validation
    }
} else {
    $validation = Invoke-FeatureValidation -FeatureName $Feature -BasePath $Path -CheckpointNum $Checkpoint
    $validations += $validation
}

# Output results
$failCount = 0
switch ($Format) {
    "console" {
        $failCount = Format-ConsoleOutput -Validations $validations
    }
    "markdown" {
        $md = Format-MarkdownOutput -Validations $validations
        Write-Output $md
        $failCount = ($validations | Where-Object { -not $_.Passed }).Count
    }
    "json" {
        $json = Format-JsonOutput -Validations $validations
        Write-Output $json
        $failCount = ($validations | Where-Object { -not $_.Passed }).Count
    }
}

if ($CI -and $failCount -gt 0) {
    exit 1
}

#endregion
