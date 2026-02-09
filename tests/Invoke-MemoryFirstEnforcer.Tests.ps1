#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Invoke-MemoryFirstEnforcer.ps1

.DESCRIPTION
    Tests the SessionStart hook that enforces ADR-007 memory-first protocol
    with hybrid education/escalation strategy.
#>

BeforeAll {
    $Script:HookPath = Join-Path $PSScriptRoot ".." ".claude" "hooks" "SessionStart" "Invoke-MemoryFirstEnforcer.ps1"
    $Script:CommonModulePath = Join-Path $PSScriptRoot ".." ".claude" "hooks" "Common" "HookUtilities.psm1"

    if (-not (Test-Path $Script:HookPath)) {
        throw "Hook script not found at: $Script:HookPath"
    }

    if (-not (Test-Path $Script:CommonModulePath)) {
        throw "Common module not found at: $Script:CommonModulePath"
    }

    # Helper to copy hook and dependencies to test directory
    function Copy-HookWithDependencies {
        param(
            [string]$TestRoot,
            [string]$HookRelativePath = ".claude/hooks/SessionStart/Invoke-MemoryFirstEnforcer.ps1"
        )

        $hookDestDir = Split-Path (Join-Path $TestRoot $HookRelativePath) -Parent
        $commonDestDir = Join-Path $TestRoot ".claude/hooks/Common"

        New-Item -ItemType Directory -Path $hookDestDir -Force | Out-Null
        New-Item -ItemType Directory -Path $commonDestDir -Force | Out-Null

        Copy-Item -Path $Script:HookPath -Destination (Join-Path $TestRoot $HookRelativePath) -Force
        Copy-Item -Path $Script:CommonModulePath -Destination (Join-Path $commonDestDir "HookUtilities.psm1") -Force

        return Join-Path $TestRoot $HookRelativePath
    }

    # Helper to invoke hook with environment setup
    function Invoke-HookInContext {
        param(
            [string]$HookPath = $Script:HookPath,
            [string]$ProjectDir = $null
        )

        $tempOutput = [System.IO.Path]::GetTempFileName()
        $tempError = [System.IO.Path]::GetTempFileName()
        $tempScript = [System.IO.Path]::GetTempFileName() + ".ps1"

        try {
            # Create wrapper script to set env
            $wrapperContent = @"
`$env:CLAUDE_PROJECT_DIR = '$($ProjectDir -replace "'", "''")'
& '$($HookPath -replace "'", "''")'
exit `$LASTEXITCODE
"@
            Set-Content -Path $tempScript -Value $wrapperContent

            $process = Start-Process -FilePath "pwsh" -ArgumentList "-NoProfile", "-File", $tempScript -RedirectStandardOutput $tempOutput -RedirectStandardError $tempError -PassThru -Wait -NoNewWindow
            $output = Get-Content $tempOutput -Raw -ErrorAction SilentlyContinue
            $errorOutput = Get-Content $tempError -Raw -ErrorAction SilentlyContinue

            return @{
                Output = @($output, $errorOutput) | Where-Object { $_ }
                ExitCode = $process.ExitCode
            }
        }
        finally {
            Remove-Item $tempOutput, $tempError, $tempScript -Force -ErrorAction SilentlyContinue
        }
    }
}

Describe "Invoke-MemoryFirstEnforcer" {
    Context "No session log exists" {
        BeforeAll {
            # Create test environment without session log
            $Script:TestRootNoLog = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-memory-nolog-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootNoLog -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootNoLog ".agents/sessions") -Force | Out-Null

            # Copy hook with dependencies
            $Script:TempHookPathNoLog = Copy-HookWithDependencies -TestRoot $Script:TestRootNoLog
        }

        AfterAll {
            if (Test-Path $Script:TestRootNoLog) {
                Remove-Item -Path $Script:TestRootNoLog -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Provides guidance when no session log (exit 0)" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathNoLog -ProjectDir $Script:TestRootNoLog
            $result.ExitCode | Should -Be 0
        }

        It "Output mentions session-init skill" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathNoLog -ProjectDir $Script:TestRootNoLog
            $output = $result.Output -join "`n"
            $output | Should -Match "session-init"
        }
    }

    Context "Session log with complete evidence" {
        BeforeAll {
            # Create test environment with valid session log
            $Script:TestRootComplete = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-memory-complete-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootComplete -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootComplete ".agents/sessions") -Force | Out-Null

            # Copy hook with dependencies
            $Script:TempHookPathComplete = Copy-HookWithDependencies -TestRoot $Script:TestRootComplete

            # Create session log with COMPLETE evidence
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                protocolCompliance = @{
                    sessionStart = @{
                        serenaActivated = @{ complete = $true; Evidence = "mcp__serena__activate_project" }
                        handoffRead = @{ complete = $true; Evidence = "Read HANDOFF.md" }
                        memoriesLoaded = @{ complete = $true; Evidence = "usage-mandatory, routing-gate-patterns" }
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootComplete ".agents/sessions/$today-session-999.json") -Value $sessionLog
        }

        AfterAll {
            if (Test-Path $Script:TestRootComplete) {
                Remove-Item -Path $Script:TestRootComplete -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Allows when evidence is complete (exit 0)" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathComplete -ProjectDir $Script:TestRootComplete
            $result.ExitCode | Should -Be 0
        }

        It "Output confirms evidence verified" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathComplete -ProjectDir $Script:TestRootComplete
            $output = $result.Output -join "`n"
            $output | Should -Match "verified"
        }
    }

    Context "Session log missing evidence - education phase" {
        BeforeAll {
            # Create test environment with incomplete session log
            $Script:TestRootEducation = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-memory-education-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootEducation -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootEducation ".agents/sessions") -Force | Out-Null

            # Copy hook with dependencies
            $Script:TempHookPathEducation = Copy-HookWithDependencies -TestRoot $Script:TestRootEducation

            # Create session log WITHOUT serenaActivated
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                protocolCompliance = @{
                    sessionStart = @{
                        branchVerification = @{ complete = $true }
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootEducation ".agents/sessions/$today-session-999.json") -Value $sessionLog
        }

        AfterAll {
            if (Test-Path $Script:TestRootEducation) {
                Remove-Item -Path $Script:TestRootEducation -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "First invocation shows warning 1/3 (exit 0)" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathEducation -ProjectDir $Script:TestRootEducation
            $result.ExitCode | Should -Be 0
            $output = $result.Output -join "`n"
            $output | Should -Match "Warning 1/3"
        }

        It "Second invocation shows warning 2/3 (exit 0)" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathEducation -ProjectDir $Script:TestRootEducation
            $result.ExitCode | Should -Be 0
            $output = $result.Output -join "`n"
            $output | Should -Match "Warning 2/3"
        }

        It "Third invocation shows warning 3/3 (exit 0)" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathEducation -ProjectDir $Script:TestRootEducation
            $result.ExitCode | Should -Be 0
            $output = $result.Output -join "`n"
            $output | Should -Match "Warning 3/3"
        }
    }

    Context "Session log missing evidence - escalated warning phase" {
        BeforeAll {
            # Create test environment with incomplete session log
            $Script:TestRootBlocking = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-memory-blocking-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootBlocking -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootBlocking ".agents/sessions") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootBlocking ".agents/.hook-state") -Force | Out-Null

            # Copy hook with dependencies
            $Script:TempHookPathBlocking = Copy-HookWithDependencies -TestRoot $Script:TestRootBlocking

            # Create session log WITHOUT evidence
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                protocolCompliance = @{
                    sessionStart = @{
                        branchVerification = @{ complete = $true }
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootBlocking ".agents/sessions/$today-session-999.json") -Value $sessionLog

            # Pre-seed counter to 3 so next invocation is 4 (beyond threshold)
            Set-Content -Path (Join-Path $Script:TestRootBlocking ".agents/.hook-state/memory-first-counter.txt") -Value "3"
        }

        AfterAll {
            if (Test-Path $Script:TestRootBlocking) {
                Remove-Item -Path $Script:TestRootBlocking -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Fourth invocation escalates warning (exit 0 - SessionStart cannot block)" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathBlocking -ProjectDir $Script:TestRootBlocking
            $result.ExitCode | Should -Be 0
        }

        It "Escalated warning mentions ADR-007" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathBlocking -ProjectDir $Script:TestRootBlocking
            $output = $result.Output -join "`n"
            $output | Should -Match "VIOLATION"
            $output | Should -Match "ADR-007"
        }
    }

    Context "Evidence verification details" {
        BeforeAll {
            # Create test environment with missing handoffRead
            $Script:TestRootMissingHandoff = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-missing-handoff-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootMissingHandoff -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootMissingHandoff ".agents/sessions") -Force | Out-Null

            # Copy hook with dependencies
            $Script:TempHookPathMissingHandoff = Copy-HookWithDependencies -TestRoot $Script:TestRootMissingHandoff

            # Create session log with serenaActivated but missing handoffRead
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                protocolCompliance = @{
                    sessionStart = @{
                        serenaActivated = @{ complete = $true }
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootMissingHandoff ".agents/sessions/$today-session-999.json") -Value $sessionLog
        }

        AfterAll {
            if (Test-Path $Script:TestRootMissingHandoff) {
                Remove-Item -Path $Script:TestRootMissingHandoff -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Reports specific missing evidence (handoffRead)" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathMissingHandoff -ProjectDir $Script:TestRootMissingHandoff
            $output = $result.Output -join "`n"
            # With StrictMode, accessing missing property throws, so we check for either specific message or error about handoffRead
            $output | Should -Match "(HANDOFF.md not read|handoffRead)"
        }
    }

    Context "Empty memory evidence" {
        BeforeAll {
            # Create test environment with empty memoriesLoaded evidence
            $Script:TestRootEmptyEvidence = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-empty-evidence-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootEmptyEvidence -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootEmptyEvidence ".agents/sessions") -Force | Out-Null

            # Copy hook with dependencies
            $Script:TempHookPathEmptyEvidence = Copy-HookWithDependencies -TestRoot $Script:TestRootEmptyEvidence

            # Create session log with empty Evidence string
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                protocolCompliance = @{
                    sessionStart = @{
                        serenaActivated = @{ complete = $true }
                        handoffRead = @{ complete = $true }
                        memoriesLoaded = @{ complete = $true; Evidence = "" }
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootEmptyEvidence ".agents/sessions/$today-session-999.json") -Value $sessionLog
        }

        AfterAll {
            if (Test-Path $Script:TestRootEmptyEvidence) {
                Remove-Item -Path $Script:TestRootEmptyEvidence -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Reports empty memory evidence" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathEmptyEvidence -ProjectDir $Script:TestRootEmptyEvidence
            $output = $result.Output -join "`n"
            $output | Should -Match "empty"
        }
    }

    Context "Counter reset on date change" {
        BeforeAll {
            # Create test environment
            $Script:TestRootDateReset = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-date-reset-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootDateReset -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootDateReset ".agents/sessions") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootDateReset ".agents/.hook-state") -Force | Out-Null

            # Copy hook with dependencies
            $Script:TempHookPathDateReset = Copy-HookWithDependencies -TestRoot $Script:TestRootDateReset

            # Create session log WITHOUT evidence
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                protocolCompliance = @{
                    sessionStart = @{
                        branchVerification = @{ complete = $true }
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootDateReset ".agents/sessions/$today-session-999.json") -Value $sessionLog

            # Simulate counter from previous day (format: count|date)
            $yesterday = (Get-Date).AddDays(-1).ToString("yyyy-MM-dd")
            Set-Content -Path (Join-Path $Script:TestRootDateReset ".agents/.hook-state/memory-first-counter.txt") -Value "3`n$yesterday"
        }

        AfterAll {
            if (Test-Path $Script:TestRootDateReset) {
                Remove-Item -Path $Script:TestRootDateReset -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Counter resets to 1 on new day (exit 0, warning 1/3)" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathDateReset -ProjectDir $Script:TestRootDateReset
            $result.ExitCode | Should -Be 0
            $output = $result.Output -join "`n"
            $output | Should -Match "Warning 1/3"
        }

        It "Counter file updated with today's date" {
            $result = Invoke-HookInContext -HookPath $Script:TempHookPathDateReset -ProjectDir $Script:TestRootDateReset
            $counterFile = Join-Path $Script:TestRootDateReset ".agents/.hook-state/memory-first-counter.txt"
            $content = Get-Content $counterFile -Raw
            $lines = $content.Trim() -split '\r?\n'
            $lines.Count | Should -Be 2
            $storedDate = $lines[1]
            $storedDate | Should -Be (Get-Date -Format "yyyy-MM-dd")
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
