<#
.SYNOPSIS
    Validates memory index consistency for tiered memory architecture (ADR-017).

.DESCRIPTION
    Implements validation for the tiered memory index architecture:
    1. Verifies all domain index entries point to existing files
    2. Checks keyword density (>=40% unique keywords per skill in domain)
    3. Validates memory-index references to domain indices
    4. Reports orphaned atomic files not referenced by any index

.PARAMETER Path
    Base path to the memories directory.
    Default: .serena/memories

.PARAMETER CI
    CI mode - returns non-zero exit code on failures.

.PARAMETER Format
    Output format: "console", "markdown", or "json".
    Default: "console"

.PARAMETER FixOrphans
    When set, reports orphaned atomic files that should be indexed.

.EXAMPLE
    .\Validate-MemoryIndex.ps1

.EXAMPLE
    .\Validate-MemoryIndex.ps1 -CI -Format json

.EXAMPLE
    .\Validate-MemoryIndex.ps1 -FixOrphans
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Path = ".serena/memories",

    [Parameter()]
    [switch]$CI,

    [Parameter()]
    [ValidateSet("console", "markdown", "json")]
    [string]$Format = "console",

    [Parameter()]
    [switch]$FixOrphans
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

function Get-DomainIndices {
    <#
    .SYNOPSIS
        Finds all domain index files (skills-*-index.md pattern)
    #>
    param([string]$MemoryPath)

    if (-not (Test-Path $MemoryPath)) {
        return ,@()
    }

    $files = @(Get-ChildItem -Path $MemoryPath -Filter "skills-*-index.md" -ErrorAction SilentlyContinue)

    if ($files.Count -eq 0) {
        return ,@()
    }

    $indices = $files | ForEach-Object {
        [PSCustomObject]@{
            Path = $_.FullName
            Name = $_.BaseName
            Domain = ($_.BaseName -replace '^skills-', '' -replace '-index$', '')
        }
    }

    return ,@($indices)
}

function Get-IndexEntries {
    <#
    .SYNOPSIS
        Parses a domain index file and extracts keyword-file mappings
    #>
    param([string]$IndexPath)

    if (-not (Test-Path $IndexPath)) {
        return ,@()
    }

    $content = Get-Content -Path $IndexPath -Raw
    $lines = $content -split "`n"
    $parsedEntries = [System.Collections.ArrayList]::new()

    foreach ($line in $lines) {
        # Match table row: | keywords... | file-name |
        if ($line -match '^\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|$') {
            $keywords = $Matches[1].Trim()
            $fileName = $Matches[2].Trim()

            # Skip header row
            if ($keywords -eq 'Keywords' -or $keywords -match '^-+$') {
                continue
            }

            # Skip separator row
            if ($fileName -match '^-+$') {
                continue
            }

            $keywordList = @($keywords -split '\s+' | Where-Object { $_ })

            [void]$parsedEntries.Add([PSCustomObject]@{
                Keywords = $keywordList
                FileName = $fileName
                RawKeywords = $keywords
            })
        }
    }

    if ($parsedEntries.Count -eq 0) {
        return ,@()
    }

    return ,@($parsedEntries)
}

function Test-FileReferences {
    <#
    .SYNOPSIS
        Validates that all index entries point to existing files
    #>
    param(
        [array]$Entries,
        [string]$MemoryPath
    )

    $result = @{
        Passed = $true
        Issues = @()
        MissingFiles = @()
        ValidFiles = @()
    }

    foreach ($entry in $Entries) {
        $filePath = Join-Path $MemoryPath "$($entry.FileName).md"

        if (Test-Path $filePath) {
            $result.ValidFiles += $entry.FileName
        } else {
            $result.Passed = $false
            $result.MissingFiles += $entry.FileName
            $result.Issues += "Missing file: $($entry.FileName).md"
        }
    }

    return $result
}

function Test-KeywordDensity {
    <#
    .SYNOPSIS
        Validates that each skill has >=40% unique keywords vs other skills in domain
    #>
    param([array]$Entries)

    $result = @{
        Passed = $true
        Issues = @()
        Densities = @{}
    }

    if ($Entries.Count -lt 2) {
        # With only 1 entry, 100% unique by definition
        if ($Entries.Count -eq 1) {
            $result.Densities[$Entries[0].FileName] = 1.0
        }
        return $result
    }

    # Build keyword sets for each entry
    $keywordSets = @{}
    foreach ($entry in $Entries) {
        $keywordSets[$entry.FileName] = [System.Collections.Generic.HashSet[string]]::new(
            [string[]]($entry.Keywords | ForEach-Object { $_.ToLowerInvariant() }),
            [System.StringComparer]::OrdinalIgnoreCase
        )
    }

    # Calculate uniqueness for each entry
    foreach ($entry in $Entries) {
        $myKeywords = $keywordSets[$entry.FileName]
        $otherKeywords = [System.Collections.Generic.HashSet[string]]::new(
            [System.StringComparer]::OrdinalIgnoreCase
        )

        # Union of all other entries' keywords
        foreach ($otherEntry in $Entries) {
            if ($otherEntry.FileName -ne $entry.FileName) {
                foreach ($kw in $keywordSets[$otherEntry.FileName]) {
                    [void]$otherKeywords.Add($kw)
                }
            }
        }

        # Count unique keywords (in my set but not in others)
        $uniqueCount = 0
        foreach ($kw in $myKeywords) {
            if (-not $otherKeywords.Contains($kw)) {
                $uniqueCount++
            }
        }

        $density = if ($myKeywords.Count -gt 0) {
            [math]::Round($uniqueCount / $myKeywords.Count, 2)
        } else {
            0
        }

        $result.Densities[$entry.FileName] = $density

        if ($density -lt 0.40) {
            $result.Passed = $false
            $result.Issues += "Low keyword uniqueness: $($entry.FileName) has $([math]::Round($density * 100))% unique keywords (need >=40%)"
        }
    }

    return $result
}

function Get-OrphanedFiles {
    <#
    .SYNOPSIS
        Finds atomic skill files not referenced by any domain index
    #>
    param(
        [array]$AllIndices,
        [string]$MemoryPath
    )

    $orphans = [System.Collections.ArrayList]::new()
    $referencedFiles = @{}

    # Collect all referenced files from all indices
    foreach ($index in $AllIndices) {
        $entries = Get-IndexEntries -IndexPath $index.Path
        foreach ($entry in $entries) {
            $referencedFiles[$entry.FileName] = $true
        }
    }

    # Check for files that look like atomic skills but aren't indexed
    $allFiles = @(Get-ChildItem -Path $MemoryPath -Filter "*.md" -ErrorAction SilentlyContinue)

    foreach ($file in $allFiles) {
        $baseName = $file.BaseName

        # Skip index files
        if ($baseName -match '-index$') {
            continue
        }

        # Skip known non-atomic files (memory-index, skills-*, pattern-*, etc.)
        if ($baseName -eq 'memory-index') {
            continue
        }

        # Check if file follows atomic naming pattern (domain prefix)
        $domains = @($AllIndices | ForEach-Object { $_.Domain })
        foreach ($domain in $domains) {
            if ($baseName -match "^$domain-" -and -not $referencedFiles.ContainsKey($baseName)) {
                [void]$orphans.Add([PSCustomObject]@{
                    File = $baseName
                    Domain = $domain
                    ExpectedIndex = "skills-$domain-index"
                })
            }
        }
    }

    if ($orphans.Count -eq 0) {
        return ,@()
    }

    return ,@($orphans)
}

function Test-MemoryIndexReferences {
    <#
    .SYNOPSIS
        Validates that memory-index references existing domain indices
    #>
    param(
        [string]$MemoryPath,
        [array]$DomainIndices
    )

    $result = @{
        Passed = $true
        Issues = @()
    }

    $memoryIndexPath = Join-Path $MemoryPath "memory-index.md"

    if (-not (Test-Path $memoryIndexPath)) {
        $result.Issues += "memory-index.md not found"
        return $result  # Not a failure, just informational
    }

    $content = Get-Content -Path $memoryIndexPath -Raw

    # Check if any domain indices are referenced
    foreach ($index in $DomainIndices) {
        $indexBaseName = $index.Name
        if ($content -notmatch [regex]::Escape($indexBaseName)) {
            $result.Issues += "Domain index not referenced in memory-index: $indexBaseName"
        }
    }

    return $result
}

#endregion

#region Main Validation Logic

function Invoke-MemoryIndexValidation {
    param([string]$MemoryPath)

    $validation = @{
        Passed = $true
        Timestamp = Get-Date -Format 'o'
        MemoryPath = $MemoryPath
        DomainResults = @{}
        MemoryIndexResult = $null
        Orphans = @()
        Summary = @{
            TotalDomains = 0
            PassedDomains = 0
            FailedDomains = 0
            TotalFiles = 0
            MissingFiles = 0
            KeywordIssues = 0
        }
    }

    # Find all domain indices
    $domainIndices = Get-DomainIndices -MemoryPath $MemoryPath
    $validation.Summary.TotalDomains = $domainIndices.Count

    Write-ColorOutput "Found $($domainIndices.Count) domain index(es)" $ColorCyan

    # Validate each domain index
    foreach ($index in $domainIndices) {
        Write-ColorOutput "`nValidating: $($index.Name)" $ColorMagenta

        $entries = Get-IndexEntries -IndexPath $index.Path
        Write-ColorOutput "  Entries: $($entries.Count)" $ColorCyan

        # Test file references
        $fileResult = Test-FileReferences -Entries $entries -MemoryPath $MemoryPath
        $validation.Summary.TotalFiles += $entries.Count
        $validation.Summary.MissingFiles += $fileResult.MissingFiles.Count

        # Test keyword density
        $keywordResult = Test-KeywordDensity -Entries $entries
        if (-not $keywordResult.Passed) {
            $validation.Summary.KeywordIssues += $keywordResult.Issues.Count
        }

        $domainPassed = $fileResult.Passed -and $keywordResult.Passed

        $validation.DomainResults[$index.Domain] = @{
            IndexPath = $index.Path
            Entries = $entries.Count
            FileReferences = $fileResult
            KeywordDensity = $keywordResult
            Passed = $domainPassed
        }

        if ($domainPassed) {
            $validation.Summary.PassedDomains++
            Write-ColorOutput "  Status: ${ColorGreen}PASS${ColorReset}"
        } else {
            $validation.Summary.FailedDomains++
            $validation.Passed = $false
            Write-ColorOutput "  Status: ${ColorRed}FAIL${ColorReset}"

            foreach ($issue in $fileResult.Issues) {
                Write-ColorOutput "    - $issue" $ColorRed
            }
            foreach ($issue in $keywordResult.Issues) {
                Write-ColorOutput "    - $issue" $ColorYellow
            }
        }

        # Show keyword densities
        if ($keywordResult.Densities.Count -gt 0) {
            Write-ColorOutput "  Keyword uniqueness:" $ColorCyan
            foreach ($file in $keywordResult.Densities.Keys) {
                $density = $keywordResult.Densities[$file]
                $color = if ($density -ge 0.40) { $ColorGreen } else { $ColorRed }
                Write-ColorOutput "    $($file): $([math]::Round($density * 100))%" $color
            }
        }
    }

    # Validate memory-index references
    $memoryIndexResult = Test-MemoryIndexReferences -MemoryPath $MemoryPath -DomainIndices $domainIndices
    $validation.MemoryIndexResult = $memoryIndexResult

    if ($memoryIndexResult.Issues.Count -gt 0) {
        Write-ColorOutput "`nMemory-index warnings:" $ColorYellow
        foreach ($issue in $memoryIndexResult.Issues) {
            Write-ColorOutput "  - $issue" $ColorYellow
        }
    }

    # Find orphaned files
    if ($FixOrphans -or $true) {  # Always check for orphans
        $orphans = Get-OrphanedFiles -AllIndices $domainIndices -MemoryPath $MemoryPath
        $validation.Orphans = $orphans

        if ($orphans.Count -gt 0) {
            Write-ColorOutput "`nOrphaned files (not indexed):" $ColorYellow
            foreach ($orphan in $orphans) {
                Write-ColorOutput "  - $($orphan.File) (should be in $($orphan.ExpectedIndex))" $ColorYellow
            }
        }
    }

    return $validation
}

#endregion

#region Output Formatting

function Format-MarkdownOutput {
    param([hashtable]$Validation)

    $sb = [System.Text.StringBuilder]::new()

    [void]$sb.AppendLine("# Memory Index Validation Report")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("**Date**: $(Get-Date -Format 'yyyy-MM-dd HH:mm')")
    [void]$sb.AppendLine("**Status**: $(if ($Validation.Passed) { 'PASSED' } else { 'FAILED' })")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("## Summary")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("| Metric | Value |")
    [void]$sb.AppendLine("|--------|-------|")
    [void]$sb.AppendLine("| Domain Indices | $($Validation.Summary.TotalDomains) |")
    [void]$sb.AppendLine("| Passed | $($Validation.Summary.PassedDomains) |")
    [void]$sb.AppendLine("| Failed | $($Validation.Summary.FailedDomains) |")
    [void]$sb.AppendLine("| Total Files | $($Validation.Summary.TotalFiles) |")
    [void]$sb.AppendLine("| Missing Files | $($Validation.Summary.MissingFiles) |")
    [void]$sb.AppendLine("| Keyword Issues | $($Validation.Summary.KeywordIssues) |")
    [void]$sb.AppendLine("")

    foreach ($domain in $Validation.DomainResults.Keys) {
        $result = $Validation.DomainResults[$domain]
        [void]$sb.AppendLine("## Domain: $domain")
        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("**Status**: $(if ($result.Passed) { 'PASS' } else { 'FAIL' })")
        [void]$sb.AppendLine("")

        if ($result.FileReferences.Issues.Count -gt 0) {
            [void]$sb.AppendLine("### File Issues")
            foreach ($issue in $result.FileReferences.Issues) {
                [void]$sb.AppendLine("- $issue")
            }
            [void]$sb.AppendLine("")
        }

        if ($result.KeywordDensity.Densities.Count -gt 0) {
            [void]$sb.AppendLine("### Keyword Uniqueness")
            [void]$sb.AppendLine("")
            [void]$sb.AppendLine("| File | Uniqueness |")
            [void]$sb.AppendLine("|------|------------|")
            foreach ($file in $result.KeywordDensity.Densities.Keys) {
                $density = $result.KeywordDensity.Densities[$file]
                $status = if ($density -ge 0.40) { "OK" } else { "LOW" }
                [void]$sb.AppendLine("| $file | $([math]::Round($density * 100))% ($status) |")
            }
            [void]$sb.AppendLine("")
        }
    }

    if ($Validation.Orphans.Count -gt 0) {
        [void]$sb.AppendLine("## Orphaned Files")
        [void]$sb.AppendLine("")
        foreach ($orphan in $Validation.Orphans) {
            [void]$sb.AppendLine("- $($orphan.File) - add to $($orphan.ExpectedIndex)")
        }
    }

    return $sb.ToString()
}

function Format-JsonOutput {
    param([hashtable]$Validation)

    return $Validation | ConvertTo-Json -Depth 10
}

#endregion

#region Main Execution

Write-ColorOutput "=== Memory Index Validation (ADR-017) ===" $ColorCyan
Write-ColorOutput "Path: $Path" $ColorMagenta
Write-ColorOutput ""

# Resolve path
$resolvedPath = if ([System.IO.Path]::IsPathRooted($Path)) {
    $Path
} else {
    Join-Path (Get-Location) $Path
}

if (-not (Test-Path $resolvedPath)) {
    Write-ColorOutput "Memory path not found: $resolvedPath" $ColorRed
    if ($CI) { exit 1 }
    exit 0
}

# Run validation
$validation = Invoke-MemoryIndexValidation -MemoryPath $resolvedPath

# Output results
Write-ColorOutput ""
Write-ColorOutput "=== Summary ===" $ColorCyan

switch ($Format) {
    "console" {
        Write-ColorOutput "Domains: $($validation.Summary.TotalDomains) total, $($validation.Summary.PassedDomains) passed, $($validation.Summary.FailedDomains) failed"
        Write-ColorOutput "Files: $($validation.Summary.TotalFiles) indexed, $($validation.Summary.MissingFiles) missing"
        Write-ColorOutput "Keyword Issues: $($validation.Summary.KeywordIssues)"

        if ($validation.Passed) {
            Write-ColorOutput "`nResult: ${ColorGreen}PASSED${ColorReset}"
        } else {
            Write-ColorOutput "`nResult: ${ColorRed}FAILED${ColorReset}"
        }
    }
    "markdown" {
        $md = Format-MarkdownOutput -Validation $validation
        Write-Output $md
    }
    "json" {
        $json = Format-JsonOutput -Validation $validation
        Write-Output $json
    }
}

if ($CI) {
    if ($validation.Passed) {
        exit 0
    } else {
        exit 1
    }
}

#endregion
