<#
.SYNOPSIS
    Synchronizes MCP configuration from Claude's .mcp.json to VS Code's .vscode/mcp.json format.

.DESCRIPTION
    Transforms Claude Code's .mcp.json (using "mcpServers" root key) to VS Code's
    mcp.json format (using "servers" root key). The script treats .mcp.json as the
    source of truth and generates .vscode/mcp.json for VS Code compatibility.

    Format differences:
    - Claude (.mcp.json):  { "mcpServers": { ... } }
    - VS Code (.vscode/mcp.json):  { "servers": { ... } }

    Server-specific transformations:
    - serena: Changes --context "claude-code" to "ide" and --port "24282" to "24283"
      for VS Code/IDE compatibility.

    Note: These are the only two supported configurations. GitHub Copilot CLI uses
    a different file (~/.copilot/mcp-config.json) in the user's home directory,
    which is not managed by this script.

.PARAMETER SourcePath
    Path to the Claude .mcp.json file. Defaults to .mcp.json in repository root.

.PARAMETER DestinationPath
    Path to the VS Code mcp.json file. Defaults to .vscode/mcp.json in repository root.

.PARAMETER Force
    Overwrite destination even if content would be identical.

.PARAMETER WhatIf
    Show what would be changed without making changes.

.PARAMETER PassThru
    Return a boolean indicating whether files were synced.

.EXAMPLE
    .\Sync-McpConfig.ps1
    # Syncs .mcp.json to .vscode/mcp.json in current repository

.EXAMPLE
    .\Sync-McpConfig.ps1 -WhatIf
    # Shows what would be changed without making changes

.EXAMPLE
    .\Sync-McpConfig.ps1 -SourcePath "C:\MyRepo\.mcp.json" -DestinationPath "C:\MyRepo\.vscode\mcp.json"
    # Syncs specific files

.LINK
    https://code.visualstudio.com/docs/copilot/customization/mcp-servers
    https://docs.anthropic.com/claude-code/docs/mcp

.NOTES
    Author: AI Agents Project
    Part of the ai-agents repository tooling.
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter()]
    [string]$SourcePath,

    [Parameter()]
    [string]$DestinationPath,

    [Parameter()]
    [switch]$Force,

    [Parameter()]
    [switch]$PassThru
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Resolve paths relative to script location or current directory
function Get-RepoRoot {
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
    $vscodePath = Join-Path $repoRoot '.vscode'
    $DestinationPath = Join-Path $vscodePath 'mcp.json'
}

# Validate source exists
if (-not (Test-Path $SourcePath)) {
    Write-Error "Source file not found: $SourcePath"
    exit 1
}

# Security: Reject symlinks (MEDIUM-002 from pre-commit patterns)
if ((Get-Item $SourcePath).LinkType) {
    Write-Error "Security: Source path is a symlink, which is not allowed: $SourcePath"
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

# Transform: mcpServers -> servers
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
if (Test-Path $DestinationPath) {
    # Security: Reject symlinks
    if ((Get-Item $DestinationPath).LinkType) {
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
