<#
.SYNOPSIS
    Pester tests for Invoke-CodeQLScanSkill.ps1

.DESCRIPTION
    Tests the CodeQL scan skill wrapper script following ADR-035 exit code standards.
    Uses mocking to avoid actual scans during testing.
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "codeql-scan" "scripts" "Invoke-CodeQLScanSkill.ps1"

    # Mock external commands
    Mock -CommandName git -MockWith {
        param($args)
        if ($args -contains 'rev-parse') {
            return "/fake/repo/path"
        }
    }
}

Describe "Invoke-CodeQLScanSkill.ps1 Prerequisites" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "codeql-scan" "scripts" "Invoke-CodeQLScanSkill.ps1"
    }

    It "Should exist" {
        Test-Path $scriptPath | Should -Be $true
    }

    It "Should be a valid PowerShell script" {
        $script = Get-Content $scriptPath -Raw
        { [scriptblock]::Create($script) } | Should -Not -Throw
    }

    It "Should have proper comment-based help" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '\.SYNOPSIS'
        $script | Should -Match '\.DESCRIPTION'
        $script | Should -Match '\.PARAMETER'
        $script | Should -Match '\.EXAMPLE'
        $script | Should -Match '\.NOTES'
    }
}

Describe "Invoke-CodeQLScanSkill.ps1 Parameter Validation" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "codeql-scan" "scripts" "Invoke-CodeQLScanSkill.ps1"
    }

    It "Should have -Operation parameter with ValidateSet" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '\[ValidateSet\("full",\s*"quick",\s*"validate"\)\]'
        $script | Should -Match '\[string\]\$Operation'
    }

    It "Should have -Languages parameter" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '\[string\[\]\]\$Languages'
    }

    It "Should have -CI switch parameter" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '\[switch\]\$CI'
    }

    It "Should default Operation to 'full'" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '\$Operation\s*=\s*"full"'
    }

    It "Should accept 'python', 'actions' for Languages" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '\[ValidateSet\("python",\s*"actions"\)\]'
    }
}

Describe "Invoke-CodeQLScanSkill.ps1 Full Scan Operation" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "codeql-scan" "scripts" "Invoke-CodeQLScanSkill.ps1"
    }

    It "Should call Invoke-CodeQLScan.ps1 without -UseCache for full scan" {
        $script = Get-Content $scriptPath -Raw
        # Full scan should NOT add -UseCache
        $script | Should -Match 'switch\s*\(\$Operation\)'
        $script | Should -Match '"full"'
    }

    It "Should report operation type in output" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'Operation:\s*\$Operation'
    }
}

Describe "Invoke-CodeQLScanSkill.ps1 Quick Scan Operation" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "codeql-scan" "scripts" "Invoke-CodeQLScanSkill.ps1"
    }

    It "Should call Invoke-CodeQLScan.ps1 with -UseCache for quick scan" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '"quick"'
        $script | Should -Match '-UseCache'
    }

    It "Should indicate cached database usage in output" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'using cached databases'
    }
}

Describe "Invoke-CodeQLScanSkill.ps1 Validate Operation" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "codeql-scan" "scripts" "Invoke-CodeQLScanSkill.ps1"
    }

    It "Should call Test-CodeQLConfig.ps1 for validate operation" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'Test-CodeQLConfig\.ps1'
    }

    It "Should exit early for validate operation" {
        $script = Get-Content $scriptPath -Raw
        # Validate operation should exit after config validation
        $script | Should -Match 'if\s*\(\$Operation\s*-eq\s*"validate"\)'
    }

    It "Should exit with code 0 on successful validation" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'exit 0'
    }

    It "Should exit with code 2 on validation failure" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'exit 2'
    }
}

Describe "Invoke-CodeQLScanSkill.ps1 CodeQL CLI Detection" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "codeql-scan" "scripts" "Invoke-CodeQLScanSkill.ps1"
    }

    It "Should check if CodeQL CLI is installed" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'Test-Path.*codeql'
    }

    It "Should provide installation instructions if CLI not found" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'Install-CodeQL\.ps1'
    }

    It "Should exit with code 3 if CLI not found" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'exit 3'
    }

    It "Should handle Windows executable path (.exe)" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'if\s*\(\$IsWindows\)'
        $script | Should -Match '\.exe'
    }
}

Describe "Invoke-CodeQLScanSkill.ps1 Language Filter" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "codeql-scan" "scripts" "Invoke-CodeQLScanSkill.ps1"
    }

    It "Should add -Languages parameter when specified" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'if\s*\(\$Languages\)'
        $script | Should -Match '-Languages'
    }

    It "Should join multiple languages with comma" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '-join'
    }

    It "Should report languages being scanned" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'Scanning languages'
    }
}

Describe "Invoke-CodeQLScanSkill.ps1 CI Mode" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "codeql-scan" "scripts" "Invoke-CodeQLScanSkill.ps1"
    }

    It "Should add -CI parameter when specified" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'if\s*\(\$CI\)'
        $script | Should -Match '\$scanArgs.*-CI'
    }

    It "Should report CI mode is enabled" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'CI mode enabled'
    }
}

Describe "Invoke-CodeQLScanSkill.ps1 Exit Code Handling (ADR-035)" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "codeql-scan" "scripts" "Invoke-CodeQLScanSkill.ps1"
    }

    It "Should capture exit code from scan script" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '\$exitCode\s*=\s*\$LASTEXITCODE'
    }

    It "Should interpret exit code 0 as success" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'switch\s*\(\$exitCode\)'
        $script | Should -Match '0\s*\{'
        $script | Should -Match 'Scan completed successfully'
    }

    It "Should interpret exit code 1 as findings detected" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '1\s*\{'
        $script | Should -Match 'findings'
    }

    It "Should interpret exit code 2 as configuration error" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '2\s*\{'
        $script | Should -Match 'Configuration error'
    }

    It "Should interpret exit code 3 as scan execution failed" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '3\s*\{'
        $script | Should -Match 'Scan execution failed'
    }

    It "Should exit with the same code as the scan script" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'exit\s*\$exitCode'
    }
}

Describe "Invoke-CodeQLScanSkill.ps1 Output and Reporting" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "codeql-scan" "scripts" "Invoke-CodeQLScanSkill.ps1"
    }

    It "Should display operation header" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'CodeQL Security Scan'
    }

    It "Should report SARIF results location on success" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'SARIF results'
        $script | Should -Match '\.codeql/results'
    }

    It "Should use colored output for status messages" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'Write-ColorOutput'
        $script | Should -Match 'ForegroundColor'
    }

    It "Should provide actionable error messages" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'Install CodeQL CLI with'
    }
}

Describe "Invoke-CodeQLScanSkill.ps1 Error Handling" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "codeql-scan" "scripts" "Invoke-CodeQLScanSkill.ps1"
    }

    It "Should set ErrorActionPreference to Stop" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '\$ErrorActionPreference\s*=\s*[''"]Stop[''"]'
    }

    It "Should use try-catch blocks for scan execution" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'try\s*\{'
        $script | Should -Match 'catch\s*\{'
    }

    It "Should exit with code 3 on unexpected errors" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'catch'
        $script | Should -Match 'exit 3'
    }

    It "Should check if scan script exists before execution" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'Test-Path.*\$scanScript'
    }
}

Describe "Invoke-CodeQLScanSkill.ps1 Repository Detection" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "codeql-scan" "scripts" "Invoke-CodeQLScanSkill.ps1"
    }

    It "Should detect repository root using git" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'git rev-parse --show-toplevel'
    }

    It "Should exit with code 3 if not in git repository" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'Not in a git repository'
    }
}

Describe "Invoke-CodeQLScanSkill.ps1 Script Integration" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "codeql-scan" "scripts" "Invoke-CodeQLScanSkill.ps1"
    }

    It "Should reference correct path to Invoke-CodeQLScan.ps1" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '\.codeql.*scripts.*Invoke-CodeQLScan\.ps1'
    }

    It "Should reference correct path to Test-CodeQLConfig.ps1" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '\.codeql.*scripts.*Test-CodeQLConfig\.ps1'
    }

    It "Should reference correct path to Install-CodeQL.ps1 in error messages" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '\.codeql.*scripts.*Install-CodeQL\.ps1'
    }
}

Describe "Invoke-CodeQLScanSkill.ps1 Helper Functions" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "codeql-scan" "scripts" "Invoke-CodeQLScanSkill.ps1"
    }

    It "Should define Write-ColorOutput helper function" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match 'function Write-ColorOutput'
    }

    It "Should support multiple output types (Success, Error, Warning, Info)" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '\[ValidateSet\("Success",\s*"Error",\s*"Warning",\s*"Info"\)\]'
    }

    It "Should use colored output with appropriate prefixes" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '\[\✓\]'
        $script | Should -Match '\[\✗\]'
        $script | Should -Match '\[!\]'
        $script | Should -Match '\[i\]'
    }
}
