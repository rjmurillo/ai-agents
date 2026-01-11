<#
.SYNOPSIS
    Validates memory index consistency for tiered memory architecture (ADR-017).

.DESCRIPTION
    Implements multi-tier validation for the tiered memory index architecture:

    P0 (Always Blocking):
    - Verifies all domain index entries point to existing files
    - Checks keyword density (>=40% unique keywords per skill in domain)
    - Validates index format (pure lookup table, no titles/metadata)
    - Detects deprecated skill- prefix in index entries
    - Detects duplicate entries in same index

    P1 (Warning):
    - Reports orphaned atomic files not referenced by any index
    - Detects unindexed skill- prefixed files

    P2 (Warning):
    - Minimum keyword count (>=5 per skill)
    - Domain prefix naming convention ({domain}-{description})

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
    # Basic validation - P0 blocking, P1/P2 warnings

.EXAMPLE
    .\Validate-MemoryIndex.ps1 -CI
    # CI mode - exits non-zero on P0 failures

.EXAMPLE
    .\Validate-MemoryIndex.ps1 -CI -Format json
    # JSON output for programmatic consumption

.NOTES
  EXIT CODES:
  0  - Success: All P0 validations passed or no memory path found
  1  - Error: P0 validation failures detected (only when -CI flag is set)

  See: ADR-035 Exit Code Standardization
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
        Validates that all index entries point to existing files and use correct naming convention
    .DESCRIPTION
        Checks:
        1. Referenced files exist in the memory path
        2. File names do NOT use deprecated 'skill-' prefix (ADR-017 Gap 1/2)
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
        NamingViolations = @()
    }

    foreach ($entry in $Entries) {
        $filePath = Join-Path $MemoryPath "$($entry.FileName).md"

        # Check for deprecated skill- prefix (ADR-017 Gap 1/2)
        if ($entry.FileName -match '^skill-') {
            $result.Passed = $false
            $result.NamingViolations += $entry.FileName
            $result.Issues += "Index references deprecated 'skill-' prefix: $($entry.FileName).md (ADR-017 violation)"
        }

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

function Test-MinimumKeywords {
    <#
    .SYNOPSIS
        Validates that each skill has a minimum number of keywords for discoverability (P2)
    .DESCRIPTION
        ADR-017 recommends 10-15 keywords per skill. Minimum threshold is 5 keywords
        to ensure adequate activation vocabulary for lexical matching.
    #>
    param(
        [array]$Entries,
        [int]$MinKeywords = 5
    )

    $result = @{
        Passed = $true
        Issues = @()
        KeywordCounts = @{}
    }

    foreach ($entry in $Entries) {
        $count = $entry.Keywords.Count
        $result.KeywordCounts[$entry.FileName] = $count

        if ($count -lt $MinKeywords) {
            $result.Passed = $false
            $result.Issues += "Insufficient keywords: $($entry.FileName) has $count keywords (need >=$MinKeywords)"
        }
    }

    return $result
}

function Test-DuplicateEntries {
    <#
    .SYNOPSIS
        Detects duplicate file references within a domain index (P2)
    .DESCRIPTION
        Each file should be referenced exactly once per index.
        Duplicates waste tokens and may cause inconsistent keyword coverage.
    #>
    param([array]$Entries)

    $result = @{
        Passed = $true
        Issues = @()
        Duplicates = @()
    }

    $seen = @{}
    foreach ($entry in $Entries) {
        if ($seen.ContainsKey($entry.FileName)) {
            $result.Passed = $false
            $result.Duplicates += $entry.FileName
            if ($result.Duplicates.Count -eq 1 -or $result.Duplicates[-1] -ne $result.Duplicates[-2]) {
                $result.Issues += "Duplicate entry: $($entry.FileName) appears multiple times in index"
            }
        }
        $seen[$entry.FileName] = $true
    }

    return $result
}

function Test-DomainPrefixNaming {
    <#
    .SYNOPSIS
        Validates that file references follow {domain}-{description} naming convention (P2)
    .DESCRIPTION
        ADR-017 specifies that atomic files should follow {domain}-{description} pattern.
        This improves discoverability and ensures consistent organization.
    #>
    param(
        [array]$Entries,
        [string]$Domain
    )

    $result = @{
        Passed = $true
        Issues = @()
        NonConforming = @()
    }

    foreach ($entry in $Entries) {
        $fileName = $entry.FileName

        # Check if file follows {domain}-{description} pattern
        # Allow common patterns: {domain}-{description}, {domain}-{number}-{description}
        $expectedPrefix = "$Domain-"

        if (-not $fileName.StartsWith($expectedPrefix)) {
            $result.Passed = $false
            $result.NonConforming += $fileName
            $result.Issues += "Naming violation: $fileName should start with '$expectedPrefix' per ADR-017"
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
    .DESCRIPTION
        Detects:
        1. Files matching domain prefix pattern not in any index
        2. Files with deprecated 'skill-' prefix (ADR-017 Gap 4) - flagged as INVALID domain
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

        # Skip known non-atomic files (memory-index)
        if ($baseName -eq 'memory-index') {
            continue
        }

        # ADR-017 Gap 4: Check for deprecated skill- prefix (silent failure mode)
        # Files with skill- prefix should be renamed to {domain}-{description} format
        # Only flag as orphan if NOT already referenced by an index (Gap 1/2 catches indexed ones)
        if ($baseName -match '^skill-' -and -not $referencedFiles.ContainsKey($baseName)) {
            [void]$orphans.Add([PSCustomObject]@{
                File = $baseName
                Domain = 'INVALID'
                ExpectedIndex = 'Rename to {domain}-{description} format per ADR-017'
            })
            continue  # Skip domain pattern matching for skill- files
        }

        # ADR-017: Check for improperly named skills-* files (not valid index files)
        # Valid pattern: skills-{domain}-index.md
        # Invalid patterns: skills-{domain}.md, skills-{random}.md
        if ($baseName -match '^skills-' -and $baseName -notmatch '-index$') {
            [void]$orphans.Add([PSCustomObject]@{
                File = $baseName
                Domain = 'INVALID'
                ExpectedIndex = 'Rename to {domain}-{description}-index format or move to atomic file per ADR-017'
            })
            continue  # Skip domain pattern matching for invalid skills- files
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

function Test-IndexFormat {
    <#
    .SYNOPSIS
        Validates that domain index files are pure lookup tables (ADR-017 token efficiency)
    .DESCRIPTION
        Ensures index files contain ONLY the keywords table with no:
        - Titles (# ...)
        - Metadata blocks (**Key**: Value)
        - Prose or explanatory text
        - Navigation sections (## Index, Parent: ...)
    #>
    param(
        [string]$IndexPath
    )

    $result = @{
        Passed = $true
        Issues = @()
        ViolationLines = @()
    }

    if (-not (Test-Path $IndexPath)) {
        return $result
    }

    $lines = Get-Content -Path $IndexPath -Encoding UTF8
    $lineNumber = 0
    $inTable = $false
    $tableHeaderFound = $false

    foreach ($line in $lines) {
        $lineNumber++
        $trimmedLine = $line.Trim()

        # Skip empty lines
        if ([string]::IsNullOrWhiteSpace($trimmedLine)) {
            continue
        }

        # Check for prohibited patterns

        # Titles: # ...
        if ($trimmedLine -match '^#+\s+') {
            $result.Passed = $false
            $result.ViolationLines += $lineNumber
            $result.Issues += "Line $lineNumber`: Title detected - '$trimmedLine' (prohibited per ADR-017)"
            continue
        }

        # Metadata blocks: **Key**: Value
        if ($trimmedLine -match '^\*\*[^*]+\*\*:\s*') {
            $result.Passed = $false
            $result.ViolationLines += $lineNumber
            $result.Issues += "Line $lineNumber`: Metadata block detected - '$trimmedLine' (prohibited per ADR-017)"
            continue
        }

        # Navigation sections: ## Index, Parent:, etc.
        if ($trimmedLine -match '^Parent:\s*' -or $trimmedLine -match '^>\s*\[.*\]') {
            $result.Passed = $false
            $result.ViolationLines += $lineNumber
            $result.Issues += "Line $lineNumber`: Navigation section detected - '$trimmedLine' (prohibited per ADR-017)"
            continue
        }

        # Check for table structure
        if ($trimmedLine -match '^\|.*\|$') {
            # Valid table row (header, separator, or data)
            $inTable = $true
            $tableHeaderFound = $true
            continue
        }

        # If we're past the table header and see non-table content, it's a violation
        if ($tableHeaderFound -and -not ($trimmedLine -match '^\|.*\|$')) {
            # Could be prose or other content after/around the table
            $result.Passed = $false
            $result.ViolationLines += $lineNumber
            $result.Issues += "Line $lineNumber`: Non-table content detected - '$trimmedLine' (prohibited per ADR-017)"
        }
    }

    return $result
}

function Test-MemoryIndexReferences {
    <#
    .SYNOPSIS
        Validates that memory-index references existing domain indices (P1)
    .DESCRIPTION
        P1 validations:
        1. All domain indices MUST be referenced in memory-index (completeness)
        2. All references in memory-index MUST point to existing files (validity)
    #>
    param(
        [string]$MemoryPath,
        [array]$DomainIndices
    )

    $result = @{
        Passed = $true
        Issues = @()
        UnreferencedIndices = @()
        BrokenReferences = @()
    }

    $memoryIndexPath = Join-Path $MemoryPath "memory-index.md"

    if (-not (Test-Path $memoryIndexPath)) {
        $result.Passed = $false
        $result.Issues += "CRITICAL: memory-index.md not found - required for tiered architecture"
        return $result
    }

    $content = Get-Content -Path $memoryIndexPath -Raw
    $lines = $content -split "`n"

    # P1: Check that ALL domain indices are referenced (completeness)
    foreach ($index in $DomainIndices) {
        $indexBaseName = $index.Name
        if ($content -notmatch [regex]::Escape($indexBaseName)) {
            $result.Passed = $false
            $result.UnreferencedIndices += $indexBaseName
            $result.Issues += "P1 COMPLETENESS: Domain index not referenced in memory-index: $indexBaseName"
        }
    }

    # P1: Check that all references in memory-index point to existing files (validity)
    # Note: memory-index may use comma-separated lists of files in the second column
    foreach ($line in $lines) {
        # Match table row: | keywords... | file-name(s) |
        if ($line -match '^\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|$') {
            $fileEntry = $Matches[2].Trim()

            # Skip header/separator rows
            if ($fileEntry -eq 'File' -or $fileEntry -match '^-+$' -or
                $fileEntry -eq 'Essential Memories' -or $fileEntry -eq 'Memory') {
                continue
            }

            # Handle comma-separated file lists (e.g., "file1, file2, file3")
            $fileNames = @($fileEntry -split ',\s*' | ForEach-Object { $_.Trim() } | Where-Object { $_ })

            foreach ($fileName in $fileNames) {
                # Check if reference exists as file
                $refPath = Join-Path $MemoryPath "$fileName.md"
                if (-not (Test-Path $refPath)) {
                    $result.Passed = $false
                    $result.BrokenReferences += $fileName
                    $result.Issues += "P1 VALIDITY: memory-index references non-existent file: $fileName.md"
                }
            }
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

        # P0: Test file references
        $fileResult = Test-FileReferences -Entries $entries -MemoryPath $MemoryPath
        $validation.Summary.TotalFiles += $entries.Count
        $validation.Summary.MissingFiles += $fileResult.MissingFiles.Count

        # P0: Test keyword density
        $keywordResult = Test-KeywordDensity -Entries $entries
        if (-not $keywordResult.Passed) {
            $validation.Summary.KeywordIssues += $keywordResult.Issues.Count
        }

        # P0: Test index format (ADR-017 pure lookup table requirement)
        $formatResult = Test-IndexFormat -IndexPath $index.Path

        # P2: Test duplicate entries
        $duplicateResult = Test-DuplicateEntries -Entries $entries

        # P2: Test minimum keywords (always run, warning only)
        $minKeywordResult = Test-MinimumKeywords -Entries $entries -MinKeywords 5

        # P2: Test domain prefix naming (always run, warning only)
        $prefixResult = Test-DomainPrefixNaming -Entries $entries -Domain $index.Domain

        # Calculate domain pass status
        # P0 validations are always blocking; P2 are warnings only
        $p0Passed = $fileResult.Passed -and $keywordResult.Passed -and $formatResult.Passed -and $duplicateResult.Passed

        $domainPassed = $p0Passed

        $validation.DomainResults[$index.Domain] = @{
            IndexPath = $index.Path
            Entries = $entries.Count
            FileReferences = $fileResult
            KeywordDensity = $keywordResult
            IndexFormat = $formatResult
            DuplicateEntries = $duplicateResult
            MinimumKeywords = $minKeywordResult
            DomainPrefixNaming = $prefixResult
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
                Write-ColorOutput "    - [P0] $issue" $ColorRed
            }
            foreach ($issue in $keywordResult.Issues) {
                Write-ColorOutput "    - [P0] $issue" $ColorYellow
            }
            foreach ($issue in $formatResult.Issues) {
                Write-ColorOutput "    - [P0] $issue" $ColorRed
            }
            foreach ($issue in $duplicateResult.Issues) {
                Write-ColorOutput "    - [P0] $issue" $ColorRed
            }
        }

        # Show P2 warnings (never blocking)
        foreach ($issue in $minKeywordResult.Issues) {
            Write-ColorOutput "    - [P2 WARN] $issue" $ColorYellow
        }
        foreach ($issue in $prefixResult.Issues) {
            Write-ColorOutput "    - [P2 WARN] $issue" $ColorYellow
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

    # P1: Validate memory-index references (completeness and validity)
    $memoryIndexResult = Test-MemoryIndexReferences -MemoryPath $MemoryPath -DomainIndices $domainIndices
    $validation.MemoryIndexResult = $memoryIndexResult

    if (-not $memoryIndexResult.Passed) {
        $validation.Passed = $false
        Write-ColorOutput "`n[P1] Memory-index validation FAILED:" $ColorRed
        foreach ($issue in $memoryIndexResult.Issues) {
            Write-ColorOutput "  - $issue" $ColorRed
        }
    } elseif ($memoryIndexResult.Issues.Count -gt 0) {
        Write-ColorOutput "`nMemory-index warnings:" $ColorYellow
        foreach ($issue in $memoryIndexResult.Issues) {
            Write-ColorOutput "  - $issue" $ColorYellow
        }
    }

    # Find orphaned files (always check)
    $orphans = Get-OrphanedFiles -AllIndices $domainIndices -MemoryPath $MemoryPath
    $validation.Orphans = $orphans

    if ($orphans.Count -gt 0) {
        # Orphans are always warnings (P1), never blocking
        Write-ColorOutput "`n[P1 WARN] Orphaned files detected (not indexed):" $ColorYellow
        foreach ($orphan in $orphans) {
            Write-ColorOutput "  - $($orphan.File) (should be in $($orphan.ExpectedIndex))" $ColorYellow
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
