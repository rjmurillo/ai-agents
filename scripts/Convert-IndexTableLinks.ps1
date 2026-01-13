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
param()

$ErrorActionPreference = 'Stop'
$memoriesPath = Join-Path $PSScriptRoot '..' '.serena' 'memories'

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
    $content = [regex]::Replace($content, '\|\s*([a-z][a-z0-9-]+)\s*\|(?!\s*$)', {
        param($match)
        $fileName = $match.Groups[1].Value.Trim()

        # Only convert if this is a known memory file and not already a link
        if ($memoryNames.ContainsKey($fileName) -and $match.Value -notmatch '\[') {
            return "| [$fileName]($fileName.md) |"
        } else {
            return $match.Value
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
