<#
.SYNOPSIS
    Installs Forgetful MCP server as a systemd user service on Linux.

.DESCRIPTION
    Creates and enables a systemd user service that runs Forgetful MCP server
    using HTTP transport on port 8020. This avoids the stdio transport bug
    (FastMCP banner corruption, upstream issue #19).

.PARAMETER Port
    Port for the HTTP server. Default: 8020

.PARAMETER Force
    Overwrite existing service file if present.

.EXAMPLE
    ./Install-ForgetfulLinux.ps1

.EXAMPLE
    ./Install-ForgetfulLinux.ps1 -Port 8025 -Force

.NOTES
    Requires: uv/uvx installed, systemd with user services enabled
    Related: ADR-007 Memory-First Architecture
#>
[CmdletBinding()]
param(
    [int]$Port = 8020,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Verify we're on Linux
if (-not $IsLinux) {
    Write-Error "This script is for Linux only. Use Install-ForgetfulWindows.ps1 on Windows."
    exit 1
}

# Check prerequisites
Write-Host "Checking prerequisites..." -ForegroundColor Cyan

# Check for uvx
$UvxPath = Get-Command uvx -ErrorAction SilentlyContinue
if (-not $UvxPath) {
    # Try common locations
    $CommonPaths = @(
        "$env:HOME/.local/bin/uvx",
        "$env:HOME/.cargo/bin/uvx",
        "/usr/local/bin/uvx"
    )
    foreach ($Path in $CommonPaths) {
        if (Test-Path $Path) {
            $UvxPath = $Path
            break
        }
    }
}

if (-not $UvxPath) {
    Write-Error @"
uvx not found. Install uv first:

    curl -LsSf https://astral.sh/uv/install.sh | sh

Then add to PATH:

    export PATH="`$HOME/.local/bin:`$PATH"
"@
    exit 1
}

$UvxFullPath = if ($UvxPath -is [System.Management.Automation.ApplicationInfo]) {
    $UvxPath.Source
} else {
    $UvxPath
}
Write-Host "  uvx found: $UvxFullPath" -ForegroundColor Green

# Check if port is available
$PortCheck = & bash -c "ss -tlnp 2>/dev/null | grep -q ':$Port ' && echo 'in-use' || echo 'available'"
if ($PortCheck -eq 'in-use') {
    Write-Warning "Port $Port is already in use. Check if Forgetful is already running:"
    Write-Host "  systemctl --user status forgetful"
    Write-Host "  lsof -i :$Port"
    if (-not $Force) {
        exit 1
    }
}

# Create systemd user directory
$SystemdUserDir = "$env:HOME/.config/systemd/user"
if (-not (Test-Path $SystemdUserDir)) {
    New-Item -ItemType Directory -Path $SystemdUserDir -Force | Out-Null
    Write-Host "  Created: $SystemdUserDir" -ForegroundColor Green
}

# Service file path
$ServiceFile = Join-Path $SystemdUserDir "forgetful.service"

# Check for existing service
if ((Test-Path $ServiceFile) -and -not $Force) {
    Write-Error "Service file already exists: $ServiceFile. Use -Force to overwrite."
    exit 1
}

# Create service file
Write-Host "Creating systemd service..." -ForegroundColor Cyan

$ServiceContent = @"
[Unit]
Description=Forgetful MCP Server
After=network.target

[Service]
ExecStart=$UvxFullPath forgetful-ai --transport http --port $Port
Restart=always
RestartSec=5
Environment="PATH=$env:HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

[Install]
WantedBy=default.target
"@

$ServiceContent | Out-File -FilePath $ServiceFile -Encoding utf8 -Force
Write-Host "  Created: $ServiceFile" -ForegroundColor Green

# Reload systemd
Write-Host "Configuring systemd..." -ForegroundColor Cyan
& systemctl --user daemon-reload
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to reload systemd daemon (exit code $LASTEXITCODE)"
    exit 1
}
Write-Host "  Reloaded systemd user daemon" -ForegroundColor Green

# Enable service
& systemctl --user enable forgetful 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to enable forgetful service (exit code $LASTEXITCODE)"
    exit 1
}
Write-Host "  Enabled forgetful service" -ForegroundColor Green

# Start service
& systemctl --user start forgetful
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to start forgetful service. Check: journalctl --user -u forgetful"
    exit 1
}
Write-Host "  Started forgetful service" -ForegroundColor Green

# Wait for startup
Start-Sleep -Seconds 2

# Verify
Write-Host "`nVerifying installation..." -ForegroundColor Cyan
$Status = & systemctl --user is-active forgetful 2>&1
if ($Status -eq 'active') {
    Write-Host "  Service is running" -ForegroundColor Green

    # Test HTTP endpoint
    try {
        $Response = Invoke-RestMethod -Uri "http://localhost:$Port/mcp" -Method Post -ContentType "application/json" -Body '{"jsonrpc":"2.0","method":"tools/list","id":1}' -TimeoutSec 5
        Write-Host "  HTTP endpoint responding" -ForegroundColor Green
    }
    catch {
        Write-Warning "HTTP endpoint not responding yet. May need a few more seconds to initialize."
    }
}
else {
    Write-Error "Service failed to start. Check logs: journalctl --user -u forgetful -f"
    exit 1
}

Write-Host "`n" -NoNewline
Write-Host "Installation complete!" -ForegroundColor Green
Write-Host @"

Forgetful MCP server is now running on http://localhost:$Port/mcp

Useful commands:
  Status:   systemctl --user status forgetful
  Logs:     journalctl --user -u forgetful -f
  Restart:  systemctl --user restart forgetful
  Stop:     systemctl --user stop forgetful

Next steps:
  1. Verify .mcp.json has: {"forgetful": {"type": "http", "url": "http://localhost:$Port/mcp"}}
  2. Verify .claude/settings.json has: {"enabledPlugins": {"forgetful@scottrbk": true}}
  3. Test with: pwsh scripts/forgetful/Test-ForgetfulHealth.ps1
"@
