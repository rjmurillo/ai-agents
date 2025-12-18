<#
.SYNOPSIS
    Validates that documentation files contain no absolute paths.

.DESCRIPTION
    Scans documentation files in .agents/ and src/ directories for absolute
    path references that would contaminate documentation with environment-specific
    information.

    Detects forbidden patterns:
    - Windows absolute paths: C:\, D:\, etc.
    - macOS/Linux absolute paths: /Users/, /home/

    This prevents Issue #I3 (Environment Contamination) as identified in
    CodeRabbit review of PR rjmurillo/ai-agents#43.

.PARAMETER Path
    Root path to scan. Defaults to current directory.

.PARAMETER Extensions
    File extensions to scan. Defaults to .md files.

.PARAMETER ExcludePaths
    Paths to exclude from scanning. Defaults to .git, node_modules, etc.

.PARAMETER FailOnViolation
    Exit with non-zero code if violations found. Used in CI/CD.

.EXAMPLE
    .\Validate-PathNormalization.ps1
    # Scan all markdown files in current directory

.EXAMPLE
    .\Validate-PathNormalization.ps1 -FailOnViolation
    # Scan and exit with error code if violations found (CI mode)

.EXAMPLE
    .\Validate-PathNormalization.ps1 -Path .agents -Extensions @('.md', '.txt')
    # Scan .agents directory for .md and .txt files

.NOTES
    Author: AI Agents Team
    Related: Issue rjmurillo/ai-agents#I3 (Environment Contamination)
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$Path = ".",

    [Parameter(Mandatory = $false)]
    [string[]]$Extensions = @('.md'),

    [Parameter(Mandatory = $false)]
    [string[]]$ExcludePaths = @('.git', 'node_modules', '.vs', 'bin', 'obj', '.agents/sessions'),

    [Parameter(Mandatory = $false)]
    [switch]$FailOnViolation
)

# Detect if colors should be disabled (CI environments, NO_COLOR standard)
$NoColor = $env:NO_COLOR -or $env:TERM -eq 'dumb' -or $env:CI

# Absolute path detection patterns
$ForbiddenPatterns = @(
    @{
        Name        = 'Windows Absolute Path'
        Pattern     = '[A-Z]:\\'
        Description = 'Windows drive letter path (e.g., C:\, D:\)'
        Example     = 'C:\Users\username\repo\file.md'
    },
    @{
        Name        = 'macOS User Path'
        Pattern     = '/Users/'
        Description = 'macOS user home directory path'
        Example     = '/Users/username/repo/file.md'
    },
    @{
        Name        = 'Linux Home Path'
        Pattern     = '/home/'
        Description = 'Linux user home directory path'
        Example     = '/home/username/repo/file.md'
    }
)

# ANSI color codes for output (disabled when NO_COLOR is set)
if ($NoColor) {
    $ColorReset = ""
    $ColorRed = ""
    $ColorYellow = ""
    $ColorGreen = ""
    $ColorCyan = ""
}
else {
    $ColorReset = "`e[0m"
    $ColorRed = "`e[31m"
    $ColorYellow = "`e[33m"
    $ColorGreen = "`e[32m"
    $ColorCyan = "`e[36m"
}

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = $ColorReset
    )
    if ($NoColor) {
        Write-Host $Message
    }
    else {
        Write-Host "$Color$Message$ColorReset"
    }
}

function Get-FilesToScan {
    param(
        [string]$RootPath,
        [string[]]$Extensions,
        [string[]]$Excludes
    )

    $files = Get-ChildItem -Path $RootPath -Recurse -File | Where-Object {
        $file = $_
        $included = $false

        # Check if extension matches
        foreach ($ext in $Extensions) {
            if ($file.Extension -eq $ext) {
                $included = $true
                break
            }
        }

        if (-not $included) {
            return $false
        }

        # Check if path should be excluded
        # Normalize path separators for cross-platform compatibility
        $relativePath = $file.FullName.Substring($RootPath.Length).TrimStart('\', '/')
        $normalizedPath = $relativePath -replace '\\', '/'
        foreach ($exclude in $Excludes) {
            $normalizedExclude = $exclude -replace '\\', '/'
            if ($normalizedPath -like "*$normalizedExclude*") {
                return $false
            }
        }

        return $true
    }

    return $files
}

function Test-FileForAbsolutePaths {
    param(
        [System.IO.FileInfo]$File,
        [array]$Patterns
    )

    $violations = @()
    $content = Get-Content -Path $File.FullName -Raw

    if ([string]::IsNullOrWhiteSpace($content)) {
        return $violations
    }

    $lineNumber = 0
    $inCodeBlock = $false
    foreach ($line in (Get-Content -Path $File.FullName)) {
        $lineNumber++

        # Track fenced code blocks (``` or ~~~)
        if ($line -match '^\s*(`{3,}|~{3,})') {
            $inCodeBlock = -not $inCodeBlock
            continue
        }

        # Skip lines inside code blocks - example paths are allowed there
        if ($inCodeBlock) {
            continue
        }

        # Skip inline code (content between backticks) by removing it before checking
        $lineWithoutInlineCode = $line -replace '`[^`]+`', ''

        foreach ($pattern in $Patterns) {
            if ($lineWithoutInlineCode -match $pattern.Pattern) {
                $violations += @{
                    File        = $File.FullName
                    Line        = $lineNumber
                    Content     = $line.Trim()
                    PatternName = $pattern.Name
                    Description = $pattern.Description
                    Example     = $pattern.Example
                }
            }
        }
    }

    return $violations
}

# Main execution
Write-ColorOutput "=== Path Normalization Validation ===" $ColorCyan
Write-Host ""

$rootPath = (Resolve-Path $Path).Path
Write-Host "Scanning path: $rootPath"
Write-Host "Extensions: $($Extensions -join ', ')"
Write-Host "Excluded paths: $($ExcludePaths -join ', ')"
Write-Host ""

# Get files to scan
$filesToScan = Get-FilesToScan -RootPath $rootPath -Extensions $Extensions -Excludes $ExcludePaths

if ($filesToScan.Count -eq 0) {
    Write-ColorOutput "No files found to scan." $ColorYellow
    exit 0
}

Write-Host "Files to scan: $($filesToScan.Count)"
Write-Host ""

# Scan files
$allViolations = @()
$filesWithViolations = 0

foreach ($file in $filesToScan) {
    $violations = Test-FileForAbsolutePaths -File $file -Patterns $ForbiddenPatterns

    if ($violations.Count -gt 0) {
        $allViolations += $violations
        $filesWithViolations++
    }
}

# Report results
if ($allViolations.Count -eq 0) {
    Write-ColorOutput "✅ SUCCESS: No absolute paths found in $($filesToScan.Count) files" $ColorGreen
    exit 0
}
else {
    Write-ColorOutput "❌ FAILURE: Found $($allViolations.Count) absolute path violations in $filesWithViolations files" $ColorRed
    Write-Host ""

    # Group violations by file
    $violationsByFile = $allViolations | Group-Object -Property File

    foreach ($fileGroup in $violationsByFile) {
        # Use Push-Location/Pop-Location for proper relative path calculation
        # This handles path normalization issues (e.g., RUNNER~1 vs runneradmin)
        Push-Location $rootPath
        try {
            $relativePath = Resolve-Path -Path $fileGroup.Name -Relative
            # Remove leading .\ or ./
            $relativePath = $relativePath -replace '^\.[\\/]', ''
        }
        finally {
            Pop-Location
        }
        Write-ColorOutput "File: $relativePath" $ColorYellow
        Write-Host ""

        foreach ($violation in $fileGroup.Group) {
            Write-Host "  Line $($violation.Line): $($violation.PatternName)"
            Write-Host "  Pattern: $($violation.Description)"
            Write-ColorOutput "  Content: $($violation.Content)" $ColorRed
            Write-Host "  Should use relative path instead"
            Write-Host ""
        }
    }

    # Summary and remediation
    Write-ColorOutput "=== Remediation Steps ===" $ColorCyan
    Write-Host ""
    Write-Host "1. Replace absolute paths with relative paths from the document's location"
    Write-Host "2. Use forward slashes (/) for cross-platform compatibility"
    Write-Host "3. Examples of correct relative paths:"
    Write-Host "   - docs/guide.md"
    Write-Host "   - ../architecture/design.md"
    Write-Host "   - .agents/planning/PRD-feature.md"
    Write-Host ""
    Write-Host "See src/claude/explainer.md for path normalization guidelines."
    Write-Host ""

    if ($FailOnViolation) {
        exit 1
    }
    else {
        exit 0
    }
}
