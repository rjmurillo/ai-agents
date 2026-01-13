<#
.SYNOPSIS
    Converts file references in index table cells to proper Markdown links.

.DESCRIPTION
    Processes index files with tables that contain file references and converts them
    to proper markdown links for better Obsidian navigation.

.EXAMPLE
    .\.claude\skills\memory\scripts\Convert-IndexTableLinks.ps1
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

# Get all index files
$allIndexFiles = Get-ChildItem -Path $memoriesPath -Filter '*-index.md' -File

# Filter by FilesToProcess if provided and non-empty
if ($FilesToProcess -and $FilesToProcess.Count -gt 0) {
    # Normalize paths for comparison
    $normalizedFilesToProcess = $FilesToProcess | ForEach-Object {
        [IO.Path]::GetFullPath($_)
    }
    $indexFiles = $allIndexFiles | Where-Object {
        $normalizedPath = [IO.Path]::GetFullPath($_.FullName)
        $normalizedFilesToProcess -contains $normalizedPath
    }
} else {
    $indexFiles = $allIndexFiles
}

# Build a set of all memory file names (without .md extension) for validation
$memoryFiles = Get-ChildItem -Path $memoriesPath -Filter '*.md' -File
$memoryNames = @{}
foreach ($file in $memoryFiles) {
    $baseName = $file.BaseName
    $memoryNames[$baseName] = $true
}

# Statistics tracking
$filesProcessed = 0
$filesModified = 0
$linksAdded = 0
$errors = @()

if (-not $OutputJson) {
    Write-Host "Found $($indexFiles.Count) index files and $($memoryFiles.Count) memory files"
}

foreach ($file in $indexFiles) {
    $filesProcessed++

    try {
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

            # Skip separator rows (only hyphens and spaces)
            if ($cellContent -match '^[\s-]+$') {
                return $cellContent
            }

            # Only convert if this is a known memory file and not already a link
            if ($memoryNames.ContainsKey($fileName) -and $cellContent -notmatch '\[') {
                return " [$fileName]($fileName.md) "
            } else {
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
