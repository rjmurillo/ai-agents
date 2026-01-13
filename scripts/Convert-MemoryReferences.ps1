<#
.SYNOPSIS
    Converts memory references in .serena/memories/ to proper Markdown links.

.DESCRIPTION
    Processes all markdown files in .serena/memories/ and converts:
    - Backtick references like `memory-name` to [memory-name](memory-name.md)
    - Only converts if the referenced file exists in .serena/memories/

.EXAMPLE
    .\scripts\Convert-MemoryReferences.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$memoriesPath = Join-Path $PSScriptRoot '..' '.serena' 'memories'

# Get all markdown files in the memories directory
$memoryFiles = Get-ChildItem -Path $memoriesPath -Filter '*.md' -File

# Build a set of all memory file names (without .md extension) for validation
$memoryNames = @{}
foreach ($file in $memoryFiles) {
    $baseName = $file.BaseName
    $memoryNames[$baseName] = $true
}

Write-Host "Found $($memoryFiles.Count) memory files"
$filesModified = 0

foreach ($file in $memoryFiles) {
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
    $pattern = '(?<![\[\(])`([a-z0-9]+(?:-[a-z0-9]+)+)`(?![\]\)])'

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
        Write-Host "Updated: $($file.Name)"
        $filesModified++
    }
}

Write-Host "`nConversion complete. Modified $filesModified files."
