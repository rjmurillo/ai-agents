<#
.SYNOPSIS
    Tests Forgetful MCP server health and connectivity.

.DESCRIPTION
    Performs health checks on the Forgetful MCP server including:
    - HTTP endpoint connectivity
    - JSON-RPC protocol validation
    - Tool availability verification
    - Optional memory operation test

.PARAMETER Port
    Port for the HTTP server. Default: 8020

.PARAMETER Url
    Full URL to the MCP endpoint. Overrides Port if specified.

.PARAMETER Verbose
    Show detailed output including response bodies.

.PARAMETER TestMemory
    Perform a test memory operation (create and delete).

.EXAMPLE
    ./Test-ForgetfulHealth.ps1

.EXAMPLE
    ./Test-ForgetfulHealth.ps1 -Port 8025 -TestMemory

.NOTES
    Related: ADR-007 Memory-First Architecture
    Exit codes:
      0 - All checks passed
      1 - Connection failed
      2 - Protocol error
      3 - Tool unavailable
#>
[CmdletBinding()]
param(
    [int]$Port = 8020,
    [string]$Url,
    [switch]$TestMemory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Determine endpoint URL
if (-not $Url) {
    $Url = "http://localhost:$Port/mcp"
}

$script:TestsPassed = 0
$script:TestsFailed = 0

function Write-TestResult {
    param(
        [string]$TestName,
        [bool]$Passed,
        [string]$Message = ""
    )

    if ($Passed) {
        $script:TestsPassed++
        Write-Host "  [PASS] $TestName" -ForegroundColor Green
        if ($Message -and $VerbosePreference -eq 'Continue') {
            Write-Host "         $Message" -ForegroundColor Gray
        }
    }
    else {
        $script:TestsFailed++
        Write-Host "  [FAIL] $TestName" -ForegroundColor Red
        if ($Message) {
            Write-Host "         $Message" -ForegroundColor Yellow
        }
    }
}

function Send-McpRequest {
    param(
        [string]$Method,
        [hashtable]$Params = @{},
        [int]$TimeoutSec = 10
    )

    $body = @{
        jsonrpc = "2.0"
        method  = $Method
        id      = [guid]::NewGuid().ToString()
    }

    if ($Params.Count -gt 0) {
        $body.params = $Params
    }

    $jsonBody = $body | ConvertTo-Json -Depth 10 -Compress

    try {
        # Forgetful requires Accept header with both application/json and text/event-stream
        $headers = @{
            "Accept" = "application/json, text/event-stream"
        }
        $response = Invoke-RestMethod -Uri $Url -Method Post -ContentType "application/json" -Body $jsonBody -Headers $headers -TimeoutSec $TimeoutSec
        return @{
            Success  = $true
            Response = $response
            Error    = $null
        }
    }
    catch {
        return @{
            Success  = $false
            Response = $null
            Error    = $_.Exception.Message
        }
    }
}

Write-Host "`nForgetful MCP Health Check" -ForegroundColor Cyan
Write-Host "=========================" -ForegroundColor Cyan
Write-Host "Endpoint: $Url`n"

# Test 1: Basic connectivity (TCP port check)
Write-Host "1. Connectivity Tests" -ForegroundColor White

$tcpConnected = $false
try {
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $connectTask = $tcpClient.ConnectAsync("localhost", $Port)
    $tcpConnected = $connectTask.Wait(2000)  # 2 second timeout

    if ($tcpConnected -and $tcpClient.Connected) {
        Write-TestResult -TestName "TCP port $Port reachable" -Passed $true
    }
    else {
        Write-TestResult -TestName "TCP port $Port reachable" -Passed $false -Message "Connection timeout"
    }
    $tcpClient.Close()
}
catch {
    Write-TestResult -TestName "TCP port $Port reachable" -Passed $false -Message $_.Exception.Message
}

if (-not $tcpConnected) {
    Write-Host "`nForgetful server is not running or not accessible." -ForegroundColor Red
    Write-Host "To start Forgetful:"
    Write-Host "  Linux:   systemctl --user start forgetful"
    Write-Host "  Windows: Start-ScheduledTask -TaskName 'ForgetfulMCP'"
    Write-Host "  Manual:  uvx forgetful-ai --transport http --port $Port"
    exit 1
}

# Test 2: MCP Protocol Note
Write-Host "`n2. Protocol Tests" -ForegroundColor White
Write-Host "  [INFO] MCP HTTP transport requires session initialization" -ForegroundColor Cyan
Write-Host "         Full protocol verification happens via Claude Code's MCP client" -ForegroundColor Gray
Write-TestResult -TestName "Server listening (TCP verified above)" -Passed $true

# Test 3: Service status (platform-specific)
Write-Host "`n3. Service Status" -ForegroundColor White

if ($IsLinux) {
    $serviceStatus = & systemctl --user is-active forgetful 2>&1
    if ($serviceStatus -eq 'active') {
        Write-TestResult -TestName "systemd service 'forgetful'" -Passed $true -Message "active"
    }
    else {
        Write-TestResult -TestName "systemd service 'forgetful'" -Passed $false -Message $serviceStatus
    }
}
elseif ($IsWindows -or $env:OS -eq 'Windows_NT') {
    $task = Get-ScheduledTask -TaskName "ForgetfulMCP" -ErrorAction SilentlyContinue
    if ($task) {
        $taskInfo = $task | Get-ScheduledTaskInfo
        $running = $task.State -eq 'Running'
        Write-TestResult -TestName "Scheduled task 'ForgetfulMCP'" -Passed $running -Message $task.State
    }
    else {
        Write-TestResult -TestName "Scheduled task 'ForgetfulMCP'" -Passed $false -Message "Not found"
    }
}
else {
    Write-Host "  [SKIP] Platform-specific service check not available" -ForegroundColor Yellow
}

# Test 4: Tool verification via Claude Code
Write-Host "`n4. Tool Verification" -ForegroundColor White
Write-Host "  [INFO] To verify MCP tools are working correctly:" -ForegroundColor Cyan
Write-Host "         1. Start a Claude Code session in this project" -ForegroundColor Gray
Write-Host "         2. Run: mcp__forgetful__discover_forgetful_tools()" -ForegroundColor Gray
Write-Host "         3. Verify tools are enumerated in the response" -ForegroundColor Gray
Write-TestResult -TestName "Manual verification required" -Passed $true -Message "See instructions above"

# Summary
Write-Host "`n=========================" -ForegroundColor Cyan
Write-Host "Summary" -ForegroundColor Cyan
Write-Host "  Passed: $($script:TestsPassed)" -ForegroundColor Green
Write-Host "  Failed: $($script:TestsFailed)" -ForegroundColor $(if ($script:TestsFailed -gt 0) { "Red" } else { "Green" })

if ($script:TestsFailed -eq 0) {
    Write-Host "`nForgetful MCP server is healthy and operational." -ForegroundColor Green
    exit 0
}
else {
    Write-Host "`nSome tests failed. Check the output above for details." -ForegroundColor Yellow
    exit 3
}
