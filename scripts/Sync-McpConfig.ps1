<#
.SYNOPSIS
    Synchronizes MCP configuration from Claude's .mcp.json to VS Code and Factory formats.

.DESCRIPTION
    Transforms Claude Code's .mcp.json (using "mcpServers" root key) to Factory's
    .factory/mcp.json and VS Code's .vscode/mcp.json formats. The script treats
    .mcp.json as the source of truth and generates configuration files for both
    Factory Droid and VS Code compatibility.

    Format differences:
    - Claude (.mcp.json):     { "mcpServers": { ... } }
    - Factory (.factory/mcp.json): { "mcpServers": { ... } }
    - VS Code (.vscode/mcp.json):  { "servers": { ... } }

    Server-specific transformations:
    - serena: Changes --context "claude-code" to "ide" and --port "24282" to "24283"
      for VS Code/IDE compatibility.

    Note: GitHub Copilot CLI uses a different file (~/.copilot/mcp-config.json)
    in the user's home directory, which is not managed by this script.

.PARAMETER SourcePath
    Path to the Claude .mcp.json file. Defaults to .mcp.json in repository root.

.PARAMETER DestinationPath
    Path to the destination mcp.json file (Factory or VS Code). Defaults to
    .vscode/mcp.json in repository root when Target is 'vscode', or .factory/mcp.json
    when Target is 'factory'.

.PARAMETER Target
    Target platform: 'factory' or 'vscode' (default 'vscode').
    - factory: Generates .factory/mcp.json (same format as .mcp.json)
    - vscode: Generates .vscode/mcp.json (transformed format)

.PARAMETER SyncAll
    Syncs to both Factory and VS Code configurations. Cannot be used with
    DestinationPath parameter.

.PARAMETER Force
    Overwrite destination even if content would be identical.

.PARAMETER WhatIf
    Show what would be changed without making changes.

.PARAMETER PassThru
    Return a boolean indicating whether files were synced.

.EXAMPLE
    .\Sync-McpConfig.ps1
    # Syncs .mcp.json to .vscode/mcp.json in current repository (default)

.EXAMPLE
    .\Sync-McpConfig.ps1 -Target vscode
    # Syncs .mcp.json to .vscode/mcp.json

.EXAMPLE
    .\Sync-McpConfig.ps1 -SyncAll
    # Syncs .mcp.json to both .factory/mcp.json and .vscode/mcp.json

.EXAMPLE
    .\Sync-McpConfig.ps1 -WhatIf
    # Shows what would be changed without making changes

.LINK
    https://docs.factory.ai/cli/configuration/mcp
    https://code.visualstudio.com/docs/copilot/customization/mcp-servers
    https://docs.anthropic.com/claude-code/docs/mcp

.NOTES
    Author: AI Agents Project
    Part of the ai-agents repository tooling.

    EXIT CODES:
    0  - Success: Configuration synced successfully
    1  - Error: File not found, invalid JSON, transformation failure, or write error

    See: ADR-035 Exit Code Standardization
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter()]
    [string]$SourcePath,

    [Parameter()]
    [string]$DestinationPath,

    [Parameter()]
    [ValidateSet('factory', 'vscode')]
    [string]$Target = 'vscode',

    [Parameter()]
    [switch]$SyncAll,

    [Parameter()]
    [switch]$Force,

    [Parameter()]
    [switch]$PassThru,

    [Parameter(DontShow)]
    [string]$RepoRootOverride
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Validate parameter combinations
if ($SyncAll -and $DestinationPath) {
    Write-Error "Cannot use SyncAll with DestinationPath parameter. They are mutually exclusive."
    exit 1
}

# Validate SyncAll vs Target (Target is meaningless when SyncAll is True)
if ($SyncAll -and $PSBoundParameters.ContainsKey('Target')) {
    Write-Error "Cannot use SyncAll with Target parameter. SyncAll generates both Factory and VS Code configs, so Target is ignored."
    exit 1
}

# Resolve paths relative to script location or current directory
function Get-RepoRoot {
    if ($RepoRootOverride) {
        return $RepoRootOverride
    }

    $gitRoot = git rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -eq 0 -and $gitRoot) {
        return $gitRoot
    }
    return $PWD.Path
}

$repoRoot = Get-RepoRoot

if (-not $SourcePath) {
    $SourcePath = Join-Path $repoRoot '.mcp.json'
}

if (-not $DestinationPath) {
    if ($Target -eq 'vscode') {
        $vscodePath = Join-Path $repoRoot '.vscode'
        $DestinationPath = Join-Path $vscodePath 'mcp.json'
    }
    else { # factory
        $factoryPath = Join-Path $repoRoot '.factory'
        $DestinationPath = Join-Path $factoryPath 'mcp.json'
    }
}

# Validate source exists and reject symlinks (MEDIUM-002)
# Use Get-Item with -Force to handle symlinks and hidden files
if (Test-Path -LiteralPath $SourcePath) {
    $sourceItem = Get-Item -LiteralPath $SourcePath -Force
    if ($sourceItem.LinkType) {
        Write-Error "Security: Source path is a symlink, which is not allowed: $SourcePath"
        exit 1
    }
} else {
    Write-Error "Source file not found: $SourcePath"
    exit 1
}

# Read and parse source
try {
    $sourceContent = Get-Content -Path $SourcePath -Raw -Encoding UTF8
    $sourceJson = $sourceContent | ConvertFrom-Json -AsHashtable
}
catch {
    Write-Error "Failed to parse source JSON from $SourcePath : $_"
    exit 1
}

# Validate source has expected structure
if (-not $sourceJson.ContainsKey('mcpServers')) {
    Write-Error "Source file does not contain 'mcpServers' key. Expected Claude .mcp.json format."
    exit 1
}

# Determine transform based on target
if ($Target -eq 'vscode') {
    # VS Code transform: mcpServers -> servers
    $servers = $sourceJson['mcpServers'].Clone()

    # Transform serena configuration for VS Code compatibility
    # Claude Code uses: --context claude-code --port 24282
    # VS Code uses:     --context ide --port 24283
    if ($servers.ContainsKey('serena') -and $servers['serena'].ContainsKey('args')) {
        # Deep clone the serena config to avoid modifying source
        $serenaConfig = @{}
        foreach ($key in $servers['serena'].Keys) {
            if ($key -eq 'args') {
                $serenaConfig[$key] = @($servers['serena']['args'])
            } else {
                $serenaConfig[$key] = $servers['serena'][$key]
            }
        }

        # Transform args: replace claude-code -> ide and 24282 -> 24283
        $serenaConfig['args'] = $serenaConfig['args'] | ForEach-Object {
            $_ -replace '^claude-code$', 'ide' -replace '^24282$', '24283'
        }

        $servers['serena'] = $serenaConfig
    }

    $destJson = [ordered]@{
        servers = $servers
    }
}
else { # factory
    # Factory uses same format as Claude: mcpServers
    # Deep clone to avoid modifying source
    $destJson = [ordered]@{
        mcpServers = $sourceJson['mcpServers'].Clone()
    }
}

# Preserve any additional top-level keys (like 'inputs' if present)
foreach ($key in $sourceJson.Keys) {
    if ($key -ne 'mcpServers' -and -not $destJson.Contains($key)) {
        $destJson[$key] = $sourceJson[$key]
    }
}

# Convert to JSON with proper formatting
$destContent = $destJson | ConvertTo-Json -Depth 10

# Normalize line endings to LF for cross-platform consistency
$destContent = $destContent -replace "`r`n", "`n"
# Ensure trailing newline
if (-not $destContent.EndsWith("`n")) {
    $destContent += "`n"
}

# Check if destination needs updating
$needsUpdate = $true
if (Test-Path -LiteralPath $DestinationPath) {
    # Security: Reject symlinks
    # Use Get-Item with -Force to handle symlinks and hidden files
    $destItem = Get-Item -LiteralPath $DestinationPath -Force
    if ($destItem.LinkType) {
        Write-Error "Security: Destination path is a symlink, which is not allowed: $DestinationPath"
        exit 1
    }

    $existingContent = Get-Content -Path $DestinationPath -Raw -Encoding UTF8
    # Normalize for comparison
    $existingNormalized = $existingContent -replace "`r`n", "`n"

    if ($existingNormalized -eq $destContent) {
        $needsUpdate = $false
        if (-not $Force) {
            Write-Host "MCP config already in sync: $DestinationPath" -ForegroundColor Green
            if ($PassThru) { return $false }
            return
        }
    }
}

# Write destination
if (-not $SyncAll) {
    if ($needsUpdate -or $Force) {
        if ($PSCmdlet.ShouldProcess($DestinationPath, "Sync MCP configuration from $SourcePath")) {
            # Ensure destination directory exists (for .vscode/mcp.json)
            $destDir = Split-Path -Parent $DestinationPath
            if ($destDir -and -not (Test-Path $destDir)) {
                New-Item -ItemType Directory -Path $destDir -Force | Out-Null
                Write-Verbose "Created directory: $destDir"
            }

            # Write with UTF8 no BOM for cross-platform compatibility
            [System.IO.File]::WriteAllText($DestinationPath, $destContent, [System.Text.UTF8Encoding]::new($false))
            Write-Host "Synced MCP config: $SourcePath -> $DestinationPath" -ForegroundColor Green
            if ($PassThru) { return $true }
        } else {
            # WhatIf: return false when PassThru is specified
            if ($PassThru) { return $false }
        }
    }
    else {
        # No sync needed (already in sync and not forcing)
        if ($PassThru) { return $false }
    }
}

# Handle SyncAll: sync to both Factory and VS Code
if ($SyncAll) {
    $anySynced = $false

    # Build parameters for recursive call
    $recursiveParams = @{
        SourcePath = $SourcePath
        Force = $Force
        PassThru = $PassThru
    }
    if ($PSBoundParameters.ContainsKey('WhatIf')) {
        $recursiveParams.WhatIf = $true
    }
    if ($PSBoundParameters.ContainsKey('RepoRootOverride')) {
        $recursiveParams.RepoRootOverride = $RepoRootOverride
    }

    # Sync to Factory
    $factoryPath = Join-Path $repoRoot '.factory'
    $factoryDestPath = Join-Path $factoryPath 'mcp.json'
    $recParams = $recursiveParams.Clone()
    $recParams.DestinationPath = $factoryDestPath
    $recParams.Target = 'factory'
    $result = & $PSCommandPath @recParams
    if ($result -eq $true) {
        $anySynced = $true
    }

    # Sync to VS Code
    $vscodePath = Join-Path $repoRoot '.vscode'
    $vscodeDestPath = Join-Path $vscodePath 'mcp.json'
    $recParams = $recursiveParams.Clone()
    $recParams.DestinationPath = $vscodeDestPath
    $recParams.Target = 'vscode'
    $result = & $PSCommandPath @recParams
    if ($result -eq $true) {
        $anySynced = $true
    }

    if ($PassThru) { return $anySynced }
}
