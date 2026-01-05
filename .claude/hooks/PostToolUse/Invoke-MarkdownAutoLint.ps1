<#
.SYNOPSIS
    Auto-lints markdown files after Write/Edit operations.

.DESCRIPTION
    Claude Code PostToolUse hook that automatically runs markdownlint-cli2 --fix
    on .md files after they are written or edited. This ensures consistent markdown
    formatting across the project without manual intervention.

    Part of the hooks expansion implementation (Issue #773, Phase 1).

.NOTES
    Hook Type: PostToolUse
    Matcher: Write|Edit
    Filter: .md files only (NOT .ps1!)
    Exit Codes:
        0 = Success, linting completed or skipped (file not markdown)
        Other = Warning (non-blocking)

.LINK
    .agents/analysis/claude-code-hooks-opportunity-analysis.md
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'  # Non-blocking hook

try {
    # Parse hook input from stdin (JSON)
    $hookInput = $null
    if (-not [Console]::IsInputRedirected) {
        # No input provided, exit gracefully
        exit 0
    }

    $inputJson = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($inputJson)) {
        exit 0
    }

    $hookInput = $inputJson | ConvertFrom-Json -ErrorAction Stop

    # Extract file path from tool input
    $filePath = $null
    if ($hookInput.PSObject.Properties['tool_input'] -and
        $hookInput.tool_input.PSObject.Properties['file_path']) {
        $filePath = $hookInput.tool_input.file_path
    }

    # Skip if no file path or not a markdown file
    if ([string]::IsNullOrWhiteSpace($filePath)) {
        exit 0
    }

    if (-not $filePath.EndsWith('.md', [StringComparison]::OrdinalIgnoreCase)) {
        exit 0
    }

    # Verify file exists
    if (-not (Test-Path $filePath)) {
        Write-Warning "Markdown file does not exist: $filePath"
        exit 0
    }

    # Get project directory
    $projectDir = $env:CLAUDE_PROJECT_DIR
    if ([string]::IsNullOrWhiteSpace($projectDir)) {
        $projectDir = $hookInput.cwd
    }

    # Run markdownlint-cli2 --fix
    $previousLocation = Get-Location
    try {
        if (-not [string]::IsNullOrWhiteSpace($projectDir)) {
            Set-Location $projectDir
        }

        # Run linter with error suppression (non-blocking)
        $lintResult = npx markdownlint-cli2 --fix $filePath 2>&1

        # Output success message for Claude's context
        Write-Output "`n**Markdown Auto-Lint**: Fixed formatting in ``$filePath```n"
    }
    finally {
        Set-Location $previousLocation
    }
}
catch {
    # Non-blocking: Log warning but don't fail
    Write-Warning "Markdown auto-lint failed: $($_.Exception.Message)"
}

exit 0
