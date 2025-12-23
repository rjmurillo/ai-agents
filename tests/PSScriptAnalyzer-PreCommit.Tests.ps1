BeforeAll {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
    $PreCommitHook = Join-Path $RepoRoot '.githooks' 'pre-commit'
    $SettingsFile = Join-Path $RepoRoot '.PSScriptAnalyzerSettings.psd1'
}

Describe "PSScriptAnalyzer Pre-Commit Hook" {
    Context "Configuration Files" {
        It "Pre-commit hook should exist" {
            $PreCommitHook | Should -Exist
        }

        It "Pre-commit hook should be executable" {
            if ($IsLinux -or $IsMacOS) {
                $permissions = (Get-Item $PreCommitHook).UnixMode
                $permissions | Should -Match 'x'
            }
            else {
                Set-ItResult -Skipped -Because "Unix permissions not applicable on Windows"
            }
        }

        It "PSScriptAnalyzer settings file should exist" {
            $SettingsFile | Should -Exist
        }

        It "PSScriptAnalyzer settings file should be valid PSD1" {
            { Import-PowerShellDataFile -Path $SettingsFile } | Should -Not -Throw
        }

        It "Settings file should configure required rules" {
            $settings = Import-PowerShellDataFile -Path $SettingsFile
            $settings.Rules.Keys | Should -Contain 'PSAvoidUsingCmdletAliases'
            $settings.Rules.Keys | Should -Contain 'PSAvoidUsingPositionalParameters'
            $settings.Rules.Keys | Should -Contain 'PSAvoidUsingInvokeExpression'
            $settings.Rules.Keys | Should -Contain 'PSUseConsistentIndentation'
            $settings.Rules.Keys | Should -Contain 'PSUseConsistentWhitespace'
        }
    }

    Context "PSScriptAnalyzer Module" {
        It "PSScriptAnalyzer module should be available" {
            Get-Module -ListAvailable PSScriptAnalyzer | Should -Not -BeNullOrEmpty
        }

        It "PSScriptAnalyzer should have Invoke-ScriptAnalyzer command" {
            Get-Command Invoke-ScriptAnalyzer -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
        }
    }

    Context "Hook Content Validation" {
        It "Hook should contain PSScriptAnalyzer section" {
            $content = Get-Content -Path $PreCommitHook -Raw
            $content | Should -Match 'PowerShell Script Analysis with PSScriptAnalyzer'
        }

        It "Hook should filter for .ps1 and .psm1 files" {
            $content = Get-Content -Path $PreCommitHook -Raw
            # Verify hook filters for PowerShell files using grep -E extended regex
            # The actual hook uses: grep -E '\.(ps1|psm1)$'
            $content | Should -Match [regex]::Escape("grep -E '\.(ps1|psm1)$'")
        }

        It "Hook should use settings file" {
            $content = Get-Content -Path $PreCommitHook -Raw
            $content | Should -Match '\.PSScriptAnalyzerSettings\.psd1'
        }

        It "Hook should check for Error and Warning severity" {
            $content = Get-Content -Path $PreCommitHook -Raw
            $content | Should -Match 'Severity Error,Warning'
        }

        It "Hook should block on Error-level issues" {
            $content = Get-Content -Path $PreCommitHook -Raw
            # Verify hook checks for Error-level output from PSScriptAnalyzer
            # The actual hook uses: grep -q "^Error:" (caret is start anchor in grep regex)
            $content | Should -Match [regex]::Escape('grep -q "^Error:"')
            $content | Should -Match 'EXIT_STATUS=1'
        }
    }

    Context "Functional Testing" {
        BeforeAll {
            # Create test directory
            $TestDir = Join-Path $TestDrive 'ps-test'
            New-Item -ItemType Directory -Path $TestDir -Force | Out-Null
            
            # Create test file with Error-level issue
            $ErrorScript = @'
# Test script with error
param([string]$Username, [string]$Password)
$SecurePassword = ConvertTo-SecureString -String "PlainText" -AsPlainText -Force
'@
            $ErrorFile = Join-Path $TestDir 'error-script.ps1'
            Set-Content -Path $ErrorFile -Value $ErrorScript

            # Create test file with Warning-level issue only
            $WarningScript = @'
# Test script with warning
Invoke-Expression "Get-Date"
'@
            $WarningFile = Join-Path $TestDir 'warning-script.ps1'
            Set-Content -Path $WarningFile -Value $WarningScript

            # Create clean test file
            $CleanScript = @'
# Clean script
param([string]$Name)
Write-Output "Hello, $Name"
'@
            $CleanFile = Join-Path $TestDir 'clean-script.ps1'
            Set-Content -Path $CleanFile -Value $CleanScript
        }

        It "Should detect Error-level issues" {
            $result = Invoke-ScriptAnalyzer -Path $ErrorFile -Settings $SettingsFile -Severity Error
            $result | Where-Object { $_.Severity -eq 'Error' } | Should -Not -BeNullOrEmpty
        }

        It "Should detect Warning-level issues" {
            $result = Invoke-ScriptAnalyzer -Path $WarningFile -Settings $SettingsFile -Severity Warning
            $result | Where-Object { $_.Severity -eq 'Warning' } | Should -Not -BeNullOrEmpty
        }

        It "Should pass clean scripts" {
            $result = Invoke-ScriptAnalyzer -Path $CleanFile -Settings $SettingsFile -Severity Error
            $result | Should -BeNullOrEmpty
        }

        It "Should complete analysis in under 5 seconds" {
            $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
            Invoke-ScriptAnalyzer -Path $CleanFile -Settings $SettingsFile -Severity Error,Warning | Out-Null
            $stopwatch.Stop()
            $stopwatch.Elapsed.TotalSeconds | Should -BeLessThan 5
        }
    }
}
