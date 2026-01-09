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
    Matcher: Bash(Invoke-Pester*|pwsh.*Invoke-Pester|npm test*|npm run test*|pnpm test*|yarn test*|pytest*|python.*pytest|dotnet test*|mvn test*|gradle test*|cargo test*|go test*)
    Supported Test Frameworks:
        PowerShell: Invoke-Pester (direct and via pwsh)
        JavaScript: npm, pnpm, yarn
        Python: pytest (direct and via python)
        .NET: dotnet test
        Java: mvn test, gradle test
        Rust: cargo test
        Go: go test
    Exit Codes:
        0 = Success, decision in stdout JSON
        Other = Warning (defaults to normal permission flow)

.LINK
    .agents/analysis/claude-code-hooks-opportunity-analysis.md
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'  # Non-blocking

try {
    # Parse hook input from stdin (JSON)
    $hookInput = $null
    if (-not [Console]::IsInputRedirected) {
        # No input, use normal permission flow
        exit 0
    }

    $inputJson = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($inputJson)) {
        exit 0
    }

    $hookInput = $inputJson | ConvertFrom-Json -ErrorAction Stop

    # Extract command from tool input
    $command = $null
    if ($hookInput.PSObject.Properties['tool_input'] -and
        $hookInput.tool_input.PSObject.Properties['command']) {
        $command = $hookInput.tool_input.command
    }

    if ([string]::IsNullOrWhiteSpace($command)) {
        # No command, use normal permission flow
        exit 0
    }

    # Define safe test command patterns
    # Use (\s|$) to match commands with or without arguments
    $safeTestPatterns = @(
        '^Invoke-Pester(\s|$)',
        '^pwsh.*Invoke-Pester',
        '^npm\s+test',
        '^npm\s+run\s+test',
        '^pnpm\s+test',
        '^yarn\s+test',
        '^pytest(\s|$)',
        '^python.*pytest',
        '^dotnet\s+test',
        '^mvn\s+test',
        '^gradle\s+test',
        '^cargo\s+test',
        '^go\s+test'
    )

    # Check if command matches any safe pattern
    $isSafeTest = $false
    foreach ($pattern in $safeTestPatterns) {
        if ($command -match $pattern) {
            $isSafeTest = $true
            break
        }
    }

    if ($isSafeTest) {
        # Auto-approve test execution
        $response = @{
            decision = "approve"
            reason = "Auto-approved test execution (safe read-only operation)"
        } | ConvertTo-Json -Compress

        Write-Output $response
        exit 0
    }

    # Not a recognized test command, use normal permission flow
    exit 0
}
catch {
    # On error, use normal permission flow (fail safe)
    Write-Warning "Test auto-approval check failed: $($_.Exception.Message)"
    exit 0
}
