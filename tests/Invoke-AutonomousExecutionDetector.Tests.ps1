#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Invoke-AutonomousExecutionDetector.ps1

.DESCRIPTION
    Tests the UserPromptSubmit hook that detects autonomy keywords
    and injects stricter protocol enforcement.
#>

BeforeAll {
    $Script:HookPath = Join-Path $PSScriptRoot ".." ".claude" "hooks" "UserPromptSubmit" "Invoke-AutonomousExecutionDetector.ps1"

    if (-not (Test-Path $Script:HookPath)) {
        throw "Hook script not found at: $Script:HookPath"
    }

    # Helper to invoke hook with JSON input via process
    function Invoke-HookWithPrompt {
        param(
            [string]$Prompt,
            [string]$HookPath = $Script:HookPath
        )

        $inputJson = @{
            prompt = $Prompt
        } | ConvertTo-Json -Compress

        $tempInput = [System.IO.Path]::GetTempFileName()
        $tempOutput = [System.IO.Path]::GetTempFileName()
        $tempError = [System.IO.Path]::GetTempFileName()

        try {
            Set-Content -Path $tempInput -Value $inputJson -NoNewline

            $process = Start-Process -FilePath "pwsh" -ArgumentList "-NoProfile", "-File", $HookPath -RedirectStandardInput $tempInput -RedirectStandardOutput $tempOutput -RedirectStandardError $tempError -PassThru -Wait -NoNewWindow
            $output = Get-Content $tempOutput -Raw -ErrorAction SilentlyContinue
            $errorOutput = Get-Content $tempError -Raw -ErrorAction SilentlyContinue

            return @{
                Output = @($output, $errorOutput) | Where-Object { $_ }
                ExitCode = $process.ExitCode
            }
        }
        finally {
            Remove-Item $tempInput, $tempOutput, $tempError -Force -ErrorAction SilentlyContinue
        }
    }
}

Describe "Invoke-AutonomousExecutionDetector" {
    Context "Non-autonomy prompts pass through silently" {
        It "Regular prompt passes through (exit 0)" {
            $result = Invoke-HookWithPrompt -Prompt "Please fix the bug in the login handler"
            $result.ExitCode | Should -Be 0
        }

        It "Regular prompt has no warning output" {
            $result = Invoke-HookWithPrompt -Prompt "Add a new feature to export data"
            $output = $result.Output -join "`n"
            $output | Should -Not -Match "Autonomous mode"
        }

        It "Empty prompt passes through (exit 0)" {
            $result = Invoke-HookWithPrompt -Prompt ""
            $result.ExitCode | Should -Be 0
        }
    }

    Context "Autonomy keyword detection" {
        It "Detects 'autonomous' keyword" {
            $result = Invoke-HookWithPrompt -Prompt "Run this in autonomous mode"
            $output = $result.Output -join "`n"
            $output | Should -Match "Autonomous mode"
        }

        It "Detects 'hands-off' keyword" {
            $result = Invoke-HookWithPrompt -Prompt "Do this hands-off without my input"
            $output = $result.Output -join "`n"
            $output | Should -Match "Autonomous mode"
        }

        It "Detects 'without asking' keyword" {
            $result = Invoke-HookWithPrompt -Prompt "Just do it without asking me"
            $output = $result.Output -join "`n"
            $output | Should -Match "Autonomous mode"
        }

        It "Detects 'without confirmation' keyword" {
            $result = Invoke-HookWithPrompt -Prompt "Proceed without confirmation"
            $output = $result.Output -join "`n"
            $output | Should -Match "Autonomous mode"
        }

        It "Detects 'auto-' prefix" {
            $result = Invoke-HookWithPrompt -Prompt "Use auto-approve for the PR"
            $output = $result.Output -join "`n"
            $output | Should -Match "Autonomous mode"
        }

        It "Detects 'unattended' keyword" {
            $result = Invoke-HookWithPrompt -Prompt "Run in unattended mode"
            $output = $result.Output -join "`n"
            $output | Should -Match "Autonomous mode"
        }

        It "Detects 'full autonomy' keyword" {
            $result = Invoke-HookWithPrompt -Prompt "Give you full autonomy"
            $output = $result.Output -join "`n"
            $output | Should -Match "Autonomous mode"
        }

        It "Detects 'blindly' keyword" {
            $result = Invoke-HookWithPrompt -Prompt "Just execute blindly"
            $output = $result.Output -join "`n"
            $output | Should -Match "Autonomous mode"
        }
    }

    Context "Guidance content verification" {
        It "Includes session log requirement" {
            $result = Invoke-HookWithPrompt -Prompt "Run autonomously"
            $output = $result.Output -join "`n"
            $output | Should -Match "Session log"
        }

        It "Includes multi-agent consensus gates info" {
            $result = Invoke-HookWithPrompt -Prompt "Run autonomously"
            $output = $result.Output -join "`n"
            $output | Should -Match "consensus gates"
        }

        It "Includes blocked operations list" {
            $result = Invoke-HookWithPrompt -Prompt "Run autonomously"
            $output = $result.Output -join "`n"
            $output | Should -Match "Blocked on main"
            $output | Should -Match "force-push"
        }

        It "Includes audit trail requirements" {
            $result = Invoke-HookWithPrompt -Prompt "Run autonomously"
            $output = $result.Output -join "`n"
            $output | Should -Match "SESSION-PROTOCOL"
        }
    }

    Context "Always allows (educational, not blocking)" {
        It "Autonomy keyword still exits 0 (not blocking)" {
            $result = Invoke-HookWithPrompt -Prompt "Run in full autonomy mode"
            $result.ExitCode | Should -Be 0
        }

        It "Multiple autonomy keywords still exits 0" {
            $result = Invoke-HookWithPrompt -Prompt "Run autonomous unattended without asking"
            $result.ExitCode | Should -Be 0
        }
    }

    Context "Edge cases and error handling" {
        It "Handles no stdin gracefully (exit 0)" {
            & $Script:HookPath
            $LASTEXITCODE | Should -Be 0
        }

        It "Handles malformed JSON gracefully (exit 0 - fail open)" {
            $tempInput = [System.IO.Path]::GetTempFileName()
            $tempOutput = [System.IO.Path]::GetTempFileName()
            try {
                Set-Content -Path $tempInput -Value "{ not valid json" -NoNewline
                $process = Start-Process -FilePath "pwsh" -ArgumentList "-NoProfile", "-File", $Script:HookPath -RedirectStandardInput $tempInput -RedirectStandardOutput $tempOutput -PassThru -Wait -NoNewWindow
                $process.ExitCode | Should -Be 0
            }
            finally {
                Remove-Item $tempInput, $tempOutput -Force -ErrorAction SilentlyContinue
            }
        }

        It "Handles missing prompt property gracefully (exit 0)" {
            $tempInput = [System.IO.Path]::GetTempFileName()
            $tempOutput = [System.IO.Path]::GetTempFileName()
            try {
                $json = @{ other = "data" } | ConvertTo-Json
                Set-Content -Path $tempInput -Value $json -NoNewline
                $process = Start-Process -FilePath "pwsh" -ArgumentList "-NoProfile", "-File", $Script:HookPath -RedirectStandardInput $tempInput -RedirectStandardOutput $tempOutput -PassThru -Wait -NoNewWindow
                $process.ExitCode | Should -Be 0
            }
            finally {
                Remove-Item $tempInput, $tempOutput -Force -ErrorAction SilentlyContinue
            }
        }

        It "Handles null prompt gracefully (exit 0)" {
            $tempInput = [System.IO.Path]::GetTempFileName()
            $tempOutput = [System.IO.Path]::GetTempFileName()
            try {
                $json = @{ prompt = $null } | ConvertTo-Json
                Set-Content -Path $tempInput -Value $json -NoNewline
                $process = Start-Process -FilePath "pwsh" -ArgumentList "-NoProfile", "-File", $Script:HookPath -RedirectStandardInput $tempInput -RedirectStandardOutput $tempOutput -PassThru -Wait -NoNewWindow
                $process.ExitCode | Should -Be 0
            }
            finally {
                Remove-Item $tempInput, $tempOutput -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context "Case sensitivity" {
        It "Matches keywords case-insensitively" {
            $result = Invoke-HookWithPrompt -Prompt "Run AUTONOMOUS mode"
            $output = $result.Output -join "`n"
            $output | Should -Match "Autonomous mode"
        }

        It "Matches mixed case keywords" {
            $result = Invoke-HookWithPrompt -Prompt "Run Hands-Off mode"
            $output = $result.Output -join "`n"
            $output | Should -Match "Autonomous mode"
        }
    }

    Context "Script structure" {
        It "Script parses without errors" {
            $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile($Script:HookPath, [ref]$null, [ref]$errors)
            $errors | Should -BeNullOrEmpty
        }
    }
}
