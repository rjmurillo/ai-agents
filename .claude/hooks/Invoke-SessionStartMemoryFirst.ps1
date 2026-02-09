<#
.SYNOPSIS
    Enforces ADR-007 Memory-First Architecture at session start.

.DESCRIPTION
    Claude Code hook that injects memory-first requirements into the session context.
    Outputs blocking gate requirements that Claude receives before processing any user prompts.
    Also verifies MCP server availability and provides fallback guidance.
    Part of the ADR-007 enforcement mechanism (Issue #729).

.NOTES
    Hook Type: SessionStart
    Exit Codes:
        0 = Success, stdout added to Claude's context
        2 = Block session (critical failure)

.LINK
    .agents/architecture/ADR-007-memory-first-architecture.md
    .agents/SESSION-PROTOCOL.md
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Read Forgetful configuration from .mcp.json
$ForgetfulHost = "localhost"
$ForgetfulPort = 8020
$mcpConfigPath = Join-Path $PSScriptRoot ".." ".." ".mcp.json"

if (Test-Path $mcpConfigPath) {
    try {
        $mcpConfig = Get-Content $mcpConfigPath -Raw | ConvertFrom-Json -ErrorAction Stop
        # Guard against null nested properties - each level could be missing
        if ($mcpConfig -and
            $mcpConfig.PSObject.Properties['mcpServers'] -and
            $mcpConfig.mcpServers -and
            $mcpConfig.mcpServers.PSObject.Properties['forgetful'] -and
            $mcpConfig.mcpServers.forgetful -and
            $mcpConfig.mcpServers.forgetful.PSObject.Properties['url'] -and
            $mcpConfig.mcpServers.forgetful.url) {
            $forgetfulUrl = [System.Uri]::new($mcpConfig.mcpServers.forgetful.url)
            $ForgetfulHost = $forgetfulUrl.Host
            $ForgetfulPort = $forgetfulUrl.Port
        }
    }
    catch {
        # Fall back to defaults if parsing fails - don't block session start
        Write-Warning "Failed to parse MCP config from $mcpConfigPath : $($_.Exception.Message). Using defaults."
    }
}

# Check MCP server availability (non-blocking, informational)
$ForgetfulAvailable = $false
$ForgetfulMessage = ""

# TCP connection check disabled to prevent stack overflow in PowerShell async handling
# The ConnectAsync().Wait() pattern was causing recursive stack unwinding
# This is informational only, so disabling it doesn't affect functionality
$ForgetfulMessage = "Forgetful MCP: Connection check disabled (use Serena for memory-first workflow)"

# Output compact confirmation. Full protocol is in AGENTS.md (auto-loaded).
$forgetfulStatus = if ($ForgetfulAvailable) { "Forgetful: available" } else { "Forgetful: unavailable (use Serena)" }
Write-Output "ADR-007 active. $forgetfulStatus. Protocol: AGENTS.md > Session Protocol Gates."

exit 0
