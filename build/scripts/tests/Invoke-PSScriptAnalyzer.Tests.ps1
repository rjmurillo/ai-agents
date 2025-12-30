<#
.SYNOPSIS
    Pester tests for Invoke-PSScriptAnalyzer.ps1 script.

.DESCRIPTION
    Unit tests for the PSScriptAnalyzer validation script, focusing on:
    - Script execution and parameter handling
    - File discovery and exclusion logic
    - Result processing and output format
    - CI mode behavior and exit codes

.NOTES
    Requires Pester 5.x or later.
    Run with: pwsh build/scripts/Invoke-PesterTests.ps1 -TestPath "./build/scripts/tests/Invoke-PSScriptAnalyzer.Tests.ps1"
#>

BeforeAll {
    # Create isolated test temp directory
    $Script:TestTempDir = Join-Path ([System.IO.Path]::GetTempPath()) "Invoke-PSScriptAnalyzer-Tests-$(Get-Random)"
    New-Item -ItemType Directory -Path $Script:TestTempDir -Force | Out-Null

    # Store repository root and script path
    $Script:RepoRoot = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
    $Script:ScriptPath = Join-Path $Script:RepoRoot "build" "scripts" "Invoke-PSScriptAnalyzer.ps1"

    # Verify script exists
    if (-not (Test-Path $Script:ScriptPath)) {
        throw "Script not found at: $Script:ScriptPath"
    }

    # Helper function: Create a valid PowerShell script
    function New-ValidTestScript {
        param([string]$Path)
        $content = @'
# Valid PowerShell script
function Get-TestValue {
    [CmdletBinding()]
    param()
    return "test"
}
'@
        Set-Content -Path $Path -Value $content -Force
    }

    # Helper function: Create a script with PSScriptAnalyzer errors
    function New-InvalidTestScript {
        param([string]$Path)
        # Using PSAvoidUsingCmdletAliases - 'cd' should be 'Set-Location'
        $content = @'
# Script with PSScriptAnalyzer issues
cd "C:\temp"
'@
        Set-Content -Path $Path -Value $content -Force
    }

    # Helper function: Create a script with syntax errors
    function New-SyntaxErrorScript {
        param([string]$Path)
        $content = @'
# Script with syntax error
function Test-Broken {
    if ($true {
        Write-Host "Missing closing paren"
    }
}
'@
        Set-Content -Path $Path -Value $content -Force
    }
}

AfterAll {
    # Cleanup test temp directory
    if (Test-Path $Script:TestTempDir) {
        Remove-Item -Path $Script:TestTempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe "Invoke-PSScriptAnalyzer Script Validation" -Tag "Unit" {

    Context "Script Exists and Has Valid Syntax" {
        It "Script file should exist" {
            Test-Path $Script:ScriptPath | Should -BeTrue
        }

        It "Script should have valid PowerShell syntax" {
            $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile(
                $Script:ScriptPath,
                [ref]$null,
                [ref]$errors
            )
            $errors.Count | Should -Be 0
        }
    }

    Context "Parameter Validation" {
        It "Should accept -Path parameter" {
            $cmd = Get-Command $Script:ScriptPath
            $cmd.Parameters.ContainsKey('Path') | Should -BeTrue
        }

        It "Should accept -CI switch" {
            $cmd = Get-Command $Script:ScriptPath
            $cmd.Parameters.ContainsKey('CI') | Should -BeTrue
        }

        It "Should accept -PassThru switch" {
            $cmd = Get-Command $Script:ScriptPath
            $cmd.Parameters.ContainsKey('PassThru') | Should -BeTrue
        }

        It "Should accept -Severity parameter with valid values" {
            $cmd = Get-Command $Script:ScriptPath
            $cmd.Parameters.ContainsKey('Severity') | Should -BeTrue
            $validateSetAttr = $cmd.Parameters['Severity'].Attributes | Where-Object { $_ -is [System.Management.Automation.ValidateSetAttribute] }
            $validateSetAttr | Should -Not -BeNullOrEmpty
            $validateSetAttr.ValidValues | Should -Contain "Error"
            $validateSetAttr.ValidValues | Should -Contain "Warning"
            $validateSetAttr.ValidValues | Should -Contain "Information"
        }
    }
}

Describe "Invoke-PSScriptAnalyzer File Discovery" -Tag "Integration" {

    BeforeEach {
        # Create test directory structure for each test
        $Script:TestDir = Join-Path $Script:TestTempDir "FileDiscovery-$(Get-Random)"
        New-Item -ItemType Directory -Path $Script:TestDir -Force | Out-Null
    }

    Context "PowerShell File Discovery" {
        It "Should find .ps1 files" {
            $testFile = Join-Path $Script:TestDir "test.ps1"
            New-ValidTestScript -Path $testFile

            $result = & $Script:ScriptPath -Path $Script:TestDir -PassThru
            $result.TotalFiles | Should -BeGreaterThan 0
        }

        It "Should find .psm1 files" {
            $testFile = Join-Path $Script:TestDir "test.psm1"
            New-ValidTestScript -Path $testFile

            $result = & $Script:ScriptPath -Path $Script:TestDir -PassThru
            $result.TotalFiles | Should -BeGreaterThan 0
        }

        It "Should report zero files when directory is empty" {
            $emptyDir = Join-Path $Script:TestDir "empty"
            New-Item -ItemType Directory -Path $emptyDir -Force | Out-Null

            $result = & $Script:ScriptPath -Path $emptyDir -PassThru
            $result.TotalFiles | Should -Be 0
        }
    }

    Context "File Exclusion" {
        It "Should exclude node_modules directory" {
            $nodeModulesDir = Join-Path $Script:TestDir "node_modules"
            New-Item -ItemType Directory -Path $nodeModulesDir -Force | Out-Null
            $excludedFile = Join-Path $nodeModulesDir "excluded.ps1"
            New-ValidTestScript -Path $excludedFile

            $includedFile = Join-Path $Script:TestDir "included.ps1"
            New-ValidTestScript -Path $includedFile

            $result = & $Script:ScriptPath -Path $Script:TestDir -PassThru
            $result.TotalFiles | Should -Be 1
        }
    }
}

Describe "Invoke-PSScriptAnalyzer Results Processing" -Tag "Integration" {

    BeforeEach {
        $Script:TestDir = Join-Path $Script:TestTempDir "Results-$(Get-Random)"
        New-Item -ItemType Directory -Path $Script:TestDir -Force | Out-Null
    }

    Context "Valid Script Analysis" {
        It "Should report zero issues for valid script" {
            $testFile = Join-Path $Script:TestDir "valid.ps1"
            New-ValidTestScript -Path $testFile

            $result = & $Script:ScriptPath -Path $Script:TestDir -PassThru
            $result.ErrorCount | Should -Be 0
        }
    }

    Context "Invalid Script Analysis" {
        It "Should report issues for a script with PSScriptAnalyzer warnings" {
            $testFile = Join-Path $Script:TestDir "invalid.ps1"
            New-InvalidTestScript -Path $testFile

            $result = & $Script:ScriptPath -Path $Script:TestDir -PassThru -Severity Warning
            $result.TotalIssues | Should -BeGreaterThan 0
            $result.WarningCount | Should -BeGreaterThan 0
        }

        It "Should handle scripts with syntax errors gracefully without throwing" {
            $testFile = Join-Path $Script:TestDir "syntax-error.ps1"
            New-SyntaxErrorScript -Path $testFile

            { & $Script:ScriptPath -Path $Script:TestDir -PassThru } | Should -Not -Throw
        }
    }

    Context "Result Object Structure" {
        It "Should return expected result properties with -PassThru" {
            $testFile = Join-Path $Script:TestDir "test.ps1"
            New-ValidTestScript -Path $testFile

            $result = & $Script:ScriptPath -Path $Script:TestDir -PassThru
            $result | Should -Not -BeNullOrEmpty
            $result.PSObject.Properties.Name | Should -Contain "TotalFiles"
            $result.PSObject.Properties.Name | Should -Contain "TotalIssues"
            $result.PSObject.Properties.Name | Should -Contain "ErrorCount"
            $result.PSObject.Properties.Name | Should -Contain "WarningCount"
            $result.PSObject.Properties.Name | Should -Contain "InformationCount"
            $result.PSObject.Properties.Name | Should -Contain "Results"
        }
    }
}

Describe "Invoke-PSScriptAnalyzer Output Generation" -Tag "Integration" {

    BeforeEach {
        $Script:TestDir = Join-Path $Script:TestTempDir "Output-$(Get-Random)"
        New-Item -ItemType Directory -Path $Script:TestDir -Force | Out-Null
        $Script:OutputDir = Join-Path $Script:TestDir "artifacts"
    }

    Context "XML Output" {
        It "Should create output directory if it does not exist" {
            $testFile = Join-Path $Script:TestDir "test.ps1"
            New-ValidTestScript -Path $testFile

            $outputPath = Join-Path $Script:OutputDir "results.xml"

            & $Script:ScriptPath -Path $Script:TestDir -OutputPath $outputPath

            Test-Path $Script:OutputDir | Should -BeTrue
        }

        It "Should create valid XML output file" {
            $testFile = Join-Path $Script:TestDir "test.ps1"
            New-ValidTestScript -Path $testFile

            $outputPath = Join-Path $Script:OutputDir "results.xml"

            & $Script:ScriptPath -Path $Script:TestDir -OutputPath $outputPath

            Test-Path $outputPath | Should -BeTrue
            { [xml](Get-Content $outputPath -Raw) } | Should -Not -Throw
        }

        It "Should create JUnit-compatible XML structure" {
            $testFile = Join-Path $Script:TestDir "test.ps1"
            New-ValidTestScript -Path $testFile

            $outputPath = Join-Path $Script:OutputDir "results.xml"

            & $Script:ScriptPath -Path $Script:TestDir -OutputPath $outputPath

            $xml = [xml](Get-Content $outputPath -Raw)
            $xml.testsuites | Should -Not -BeNullOrEmpty
        }
    }
}
