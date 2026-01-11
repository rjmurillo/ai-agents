#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Invoke-SessionLogGuard.ps1

.DESCRIPTION
    Tests the PreToolUse hook that blocks git commit without session log evidence.
    Validates command detection, session log checks, and exit code behavior.
#>

BeforeAll {
    # Import shared test utilities (Issue #859 Thread 4: DRY violation fix)
    Import-Module "$PSScriptRoot/TestUtilities.psm1" -Force

    $Script:HookPath = Join-Path $PSScriptRoot ".." ".claude" "hooks" "PreToolUse" "Invoke-SessionLogGuard.ps1"

    if (-not (Test-Path $Script:HookPath)) {
        throw "Hook script not found at: $Script:HookPath"
    }

    # Wrapper function for backward compatibility with existing tests
    function Invoke-HookWithInput {
        param(
            [string]$Command,
            [string]$HookPath = $Script:HookPath,
            [string]$ProjectDir = $null
        )
        Invoke-HookInNewProcess -Command $Command -HookPath $HookPath -ProjectDir $ProjectDir
    }
}

Describe "Invoke-SessionLogGuard" {
    Context "Non-commit commands pass through" {
        It "Allows git status (exit 0)" {
            $result = Invoke-HookWithInput -Command "git status"
            $result.ExitCode | Should -Be 0
        }

        It "Allows git diff (exit 0)" {
            $result = Invoke-HookWithInput -Command "git diff"
            $result.ExitCode | Should -Be 0
        }

        It "Allows git push (exit 0)" {
            $result = Invoke-HookWithInput -Command "git push origin main"
            $result.ExitCode | Should -Be 0
        }

        It "Allows git log (exit 0)" {
            $result = Invoke-HookWithInput -Command "git log --oneline -5"
            $result.ExitCode | Should -Be 0
        }

        It "Allows non-git commands (exit 0)" {
            $result = Invoke-HookWithInput -Command "ls -la"
            $result.ExitCode | Should -Be 0
        }

        It "Allows npm commands (exit 0)" {
            $result = Invoke-HookWithInput -Command "npm test"
            $result.ExitCode | Should -Be 0
        }
    }

    Context "Git commit command detection" {
        BeforeAll {
            # Create temp test environment with valid session log
            $Script:TestRoot = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-commit-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRoot -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRoot ".claude/hooks/PreToolUse") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRoot ".agents/sessions") -Force | Out-Null

            # Copy hook
            $Script:TempHookPath = Join-Path $Script:TestRoot ".claude/hooks/PreToolUse/Invoke-SessionLogGuard.ps1"
            Copy-Item -Path $Script:HookPath -Destination $Script:TempHookPath -Force

            # Create valid session log for today
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{
                    number = 999
                    date = $today
                    branch = "test-branch"
                    startingCommit = "abc1234"
                    objective = "Test session for unit tests"
                }
                protocolCompliance = @{
                    sessionStart = @{
                        branchVerification = @{ complete = $true; level = "MUST"; evidence = "test" }
                    }
                    sessionEnd = @{
                        commitMade = @{ complete = $true; level = "MUST"; evidence = "test" }
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRoot ".agents/sessions/$today-session-999.json") -Value $sessionLog

            # Set project directory
            $env:CLAUDE_PROJECT_DIR = $Script:TestRoot
        }

        AfterAll {
            Remove-Item Env:\CLAUDE_PROJECT_DIR -ErrorAction SilentlyContinue
            if (Test-Path $Script:TestRoot) {
                Remove-Item -Path $Script:TestRoot -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Detects 'git commit' command" {
            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPath -ProjectDir $Script:TestRoot
            # Should allow since we have valid session log
            $result.ExitCode | Should -Be 0
        }

        It "Detects 'git commit' with flags before" {
            $result = Invoke-HookWithInput -Command "git -c user.name='Test' commit -m 'test'" -HookPath $Script:TempHookPath -ProjectDir $Script:TestRoot
            $result.ExitCode | Should -Be 0
        }

        It "Detects 'git ci' alias" {
            $result = Invoke-HookWithInput -Command "git ci -m 'test'" -HookPath $Script:TempHookPath -ProjectDir $Script:TestRoot
            $result.ExitCode | Should -Be 0
        }
    }

    Context "Missing session log blocks commit" {
        BeforeAll {
            # Create temp test environment WITHOUT session log
            $Script:TestRootNoLog = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-no-log-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootNoLog -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootNoLog ".claude/hooks/PreToolUse") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootNoLog ".agents/sessions") -Force | Out-Null

            # Copy hook
            $Script:TempHookPathNoLog = Join-Path $Script:TestRootNoLog ".claude/hooks/PreToolUse/Invoke-SessionLogGuard.ps1"
            Copy-Item -Path $Script:HookPath -Destination $Script:TempHookPathNoLog -Force

            # Set project directory (no session log exists)
            $env:CLAUDE_PROJECT_DIR = $Script:TestRootNoLog
        }

        AfterAll {
            Remove-Item Env:\CLAUDE_PROJECT_DIR -ErrorAction SilentlyContinue
            if (Test-Path $Script:TestRootNoLog) {
                Remove-Item -Path $Script:TestRootNoLog -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Blocks git commit when no session log exists (exit 2)" {
            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathNoLog -ProjectDir $Script:TestRootNoLog
            $result.ExitCode | Should -Be 2
        }

        It "Outputs blocking message with session-init instruction" {
            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathNoLog -ProjectDir $Script:TestRootNoLog
            $output = $result.Output -join "`n"
            $output | Should -Match "BLOCKED"
            $output | Should -Match "session-init"
        }
    }

    Context "Empty or invalid session log blocks commit" {
        BeforeAll {
            # Create temp test environment with EMPTY session log
            $Script:TestRootEmpty = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-empty-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootEmpty -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootEmpty ".claude/hooks/PreToolUse") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootEmpty ".agents/sessions") -Force | Out-Null

            # Copy hook
            $Script:TempHookPathEmpty = Join-Path $Script:TestRootEmpty ".claude/hooks/PreToolUse/Invoke-SessionLogGuard.ps1"
            Copy-Item -Path $Script:HookPath -Destination $Script:TempHookPathEmpty -Force

            # Create EMPTY session log for today
            $today = Get-Date -Format "yyyy-MM-dd"
            Set-Content -Path (Join-Path $Script:TestRootEmpty ".agents/sessions/$today-session-999.json") -Value "{}"

            # Set project directory
            $env:CLAUDE_PROJECT_DIR = $Script:TestRootEmpty
        }

        AfterAll {
            Remove-Item Env:\CLAUDE_PROJECT_DIR -ErrorAction SilentlyContinue
            if (Test-Path $Script:TestRootEmpty) {
                Remove-Item -Path $Script:TestRootEmpty -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Blocks git commit when session log is empty (exit 2)" {
            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathEmpty -ProjectDir $Script:TestRootEmpty
            $result.ExitCode | Should -Be 2
        }

        It "Outputs message about insufficient evidence" {
            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathEmpty -ProjectDir $Script:TestRootEmpty
            $output = $result.Output -join "`n"
            $output | Should -Match "BLOCKED|empty|Invalid"
        }
    }

    Context "Valid session log allows commit" {
        BeforeAll {
            # Create temp test environment with VALID session log
            $Script:TestRootValid = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-valid-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootValid -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootValid ".claude/hooks/PreToolUse") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootValid ".agents/sessions") -Force | Out-Null

            # Copy hook
            $Script:TempHookPathValid = Join-Path $Script:TestRootValid ".claude/hooks/PreToolUse/Invoke-SessionLogGuard.ps1"
            Copy-Item -Path $Script:HookPath -Destination $Script:TempHookPathValid -Force

            # Create VALID session log for today
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                schemaVersion = "1.0"
                session = @{
                    number = 999
                    date = $today
                    branch = "feat/test-branch"
                    startingCommit = "abc1234567890"
                    objective = "Implement feature X for testing purposes"
                }
                protocolCompliance = @{
                    sessionStart = @{
                        branchVerification = @{ complete = $true; level = "MUST"; evidence = "Verified on feature branch" }
                        handoffRead = @{ complete = $true; level = "MUST"; evidence = "Read HANDOFF.md" }
                    }
                    sessionEnd = @{
                        commitMade = @{ complete = $true; level = "MUST"; evidence = "Commit abc123" }
                        testsPass = @{ complete = $true; level = "MUST"; evidence = "All tests green" }
                    }
                }
                workLog = @(
                    @{ action = "Created test file"; result = "Success" }
                    @{ action = "Updated configuration"; result = "Applied" }
                )
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootValid ".agents/sessions/$today-session-999.json") -Value $sessionLog

            # Set project directory
            $env:CLAUDE_PROJECT_DIR = $Script:TestRootValid
        }

        AfterAll {
            Remove-Item Env:\CLAUDE_PROJECT_DIR -ErrorAction SilentlyContinue
            if (Test-Path $Script:TestRootValid) {
                Remove-Item -Path $Script:TestRootValid -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Allows git commit when valid session log exists (exit 0)" {
            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathValid -ProjectDir $Script:TestRootValid
            $result.ExitCode | Should -Be 0
        }
    }

    Context "Edge cases and error handling" {
        It "Handles no stdin gracefully (exit 0)" {
            # When no stdin is redirected, script exits 0
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

        It "Handles missing tool_input gracefully (exit 0)" {
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

        It "Handles missing command property gracefully (exit 0)" {
            $tempInput = [System.IO.Path]::GetTempFileName()
            $tempOutput = [System.IO.Path]::GetTempFileName()
            try {
                $json = @{ tool_input = @{ other = "data" } } | ConvertTo-Json
                Set-Content -Path $tempInput -Value $json -NoNewline
                $process = Start-Process -FilePath "pwsh" -ArgumentList "-NoProfile", "-File", $Script:HookPath -RedirectStandardInput $tempInput -RedirectStandardOutput $tempOutput -PassThru -Wait -NoNewWindow
                $process.ExitCode | Should -Be 0
            }
            finally {
                Remove-Item $tempInput, $tempOutput -Force -ErrorAction SilentlyContinue
            }
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
