<#
.SYNOPSIS
    Converts file references in index table cells to proper Markdown links.

.DESCRIPTION
    Processes index files with tables that contain file references and converts them
    to proper markdown links for better Obsidian navigation.

.EXAMPLE
    .\scripts\Convert-IndexTableLinks.ps1
#>

[CmdletBinding()]
param(
    [string]$MemoriesPath,

    [switch]$SkipPathValidation
)

$ErrorActionPreference = 'Stop'

# Determine project root robustly
try {
    $projectRoot = git rev-parse --show-toplevel 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Not in a git repository"
    }
} catch {
    Write-Warning "git rev-parse failed, falling back to directory traversal"
    $projectRoot = $PSScriptRoot
    while ($projectRoot -and -not (Test-Path (Join-Path $projectRoot '.git'))) {
        $projectRoot = Split-Path $projectRoot -Parent
    }
    if (-not $projectRoot) {
        throw "Could not find project root (no .git directory found)"
    }
}

# Use provided path or default to .serena/memories
if (-not $MemoriesPath) {
    $memoriesPath = Join-Path $projectRoot '.serena' 'memories'
} else {
    # Validate provided path is within project root (CWE-22 mitigation)
    # Skip validation only when explicitly requested (e.g., for tests)
    if (-not $SkipPathValidation) {
        $resolvedPath = [IO.Path]::GetFullPath($MemoriesPath)
        $resolvedProjectRoot = [IO.Path]::GetFullPath($projectRoot)

        if (-not $resolvedPath.StartsWith($resolvedProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Security: MemoriesPath must be within project directory. Provided: $resolvedPath, Project root: $resolvedProjectRoot"
        }

        $memoriesPath = $resolvedPath
    } else {
        $memoriesPath = [IO.Path]::GetFullPath($MemoriesPath)
    }
}

# Get all index files
$indexFiles = Get-ChildItem -Path $memoriesPath -Filter '*-index.md' -File

# Build a set of all memory file names (without .md extension) for validation
$memoryFiles = Get-ChildItem -Path $memoriesPath -Filter '*.md' -File
$memoryNames = @{}
foreach ($file in $memoryFiles) {
    $baseName = $file.BaseName
    $memoryNames[$baseName] = $true
}

Write-Host "Found $($indexFiles.Count) index files and $($memoryFiles.Count) memory files"
$filesModified = 0

foreach ($file in $indexFiles) {
    $content = Get-Content $file.FullName -Raw -Encoding UTF8

    # Skip empty files
    if ([string]::IsNullOrEmpty($content)) {
        continue
    }

    $originalContent = $content

    # Pattern 1: Convert table cells with single file references like "| keyword | filename |"
    # Match filename without .md extension in table cells, not already a link
    # Using lookaround to avoid consuming pipes, allowing overlapping matches
    $content = [regex]::Replace($content, '(?<=\|)\s*([a-z][a-z0-9-]+)\s*(?=\|)', {
        param($match)
        $fileName = $match.Groups[1].Value.Trim()
        $cellContent = $match.Value

        # Skip separator rows (only hyphens and spaces, no letters/digits)
        if ($cellContent -match '^[\s-]+$' -and $cellContent -notmatch '[a-z0-9]') {
            return $cellContent
        }

        # Only convert if this is a known memory file and not already a link
        if ($memoryNames.ContainsKey($fileName) -and $cellContent -notmatch '\[') {
            # Write-Host "DEBUG: Converting $fileName"
            return " [$fileName]($fileName.md) "
        } else {
            # Write-Host "DEBUG: Skipping $fileName (in memory: $($memoryNames.ContainsKey($fileName)))"
            return $cellContent
        }
    })

    # Pattern 2: Convert comma-separated file lists in table cells like "| keyword | file1, file2, file3 |"
    $content = [regex]::Replace($content, '\|\s*([a-z][a-z0-9-]+(?:,\s*[a-z][a-z0-9-]+)+)\s*\|', {
        param($match)
        $fileList = $match.Groups[1].Value

        # Skip if already has markdown links
        if ($fileList -match '\[') {
            return $match.Value
        }

        # Split by comma and convert each file
        $files = $fileList -split ',\s*'
        $convertedFiles = @()

        foreach ($fileName in $files) {
            $fileName = $fileName.Trim()
            if ($memoryNames.ContainsKey($fileName)) {
                $convertedFiles += "[$fileName]($fileName.md)"
            } else {
                $convertedFiles += $fileName
            }
        }

        return "| $($convertedFiles -join ', ') |"
    })

    # Check if content changed
    if ($content -ne $originalContent) {
        Set-Content -Path $file.FullName -Value $content -NoNewline -Encoding UTF8
        Write-Host "Updated: $($file.Name)"
        $filesModified++
    }
}

Write-Host "`nConversion complete. Modified $filesModified files."
