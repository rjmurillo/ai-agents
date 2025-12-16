<#
.SYNOPSIS
    Generates platform-specific agent files from shared sources.

.DESCRIPTION
    Reads shared agent source files from templates/agents/*.shared.md and generates
    platform-specific outputs for VS Code and Copilot CLI. This enables maintaining
    a single source of truth for agents that differ only in frontmatter.

    The script transforms:
    - YAML frontmatter (model field, name field, tools array)
    - Handoff syntax (#runSubagent vs /agent)

.PARAMETER TemplatesPath
    Path to the templates directory. Defaults to templates/ in repository root.

.PARAMETER OutputRoot
    Root directory for generated output. Defaults to src/ in repository root.

.PARAMETER Verbose
    Show detailed logging of transformation steps.

.PARAMETER WhatIf
    Dry-run mode. Show what would be generated without writing files.

.PARAMETER Validate
    CI mode. Regenerate files and compare to committed files. Exit 1 if differences found.

.EXAMPLE
    .\Generate-Agents.ps1
    # Generate all agents with default settings

.EXAMPLE
    .\Generate-Agents.ps1 -Verbose
    # Generate with detailed logging

.EXAMPLE
    .\Generate-Agents.ps1 -WhatIf
    # Show what would be generated without writing

.EXAMPLE
    .\Generate-Agents.ps1 -Validate
    # CI mode: regenerate and compare to committed files

.NOTES
    Security: Output paths are validated to remain within repository root.
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter()]
    [string]$TemplatesPath,

    [Parameter()]
    [string]$OutputRoot,

    [Parameter()]
    [switch]$Validate
)

$ErrorActionPreference = "Stop"

#region Module Import

# Import shared functions from module
$ModulePath = Join-Path $PSScriptRoot "Generate-Agents.Common.psm1"
if (-not (Test-Path $ModulePath)) {
    Write-Error "Required module not found: $ModulePath"
    exit 1
}
Import-Module $ModulePath -Force

#endregion

#region Path Resolution

# Resolve repository root
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $TemplatesPath) {
    $TemplatesPath = Join-Path $RepoRoot "templates"
}
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $RepoRoot "src"
}

# Validate paths exist
if (-not (Test-Path $TemplatesPath)) {
    Write-Error "Templates path not found: $TemplatesPath"
    exit 1
}

#endregion

#region Helper Functions

# Note: Most helper functions are imported from Generate-Agents.Common.psm1
# Only script-specific functions are defined here.

function Read-PlatformConfig {
    <#
    .SYNOPSIS
        Reads platform configuration from YAML file.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$ConfigPath
    )

    if (-not (Test-Path $ConfigPath)) {
        Write-Error "Platform config not found: $ConfigPath"
        return $null
    }

    $content = Get-Content -Path $ConfigPath -Raw

    # Parse simple YAML (no external module dependency)
    $config = @{}
    $currentSection = $null

    foreach ($line in ($content -split '\r?\n')) {
        # Skip comments and empty lines
        if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }

        # Check for section (key followed by colon with no value)
        if ($line -match '^(\w+):\s*$') {
            $currentSection = $Matches[1]
            $config[$currentSection] = @{}
            continue
        }

        # Check for nested key-value (indented)
        if ($line -match '^\s+(\w+):\s*(.*)$') {
            $key = $Matches[1]
            $value = $Matches[2].Trim()

            # Parse value
            if ($value -eq 'true') { $value = $true }
            elseif ($value -eq 'false') { $value = $false }
            elseif ($value -eq 'null' -or $value -eq '') { $value = $null }
            elseif ($value -match '^"(.*)"$') { $value = $Matches[1] }

            if ($currentSection) {
                $config[$currentSection][$key] = $value
            }
            continue
        }

        # Top-level key-value
        if ($line -match '^(\w+):\s*(.+)$') {
            $key = $Matches[1]
            $value = $Matches[2].Trim()

            # Parse value
            if ($value -eq 'true') { $value = $true }
            elseif ($value -eq 'false') { $value = $false }
            elseif ($value -eq 'null') { $value = $null }
            elseif ($value -match '^"(.*)"$') { $value = $Matches[1] }

            $config[$key] = $value
            $currentSection = $null
        }
    }

    return $config
}

#endregion

#region Main Logic

Write-Host ""
Write-Host "=== Agent Generation ===" -ForegroundColor Cyan
Write-Host "Templates Path: $TemplatesPath"
Write-Host "Output Root: $OutputRoot"
Write-Host "Mode: $(if ($Validate) { 'Validate' } elseif ($WhatIfPreference) { 'WhatIf' } else { 'Generate' })"
Write-Host ""

$startTime = Get-Date

# Load platform configurations
$platformsPath = Join-Path $TemplatesPath "platforms"
$platforms = @()

foreach ($configFile in (Get-ChildItem -Path $platformsPath -Filter "*.yaml" -ErrorAction SilentlyContinue)) {
    $config = Read-PlatformConfig -ConfigPath $configFile.FullName
    if ($config) {
        $platforms += $config
        Write-Verbose "Loaded platform config: $($config['platform'])"
    }
}

if ($platforms.Count -eq 0) {
    Write-Error "No platform configurations found in $platformsPath"
    exit 1
}

Write-Host "Loaded $($platforms.Count) platform configuration(s)" -ForegroundColor Green

# Find all shared source files
$agentsPath = Join-Path $TemplatesPath "agents"
$sharedFiles = Get-ChildItem -Path $agentsPath -Filter "*.shared.md" -ErrorAction SilentlyContinue

if (-not $sharedFiles -or $sharedFiles.Count -eq 0) {
    Write-Error "No shared source files found in $agentsPath"
    exit 1
}

Write-Host "Found $($sharedFiles.Count) shared source file(s)" -ForegroundColor Green
Write-Host ""

# Track results
$generated = 0
$errors = 0
$differences = @()

# Process each shared source
foreach ($sharedFile in $sharedFiles) {
    $agentName = $sharedFile.BaseName -replace '\.shared$', ''
    Write-Host "Processing: $agentName" -ForegroundColor Yellow

    # Read shared source
    $content = Get-Content -Path $sharedFile.FullName -Raw -Encoding UTF8

    # Parse frontmatter
    $parsed = Read-YamlFrontmatter -Content $content
    if (-not $parsed) {
        Write-Error "  Failed to parse frontmatter for $agentName"
        $errors++
        continue
    }

    $frontmatter = ConvertFrom-SimpleFrontmatter -FrontmatterRaw $parsed.FrontmatterRaw
    $body = $parsed.Body

    # Generate for each platform
    foreach ($platform in $platforms) {
        $platformName = $platform['platform']
        # Handle outputDir - remove src/ prefix if present since OutputRoot is already src/
        $outputDirRelative = $platform['outputDir']
        if ($outputDirRelative -match '^src/(.*)$') {
            $outputDirRelative = $Matches[1]
        }
        $outputDir = Join-Path $OutputRoot $outputDirRelative
        $outputFile = Join-Path $outputDir "$agentName$($platform['fileExtension'])"

        # Security check: validate output path
        if (-not (Test-PathWithinRoot -Path $outputFile -Root $RepoRoot)) {
            Write-Error "  Security: Output path escapes repository root: $outputFile"
            $errors++
            continue
        }

        Write-Verbose "  -> ${platformName}: $outputFile"

        # Transform frontmatter
        $transformedFrontmatter = Convert-FrontmatterForPlatform `
            -Frontmatter $frontmatter `
            -PlatformConfig $platform `
            -AgentName $agentName

        # Transform body (handoff syntax and memory prefix)
        $handoffSyntax = $platform['handoffSyntax']
        $memoryPrefix = $platform['memoryPrefix']
        if (-not $memoryPrefix) { $memoryPrefix = 'cloudmcp-manager/' }

        $transformedBody = Convert-HandoffSyntax -Body $body -TargetSyntax $handoffSyntax
        $transformedBody = Convert-MemoryPrefix -Body $transformedBody -MemoryPrefix $memoryPrefix

        # Build output content with CRLF line endings (matching existing files)
        $frontmatterYaml = Format-FrontmatterYaml -Frontmatter $transformedFrontmatter
        # First build with LF, then convert to CRLF for consistency
        $outputContent = "---`n$frontmatterYaml`n---`n$transformedBody"
        # Normalize to LF first, then convert to CRLF
        $outputContent = $outputContent -replace '\r\n', "`n" -replace '\n', "`r`n"

        if ($Validate) {
            # Compare with existing file
            if (Test-Path $outputFile) {
                $existingContent = Get-Content -Path $outputFile -Raw -Encoding UTF8
                # Normalize line endings for comparison
                $normalizedExisting = $existingContent -replace '\r\n', "`n"
                $normalizedGenerated = $outputContent -replace '\r\n', "`n"

                if ($normalizedExisting -ne $normalizedGenerated) {
                    Write-Host "  DIFF: $platformName output differs from committed file" -ForegroundColor Red
                    $differences += $outputFile
                }
                else {
                    Write-Host "  OK: $platformName" -ForegroundColor Green
                }
            }
            else {
                Write-Host "  MISSING: $outputFile" -ForegroundColor Red
                $differences += $outputFile
            }
        }
        elseif ($WhatIfPreference) {
            Write-Host "  Would generate: $outputFile" -ForegroundColor Cyan
        }
        else {
            # Ensure output directory exists
            if (-not (Test-Path $outputDir)) {
                New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
            }

            # Write file
            Set-Content -Path $outputFile -Value $outputContent -Encoding UTF8 -NoNewline
            Write-Host "  Generated: $platformName" -ForegroundColor Green
            $generated++
        }
    }
}

$duration = (Get-Date) - $startTime

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Duration: $($duration.TotalSeconds.ToString('F2'))s"

if ($Validate) {
    if ($differences.Count -gt 0) {
        Write-Host ""
        Write-Host "VALIDATION FAILED: $($differences.Count) file(s) differ from generated output" -ForegroundColor Red
        Write-Host ""
        Write-Host "Files with differences:" -ForegroundColor Red
        foreach ($diff in $differences) {
            Write-Host "  - $diff" -ForegroundColor Red
        }
        Write-Host ""
        Write-Host "To fix: Run 'pwsh build/Generate-Agents.ps1' and commit the changes" -ForegroundColor Yellow
        exit 1
    }
    else {
        Write-Host "VALIDATION PASSED: All generated files match committed files" -ForegroundColor Green
        exit 0
    }
}
elseif ($WhatIfPreference) {
    Write-Host "Dry run complete. No files were written."
}
else {
    Write-Host "Generated: $generated file(s)"
    if ($errors -gt 0) {
        Write-Host "Errors: $errors" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""

#endregion
