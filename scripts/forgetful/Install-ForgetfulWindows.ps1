<#
.SYNOPSIS
    Installs Forgetful MCP server as a scheduled task on Windows.

.DESCRIPTION
    Creates a scheduled task that runs Forgetful MCP server at user login
    using HTTP transport on port 8020. This avoids the stdio transport bug
    (FastMCP banner corruption, upstream issue #19).

.PARAMETER Port
    Port for the HTTP server. Default: 8020

.PARAMETER Force
    Overwrite existing scheduled task if present.

.PARAMETER StartNow
    Start the server immediately after installation. Default: $true

.EXAMPLE
    ./Install-ForgetfulWindows.ps1

.EXAMPLE
    ./Install-ForgetfulWindows.ps1 -Port 8025 -Force

.NOTES
    Requires: uv/uvx installed, Windows 10/11 or Windows Server 2016+
    Related: ADR-007 Memory-First Architecture
#>
[CmdletBinding()]
param(
    [int]$Port = 8020,
    [switch]$Force,
    [switch]$StartNow = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Verify we're on Windows
if (-not $IsWindows -and $env:OS -ne 'Windows_NT') {
    Write-Error "This script is for Windows only. Use Install-ForgetfulLinux.ps1 on Linux."
    exit 1
}

$TaskName = "ForgetfulMCP"

# Check prerequisites
Write-Host "Checking prerequisites..." -ForegroundColor Cyan

# Check for uvx
$UvxPath = Get-Command uvx -ErrorAction SilentlyContinue
if (-not $UvxPath) {
    # Try common locations
    $CommonPaths = @(
        "$env:USERPROFILE\.local\bin\uvx.exe",
        "$env:USERPROFILE\.cargo\bin\uvx.exe",
        "$env:LOCALAPPDATA\Programs\uv\uvx.exe"
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

    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

Then restart your terminal or add to PATH:

    `$env:PATH = "`$env:USERPROFILE\.local\bin;`$env:PATH"
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
$PortInUse = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($PortInUse) {
    Write-Warning "Port $Port is already in use. Check if Forgetful is already running:"
    Write-Host "  Get-ScheduledTask -TaskName '$TaskName'"
    Write-Host "  netstat -ano | findstr :$Port"
    if (-not $Force) {
        exit 1
    }
}

# Check for existing task
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($ExistingTask -and -not $Force) {
    Write-Error "Scheduled task already exists: $TaskName. Use -Force to overwrite."
    exit 1
}

if ($ExistingTask) {
    Write-Host "Removing existing scheduled task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create scheduled task
Write-Host "Creating scheduled task..." -ForegroundColor Cyan

# Action: Run uvx forgetful-ai with HTTP transport
$Action = New-ScheduledTaskAction -Execute $UvxFullPath -Argument "forgetful-ai --transport http --port $Port"

# Trigger: At logon
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Settings
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

# Principal: Run as current user, no elevation needed
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

# Register the task
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Forgetful MCP Server - Semantic memory for AI agents (HTTP transport on port $Port)" | Out-Null

Write-Host "  Created scheduled task: $TaskName" -ForegroundColor Green

# Start now if requested
if ($StartNow) {
    Write-Host "Starting Forgetful server..." -ForegroundColor Cyan
    Start-ScheduledTask -TaskName $TaskName

    # Wait for startup
    Start-Sleep -Seconds 3

    # Verify
    $TaskInfo = Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo
    if ($TaskInfo.LastTaskResult -eq 0 -or $TaskInfo.LastTaskResult -eq 267009) {
        # 267009 = task is currently running
        Write-Host "  Task started successfully" -ForegroundColor Green

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
        Write-Warning "Task may not have started correctly. Last result: $($TaskInfo.LastTaskResult)"
    }
}

Write-Host "`n" -NoNewline
Write-Host "Installation complete!" -ForegroundColor Green
Write-Host @"

Forgetful MCP server is configured to run on http://localhost:$Port/mcp

Useful commands:
  Status:   Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo
  Start:    Start-ScheduledTask -TaskName '$TaskName'
  Stop:     Stop-ScheduledTask -TaskName '$TaskName'
  Remove:   Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false

Next steps:
  1. Verify .mcp.json has: {"forgetful": {"type": "http", "url": "http://localhost:$Port/mcp"}}
  2. Verify .claude/settings.json has: {"enabledPlugins": {"forgetful@scottrbk": true}}
  3. Test with: pwsh scripts/forgetful/Test-ForgetfulHealth.ps1
"@

# Create a helper script for manual start (useful if task scheduling is blocked)
$ManualStartScript = @"
# Manual start script for Forgetful MCP Server
# Use this if scheduled task is blocked by policy

`$UvxPath = "$UvxFullPath"
`$Port = $Port

Write-Host "Starting Forgetful MCP server on port `$Port..."
& `$UvxPath forgetful-ai --transport http --port `$Port
"@

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ManualStartPath = Join-Path $ScriptDir "Start-ForgetfulManual.ps1"
$ManualStartScript | Out-File -FilePath $ManualStartPath -Encoding utf8 -Force
Write-Host "`nAlso created: $ManualStartPath (for manual start if needed)"
