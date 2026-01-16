<#
.SYNOPSIS
    Pester tests for Test-CodeQLRollout.ps1

.DESCRIPTION
    Comprehensive unit tests for the CodeQL rollout validation script.
    Tests cover all validation categories: CLI installation, configuration,
    scripts, CI/CD integration, local development, automatic scanning,
    documentation, tests, and gitignore.

    Tests follow the repository's testing patterns using Pester 5.x with
    BeforeAll/AfterAll for setup/cleanup and mock-based validation checks.
#>

BeforeAll {
    # Import script under test
    $script:ScriptPath = Join-Path $PSScriptRoot "../.codeql/scripts/Test-CodeQLRollout.ps1"

    # Create temp directory for test artifacts
    $script:TestTempDir = Join-Path ([System.IO.Path]::GetTempPath()) "CodeQL-Rollout-Tests-$(Get-Random)"
    New-Item -ItemType Directory -Path $script:TestTempDir -Force | Out-Null

    # Store original location
    $script:OriginalLocation = Get-Location

    # Function to create test file structure
    function Initialize-TestRepository {
        param([string]$BasePath)

        # Create directory structure
        $directories = @(
            ".codeql/cli",
            ".codeql/scripts",
            ".github/codeql",
            ".github/workflows",
            ".vscode",
            ".claude/skills/codeql-scan/scripts",
            ".claude/hooks/PostToolUse",
            "docs",
            ".agents/architecture",
            "tests"
        )

        foreach ($dir in $directories) {
            $fullPath = Join-Path $BasePath $dir
            New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
        }
    }

    # Function to create mock CLI
    function New-MockCodeQLCLI {
        param([string]$BasePath)

        $cliPath = Join-Path $BasePath ".codeql/cli"
        $exeName = if ($IsWindows) { "codeql.exe" } else { "codeql" }
        $cliFile = Join-Path $cliPath $exeName

        if ($IsWindows) {
            # Windows batch file
            Set-Content -Path $cliFile -Value "@echo off`necho CodeQL command-line toolchain release 2.23.9"
        }
        else {
            # Unix shell script
            Set-Content -Path $cliFile -Value "#!/bin/sh`necho 'CodeQL command-line toolchain release 2.23.9'"
            & chmod +x $cliFile
        }
    }

    # Function to create required files
    function New-RequiredFiles {
        param([string]$BasePath)

        $files = @{
            ".codeql/scripts/Install-CodeQL.ps1"                                = "# Install script"
            ".codeql/scripts/Invoke-CodeQLScan.ps1"                             = "# Scan script"
            ".codeql/scripts/Test-CodeQLConfig.ps1"                             = "# Config test script"
            ".codeql/scripts/Get-CodeQLDiagnostics.ps1"                         = "# Diagnostics script"
            ".codeql/scripts/Install-CodeQLIntegration.ps1"                     = "# Integration script"
            ".github/codeql/codeql-config.yml"                                  = "name: CodeQL Config`nqueries:`n  - uses: security-extended"
            ".github/codeql/codeql-config-quick.yml"                            = "name: Quick Config`nqueries:`n  - uses: security-extended"
            ".github/workflows/codeql-analysis.yml"                             = "name: CodeQL`nuses: github/codeql-action/init@e675ced7a7522a761fc9c8eb26682c8b27c42b2b`nconfig-file: .github/codeql/codeql-config.yml"
            ".github/workflows/test-codeql-integration.yml"                     = "name: Test CodeQL"
            ".vscode/extensions.json"                                           = '{"recommendations":["github.vscode-codeql"]}'
            ".vscode/tasks.json"                                                = '{"tasks":[{"label":"CodeQL: Full Scan"}]}'
            ".vscode/settings.json"                                             = '{"codeQL.cli.executablePath":".codeql/cli/codeql"}'
            ".claude/skills/codeql-scan/SKILL.md"                               = "# CodeQL Scan Skill"
            ".claude/skills/codeql-scan/scripts/Invoke-CodeQLScanSkill.ps1"    = "# Skill script"
            ".claude/hooks/PostToolUse/Invoke-CodeQLQuickScan.ps1"              = "# Hook script with codeql-config-quick.yml reference"
            "docs/codeql-integration.md"                                        = "# CodeQL Integration"
            "docs/codeql-architecture.md"                                       = "# CodeQL Architecture"
            ".agents/architecture/ADR-041-codeql-integration.md"                = "# ADR-041"
            "AGENTS.md"                                                         = "## Commands\n### CodeQL Security Analysis\n"
            "tests/Install-CodeQL.Tests.ps1"                                    = "Describe 'Test' {}"
            "tests/Invoke-CodeQLScan.Tests.ps1"                                 = "Describe 'Test' {}"
            "tests/CodeQL-Integration.Tests.ps1"                                = "Describe 'Test' {}"
            ".gitignore"                                                        = ".codeql/cli/`n.codeql/db/`n.codeql/results/`n.codeql/logs/"
        }

        foreach ($file in $files.Keys) {
            $fullPath = Join-Path $BasePath $file
            $directory = Split-Path -Parent $fullPath

            if (-not (Test-Path $directory)) {
                New-Item -ItemType Directory -Path $directory -Force | Out-Null
            }

            Set-Content -Path $fullPath -Value $files[$file]
        }

        # Set executable permissions for scripts and hooks (Unix only)
        if (-not $IsWindows) {
            & chmod +x (Join-Path $BasePath ".codeql/scripts/*.ps1")
            & chmod +x (Join-Path $BasePath ".claude/hooks/PostToolUse/*.ps1")
        }
    }
}

AfterAll {
    # Restore original location
    Set-Location $script:OriginalLocation

    # Cleanup test artifacts
    if (Test-Path $script:TestTempDir) {
        Remove-Item -Path $script:TestTempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe "Test-CodeQLRollout Script Execution" {
    Context "Complete Installation" {
        BeforeAll {
            # Create complete test repository
            $script:CompleteRepo = Join-Path $script:TestTempDir "complete-repo"
            Initialize-TestRepository -BasePath $script:CompleteRepo
            New-RequiredFiles -BasePath $script:CompleteRepo
            New-MockCodeQLCLI -BasePath $script:CompleteRepo

            # Change to test directory
            Set-Location $script:CompleteRepo
        }

        It "Should pass all checks in complete installation" {
            $result = & $script:ScriptPath -Format console

            $LASTEXITCODE | Should -Be 0
        }

        It "Should output status in console format" {
            $output = & $script:ScriptPath -Format console

            # Check that output was produced
            $output | Should -Not -BeNullOrEmpty

            # Check for any status indicators (PASS or FAIL)
            $outputString = $output -join "`n"
            $outputString | Should -Match "\[PASS\]|\[FAIL\]"

            # Check for overall status line
            $outputString | Should -Match "Overall Status:"
        }

        It "Should output valid JSON when requested" {
            $output = & $script:ScriptPath -Format json

            { $output | ConvertFrom-Json } | Should -Not -Throw
        }

        It "Should include all validation categories in JSON output" {
            $output = & $script:ScriptPath -Format json
            $json = $output | ConvertFrom-Json

            $json.Categories.CLI | Should -Not -BeNullOrEmpty
            $json.Categories.Configuration | Should -Not -BeNullOrEmpty
            $json.Categories.Scripts | Should -Not -BeNullOrEmpty
            $json.Categories.CICD | Should -Not -BeNullOrEmpty
            $json.Categories.LocalDev | Should -Not -BeNullOrEmpty
            $json.Categories.Automatic | Should -Not -BeNullOrEmpty
            $json.Categories.Documentation | Should -Not -BeNullOrEmpty
            $json.Categories.Tests | Should -Not -BeNullOrEmpty
            $json.Categories.Gitignore | Should -Not -BeNullOrEmpty
        }

        It "Should report total and passed checks" {
            $output = & $script:ScriptPath -Format json
            $json = $output | ConvertFrom-Json

            $json.TotalChecks | Should -BeGreaterThan 0
            $json.PassedChecks | Should -Be $json.TotalChecks
            $json.Status | Should -Be "PASS"
        }
    }

    Context "Missing CLI Installation" {
        BeforeAll {
            # Create repository without CLI
            $script:NoCLIRepo = Join-Path $script:TestTempDir "no-cli-repo"
            Initialize-TestRepository -BasePath $script:NoCLIRepo
            New-RequiredFiles -BasePath $script:NoCLIRepo
            # Intentionally skip: New-MockCodeQLCLI

            Set-Location $script:NoCLIRepo
        }

        It "Should fail CLI checks when CLI not installed" {
            $output = & $script:ScriptPath -Format json
            $json = $output | ConvertFrom-Json

            $cliChecks = $json.Categories.CLI
            $cliChecks | Should -Not -BeNullOrEmpty

            $failedCheck = $cliChecks | Where-Object { $_.Name -eq "CLI exists" }
            $failedCheck.Passed | Should -Be $false
        }

        It "Should still complete other validation checks" {
            $output = & $script:ScriptPath -Format json
            $json = $output | ConvertFrom-Json

            # Should have checks from other categories
            $json.Categories.Configuration | Should -Not -BeNullOrEmpty
            $json.Categories.Scripts | Should -Not -BeNullOrEmpty
        }

        It "Should report overall failure status" {
            $output = & $script:ScriptPath -Format json
            $json = $output | ConvertFrom-Json

            $json.Status | Should -Be "FAIL"
            $json.PassedChecks | Should -BeLessThan $json.TotalChecks
        }
    }

    Context "Missing Configuration Files" {
        BeforeAll {
            # Create repository without config files
            $script:NoConfigRepo = Join-Path $script:TestTempDir "no-config-repo"
            Initialize-TestRepository -BasePath $script:NoConfigRepo
            New-RequiredFiles -BasePath $script:NoConfigRepo
            New-MockCodeQLCLI -BasePath $script:NoConfigRepo

            # Remove config files
            Remove-Item (Join-Path $script:NoConfigRepo ".github/codeql/codeql-config.yml") -Force
            Remove-Item (Join-Path $script:NoConfigRepo ".github/codeql/codeql-config-quick.yml") -Force

            Set-Location $script:NoConfigRepo
        }

        It "Should fail configuration checks" {
            $output = & $script:ScriptPath -Format json
            $json = $output | ConvertFrom-Json

            $configChecks = $json.Categories.Configuration
            $sharedConfigCheck = $configChecks | Where-Object { $_.Name -eq "Shared config" }
            $quickConfigCheck = $configChecks | Where-Object { $_.Name -eq "Quick config" }

            $sharedConfigCheck.Passed | Should -Be $false
            $quickConfigCheck.Passed | Should -Be $false
        }
    }

    Context "Missing Documentation" {
        BeforeAll {
            # Create repository without documentation
            $script:NoDocsRepo = Join-Path $script:TestTempDir "no-docs-repo"
            Initialize-TestRepository -BasePath $script:NoDocsRepo
            New-RequiredFiles -BasePath $script:NoDocsRepo
            New-MockCodeQLCLI -BasePath $script:NoDocsRepo

            # Remove documentation files
            Remove-Item (Join-Path $script:NoDocsRepo "docs/codeql-integration.md") -Force
            Remove-Item (Join-Path $script:NoDocsRepo "docs/codeql-architecture.md") -Force
            Remove-Item (Join-Path $script:NoDocsRepo ".agents/architecture/ADR-041-codeql-integration.md") -Force

            Set-Location $script:NoDocsRepo
        }

        It "Should fail documentation checks" {
            $output = & $script:ScriptPath -Format json
            $json = $output | ConvertFrom-Json

            $docChecks = $json.Categories.Documentation
            $userDocsCheck = $docChecks | Where-Object { $_.Name -eq "User docs" }
            $devDocsCheck = $docChecks | Where-Object { $_.Name -eq "Developer docs" }
            $adrCheck = $docChecks | Where-Object { $_.Name -eq "ADR" }

            $userDocsCheck.Passed | Should -Be $false
            $devDocsCheck.Passed | Should -Be $false
            $adrCheck.Passed | Should -Be $false
        }
    }

    Context "CI Mode Exit Codes" {
        BeforeAll {
            # Create complete repository for exit code tests
            $script:ExitCodeRepo = Join-Path $script:TestTempDir "exit-code-repo"
            Initialize-TestRepository -BasePath $script:ExitCodeRepo
            New-RequiredFiles -BasePath $script:ExitCodeRepo
            New-MockCodeQLCLI -BasePath $script:ExitCodeRepo

            Set-Location $script:ExitCodeRepo
        }

        It "Should return exit code 0 when all checks pass in CI mode" {
            & $script:ScriptPath -CI -Format json | Out-Null

            $LASTEXITCODE | Should -Be 0
        }

        It "Should return exit code 0 when checks fail without CI mode" {
            # Remove a required file to cause failure
            Remove-Item (Join-Path $script:ExitCodeRepo ".github/codeql/codeql-config.yml") -Force

            & $script:ScriptPath -Format json | Out-Null

            $LASTEXITCODE | Should -Be 0
        }

        It "Should return exit code 1 when checks fail in CI mode" {
            # File still removed from previous test

            & $script:ScriptPath -CI -Format json 2>&1 | Out-Null

            $LASTEXITCODE | Should -Be 1
        }
    }
}

Describe "Test-CodeQLRollout Validation Categories" {
    Context "CLI Installation Checks" {
        It "Should validate CLI existence" {
            $repo = Join-Path $script:TestTempDir "cli-check-repo"
            Initialize-TestRepository -BasePath $repo
            New-RequiredFiles -BasePath $repo
            New-MockCodeQLCLI -BasePath $repo
            Set-Location $repo

            $output = & $script:ScriptPath -Format json
            $json = $output | ConvertFrom-Json

            $cliCheck = $json.Categories.CLI | Where-Object { $_.Name -eq "CLI exists" }
            $cliCheck.Passed | Should -Be $true
        }

        It "Should validate CLI version" {
            $repo = Join-Path $script:TestTempDir "cli-version-repo"
            Initialize-TestRepository -BasePath $repo
            New-RequiredFiles -BasePath $repo
            New-MockCodeQLCLI -BasePath $repo
            Set-Location $repo

            $output = & $script:ScriptPath -Format json
            $json = $output | ConvertFrom-Json

            $versionCheck = $json.Categories.CLI | Where-Object { $_.Name -eq "CLI version" }
            $versionCheck | Should -Not -BeNullOrEmpty
        }
    }

    Context "Scripts Validation" {
        It "Should validate all required scripts exist" {
            $repo = Join-Path $script:TestTempDir "scripts-repo"
            Initialize-TestRepository -BasePath $repo
            New-RequiredFiles -BasePath $repo
            Set-Location $repo

            $output = & $script:ScriptPath -Format json
            $json = $output | ConvertFrom-Json

            $scriptsCheck = $json.Categories.Scripts | Where-Object { $_.Name -eq "Scripts exist" }
            $scriptsCheck.Passed | Should -Be $true
        }

        It "Should validate Pester tests exist" {
            $repo = Join-Path $script:TestTempDir "tests-repo"
            Initialize-TestRepository -BasePath $repo
            New-RequiredFiles -BasePath $repo
            Set-Location $repo

            $output = & $script:ScriptPath -Format json
            $json = $output | ConvertFrom-Json

            $testsCheck = $json.Categories.Scripts | Where-Object { $_.Name -eq "Pester tests" }
            $testsCheck.Passed | Should -Be $true
        }
    }

    Context "CI/CD Integration" {
        It "Should validate workflow files exist" {
            $repo = Join-Path $script:TestTempDir "cicd-repo"
            Initialize-TestRepository -BasePath $repo
            New-RequiredFiles -BasePath $repo
            Set-Location $repo

            $output = & $script:ScriptPath -Format json
            $json = $output | ConvertFrom-Json

            $workflowCheck = $json.Categories.CICD | Where-Object { $_.Name -eq "CodeQL workflow" }
            $workflowCheck.Passed | Should -Be $true
        }

        It "Should validate SHA-pinned actions" {
            $repo = Join-Path $script:TestTempDir "sha-pin-repo"
            Initialize-TestRepository -BasePath $repo
            New-RequiredFiles -BasePath $repo
            Set-Location $repo

            $output = & $script:ScriptPath -Format json
            $json = $output | ConvertFrom-Json

            $shaPinCheck = $json.Categories.CICD | Where-Object { $_.Name -eq "SHA-pinned actions" }
            $shaPinCheck.Passed | Should -Be $true
        }

        It "Should validate shared config reference" {
            $repo = Join-Path $script:TestTempDir "config-ref-repo"
            Initialize-TestRepository -BasePath $repo
            New-RequiredFiles -BasePath $repo
            Set-Location $repo

            $output = & $script:ScriptPath -Format json
            $json = $output | ConvertFrom-Json

            $configRefCheck = $json.Categories.CICD | Where-Object { $_.Name -eq "Shared config ref" }
            $configRefCheck.Passed | Should -Be $true
        }
    }

    Context "Local Development Integration" {
        It "Should validate VSCode integration" {
            $repo = Join-Path $script:TestTempDir "vscode-repo"
            Initialize-TestRepository -BasePath $repo
            New-RequiredFiles -BasePath $repo
            Set-Location $repo

            $output = & $script:ScriptPath -Format json
            $json = $output | ConvertFrom-Json

            $extensionsCheck = $json.Categories.LocalDev | Where-Object { $_.Name -eq "VSCode extensions" }
            $tasksCheck = $json.Categories.LocalDev | Where-Object { $_.Name -eq "VSCode tasks" }
            $settingsCheck = $json.Categories.LocalDev | Where-Object { $_.Name -eq "VSCode settings" }

            $extensionsCheck.Passed | Should -Be $true
            $tasksCheck.Passed | Should -Be $true
            $settingsCheck.Passed | Should -Be $true
        }

        It "Should validate Claude Code skill" {
            $repo = Join-Path $script:TestTempDir "claude-skill-repo"
            Initialize-TestRepository -BasePath $repo
            New-RequiredFiles -BasePath $repo
            Set-Location $repo

            $output = & $script:ScriptPath -Format json
            $json = $output | ConvertFrom-Json

            $skillCheck = $json.Categories.LocalDev | Where-Object { $_.Name -eq "Claude skill" }
            $skillCheck.Passed | Should -Be $true
        }
    }

    Context "Gitignore Configuration" {
        It "Should validate gitignore patterns" {
            $repo = Join-Path $script:TestTempDir "gitignore-repo"
            Initialize-TestRepository -BasePath $repo
            New-RequiredFiles -BasePath $repo
            Set-Location $repo

            $output = & $script:ScriptPath -Format json
            $json = $output | ConvertFrom-Json

            $gitignoreCheck = $json.Categories.Gitignore | Where-Object { $_.Name -eq "Gitignore config" }
            $gitignoreCheck.Passed | Should -Be $true
        }
    }
}
