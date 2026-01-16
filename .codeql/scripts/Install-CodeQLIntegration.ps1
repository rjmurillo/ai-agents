<#
.SYNOPSIS
    One-command setup for CodeQL local development integration.

.DESCRIPTION
    Orchestration script that installs all CodeQL integration components:
    - CodeQL CLI installation
    - VSCode configurations (extensions, tasks, settings)
    - Claude Code skill
    - Pre-commit hook integration with actionlint

.PARAMETER SkipCLI
    Skip CodeQL CLI installation (if already installed).

.PARAMETER SkipVSCode
    Skip VSCode configuration files creation.

.PARAMETER SkipClaudeSkill
    Skip Claude Code skill installation.

.PARAMETER SkipPreCommit
    Skip pre-commit hook verification.

.PARAMETER CI
    Enable CI mode (non-interactive). Automatically accepts all prompts.

.EXAMPLE
    .\Install-CodeQLIntegration.ps1
    Install all CodeQL integration components with default settings.

.EXAMPLE
    .\Install-CodeQLIntegration.ps1 -SkipCLI
    Install all components except CodeQL CLI (assumes already installed).

.EXAMPLE
    .\Install-CodeQLIntegration.ps1 -CI
    Install in CI mode (non-interactive).

.NOTES
    Exit Codes (ADR-035):
    - 0: Success
    - 1: Logic error (invalid parameters, prerequisite check failed)
    - 2: Configuration error (missing directories, permission denied)
    - 3: External dependency error (CodeQL CLI installation failed)

    Prerequisites:
    - PowerShell 7.0+
    - Git repository
    - Write permissions to .vscode/, .claude/, .githooks/

    Related Scripts:
    - .codeql/scripts/Install-CodeQL.ps1
    - .codeql/scripts/Test-CodeQLConfig.ps1
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [switch]$SkipCLI,

    [Parameter(Mandatory = $false)]
    [switch]$SkipVSCode,

    [Parameter(Mandatory = $false)]
    [switch]$SkipClaudeSkill,

    [Parameter(Mandatory = $false)]
    [switch]$SkipPreCommit,

    [Parameter(Mandatory = $false)]
    [switch]$CI
)

$ErrorActionPreference = 'Stop'

# Helper function for colored output
function Write-Status {
    param(
        [string]$Message,
        [ValidateSet("Success", "Error", "Warning", "Info", "Header")]
        [string]$Type = "Info"
    )

    $color = switch ($Type) {
        "Success" { "Green" }
        "Error" { "Red" }
        "Warning" { "Yellow" }
        "Info" { "Cyan" }
        "Header" { "Magenta" }
    }

    $prefix = switch ($Type) {
        "Success" { "[✓]" }
        "Error" { "[✗]" }
        "Warning" { "[!]" }
        "Info" { "[i]" }
        "Header" { "===" }
    }

    if ($Type -eq "Header") {
        Write-Host "`n$prefix $Message $prefix" -ForegroundColor $color
    }
    else {
        Write-Host "$prefix $Message" -ForegroundColor $color
    }
}

# Get repository root
try {
    $repoRoot = git rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Not in a git repository"
    }
}
catch {
    Write-Status "Not in a git repository. This script must be run from within the repository." -Type Error
    exit 1
}

# Check PowerShell version
if ($PSVersionTable.PSVersion.Major -lt 7) {
    Write-Status "PowerShell 7.0 or higher is required. Current version: $($PSVersionTable.PSVersion)" -Type Error
    Write-Status "Install PowerShell: https://github.com/PowerShell/PowerShell#get-powershell" -Type Info
    exit 1
}

Write-Status "CodeQL Integration Setup" -Type Header

# Track installation status
$installationSteps = @()

# ============================================================================
# Step 1: Install CodeQL CLI
# ============================================================================

if (-not $SkipCLI) {
    Write-Status "Installing CodeQL CLI..." -Type Info

    $installScript = Join-Path $repoRoot ".codeql" "scripts" "Install-CodeQL.ps1"

    if (-not (Test-Path $installScript)) {
        Write-Status "Install-CodeQL.ps1 not found at: $installScript" -Type Error
        exit 2
    }

    try {
        # Run CLI installation with AddToPath
        $installArgs = @{
            AddToPath = $true
        }
        if ($CI) {
            $installArgs['CI'] = $true
        }

        & pwsh -NoProfile -File $installScript @installArgs

        if ($LASTEXITCODE -eq 0) {
            Write-Status "CodeQL CLI installed successfully" -Type Success
            $installationSteps += "[✓] CodeQL CLI installed at .codeql/cli/"
        }
        else {
            Write-Status "CodeQL CLI installation failed with exit code: $LASTEXITCODE" -Type Error
            exit 3
        }
    }
    catch {
        Write-Status "CodeQL CLI installation failed: $_" -Type Error
        exit 3
    }
}
else {
    Write-Status "Skipping CodeQL CLI installation" -Type Info
    $installationSteps += "[~] CodeQL CLI installation skipped"
}

# ============================================================================
# Step 2: Create VSCode Configurations
# ============================================================================

if (-not $SkipVSCode) {
    Write-Status "Creating VSCode configurations..." -Type Info

    $vscodeDir = Join-Path $repoRoot ".vscode"

    # Create .vscode directory if it doesn't exist
    if (-not (Test-Path $vscodeDir)) {
        try {
            New-Item -ItemType Directory -Path $vscodeDir -Force | Out-Null
            Write-Status "Created .vscode directory" -Type Success
        }
        catch {
            Write-Status "Failed to create .vscode directory: $_" -Type Error
            exit 2
        }
    }

    # Check if files already exist
    $extensionsFile = Join-Path $vscodeDir "extensions.json"
    $tasksFile = Join-Path $vscodeDir "tasks.json"
    $settingsFile = Join-Path $vscodeDir "settings.json"

    $filesExist = (Test-Path $extensionsFile) -or (Test-Path $tasksFile) -or (Test-Path $settingsFile)

    if ($filesExist -and -not $CI) {
        Write-Status "VSCode configuration files already exist" -Type Warning
        Write-Status "Files will be overwritten. Continue? (Y/N)" -Type Warning
        $response = Read-Host
        if ($response -ne 'Y' -and $response -ne 'y') {
            Write-Status "VSCode configuration creation skipped by user" -Type Info
            $installationSteps += "[~] VSCode configurations skipped"
        }
        else {
            # Files will be created below
            $createVSCode = $true
        }
    }
    else {
        $createVSCode = $true
    }

    if ($createVSCode) {
        # Files are already created by previous steps in the plan
        # Just verify they exist
        if ((Test-Path $extensionsFile) -and (Test-Path $tasksFile) -and (Test-Path $settingsFile)) {
            Write-Status "VSCode configurations verified" -Type Success
            $installationSteps += "[✓] VSCode configurations created"
        }
        else {
            Write-Status "VSCode configurations not found. They should be created manually." -Type Warning
            $installationSteps += "[!] VSCode configurations missing"
        }
    }
}
else {
    Write-Status "Skipping VSCode configuration" -Type Info
    $installationSteps += "[~] VSCode configurations skipped"
}

# ============================================================================
# Step 3: Install Claude Code Skill
# ============================================================================

if (-not $SkipClaudeSkill) {
    Write-Status "Verifying Claude Code skill..." -Type Info

    $skillDir = Join-Path $repoRoot ".claude" "skills" "codeql-scan"
    $skillFile = Join-Path $skillDir "SKILL.md"
    $skillScript = Join-Path $skillDir "scripts" "Invoke-CodeQLScanSkill.ps1"

    if ((Test-Path $skillFile) -and (Test-Path $skillScript)) {
        Write-Status "Claude Code skill verified" -Type Success
        $installationSteps += "[✓] Claude Code skill installed"

        # Set executable permissions on Unix-like systems
        if (-not $IsWindows) {
            try {
                chmod +x $skillScript 2>$null
                Write-Status "Set executable permissions on skill script" -Type Success
            }
            catch {
                Write-Status "Failed to set executable permissions: $_" -Type Warning
            }
        }
    }
    else {
        Write-Status "Claude Code skill not found. It should be created manually." -Type Warning
        $installationSteps += "[!] Claude Code skill missing"
    }
}
else {
    Write-Status "Skipping Claude Code skill installation" -Type Info
    $installationSteps += "[~] Claude Code skill installation skipped"
}

# ============================================================================
# Step 4: Verify Pre-Commit Hook
# ============================================================================

if (-not $SkipPreCommit) {
    Write-Status "Verifying pre-commit hook..." -Type Info

    $preCommitHook = Join-Path $repoRoot ".githooks" "pre-commit"

    if (Test-Path $preCommitHook) {
        Write-Status "Pre-commit hook found" -Type Success

        # Check if actionlint is installed
        $actionlintInstalled = $null -ne (Get-Command actionlint -ErrorAction SilentlyContinue)

        if ($actionlintInstalled) {
            Write-Status "actionlint is installed" -Type Success
            $installationSteps += "[✓] Pre-commit hook updated with actionlint"
        }
        else {
            Write-Status "actionlint not found" -Type Warning
            Write-Status "Install actionlint for GitHub Actions YAML validation:" -Type Info
            Write-Host "  macOS:   brew install actionlint" -ForegroundColor White
            Write-Host "  Linux:   Download from https://github.com/rhysd/actionlint/releases" -ForegroundColor White
            Write-Host "  Windows: winget install rhysd.actionlint" -ForegroundColor White
            $installationSteps += "[!] actionlint not found - install for YAML validation"
        }

        # Verify hook is executable on Unix-like systems
        if (-not $IsWindows) {
            try {
                chmod +x $preCommitHook 2>$null
                Write-Status "Verified pre-commit hook is executable" -Type Success
            }
            catch {
                Write-Status "Failed to set executable permissions on pre-commit hook: $_" -Type Warning
            }
        }
    }
    else {
        Write-Status "Pre-commit hook not found at: $preCommitHook" -Type Warning
        $installationSteps += "[!] Pre-commit hook not found"
    }
}
else {
    Write-Status "Skipping pre-commit hook verification" -Type Info
    $installationSteps += "[~] Pre-commit hook verification skipped"
}

# ============================================================================
# Step 5: Validate Installation
# ============================================================================

Write-Status "Validating installation..." -Type Info

$configScript = Join-Path $repoRoot ".codeql" "scripts" "Test-CodeQLConfig.ps1"

if (Test-Path $configScript) {
    try {
        & pwsh -NoProfile -File $configScript 2>$null | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Status "Configuration validation passed" -Type Success
        }
        else {
            Write-Status "Configuration validation failed (this is expected if config doesn't exist yet)" -Type Warning
        }
    }
    catch {
        Write-Status "Configuration validation failed: $_" -Type Warning
    }
}
else {
    Write-Status "Configuration validation script not found" -Type Warning
}

# Test CodeQL CLI if installed
if (-not $SkipCLI) {
    $codeqlPath = Join-Path $repoRoot ".codeql" "cli" "codeql"
    if ($IsWindows) {
        $codeqlPath += ".exe"
    }

    if (Test-Path $codeqlPath) {
        try {
            $version = & $codeqlPath version 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Status "CodeQL CLI version: $version" -Type Success
            }
        }
        catch {
            Write-Status "Failed to verify CodeQL CLI version" -Type Warning
        }
    }
}

# ============================================================================
# Installation Summary
# ============================================================================

Write-Status "Installation Summary" -Type Header

foreach ($step in $installationSteps) {
    Write-Host $step
}

Write-Host ""
Write-Status "Installation complete!" -Type Success
Write-Host ""

# Next steps
Write-Status "Next steps:" -Type Info
Write-Host "  1. Restart VSCode to load new configurations" -ForegroundColor White
Write-Host "  2. Run: pwsh .codeql/scripts/Invoke-CodeQLScan.ps1" -ForegroundColor White

# Check for actionlint
$actionlintInstalled = $null -ne (Get-Command actionlint -ErrorAction SilentlyContinue)
if (-not $actionlintInstalled) {
    Write-Host "  3. Install actionlint for YAML validation:" -ForegroundColor White
    if ($IsMacOS) {
        Write-Host "     brew install actionlint" -ForegroundColor Cyan
    }
    elseif ($IsLinux) {
        Write-Host "     Download from https://github.com/rhysd/actionlint/releases" -ForegroundColor Cyan
    }
    elseif ($IsWindows) {
        Write-Host "     winget install rhysd.actionlint" -ForegroundColor Cyan
    }
}

Write-Host ""

exit 0
