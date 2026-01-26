<#
.SYNOPSIS
    Validates traceability cross-references between specification artifacts.

.DESCRIPTION
    Implements the orphan detection algorithm defined in .agents/governance/traceability-schema.md.
    Checks:
    - Rule 1: Forward Traceability (REQ -> DESIGN)
    - Rule 2: Backward Traceability (TASK -> DESIGN)
    - Rule 3: Complete Chain (DESIGN has both REQ and TASK references)
    - Rule 4: Reference Validity (all referenced IDs exist as files)
    - Rule 5: Status Consistency (completed status propagates correctly)

.PARAMETER SpecsPath
    Path to the specs directory. Default: ".agents/specs"

.PARAMETER Strict
    Fail on warnings (orphaned specs). Without -Strict, only errors cause failure.

.PARAMETER Format
    Output format: "console", "markdown", or "json".
    Default: "console"

.PARAMETER NoCache
    Disable caching. Forces re-parsing of all spec files.

.PARAMETER Benchmark
    Display timing information for performance analysis.

.EXAMPLE
    .\Validate-Traceability.ps1

.EXAMPLE
    .\Validate-Traceability.ps1 -Strict

.EXAMPLE
    .\Validate-Traceability.ps1 -SpecsPath ".agents/specs" -Format markdown

.EXAMPLE
    .\Validate-Traceability.ps1 -NoCache
    # Run validation without using cached data

.EXAMPLE
    .\Validate-Traceability.ps1 -Benchmark
    # Run validation and display timing information

.NOTES
    Exit codes:
    0 = Pass (no errors; warnings allowed unless -Strict)
    1 = Errors found (broken references, untraced tasks)
    2 = Warnings found with -Strict flag (orphaned REQs/DESIGNs)

    See: ADR-035 Exit Code Standardization
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$SpecsPath = ".agents/specs",

    [Parameter()]
    [switch]$Strict,

    [Parameter()]
    [ValidateSet("console", "markdown", "json")]
    [string]$Format = "console",

    [Parameter()]
    [switch]$NoCache,

    [Parameter()]
    [switch]$Benchmark
)

$ErrorActionPreference = "Stop"

#region Caching and Benchmarking
# Import caching module
$cacheModulePath = Join-Path $PSScriptRoot "traceability/TraceabilityCache.psm1"
if (Test-Path $cacheModulePath) {
    Import-Module $cacheModulePath -Force
    $script:CacheAvailable = $true
} else {
    $script:CacheAvailable = $false
}

# Clear cache if -NoCache specified
if ($NoCache -and $script:CacheAvailable) {
    Clear-TraceabilityCache
}

# Benchmark timing
$script:BenchmarkTimings = @{}
function Measure-Step {
    param([string]$StepName, [scriptblock]$ScriptBlock)
    if ($Benchmark) {
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        $result = & $ScriptBlock
        $stopwatch.Stop()
        $script:BenchmarkTimings[$StepName] = $stopwatch.ElapsedMilliseconds
        return $result
    } else {
        return & $ScriptBlock
    }
}

function Write-BenchmarkReport {
    if ($Benchmark -and $script:BenchmarkTimings.Count -gt 0) {
        Write-Host ""
        Write-Host "Benchmark Results:" -ForegroundColor Cyan
        Write-Host "==================" -ForegroundColor Cyan
        $total = 0
        foreach ($step in $script:BenchmarkTimings.GetEnumerator() | Sort-Object Name) {
            Write-Host ("  {0,-25}: {1,6} ms" -f $step.Name, $step.Value)
            $total += $step.Value
        }
        Write-Host ("  {0,-25}: {1,6} ms" -f "TOTAL", $total) -ForegroundColor Green

        if ($script:CacheAvailable) {
            $cacheStats = Get-CacheStat
            Write-Host ""
            Write-Host "Cache Statistics:" -ForegroundColor Cyan
            Write-Host ("  Memory entries: {0}" -f $cacheStats.MemoryCacheEntries)
            Write-Host ("  Disk entries:   {0}" -f $cacheStats.DiskCacheEntries)
        }
    }
}
#endregion

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

#region YAML Parsing
function Get-YamlFrontMatter {
    <#
    .SYNOPSIS
        Extracts YAML front matter from a markdown file.
    #>
    param([string]$FilePath)

    $content = Get-Content -Path $FilePath -Raw -ErrorAction SilentlyContinue
    if (-not $content) { return $null }

    # Match YAML front matter between --- markers
    if ($content -match '(?s)^---\r?\n(.+?)\r?\n---') {
        $yaml = $Matches[1]
        $result = @{
            type = ''
            id = ''
            status = ''
            related = @()
            filePath = $FilePath
        }

        # Parse type
        if ($yaml -match '(?m)^type:\s*(.+)$') {
            $result.type = $Matches[1].Trim()
        }

        # Parse id
        if ($yaml -match '(?m)^id:\s*(.+)$') {
            $result.id = $Matches[1].Trim()
        }

        # Parse status
        if ($yaml -match '(?m)^status:\s*(.+)$') {
            $result.status = $Matches[1].Trim()
        }

        # Parse related (array) - supports both numeric and alphanumeric IDs (e.g., REQ-001, REQ-ABC)
        if ($yaml -match '(?s)related:\s*\r?\n((?:\s+-\s+.+\r?\n?)+)') {
            $relatedBlock = $Matches[1]
            $result.related = [regex]::Matches($relatedBlock, '-\s+([A-Z]+-[A-Z0-9]+)') |
                ForEach-Object { $_.Groups[1].Value }
        }

        return $result
    }

    return $null
}
#endregion

#region Spec Loading
function Get-AllSpecs {
    <#
    .SYNOPSIS
        Loads all specification files from the specs directory.
    #>
    param([string]$BasePath)

    $specs = @{
        requirements = @{}
        designs = @{}
        tasks = @{}
        all = @{}
    }

    # Load requirements
    $reqPath = Join-Path $BasePath "requirements"
    if (Test-Path $reqPath) {
        Get-ChildItem -Path $reqPath -Filter "REQ-*.md" | ForEach-Object {
            $spec = Get-YamlFrontMatter -FilePath $_.FullName
            if ($spec -and $spec.id) {
                $specs.requirements[$spec.id] = $spec
                $specs.all[$spec.id] = $spec
            }
        }
    }

    # Load designs
    $designPath = Join-Path $BasePath "design"
    if (Test-Path $designPath) {
        Get-ChildItem -Path $designPath -Filter "DESIGN-*.md" | ForEach-Object {
            $spec = Get-YamlFrontMatter -FilePath $_.FullName
            if ($spec -and $spec.id) {
                $specs.designs[$spec.id] = $spec
                $specs.all[$spec.id] = $spec
            }
        }
    }

    # Load tasks
    $taskPath = Join-Path $BasePath "tasks"
    if (Test-Path $taskPath) {
        Get-ChildItem -Path $taskPath -Filter "TASK-*.md" | ForEach-Object {
            $spec = Get-YamlFrontMatter -FilePath $_.FullName
            if ($spec -and $spec.id) {
                $specs.tasks[$spec.id] = $spec
                $specs.all[$spec.id] = $spec
            }
        }
    }

    return $specs
}
#endregion

#region Traceability Validation
function Test-Traceability {
    <#
    .SYNOPSIS
        Validates traceability rules and detects orphans.
    #>
    param([hashtable]$Specs)

    $results = @{
        errors = @()
        warnings = @()
        info = @()
        stats = @{
            requirements = $Specs.requirements.Count
            designs = $Specs.designs.Count
            tasks = $Specs.tasks.Count
            validChains = 0
        }
    }

    # Build reference indices
    # req_refs: REQ-ID -> [DESIGN-IDs that reference it]
    # design_refs: DESIGN-ID -> [TASK-IDs that reference it]
    $reqRefs = @{}
    $designRefs = @{}

    # Initialize ref arrays
    foreach ($reqId in $Specs.requirements.Keys) {
        $reqRefs[$reqId] = @()
    }
    foreach ($designId in $Specs.designs.Keys) {
        $designRefs[$designId] = @()
    }

    # Build forward references from tasks to designs
    foreach ($taskId in $Specs.tasks.Keys) {
        $task = $Specs.tasks[$taskId]
        foreach ($relatedId in $task.related) {
            if ($relatedId -match '^DESIGN-') {
                if ($Specs.designs.ContainsKey($relatedId)) {
                    $designRefs[$relatedId] += $taskId
                }
                else {
                    # Rule 4: Broken reference
                    $results.errors += @{
                        rule = "Rule 4: Reference Validity"
                        source = $taskId
                        target = $relatedId
                        message = "TASK '$taskId' references non-existent DESIGN '$relatedId'"
                    }
                }
            }
        }

        # Rule 2: Backward Traceability - Task must reference at least one design
        $designRefs_for_task = $task.related | Where-Object { $_ -match '^DESIGN-' }
        if (-not $designRefs_for_task -or $designRefs_for_task.Count -eq 0) {
            $results.errors += @{
                rule = "Rule 2: Backward Traceability"
                source = $taskId
                target = $null
                message = "TASK '$taskId' has no DESIGN reference (untraced task)"
            }
        }
    }

    # Build forward references from designs to requirements
    foreach ($designId in $Specs.designs.Keys) {
        $design = $Specs.designs[$designId]
        foreach ($relatedId in $design.related) {
            if ($relatedId -match '^REQ-') {
                if ($Specs.requirements.ContainsKey($relatedId)) {
                    $reqRefs[$relatedId] += $designId
                }
                else {
                    # Rule 4: Broken reference
                    $results.errors += @{
                        rule = "Rule 4: Reference Validity"
                        source = $designId
                        target = $relatedId
                        message = "DESIGN '$designId' references non-existent REQ '$relatedId'"
                    }
                }
            }
        }
    }

    # Rule 1: Forward Traceability - Every REQ must trace to at least one DESIGN
    foreach ($reqId in $Specs.requirements.Keys) {
        if (-not $reqRefs[$reqId] -or $reqRefs[$reqId].Count -eq 0) {
            $results.warnings += @{
                rule = "Rule 1: Forward Traceability"
                source = $reqId
                target = $null
                message = "REQ '$reqId' has no DESIGN referencing it (orphaned requirement)"
            }
        }
    }

    # Rule 3: Complete Chain - Every DESIGN must have both REQ and TASK references
    foreach ($designId in $Specs.designs.Keys) {
        $design = $Specs.designs[$designId]
        $hasReqRef = ($design.related | Where-Object { $_ -match '^REQ-' }).Count -gt 0
        $hasTaskRef = $designRefs[$designId].Count -gt 0

        if (-not $hasReqRef) {
            $results.warnings += @{
                rule = "Rule 3: Complete Chain"
                source = $designId
                target = $null
                message = "DESIGN '$designId' has no REQ reference (missing backward trace)"
            }
        }

        if (-not $hasTaskRef) {
            $results.warnings += @{
                rule = "Rule 3: Complete Chain"
                source = $designId
                target = $null
                message = "DESIGN '$designId' has no TASK referencing it (orphaned design)"
            }
        }

        if ($hasReqRef -and $hasTaskRef) {
            $results.stats.validChains++
        }
    }

    # Rule 5: Status Consistency
    foreach ($taskId in $Specs.tasks.Keys) {
        $task = $Specs.tasks[$taskId]
        if ($task.status -in @('complete', 'done', 'implemented')) {
            foreach ($relatedId in $task.related) {
                if ($relatedId -match '^DESIGN-' -and $Specs.designs.ContainsKey($relatedId)) {
                    $design = $Specs.designs[$relatedId]
                    if ($design.status -notin @('implemented', 'complete', 'done')) {
                        $results.info += @{
                            rule = "Rule 5: Status Consistency"
                            source = $taskId
                            target = $relatedId
                            message = "TASK '$taskId' is complete but DESIGN '$relatedId' is '$($design.status)'"
                        }
                    }
                }
            }
        }
    }

    return $results
}
#endregion

#region Output Formatting
function Format-Results {
    param(
        [hashtable]$Results,
        [string]$OutputFormat
    )

    switch ($OutputFormat) {
        "json" {
            return $Results | ConvertTo-Json -Depth 5
        }
        "markdown" {
            $sb = [System.Text.StringBuilder]::new()
            [void]$sb.AppendLine("# Traceability Validation Report")
            [void]$sb.AppendLine()
            [void]$sb.AppendLine("## Summary")
            [void]$sb.AppendLine()
            [void]$sb.AppendLine("| Metric | Count |")
            [void]$sb.AppendLine("|--------|-------|")
            [void]$sb.AppendLine("| Requirements | $($Results.stats.requirements) |")
            [void]$sb.AppendLine("| Designs | $($Results.stats.designs) |")
            [void]$sb.AppendLine("| Tasks | $($Results.stats.tasks) |")
            [void]$sb.AppendLine("| Valid Chains | $($Results.stats.validChains) |")
            [void]$sb.AppendLine("| Errors | $($Results.errors.Count) |")
            [void]$sb.AppendLine("| Warnings | $($Results.warnings.Count) |")
            [void]$sb.AppendLine()

            if ($Results.errors.Count -gt 0) {
                [void]$sb.AppendLine("## Errors")
                [void]$sb.AppendLine()
                foreach ($errorItem in $Results.errors) {
                    [void]$sb.AppendLine("- **$($errorItem.rule)**: $($errorItem.message)")
                }
                [void]$sb.AppendLine()
            }

            if ($Results.warnings.Count -gt 0) {
                [void]$sb.AppendLine("## Warnings")
                [void]$sb.AppendLine()
                foreach ($warning in $Results.warnings) {
                    [void]$sb.AppendLine("- **$($warning.rule)**: $($warning.message)")
                }
                [void]$sb.AppendLine()
            }

            if ($Results.info.Count -gt 0) {
                [void]$sb.AppendLine("## Info")
                [void]$sb.AppendLine()
                foreach ($info in $Results.info) {
                    [void]$sb.AppendLine("- **$($info.rule)**: $($info.message)")
                }
                [void]$sb.AppendLine()
            }

            return $sb.ToString()
        }
        default {
            # Console output
            Write-ColorOutput "Traceability Validation Report" $ColorCyan
            Write-ColorOutput "==============================" $ColorCyan
            Write-ColorOutput ""
            Write-ColorOutput "Stats:" $ColorMagenta
            Write-ColorOutput "  Requirements: $($Results.stats.requirements)"
            Write-ColorOutput "  Designs:      $($Results.stats.designs)"
            Write-ColorOutput "  Tasks:        $($Results.stats.tasks)"
            Write-ColorOutput "  Valid Chains: $($Results.stats.validChains)"
            Write-ColorOutput ""

            if ($Results.errors.Count -gt 0) {
                Write-ColorOutput "ERRORS ($($Results.errors.Count)):" $ColorRed
                foreach ($errorItem in $Results.errors) {
                    Write-ColorOutput "  [$($errorItem.rule)] $($errorItem.message)" $ColorRed
                }
                Write-ColorOutput ""
            }

            if ($Results.warnings.Count -gt 0) {
                Write-ColorOutput "WARNINGS ($($Results.warnings.Count)):" $ColorYellow
                foreach ($warning in $Results.warnings) {
                    Write-ColorOutput "  [$($warning.rule)] $($warning.message)" $ColorYellow
                }
                Write-ColorOutput ""
            }

            if ($Results.info.Count -gt 0) {
                Write-ColorOutput "INFO ($($Results.info.Count)):" $ColorCyan
                foreach ($info in $Results.info) {
                    Write-ColorOutput "  [$($info.rule)] $($info.message)" $ColorCyan
                }
                Write-ColorOutput ""
            }

            if ($Results.errors.Count -eq 0 -and $Results.warnings.Count -eq 0) {
                Write-ColorOutput "All traceability checks passed!" $ColorGreen
            }

            return $null
        }
    }
}
#endregion

#region Main
# Resolve specs path
$resolvedPath = Resolve-Path -Path $SpecsPath -ErrorAction SilentlyContinue
if (-not $resolvedPath) {
    Write-Error "Specs path not found: $SpecsPath"
    exit 1
}

# Path traversal protection: When running from a git repository, ensure paths stay within repo root
# Skip this check for absolute paths (e.g., test fixtures in /tmp) to allow legitimate test scenarios
$repoRoot = try { git rev-parse --show-toplevel 2>$null } catch { $null }
if ($repoRoot) {
    $normalizedPath = [System.IO.Path]::GetFullPath($resolvedPath.Path)
    $allowedBase = [System.IO.Path]::GetFullPath($repoRoot)

    # Only enforce path traversal check if the original path was relative (not an absolute temp path)
    $isRelativePath = -not [System.IO.Path]::IsPathRooted($SpecsPath)
    if ($isRelativePath -and -not $normalizedPath.StartsWith($allowedBase, [System.StringComparison]::OrdinalIgnoreCase)) {
        Write-Error "Path traversal attempt detected: '$SpecsPath' is outside the repository root." -ErrorAction Continue
        exit 1
    }
}

# Load all specs
$specs = Measure-Step -StepName "Load Specs" -ScriptBlock {
    Get-AllSpecs -BasePath $resolvedPath.Path
}

# Validate traceability
$results = Measure-Step -StepName "Validate Traceability" -ScriptBlock {
    Test-Traceability -Specs $specs
}

# Output results
$output = Measure-Step -StepName "Format Results" -ScriptBlock {
    Format-Results -Results $results -OutputFormat $Format
}
if ($output) {
    Write-Output $output
}

# Display benchmark results if requested
Write-BenchmarkReport

# Determine exit code
if ($results.errors.Count -gt 0) {
    exit 1
}
elseif ($results.warnings.Count -gt 0) {
    if ($Strict) {
        exit 2
    }
}

exit 0
#endregion
