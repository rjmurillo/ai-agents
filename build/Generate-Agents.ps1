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
    Generated files include an AUTO-GENERATED header comment.
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

function Test-PathWithinRoot {
    <#
    .SYNOPSIS
        Security check: Validates that a path is within the repository root.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [string]$Root
    )

    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
    $resolvedRoot = [System.IO.Path]::GetFullPath($Root)

    return $resolvedPath.StartsWith($resolvedRoot, [StringComparison]::OrdinalIgnoreCase)
}

function Read-YamlFrontmatter {
    <#
    .SYNOPSIS
        Extracts YAML frontmatter from a markdown file.
    .OUTPUTS
        PSCustomObject with FrontmatterRaw, FrontmatterLines, Body properties.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Content
    )

    # Match YAML frontmatter between --- markers
    if ($Content -match '^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$') {
        $frontmatterRaw = $Matches[1]
        $body = $Matches[2]

        return [PSCustomObject]@{
            FrontmatterRaw = $frontmatterRaw
            Body           = $body
        }
    }

    Write-Warning "No valid YAML frontmatter found"
    return $null
}

function ConvertFrom-SimpleFrontmatter {
    <#
    .SYNOPSIS
        Parses simple YAML frontmatter into a hashtable.
        Handles basic key: value pairs and arrays in ['item1', 'item2'] format.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$FrontmatterRaw
    )

    $result = @{}
    $lines = $FrontmatterRaw -split '\r?\n'

    foreach ($line in $lines) {
        if ($line -match '^(\w+):\s*(.*)$') {
            $key = $Matches[1]
            $value = $Matches[2].Trim()

            # Check if it's an array (starts with [ and ends with ])
            if ($value -match "^\[.*\]$") {
                # Keep the raw array string for now
                $result[$key] = $value
            }
            elseif ($value -eq '' -or $value -eq 'null') {
                $result[$key] = $null
            }
            else {
                # Remove surrounding quotes if present
                if ($value -match '^"(.*)"$' -or $value -match "^'(.*)'$") {
                    $value = $Matches[1]
                }
                $result[$key] = $value
            }
        }
    }

    return $result
}

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

function Convert-FrontmatterForPlatform {
    <#
    .SYNOPSIS
        Transforms frontmatter for a specific platform.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [hashtable]$Frontmatter,

        [Parameter(Mandatory)]
        [hashtable]$PlatformConfig,

        [Parameter(Mandatory)]
        [string]$AgentName
    )

    $result = @{}
    $platformName = $PlatformConfig['platform']

    # Copy existing fields (excluding placeholders and platform-specific tools)
    foreach ($key in $Frontmatter.Keys) {
        $value = $Frontmatter[$key]
        # Skip placeholder values
        if ($value -match '^\{\{PLATFORM_') { continue }
        # Skip platform-specific tools fields (tools_vscode, tools_copilot)
        if ($key -match '^tools_') { continue }
        # Skip the generic tools field if we have platform-specific ones
        if ($key -eq 'tools' -and ($Frontmatter.ContainsKey('tools_vscode') -or $Frontmatter.ContainsKey('tools_copilot'))) { continue }

        $result[$key] = $value
    }

    # Apply platform-specific transformations
    $fm = $PlatformConfig['frontmatter']

    # Handle name field
    if ($fm -and $fm['includeNameField'] -eq $true) {
        $result['name'] = $AgentName
    }
    else {
        $result.Remove('name')
    }

    # Handle model field
    if ($fm -and $fm['model']) {
        $result['model'] = $fm['model']
    }
    else {
        $result.Remove('model')
    }

    # Handle platform-specific tools array
    $toolsKey = "tools_$($platformName -replace '-', '')"  # tools_vscode, tools_copilotcli
    # Also try with hyphen for copilot-cli -> tools_copilot
    $toolsKeyAlt = "tools_$($platformName -replace '-cli$', '')"  # tools_copilot

    if ($Frontmatter.ContainsKey($toolsKey)) {
        $result['tools'] = $Frontmatter[$toolsKey]
    }
    elseif ($Frontmatter.ContainsKey($toolsKeyAlt)) {
        $result['tools'] = $Frontmatter[$toolsKeyAlt]
    }
    elseif ($Frontmatter.ContainsKey('tools')) {
        # Fallback to generic tools if no platform-specific one exists
        $result['tools'] = $Frontmatter['tools']
    }

    return $result
}

function Format-FrontmatterYaml {
    <#
    .SYNOPSIS
        Converts frontmatter hashtable back to YAML string.
        Maintains specific field order for consistency.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [hashtable]$Frontmatter
    )

    $lines = @()

    # Define field order
    $fieldOrder = @('name', 'description', 'tools', 'model')

    # Output fields in order
    foreach ($field in $fieldOrder) {
        if ($Frontmatter.ContainsKey($field) -and $null -ne $Frontmatter[$field]) {
            $value = $Frontmatter[$field]
            $lines += "${field}: $value"
        }
    }

    # Output any remaining fields
    foreach ($key in $Frontmatter.Keys) {
        if ($key -notin $fieldOrder -and $null -ne $Frontmatter[$key]) {
            $lines += "${key}: $($Frontmatter[$key])"
        }
    }

    return $lines -join "`n"
}

function Convert-HandoffSyntax {
    <#
    .SYNOPSIS
        Transforms handoff syntax in markdown body.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Body,

        [Parameter(Mandatory)]
        [string]$TargetSyntax
    )

    $result = $Body

    switch ($TargetSyntax) {
        "#runSubagent" {
            # Convert /agent to #runSubagent
            $result = $result -replace '`/agent\s+(\w+)`', '`#runSubagent with subagentType=$1`'
            $result = $result -replace '/agent\s+\[agent_name\]', '#runSubagent with subagentType={agent_name}'
        }
        "/agent" {
            # Convert #runSubagent to /agent
            $result = $result -replace '`#runSubagent with subagentType=(\w+)`', '`/agent $1`'
            $result = $result -replace '#runSubagent with subagentType=\{agent_name\}', '/agent [agent_name]'
        }
    }

    return $result
}

function Get-AutoGeneratedHeader {
    <#
    .SYNOPSIS
        Returns the auto-generated header comment.
    #>
    return @"
<!-- AUTO-GENERATED FILE - DO NOT EDIT DIRECTLY
     Generated from: templates/agents/{0}.shared.md
     To modify this file, edit the source and run: pwsh build/Generate-Agents.ps1
-->
"@
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
    Write-Warning "No shared source files found in $agentsPath"
    exit 0
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

        # Transform body (handoff syntax)
        $handoffSyntax = $platform['handoffSyntax']
        $transformedBody = Convert-HandoffSyntax -Body $body -TargetSyntax $handoffSyntax

        # Build output content with CRLF line endings (matching existing files)
        $header = Get-AutoGeneratedHeader -f $agentName
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
