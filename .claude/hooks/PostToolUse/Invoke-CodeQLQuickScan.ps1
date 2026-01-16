<#
.SYNOPSIS
    Auto-runs CodeQL quick scan after Python/workflow file writes.

.DESCRIPTION
    Claude Code PostToolUse hook that automatically triggers targeted CodeQL security
    scans after Write operations on Python files (*.py) or GitHub Actions workflows
    (*.yml in .github/workflows/).

    Uses a quick scan configuration with only 5-10 critical CWEs (command injection,
    SQL injection, XSS, path traversal, hardcoded credentials) to meet a 30-second
    performance budget. Gracefully degrades if CodeQL CLI is not installed.

    Part of the CodeQL multi-tier security strategy (Tier 3: PostToolUse Hook).

.NOTES
    Hook Type: PostToolUse
    Matcher: Write
    Filter: *.py files, *.yml in .github/workflows/
    Performance Budget: 30 seconds
    Exit Codes:
        0 = Always (non-blocking hook, all errors are warnings)

    Requirements:
        - CodeQL CLI installed at .codeql/cli/codeql (optional, graceful degradation)
        - Quick config at .github/codeql/codeql-config-quick.yml
        - Invoke-CodeQLScan.ps1 available

.LINK
    .agents/planning/CodeQL/plan.md
    .codeql/scripts/Invoke-CodeQLScan.ps1
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'  # Non-blocking hook

function Get-FilePathFromInput {
    param($HookInput)

    if ($HookInput.PSObject.Properties['tool_input'] -and
        $HookInput.tool_input.PSObject.Properties['file_path']) {
        return $HookInput.tool_input.file_path
    }
    return $null
}

function Get-ProjectDirectory {
    param($HookInput)

    if (-not [string]::IsNullOrWhiteSpace($env:CLAUDE_PROJECT_DIR)) {
        return $env:CLAUDE_PROJECT_DIR
    }
    return $HookInput.cwd
}

function Test-ShouldScanFile {
    <#
    .SYNOPSIS
        Determines if file should trigger CodeQL quick scan.
    .DESCRIPTION
        Returns true for:
        - Python files (*.py)
        - GitHub Actions workflows (*.yml in .github/workflows/)
    #>
    param([string]$FilePath)

    if ([string]::IsNullOrWhiteSpace($FilePath)) {
        return $false
    }

    if (-not (Test-Path $FilePath)) {
        Write-Verbose "File does not exist: $FilePath"
        return $false
    }

    # Check for Python files
    if ($FilePath.EndsWith('.py', [StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }

    # Check for GitHub Actions workflows
    if ($FilePath.EndsWith('.yml', [StringComparison]::OrdinalIgnoreCase) -or
        $FilePath.EndsWith('.yaml', [StringComparison]::OrdinalIgnoreCase)) {
        $normalizedPath = $FilePath -replace '\\', '/'
        if ($normalizedPath -match '\.github/workflows/') {
            return $true
        }
    }

    return $false
}

function Test-CodeQLInstalled {
    <#
    .SYNOPSIS
        Checks if CodeQL CLI is installed and accessible.
    #>
    param([string]$ProjectDir)

    # Check if in PATH
    $codeqlCmd = Get-Command codeql -ErrorAction SilentlyContinue
    if ($codeqlCmd) {
        return $true
    }

    # Check default installation path
    $defaultPath = Join-Path $ProjectDir ".codeql/cli/codeql"
    if ($IsWindows) {
        $defaultPath += ".exe"
    }

    return Test-Path $defaultPath
}

function Get-LanguageFromFile {
    <#
    .SYNOPSIS
        Determines CodeQL language from file extension.
    #>
    param([string]$FilePath)

    if ($FilePath.EndsWith('.py', [StringComparison]::OrdinalIgnoreCase)) {
        return 'python'
    }

    if ($FilePath.EndsWith('.yml', [StringComparison]::OrdinalIgnoreCase) -or
        $FilePath.EndsWith('.yaml', [StringComparison]::OrdinalIgnoreCase)) {
        return 'actions'
    }

    return $null
}

try {
    # Check if stdin is available
    if (-not [Console]::IsInputRedirected) {
        exit 0
    }

    $inputJson = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($inputJson)) {
        exit 0
    }

    $hookInput = $inputJson | ConvertFrom-Json -ErrorAction Stop
    $filePath = Get-FilePathFromInput -HookInput $hookInput

    # Filter: Only scan relevant file types
    if (-not (Test-ShouldScanFile -FilePath $filePath)) {
        exit 0
    }

    $projectDir = Get-ProjectDirectory -HookInput $hookInput

    # Graceful degradation: Check if CodeQL CLI is installed
    if (-not (Test-CodeQLInstalled -ProjectDir $projectDir)) {
        Write-Verbose "CodeQL CLI not installed, skipping quick scan"
        exit 0
    }

    $previousLocation = Get-Location

    try {
        if (-not [string]::IsNullOrWhiteSpace($projectDir)) {
            Set-Location $projectDir
        }

        # Detect language from file
        $language = Get-LanguageFromFile -FilePath $filePath
        if (-not $language) {
            Write-Verbose "Unable to determine language for $filePath"
            exit 0
        }

        # Build script path
        $scanScriptPath = Join-Path $projectDir ".codeql/scripts/Invoke-CodeQLScan.ps1"
        if (-not (Test-Path $scanScriptPath)) {
            Write-Verbose "Scan script not found at $scanScriptPath"
            exit 0
        }

        Write-Verbose "Starting CodeQL quick scan for $filePath (language: $language)"

        # Invoke quick scan with 30-second timeout
        $job = Start-Job -ScriptBlock {
            param($ScanScript, $ScanLanguage, $ProjectDirectory)
            & $ScanScript -Languages $ScanLanguage -QuickScan -UseCache -RepoPath $ProjectDirectory -Format console 2>&1
        } -ArgumentList $scanScriptPath, $language, $projectDir

        $completed = Wait-Job -Job $job -Timeout 30
        if ($null -eq $completed) {
            # Timeout occurred
            Stop-Job -Job $job -ErrorAction SilentlyContinue
            Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
            Write-Warning "CodeQL quick scan timed out after 30 seconds for $filePath"
            Write-Output "`n**CodeQL Quick Scan WARNING**: Scan timed out after 30s for ``$filePath``. Run full scan manually.`n"
        }
        else {
            # Get results
            $scanOutput = Receive-Job -Job $job
            Remove-Job -Job $job -Force -ErrorAction SilentlyContinue

            # Parse output for findings count
            $findingsCount = 0
            if ($scanOutput -match 'Found (\d+) findings') {
                $findingsCount = [int]$matches[1]
            }

            if ($findingsCount -gt 0) {
                Write-Output "`n**CodeQL Quick Scan**: Analyzed ``$filePath`` - **$findingsCount finding(s) detected**`n"
            }
            else {
                Write-Output "`n**CodeQL Quick Scan**: Analyzed ``$filePath`` - No findings`n"
            }
        }
    }
    finally {
        Set-Location $previousLocation
    }
}
catch [System.ArgumentException], [System.InvalidOperationException] {
    # JSON parsing failures from ConvertFrom-Json
    Write-Verbose "CodeQL quick scan: Failed to parse hook input JSON - $($_.Exception.Message)"
}
catch [System.IO.IOException], [System.UnauthorizedAccessException] {
    Write-Verbose "CodeQL quick scan: File system error for $filePath - $($_.Exception.Message)"
}
catch [System.TimeoutException] {
    Write-Warning "CodeQL quick scan: Timeout error - $($_.Exception.Message)"
    Write-Output "`n**CodeQL Quick Scan WARNING**: Scan operation timed out. Try manual scan.`n"
}
catch {
    Write-Verbose "CodeQL quick scan unexpected error: $($_.Exception.GetType().FullName) - $($_.Exception.Message)"
}

# Always exit 0 (non-blocking hook per ADR-035)
exit 0
