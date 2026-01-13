<#
.SYNOPSIS
    Converts memory references in .serena/memories/ to proper Markdown links.

.DESCRIPTION
    Processes markdown files in .serena/memories/ and converts:
    - Backtick references like `memory-name` to [memory-name](memory-name.md)
    - Only converts if the referenced file exists in .serena/memories/
    - Supports processing specific files via -FilesToProcess parameter

.EXAMPLE
    .\.claude\skills\memory\scripts\Convert-MemoryReferences.ps1
#>

[CmdletBinding()]
param(
    [string]$MemoriesPath,

    [string[]]$FilesToProcess,

    [switch]$OutputJson,

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
    $gitError = $_.Exception.Message
    Write-Warning "git rev-parse failed ($gitError), falling back to directory traversal"
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

        # Ensure comparison includes directory separator to prevent sibling directory attacks (CWE-22)
        # e.g., /home/user/project-attacker/ should not match /home/user/project/
        $projectRootWithSep = $resolvedProjectRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
        if (-not $resolvedPath.StartsWith($projectRootWithSep, [System.StringComparison]::OrdinalIgnoreCase) -and
            $resolvedPath -ne $resolvedProjectRoot) {
            throw "Security: MemoriesPath must be within project directory. Provided: $resolvedPath, Project root: $resolvedProjectRoot"
        }

        $memoriesPath = $resolvedPath
    } else {
        $memoriesPath = [IO.Path]::GetFullPath($MemoriesPath)
    }
}

# Get all markdown files in the memories directory
$allMemoryFiles = Get-ChildItem -Path $memoriesPath -Filter '*.md' -File

# Filter by FilesToProcess if provided and non-empty
if ($FilesToProcess -and $FilesToProcess.Count -gt 0) {
    # Normalize paths for comparison
    $normalizedFilesToProcess = $FilesToProcess | ForEach-Object {
        [IO.Path]::GetFullPath($_)
    }
    $memoryFilesToProcess = $allMemoryFiles | Where-Object {
        $normalizedPath = [IO.Path]::GetFullPath($_.FullName)
        $normalizedFilesToProcess -contains $normalizedPath
    }
} else {
    $memoryFilesToProcess = $allMemoryFiles
}

# Build a set of all memory file names (without .md extension) for validation
$memoryNames = @{}
foreach ($file in $allMemoryFiles) {
    $baseName = $file.BaseName
    $memoryNames[$baseName] = $true
}

# Statistics tracking
$filesProcessed = 0
$filesModified = 0
$linksAdded = 0
$errors = @()

if (-not $OutputJson) {
    Write-Host "Found $($allMemoryFiles.Count) memory files"
}

foreach ($file in $memoryFilesToProcess) {
    $filesProcessed++

    try {
        $content = Get-Content $file.FullName -Raw -Encoding UTF8

        # Skip empty files
        if ([string]::IsNullOrEmpty($content)) {
            continue
        }

        $originalContent = $content

        # Pattern 1: Convert backtick references like `memory-name` to [memory-name](memory-name.md)
        # But exclude:
        # - File paths (containing / or \)
        # - Code snippets (things that look like code)
        # - Already linked items
        # - Things with spaces (likely not memory names)
        # Match backticks with memory names (allow single-token or hyphenated names)
        $pattern = '(?<![\[\(])`([a-z0-9]+(?:-[a-z0-9]+)*)`(?![\]\)])'

        $content = [regex]::Replace($content, $pattern, {
            param($match)
            $memoryName = $match.Groups[1].Value

            # Only convert if this is an actual memory file
            if ($memoryNames.ContainsKey($memoryName)) {
                return "[$memoryName]($memoryName.md)"
            } else {
                # Keep original backticks if not a known memory
                return $match.Value
            }
        })

        # Check if content changed
        if ($content -ne $originalContent) {
            Set-Content -Path $file.FullName -Value $content -NoNewline -Encoding UTF8
            if (-not $OutputJson) {
                Write-Host "Updated: $($file.Name)"
            }
            $filesModified++

            # Count links added (approximate by counting markdown link patterns added)
            $originalLinkCount = ([regex]::Matches($originalContent, '\[[^\]]+\]\([^\)]+\.md\)')).Count
            $newLinkCount = ([regex]::Matches($content, '\[[^\]]+\]\([^\)]+\.md\)')).Count
            $linksAdded += ($newLinkCount - $originalLinkCount)
        }
    } catch {
        $errors += "Error processing $($file.Name): $($_.Exception.Message)"
        if (-not $OutputJson) {
            Write-Warning "Error processing $($file.Name): $($_.Exception.Message)"
        }
    }
}

# Output results
if ($OutputJson) {
    [PSCustomObject]@{
        FilesProcessed = $filesProcessed
        FilesModified  = $filesModified
        LinksAdded     = $linksAdded
        Errors         = $errors
    } | ConvertTo-Json -Compress
} else {
    Write-Host "`nConversion complete. Modified $filesModified files."
}
