<#
.SYNOPSIS
    Auto-approves test execution commands to reduce permission fatigue.

.DESCRIPTION
    Claude Code PermissionRequest hook that automatically approves safe test
    execution commands (Invoke-Pester, npm test, pytest, etc.) without user
    intervention. This improves developer experience by eliminating repetitive
    permission prompts for known-safe operations.

    Part of the hooks expansion implementation (Issue #773, Phase 3).

.NOTES
    Hook Type: PermissionRequest
    Matcher: Bash(Invoke-Pester*|pwsh*Invoke-Pester*|npm test*|npm run test*|pnpm test*|yarn test*|pytest*|python*pytest*|dotnet test*|mvn test*|gradle test*|cargo test*|go test*)
    Supported Test Frameworks:
        PowerShell: pwsh with Invoke-Pester
        JavaScript: npm, pnpm, yarn
        Python: pytest (direct and via python)
        .NET: dotnet test
        Java: mvn test, gradle test
        Rust: cargo test
        Go: go test
    Exit Codes:
        0 = Always (non-blocking hook, all errors are warnings)

.LINK
    .agents/analysis/claude-code-hooks-opportunity-analysis.md
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'  # Non-blocking

function Get-CommandFromInput {
    param($HookInput)

    if ($HookInput.PSObject.Properties['tool_input'] -and
        $HookInput.tool_input.PSObject.Properties['command']) {
        return $HookInput.tool_input.command
    }
    return $null
}

function Test-IsSafeTestCommand {
    param([string]$Command)

    # Security check: Block compound commands with shell metacharacters
    # Prevents command injection like: npm test; rm -rf /
    $dangerousMetachars = @(';', '|', '&', '<', '>', '$', '`', "`n", "`r")
    foreach ($char in $dangerousMetachars) {
        if ($Command.Contains($char)) {
            Write-Warning "Test auto-approval: Rejected command containing dangerous metacharacter '$char': $Command"
            return $false
        }
    }

    $safeTestPatterns = @(
        '^pwsh\s+.*Invoke-Pester',
        '^npm\s+test',
        '^npm\s+run\s+test',
        '^pnpm\s+test',
        '^yarn\s+test',
        '^pytest(\s|$)',
        '^python\s+.*pytest',
        '^dotnet\s+test',
        '^mvn\s+test',
        '^gradle\s+test',
        '^cargo\s+test',
        '^go\s+test'
    )

    foreach ($pattern in $safeTestPatterns) {
        try {
            if ($Command -match $pattern) {
                return $true
            }
        }
        catch [System.ArgumentException] {
            # Invalid regex pattern - log and continue
            Write-Warning "Test auto-approval: Invalid regex pattern '$pattern' - $($_.Exception.Message)"
            continue
        }
    }

    return $false
}

try {
    if (-not [Console]::IsInputRedirected) {
        exit 0
    }

    $inputJson = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($inputJson)) {
        exit 0
    }

    $hookInput = $inputJson | ConvertFrom-Json -ErrorAction Stop
    $command = Get-CommandFromInput -HookInput $hookInput

    if ([string]::IsNullOrWhiteSpace($command)) {
        exit 0
    }

    if (Test-IsSafeTestCommand -Command $command) {
        $response = @{
            decision = "approve"
            reason = "Auto-approved test execution (safe read-only operation)"
        } | ConvertTo-Json -Compress

        Write-Output $response
        exit 0
    }

    exit 0
}
catch {
    Write-Warning "Test auto-approval check failed: $($_.Exception.GetType().FullName) - $($_.Exception.Message)"
    Write-Output "`n**Test Auto-Approval Hook ERROR**: Auto-approval failed. You'll see standard permission prompts. Error: $($_.Exception.Message)`n"
    exit 0
}
