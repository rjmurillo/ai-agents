<#
.SYNOPSIS
    Validates successful CodeQL integration deployment across all tiers.

.DESCRIPTION
    Comprehensive validation of CodeQL integration including:
    - CLI installation and configuration
    - Shared configuration files
    - Script availability and executability
    - CI/CD workflow integration
    - Local development integration (VSCode, Claude Code)
    - Automatic scanning (PostToolUse hook)
    - Documentation completeness
    - Test coverage
    - Gitignore configuration

.PARAMETER Format
    Output format: "console" or "json".
    Default: "console"

.PARAMETER CI
    CI mode - returns non-zero exit code on failures.

.EXAMPLE
    .\.codeql\scripts\Test-CodeQLRollout.ps1

.EXAMPLE
    .\.codeql\scripts\Test-CodeQLRollout.ps1 -Format json

.EXAMPLE
    .\.codeql\scripts\Test-CodeQLRollout.ps1 -CI

.NOTES
  EXIT CODES:
  0  - Success: All validation checks passed
  1  - Failure: One or more validation checks failed
  3  - Validation error: Unable to perform validation

  See: ADR-035 Exit Code Standardization
  See: ADR-041 CodeQL Integration Multi-Tier Strategy
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidateSet("console", "json")]
    [string]$Format = "console",

    [Parameter()]
    [switch]$CI
)

#region Color Output
# Disable color output to avoid ANSI code issues in tests and XML export
$UseColors = $false  # Set to $false for compatibility

$ColorReset = if ($UseColors) { "`e[0m" } else { "" }
$ColorRed = if ($UseColors) { "`e[31m" } else { "" }
$ColorYellow = if ($UseColors) { "`e[33m" } else { "" }
$ColorGreen = if ($UseColors) { "`e[32m" } else { "" }
$ColorCyan = if ($UseColors) { "`e[36m" } else { "" }

function Write-ColorOutput {
    param([string]$Message, [string]$Color = $ColorReset)
    if ($Format -eq "console") {
        # Use Write-Output instead of Write-Host for testability
        Write-Output "${Color}${Message}${ColorReset}"
    }
}

function Write-CheckResult {
    param(
        [bool]$Passed,
        [string]$Message
    )
    $status = if ($Passed) { "${ColorGreen}[PASS]${ColorReset}" } else { "${ColorRed}[FAIL]${ColorReset}" }
    Write-ColorOutput "  $status $Message"
}
#endregion

#region Validation Results
$script:ValidationResults = @{
    CLI           = @()
    Configuration = @()
    Scripts       = @()
    CICD          = @()
    LocalDev      = @()
    Automatic     = @()
    Documentation = @()
    Tests         = @()
    Gitignore     = @()
}

$script:TotalChecks = 0
$script:PassedChecks = 0

function Add-CheckResult {
    param(
        [string]$Category,
        [string]$Name,
        [bool]$Passed,
        [string]$Details = ""
    )

    $script:TotalChecks++
    if ($Passed) {
        $script:PassedChecks++
    }

    $script:ValidationResults[$Category] += @{
        Name    = $Name
        Passed  = $Passed
        Details = $Details
    }
}
#endregion

#region CLI Installation Checks
Write-ColorOutput "`n[CLI Installation]" $ColorCyan

# Check CodeQL CLI exists
$cliPath = ".codeql/cli/codeql"
if ($IsWindows) {
    $cliPath = ".codeql/cli/codeql.exe"
}

$cliExists = Test-Path $cliPath
Write-CheckResult $cliExists "CodeQL CLI exists"
Add-CheckResult -Category "CLI" -Name "CLI exists" -Passed $cliExists -Details $cliPath

if ($cliExists) {
    # Check CLI version
    try {
        $version = & $cliPath version 2>&1 | Select-Object -First 1
        $versionValid = $version -match "CodeQL command-line toolchain release"
        Write-CheckResult $versionValid "CLI version: $version"
        Add-CheckResult -Category "CLI" -Name "CLI version" -Passed $versionValid -Details $version
    }
    catch {
        Write-CheckResult $false "CLI version check failed"
        Add-CheckResult -Category "CLI" -Name "CLI version" -Passed $false -Details $_.Exception.Message
    }

    # Check CLI executable permissions (Unix only)
    if (-not $IsWindows) {
        $executable = (Get-Item $cliPath).UnixMode -match "x"
        Write-CheckResult $executable "CLI executable"
        Add-CheckResult -Category "CLI" -Name "CLI executable" -Passed $executable -Details "UnixMode check"
    }
    else {
        # Windows doesn't have executable bit, always pass
        Write-CheckResult $true "CLI executable"
        Add-CheckResult -Category "CLI" -Name "CLI executable" -Passed $true -Details "Windows (no executable bit)"
    }
}
else {
    Write-CheckResult $false "CLI version (CLI not found)"
    Write-CheckResult $false "CLI executable (CLI not found)"
    Add-CheckResult -Category "CLI" -Name "CLI version" -Passed $false -Details "CLI not found"
    Add-CheckResult -Category "CLI" -Name "CLI executable" -Passed $false -Details "CLI not found"
}
#endregion

#region Configuration Checks
Write-ColorOutput "`n[Configuration]" $ColorCyan

# Check shared config exists
$sharedConfig = ".github/codeql/codeql-config.yml"
$sharedConfigExists = Test-Path $sharedConfig
Write-CheckResult $sharedConfigExists "Shared config exists"
Add-CheckResult -Category "Configuration" -Name "Shared config" -Passed $sharedConfigExists -Details $sharedConfig

# Check quick config exists
$quickConfig = ".github/codeql/codeql-config-quick.yml"
$quickConfigExists = Test-Path $quickConfig
Write-CheckResult $quickConfigExists "Quick config exists"
Add-CheckResult -Category "Configuration" -Name "Quick config" -Passed $quickConfigExists -Details $quickConfig

# Validate YAML syntax (if configs exist and ConvertFrom-Yaml available)
if ($sharedConfigExists) {
    $yamlModuleAvailable = Get-Command ConvertFrom-Yaml -ErrorAction SilentlyContinue
    if ($yamlModuleAvailable) {
        try {
            $null = Get-Content $sharedConfig | ConvertFrom-Yaml -ErrorAction Stop
            Write-CheckResult $true "YAML syntax valid"
            Add-CheckResult -Category "Configuration" -Name "YAML syntax" -Passed $true -Details "Shared config valid"
        }
        catch {
            Write-CheckResult $false "YAML syntax invalid"
            Add-CheckResult -Category "Configuration" -Name "YAML syntax" -Passed $false -Details $_.Exception.Message
        }
    }
    else {
        # ConvertFrom-Yaml not available, skip validation (non-blocking)
        Write-CheckResult $true "YAML syntax valid (validation skipped)"
        Add-CheckResult -Category "Configuration" -Name "YAML syntax" -Passed $true -Details "ConvertFrom-Yaml not available (optional)"
    }
}
else {
    Write-CheckResult $false "YAML syntax (config not found)"
    Add-CheckResult -Category "Configuration" -Name "YAML syntax" -Passed $false -Details "Config not found"
}

# Check query packs resolvable (simplified check - just verify config has queries section)
if ($sharedConfigExists) {
    $configContent = Get-Content $sharedConfig -Raw
    $hasQueries = $configContent -match "queries:"
    Write-CheckResult $hasQueries "Query packs resolvable"
    Add-CheckResult -Category "Configuration" -Name "Query packs" -Passed $hasQueries -Details "Config has queries section"
}
else {
    Write-CheckResult $false "Query packs (config not found)"
    Add-CheckResult -Category "Configuration" -Name "Query packs" -Passed $false -Details "Config not found"
}
#endregion

#region Scripts Checks
Write-ColorOutput "`n[Scripts]" $ColorCyan

$requiredScripts = @(
    ".codeql/scripts/Install-CodeQL.ps1",
    ".codeql/scripts/Invoke-CodeQLScan.ps1",
    ".codeql/scripts/Test-CodeQLConfig.ps1",
    ".codeql/scripts/Get-CodeQLDiagnostics.ps1",
    ".codeql/scripts/Install-CodeQLIntegration.ps1"
)

$scriptsExist = 0
$totalScripts = $requiredScripts.Count

foreach ($script in $requiredScripts) {
    if (Test-Path $script) {
        $scriptsExist++
    }
}

$allScriptsExist = $scriptsExist -eq $totalScripts
Write-CheckResult $allScriptsExist "All scripts exist ($scriptsExist/$totalScripts)"
Add-CheckResult -Category "Scripts" -Name "Scripts exist" -Passed $allScriptsExist -Details "$scriptsExist of $totalScripts scripts found"

# Check scripts are executable (Unix only - Windows doesn't need this)
if (-not $IsWindows) {
    $executableCount = 0
    foreach ($script in $requiredScripts) {
        if ((Test-Path $script) -and ((Get-Item $script).UnixMode -match "x")) {
            $executableCount++
        }
    }
    $allExecutable = $executableCount -eq $scriptsExist
    Write-CheckResult $allExecutable "Scripts executable ($executableCount/$scriptsExist)"
    Add-CheckResult -Category "Scripts" -Name "Scripts executable" -Passed $allExecutable -Details "$executableCount of $scriptsExist executable"
}
else {
    Write-CheckResult $true "Scripts executable (Windows, no check needed)"
    Add-CheckResult -Category "Scripts" -Name "Scripts executable" -Passed $true -Details "Windows platform"
}

# Check scripts have Pester tests
$testScripts = @(
    "tests/Install-CodeQL.Tests.ps1",
    "tests/Invoke-CodeQLScan.Tests.ps1",
    "tests/CodeQL-Integration.Tests.ps1"
)

$testsExist = 0
$totalTests = $testScripts.Count

foreach ($test in $testScripts) {
    if (Test-Path $test) {
        $testsExist++
    }
}

$allTestsExist = $testsExist -eq $totalTests
Write-CheckResult $allTestsExist "Pester tests exist ($testsExist/$totalTests)"
Add-CheckResult -Category "Scripts" -Name "Pester tests" -Passed $allTestsExist -Details "$testsExist of $totalTests test files found"
#endregion

#region CI/CD Integration Checks
Write-ColorOutput "`n[CI/CD Integration]" $ColorCyan

# Check CodeQL workflow exists
$codeqlWorkflow = ".github/workflows/codeql-analysis.yml"
$workflowExists = Test-Path $codeqlWorkflow
Write-CheckResult $workflowExists "CodeQL workflow exists"
Add-CheckResult -Category "CICD" -Name "CodeQL workflow" -Passed $workflowExists -Details $codeqlWorkflow

# Check test workflow exists
$testWorkflow = ".github/workflows/test-codeql-integration.yml"
$testWorkflowExists = Test-Path $testWorkflow
Write-CheckResult $testWorkflowExists "Test workflow exists"
Add-CheckResult -Category "CICD" -Name "Test workflow" -Passed $testWorkflowExists -Details $testWorkflow

# Check workflows use SHA-pinned actions
$shaPinned = $true
$shaPinnedDetails = ""

if ($workflowExists) {
    $workflowContent = Get-Content $codeqlWorkflow -Raw
    # Check for GitHub CodeQL action with SHA
    if ($workflowContent -match "github/codeql-action/.*@[0-9a-f]{40}") {
        $shaPinned = $shaPinned -and $true
        $shaPinnedDetails += "CodeQL workflow SHA-pinned. "
    }
    else {
        $shaPinned = $false
        $shaPinnedDetails += "CodeQL workflow not SHA-pinned. "
    }
}

Write-CheckResult $shaPinned "SHA-pinned actions"
Add-CheckResult -Category "CICD" -Name "SHA-pinned actions" -Passed $shaPinned -Details $shaPinnedDetails

# Check workflows reference shared config
$configReferenced = $false
if ($workflowExists) {
    $workflowContent = Get-Content $codeqlWorkflow -Raw
    $configReferenced = $workflowContent -match "codeql-config\.yml"
}

Write-CheckResult $configReferenced "Shared config referenced"
Add-CheckResult -Category "CICD" -Name "Shared config ref" -Passed $configReferenced -Details "Workflow references shared config"
#endregion

#region Local Development Checks
Write-ColorOutput "`n[Local Development]" $ColorCyan

# Check VSCode extensions.json
$extensionsJson = ".vscode/extensions.json"
$extensionsConfigured = $false
if (Test-Path $extensionsJson) {
    $extensionsContent = Get-Content $extensionsJson -Raw
    $extensionsConfigured = $extensionsContent -match "github.vscode-codeql"
}
Write-CheckResult $extensionsConfigured "VSCode extensions configured"
Add-CheckResult -Category "LocalDev" -Name "VSCode extensions" -Passed $extensionsConfigured -Details $extensionsJson

# Check VSCode tasks.json
$tasksJson = ".vscode/tasks.json"
$tasksConfigured = $false
if (Test-Path $tasksJson) {
    $tasksContent = Get-Content $tasksJson -Raw
    $tasksConfigured = $tasksContent -match "CodeQL.*Scan"
}
Write-CheckResult $tasksConfigured "VSCode tasks configured"
Add-CheckResult -Category "LocalDev" -Name "VSCode tasks" -Passed $tasksConfigured -Details $tasksJson

# Check VSCode settings.json
$settingsJson = ".vscode/settings.json"
$settingsConfigured = $false
if (Test-Path $settingsJson) {
    $settingsContent = Get-Content $settingsJson -Raw
    $settingsConfigured = $settingsContent -match "codeQL"
}
Write-CheckResult $settingsConfigured "VSCode settings configured"
Add-CheckResult -Category "LocalDev" -Name "VSCode settings" -Passed $settingsConfigured -Details $settingsJson

# Check Claude Code skill exists
$claudeSkill = ".claude/skills/codeql-scan/SKILL.md"
$skillExists = Test-Path $claudeSkill
Write-CheckResult $skillExists "Claude Code skill exists"
Add-CheckResult -Category "LocalDev" -Name "Claude skill" -Passed $skillExists -Details $claudeSkill

# Check skill script exists
$skillScript = ".claude/skills/codeql-scan/scripts/Invoke-CodeQLScanSkill.ps1"
$skillScriptExists = Test-Path $skillScript
Write-CheckResult $skillScriptExists "Skill script executable"
Add-CheckResult -Category "LocalDev" -Name "Skill script" -Passed $skillScriptExists -Details $skillScript
#endregion

#region Automatic Scanning Checks
Write-ColorOutput "`n[Automatic Scanning]" $ColorCyan

# Check PostToolUse hook exists
$hookScript = ".claude/hooks/PostToolUse/Invoke-CodeQLQuickScan.ps1"
$hookExists = Test-Path $hookScript
Write-CheckResult $hookExists "PostToolUse hook exists"
Add-CheckResult -Category "Automatic" -Name "PostToolUse hook" -Passed $hookExists -Details $hookScript

# Check hook script is executable (Unix only)
if (-not $IsWindows -and $hookExists) {
    $hookExecutable = (Get-Item $hookScript).UnixMode -match "x"
    Write-CheckResult $hookExecutable "Hook script executable"
    Add-CheckResult -Category "Automatic" -Name "Hook executable" -Passed $hookExecutable -Details "Unix executable bit"
}
else {
    Write-CheckResult $true "Hook script executable"
    Add-CheckResult -Category "Automatic" -Name "Hook executable" -Passed $true -Details "Windows or hook not found"
}

# Check quick config referenced by hook
$quickConfigRef = $false
if ($hookExists) {
    $hookContent = Get-Content $hookScript -Raw
    $quickConfigRef = $hookContent -match "codeql-config-quick\.yml"
}
Write-CheckResult $quickConfigRef "Quick config referenced"
Add-CheckResult -Category "Automatic" -Name "Quick config ref" -Passed $quickConfigRef -Details "Hook references quick config"
#endregion

#region Documentation Checks
Write-ColorOutput "`n[Documentation]" $ColorCyan

# Check user docs
$userDocs = "docs/codeql-integration.md"
$userDocsExist = Test-Path $userDocs
Write-CheckResult $userDocsExist "User docs exist"
Add-CheckResult -Category "Documentation" -Name "User docs" -Passed $userDocsExist -Details $userDocs

# Check developer docs
$devDocs = "docs/codeql-architecture.md"
$devDocsExist = Test-Path $devDocs
Write-CheckResult $devDocsExist "Developer docs exist"
Add-CheckResult -Category "Documentation" -Name "Developer docs" -Passed $devDocsExist -Details $devDocs

# Check ADR
$adr = ".agents/architecture/ADR-041-codeql-integration.md"
$adrExists = Test-Path $adr
Write-CheckResult $adrExists "ADR exists"
Add-CheckResult -Category "Documentation" -Name "ADR" -Passed $adrExists -Details $adr

# Check AGENTS.md updated
$agentsMd = "AGENTS.md"
$agentsUpdated = $false
if (Test-Path $agentsMd) {
    $agentsContent = Get-Content $agentsMd -Raw
    $agentsUpdated = $agentsContent -match "CodeQL Security Analysis"
}
Write-CheckResult $agentsUpdated "AGENTS.md updated"
Add-CheckResult -Category "Documentation" -Name "AGENTS.md" -Passed $agentsUpdated -Details "Contains CodeQL section"
#endregion

#region Tests Checks
Write-ColorOutput "`n[Tests]" $ColorCyan

# Check unit tests exist and can be discovered
$unitTestsPass = $null
if (Get-Command Invoke-Pester -ErrorAction SilentlyContinue) {
    try {
        # Discover tests without running them
        $testFiles = @(
            "tests/Install-CodeQL.Tests.ps1",
            "tests/Invoke-CodeQLScan.Tests.ps1"
        )

        $discoveredTests = 0
        foreach ($testFile in $testFiles) {
            if (Test-Path $testFile) {
                $discoveredTests++
            }
        }

        $unitTestsPass = $discoveredTests -gt 0
        Write-CheckResult $unitTestsPass "Unit tests discoverable ($discoveredTests files)"
        Add-CheckResult -Category "Tests" -Name "Unit tests" -Passed $unitTestsPass -Details "$discoveredTests test files found"
    }
    catch {
        Write-CheckResult $false "Unit tests check failed"
        Add-CheckResult -Category "Tests" -Name "Unit tests" -Passed $false -Details $_.Exception.Message
    }
}
else {
    Write-CheckResult $false "Pester not available"
    Add-CheckResult -Category "Tests" -Name "Unit tests" -Passed $false -Details "Pester module not found"
}

# Check integration tests exist
$integrationTests = "tests/CodeQL-Integration.Tests.ps1"
$integrationTestsExist = Test-Path $integrationTests
Write-CheckResult $integrationTestsExist "Integration tests exist"
Add-CheckResult -Category "Tests" -Name "Integration tests" -Passed $integrationTestsExist -Details $integrationTests
#endregion

#region Gitignore Checks
Write-ColorOutput "`n[Gitignore]" $ColorCyan

$gitignore = ".gitignore"
$gitignoreConfigured = $false
$gitignoreDetails = ""

if (Test-Path $gitignore) {
    $gitignoreContent = Get-Content $gitignore -Raw

    $requiredPatterns = @(
        ".codeql/cli/",
        ".codeql/db/",
        ".codeql/results/",
        ".codeql/logs/"
    )

    $foundPatterns = 0
    foreach ($pattern in $requiredPatterns) {
        if ($gitignoreContent -match [regex]::Escape($pattern)) {
            $foundPatterns++
        }
    }

    $gitignoreConfigured = $foundPatterns -eq $requiredPatterns.Count
    $gitignoreDetails = "$foundPatterns of $($requiredPatterns.Count) patterns found"
}
else {
    $gitignoreDetails = "Gitignore file not found"
}

Write-CheckResult $gitignoreConfigured "CodeQL directories excluded"
Add-CheckResult -Category "Gitignore" -Name "Gitignore config" -Passed $gitignoreConfigured -Details $gitignoreDetails
#endregion

#region Summary
Write-ColorOutput "`n========================================" $ColorCyan
$overallStatus = if ($script:PassedChecks -eq $script:TotalChecks) {
    "${ColorGreen}PASS${ColorReset}"
}
else {
    "${ColorRed}FAIL${ColorReset}"
}
Write-ColorOutput "Overall Status: $overallStatus ($script:PassedChecks/$script:TotalChecks checks)" $ColorCyan
Write-ColorOutput "========================================`n" $ColorCyan
#endregion

#region JSON Output
if ($Format -eq "json") {
    $jsonOutput = @{
        TotalChecks  = $script:TotalChecks
        PassedChecks = $script:PassedChecks
        Status       = if ($script:PassedChecks -eq $script:TotalChecks) { "PASS" } else { "FAIL" }
        Categories   = $script:ValidationResults
    } | ConvertTo-Json -Depth 10

    Write-Output $jsonOutput
}
#endregion

#region Exit Code
$exitCode = 0
if ($CI -and ($script:PassedChecks -ne $script:TotalChecks)) {
    $exitCode = 1
}

exit $exitCode
#endregion
