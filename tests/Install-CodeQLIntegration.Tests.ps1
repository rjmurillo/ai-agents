<#
.SYNOPSIS
    Pester tests for Install-CodeQLIntegration.ps1

.DESCRIPTION
    Tests the CodeQL integration installation script following ADR-035 exit code standards.
    Uses mocking to avoid actual installations during testing.
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot ".." ".codeql" "scripts" "Install-CodeQLIntegration.ps1"

    # Mock external commands
    Mock -CommandName git -MockWith { return "/fake/repo/path" }
    Mock -CommandName Get-Command -MockWith {
        param($Name, $ErrorAction)
        if ($Name -eq 'actionlint') {
            return $null
        }
        return @{ Name = $Name }
    }
}

Describe "Install-CodeQLIntegration.ps1 Prerequisites" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".codeql" "scripts" "Install-CodeQLIntegration.ps1"
    }

    It "Should exist" {
        Test-Path $scriptPath | Should -Be $true
    }

    It "Should be a valid PowerShell script" {
        $script = Get-Content $scriptPath -Raw
        { [scriptblock]::Create($script) } | Should -Not -Throw
    }

    It "Should have proper parameter definitions" {
        $script = Get-Content $scriptPath -Raw
        $script | Should -Match '\[switch\]\$SkipCLI'
        $script | Should -Match '\[switch\]\$SkipVSCode'
        $script | Should -Match '\[switch\]\$SkipClaudeSkill'
        $script | Should -Match '\[switch\]\$SkipPreCommit'
        $script | Should -Match '\[switch\]\$CI'
    }
}

Describe "Install-CodeQLIntegration.ps1 CLI Installation" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".codeql" "scripts" "Install-CodeQLIntegration.ps1"
    }

    It "Should skip CLI installation when -SkipCLI is specified" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'if \(-not \$SkipCLI\)'
    }

    It "Should call Install-CodeQL.ps1 when CLI installation is not skipped" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'Install-CodeQL\.ps1'
    }

    It "Should pass -AddToPath parameter to Install-CodeQL.ps1" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'AddToPath\s*=\s*\$true'
    }

    It "Should handle CLI installation failure with exit code 3" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'exit 3'
    }
}

Describe "Install-CodeQLIntegration.ps1 VSCode Configuration" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".codeql" "scripts" "Install-CodeQLIntegration.ps1"
    }

    It "Should create .vscode directory if it doesn't exist" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'New-Item.*\$vscodeDir'
    }

    It "Should check for existing configuration files" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'extensions\.json'
        $content | Should -Match 'tasks\.json'
        $content | Should -Match 'settings\.json'
    }

    It "Should prompt user before overwriting existing files (non-CI mode)" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'Read-Host'
    }

    It "Should skip VSCode configuration when -SkipVSCode is specified" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'if \(-not \$SkipVSCode\)'
    }

    It "Should update CodeQL CLI path with .exe suffix on Windows" {
        $content = Get-Content $scriptPath -Raw
        # Check for Windows-specific path update logic
        $content | Should -Match 'if \(\$IsWindows\)'
        $content | Should -Match "codeQL\.cli\.executablePath"
        $content | Should -Match '\.exe'
    }
}

Describe "Install-CodeQLIntegration.ps1 Claude Skill" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".codeql" "scripts" "Install-CodeQLIntegration.ps1"
    }

    It "Should verify Claude Code skill directory exists" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match '\.claude.*skills.*codeql-scan'
    }

    It "Should check for SKILL.md file" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'SKILL\.md'
    }

    It "Should check for Invoke-CodeQLScanSkill.ps1 script" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'Invoke-CodeQLScanSkill\.ps1'
    }

    It "Should set executable permissions on Unix-like systems" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'chmod \+x'
    }

    It "Should skip Claude skill when -SkipClaudeSkill is specified" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'if \(-not \$SkipClaudeSkill\)'
    }
}

Describe "Install-CodeQLIntegration.ps1 Pre-Commit Hook" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".codeql" "scripts" "Install-CodeQLIntegration.ps1"
    }

    It "Should check for pre-commit hook existence" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match '\.githooks.*pre-commit'
    }

    It "Should check if actionlint is installed" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'Get-Command actionlint'
    }

    It "Should provide installation instructions for actionlint" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'brew install actionlint'
        $content | Should -Match 'winget install rhysd\.actionlint'
    }

    It "Should skip pre-commit hook verification when -SkipPreCommit is specified" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'if \(-not \$SkipPreCommit\)'
    }
}

Describe "Install-CodeQLIntegration.ps1 Validation" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".codeql" "scripts" "Install-CodeQLIntegration.ps1"
    }

    It "Should run Test-CodeQLConfig.ps1 for validation" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'Test-CodeQLConfig\.ps1'
    }

    It "Should verify CodeQL CLI version if installed" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match '\$codeqlPath version'
    }

    It "Should display installation summary" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'Installation Summary'
    }

    It "Should provide next steps guidance" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'Next steps'
    }
}

Describe "Install-CodeQLIntegration.ps1 Exit Codes (ADR-035)" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".codeql" "scripts" "Install-CodeQLIntegration.ps1"
    }

    It "Should exit 0 on success" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'exit 0'
    }

    It "Should exit 1 on logic error (not in git repo)" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'exit 1'
    }

    It "Should exit 2 on configuration error (missing directories)" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'exit 2'
    }

    It "Should exit 3 on external dependency error (CLI installation failed)" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'exit 3'
    }
}

Describe "Install-CodeQLIntegration.ps1 CI Mode" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".codeql" "scripts" "Install-CodeQLIntegration.ps1"
    }

    It "Should support -CI parameter" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match '\[switch\]\$CI'
    }

    It "Should pass -CI to Install-CodeQL.ps1" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'if\s*\(\$CI\)'
        $content | Should -Match "\`$installArgs\['CI'\]\s*=\s*\`$true"
    }

    It "Should skip user prompts in CI mode" {
        $content = Get-Content $scriptPath -Raw
        # CI mode should check $CI before prompting
        $content | Should -Match 'if.*\$CI'
    }
}

Describe "Install-CodeQLIntegration.ps1 PowerShell Version Check" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".codeql" "scripts" "Install-CodeQLIntegration.ps1"
    }

    It "Should check for PowerShell 7.0+" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match '\$PSVersionTable\.PSVersion'
    }

    It "Should exit with error if PowerShell version is too old" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'PowerShell 7\.0 or higher is required'
    }
}

Describe "Install-CodeQLIntegration.ps1 Error Handling" {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot ".." ".codeql" "scripts" "Install-CodeQLIntegration.ps1"
    }

    It "Should set ErrorActionPreference to Stop" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match '\$ErrorActionPreference\s*=\s*[''"]Stop[''"]'
    }

    It "Should use try-catch blocks for critical operations" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'try\s*\{'
        $content | Should -Match 'catch\s*\{'
    }

    It "Should provide meaningful error messages" {
        $content = Get-Content $scriptPath -Raw
        $content | Should -Match 'Write-Status.*Error'
    }
}
