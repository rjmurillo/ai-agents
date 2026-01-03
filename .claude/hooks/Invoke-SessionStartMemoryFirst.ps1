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
    }
}

# Check MCP server availability (non-blocking, informational)
$ForgetfulAvailable = $false
$ForgetfulMessage = ""

try {
    # Simple TCP port check - MCP protocol requires session initialization which is complex
    # Just verify the server is listening on the port
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $connectTask = $tcpClient.ConnectAsync($ForgetfulHost, $ForgetfulPort)
    $connected = $connectTask.Wait(1000)  # 1 second timeout

    if ($connected -and $tcpClient.Connected) {
        $ForgetfulAvailable = $true
        $ForgetfulMessage = "Forgetful MCP: AVAILABLE ($ForgetfulHost`:$ForgetfulPort)"
    }
    else {
        $ForgetfulMessage = "Forgetful MCP: UNAVAILABLE (Serena-only workflow) - connection timeout"
    }
}
catch {
    # Log exception details for debugging - don't silently swallow errors
    $exceptionMessage = $_.Exception.Message
    $ForgetfulMessage = "Forgetful MCP: UNAVAILABLE (Serena-only workflow) - $exceptionMessage"
}
finally {
    if ($null -ne $tcpClient) {
        $tcpClient.Dispose()
    }
}

# Output context that will be injected into Claude's context window

$output = @"

## ADR-007 Memory-First Enforcement (Session Start)

**BLOCKING GATE**: Complete these steps BEFORE any reasoning or implementation:

### MCP Server Status

$ForgetfulMessage
"@

if (-not $ForgetfulAvailable) {
    $output += @"

> **Fallback Mode**: Forgetful is unavailable. Use Serena memory-index for keyword-based discovery.
> To start Forgetful: ``pwsh scripts/forgetful/Install-ForgetfulLinux.ps1`` (Linux) or ``pwsh scripts/forgetful/Install-ForgetfulWindows.ps1`` (Windows)

"@
}

$output += @"

### Phase 1: Serena Initialization (REQUIRED)

1. ``mcp__serena__activate_project`` - Activate project memory
2. ``mcp__serena__initial_instructions`` - Load Serena guidance

### Phase 2: Context Retrieval (REQUIRED)

1. Read ``.agents/HANDOFF.md`` - Previous session context
2. Read ``memory-index`` from Serena - Identify relevant memories
3. Read task-relevant memories - Apply learned patterns
"@

if ($ForgetfulAvailable) {
    $output += @"

4. (Optional) Query Forgetful for semantic search - Augment with cross-project patterns

"@
}

$output += @"

### Verification

Session logs MUST evidence memory retrieval BEFORE decisions.
Pre-commit validation will fail without proper evidence.

**Protocol**: ``.agents/SESSION-PROTOCOL.md``
**Architecture**: ``.agents/architecture/ADR-007-memory-first-architecture.md``

"@

Write-Output $output

exit 0
