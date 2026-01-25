<#
.SYNOPSIS
    Shared test utilities for hook tests.

.DESCRIPTION
    Provides common test helper functions used across multiple hook test files
    to eliminate code duplication and ensure consistent test behavior.

.NOTES
    This module is imported by Pester test files that need these functions.
    All functions are exported and available after Import-Module.

.LINK
    Issue #859 - Thread 4: Extract duplicated Invoke-HookWithInput helper
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-HookInNewProcess {
    <#
    .SYNOPSIS
        Invokes a hook script in an isolated PowerShell process.

    .DESCRIPTION
        Creates a wrapper script and spawns a new PowerShell process to test
        hook behavior in isolation. This ensures hooks are tested in the same
        environment they run in production (separate process, stdin redirection).

    .PARAMETER Command
        The command string to pass to the hook via JSON input.

    .PARAMETER HookPath
        Path to the hook script to test.

    .PARAMETER ProjectDir
        Optional project directory to set via CLAUDE_PROJECT_DIR environment variable.

    .PARAMETER WorkingDir
        Optional working directory to set before running the hook (for git operations).

    .OUTPUTS
        Hashtable with Output (array of stdout/stderr) and ExitCode.

    .EXAMPLE
        $result = Invoke-HookInNewProcess -Command "git commit -m 'test'" -HookPath $hookPath
        $result.ExitCode | Should -Be 0

    .NOTES
        Renamed from Invoke-HookWithInput per Copilot #2679880660 to clarify
        that it spawns a new process rather than invoking directly.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Command,

        [Parameter(Mandatory)]
        [string]$HookPath,

        [string]$ProjectDir = $null,

        [string]$WorkingDir = $null
    )

    $inputJson = @{
        tool_input = @{
            command = $Command
        }
    } | ConvertTo-Json -Compress

    $tempInput = [System.IO.Path]::GetTempFileName()
    $tempOutput = [System.IO.Path]::GetTempFileName()
    $tempError = [System.IO.Path]::GetTempFileName()
    $tempScript = [System.IO.Path]::GetTempFileName() + ".ps1"

    try {
        Set-Content -Path $tempInput -Value $inputJson -NoNewline

        # Security: Use environment variables to pass paths instead of string interpolation
        # This prevents command injection via malicious paths containing special characters
        # The wrapper script reads paths from environment variables, avoiding any escaping issues
        $wrapperContent = @'
$env:CLAUDE_PROJECT_DIR = $env:TEST_PROJECT_DIR
if ($env:TEST_WORKING_DIR) { Set-Location $env:TEST_WORKING_DIR }
& $env:TEST_HOOK_PATH
exit $LASTEXITCODE
'@
        Set-Content -Path $tempScript -Value $wrapperContent

        # Build environment variable hashtable for the subprocess
        $envVars = @{
            TEST_PROJECT_DIR = $ProjectDir
            TEST_HOOK_PATH = $HookPath
        }
        if ($WorkingDir) {
            $envVars.TEST_WORKING_DIR = $WorkingDir
        }

        # Set environment variables before starting the process
        foreach ($key in $envVars.Keys) {
            [System.Environment]::SetEnvironmentVariable($key, $envVars[$key], 'Process')
        }

        $process = Start-Process -FilePath "pwsh" `
            -ArgumentList "-NoProfile", "-File", $tempScript `
            -RedirectStandardInput $tempInput `
            -RedirectStandardOutput $tempOutput `
            -RedirectStandardError $tempError `
            -PassThru -Wait -NoNewWindow

        # Clean up environment variables
        foreach ($key in $envVars.Keys) {
            [System.Environment]::SetEnvironmentVariable($key, $null, 'Process')
        }

        $output = Get-Content $tempOutput -Raw -ErrorAction SilentlyContinue
        $errorOutput = Get-Content $tempError -Raw -ErrorAction SilentlyContinue

        return @{
            Output = @($output, $errorOutput) | Where-Object { $_ }
            ExitCode = $process.ExitCode
        }
    }
    finally {
        Remove-Item $tempInput, $tempOutput, $tempError, $tempScript -Force -ErrorAction SilentlyContinue
    }
}

# Export all functions
Export-ModuleMember -Function Invoke-HookInNewProcess
