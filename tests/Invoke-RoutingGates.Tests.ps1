#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Invoke-RoutingGates.ps1

.DESCRIPTION
    Tests the QA Validation Gate per ADR-033.
    Validates gate detection, QA evidence checking, and bypass conditions.
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot ".." ".claude" "hooks" "Invoke-RoutingGates.ps1"
}

Describe "Invoke-RoutingGates" {
    Context "Script execution basics" {
        It "Executes without error with empty input" {
            { '' | & $ScriptPath } | Should -Not -Throw
        }

        It "Returns exit code 0 with empty input" {
            '' | & $ScriptPath
            $LASTEXITCODE | Should -Be 0
        }

        It "Handles malformed JSON gracefully" {
            { 'not valid json' | & $ScriptPath } | Should -Not -Throw
            $LASTEXITCODE | Should -Be 0
        }

        It "Handles missing tool_input field" {
            $TestInput = '{"other": "field"}'
            { $TestInput | & $ScriptPath } | Should -Not -Throw
            $LASTEXITCODE | Should -Be 0
        }

        It "Handles null command field" {
            $TestInput = '{"tool_input": {}}'
            { $TestInput | & $ScriptPath } | Should -Not -Throw
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "Non-triggering commands" {
        It "Allows git status command" {
            $TestInput = '{"tool_input": {"command": "git status"}}'
            $Output = $TestInput | & $ScriptPath
            $LASTEXITCODE | Should -Be 0
            $Output | Should -BeNullOrEmpty
        }

        It "Allows git diff command" {
            $TestInput = '{"tool_input": {"command": "git diff"}}'
            $Output = $TestInput | & $ScriptPath
            $LASTEXITCODE | Should -Be 0
            $Output | Should -BeNullOrEmpty
        }

        It "Allows gh pr list command" {
            $TestInput = '{"tool_input": {"command": "gh pr list"}}'
            $Output = $TestInput | & $ScriptPath
            $LASTEXITCODE | Should -Be 0
            $Output | Should -BeNullOrEmpty
        }

        It "Allows gh pr view command" {
            $TestInput = '{"tool_input": {"command": "gh pr view 123"}}'
            $Output = $TestInput | & $ScriptPath
            $LASTEXITCODE | Should -Be 0
            $Output | Should -BeNullOrEmpty
        }

        It "Allows echo command" {
            $TestInput = '{"tool_input": {"command": "echo hello"}}'
            $Output = $TestInput | & $ScriptPath
            $LASTEXITCODE | Should -Be 0
            $Output | Should -BeNullOrEmpty
        }
    }

    Context "QA Gate trigger detection" {
        BeforeEach {
            # Ensure no bypass conditions are active
            $env:SKIP_QA_GATE = $null
        }

        AfterEach {
            $env:SKIP_QA_GATE = $null
        }

        It "Triggers on 'gh pr create' command" {
            # Create a temporary test environment
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents" "sessions") -Force | Out-Null

            try {
                Set-Location $TempDir
                # Initialize git repo for the test
                & git init --quiet 2>$null
                & git config user.email "test@test.com" 2>$null
                & git config user.name "Test" 2>$null

                # Create a code file to trigger non-docs-only
                "test" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "initial" --quiet 2>$null
                & git branch "origin/main" HEAD 2>$null
                "changed" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "change" --quiet 2>$null

                $TestInput = '{"tool_input": {"command": "gh pr create --title test"}}'
                $Output = ($TestInput | & $ScriptPath) -join "`n"
                # Should get a deny decision since no QA evidence exists
                $Output | Should -Match "QA VALIDATION GATE"
            }
            finally {
                Set-Location $OriginalLocation
                Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Triggers on 'gh pr create' with various flags" {
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents" "sessions") -Force | Out-Null

            try {
                Set-Location $TempDir
                & git init --quiet 2>$null
                & git config user.email "test@test.com" 2>$null
                & git config user.name "Test" 2>$null
                "test" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "initial" --quiet 2>$null
                & git branch "origin/main" HEAD 2>$null
                "changed" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "change" --quiet 2>$null

                $TestInput = '{"tool_input": {"command": "gh pr create --title \"Feature\" --body \"Description\""}}'
                $Output = ($TestInput | & $ScriptPath) -join "`n"
                $Output | Should -Match "QA VALIDATION GATE"
            }
            finally {
                Set-Location $OriginalLocation
                Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context "QA Evidence detection - QA reports" {
        BeforeEach {
            $env:SKIP_QA_GATE = $null
        }

        AfterEach {
            $env:SKIP_QA_GATE = $null
        }

        It "Allows PR creation when recent QA report exists" {
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents" "qa") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents" "sessions") -Force | Out-Null

            try {
                Set-Location $TempDir
                & git init --quiet 2>$null
                & git config user.email "test@test.com" 2>$null
                & git config user.name "Test" 2>$null
                "test" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "initial" --quiet 2>$null
                & git branch "origin/main" HEAD 2>$null
                "changed" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "change" --quiet 2>$null

                # Create a recent QA report
                $QAReport = Join-Path $TempDir ".agents" "qa" "test-qa-report.md"
                "# QA Report`n`nTest passed" | Set-Content $QAReport

                $TestInput = '{"tool_input": {"command": "gh pr create --title test"}}'
                $Output = $TestInput | & $ScriptPath
                $LASTEXITCODE | Should -Be 0
                $Output | Should -BeNullOrEmpty
            }
            finally {
                Set-Location $OriginalLocation
                Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Blocks PR creation when QA report is older than 24 hours" {
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents" "qa") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents" "sessions") -Force | Out-Null

            try {
                Set-Location $TempDir
                & git init --quiet 2>$null
                & git config user.email "test@test.com" 2>$null
                & git config user.name "Test" 2>$null
                "test" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "initial" --quiet 2>$null
                & git branch "origin/main" HEAD 2>$null
                "changed" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "change" --quiet 2>$null

                # Create an old QA report
                $QAReport = Join-Path $TempDir ".agents" "qa" "old-qa-report.md"
                "# QA Report`n`nTest passed" | Set-Content $QAReport
                # Set the file time to 25 hours ago
                $OldTime = (Get-Date).AddHours(-25)
                (Get-Item $QAReport).LastWriteTime = $OldTime

                $TestInput = '{"tool_input": {"command": "gh pr create --title test"}}'
                $Output = ($TestInput | & $ScriptPath) -join "`n"
                $Output | Should -Match "QA VALIDATION GATE"
            }
            finally {
                Set-Location $OriginalLocation
                Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context "QA Evidence detection - Session log" {
        BeforeEach {
            $env:SKIP_QA_GATE = $null
        }

        AfterEach {
            $env:SKIP_QA_GATE = $null
        }

        It "Allows PR creation when session log has QA section" {
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents" "sessions") -Force | Out-Null

            try {
                Set-Location $TempDir
                & git init --quiet 2>$null
                & git config user.email "test@test.com" 2>$null
                & git config user.name "Test" 2>$null
                "test" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "initial" --quiet 2>$null
                & git branch "origin/main" HEAD 2>$null
                "changed" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "change" --quiet 2>$null

                # Create today's session log with QA section
                $Today = Get-Date -Format "yyyy-MM-dd"
                $SessionLog = Join-Path $TempDir ".agents" "sessions" "$Today-session-01.md"
                @"
# Session Log

## QA

QA agent was invoked and tests passed.
"@ | Set-Content $SessionLog

                $TestInput = '{"tool_input": {"command": "gh pr create --title test"}}'
                $Output = $TestInput | & $ScriptPath
                $LASTEXITCODE | Should -Be 0
                $Output | Should -BeNullOrEmpty
            }
            finally {
                Set-Location $OriginalLocation
                Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Allows PR creation when session log mentions 'qa agent'" {
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents" "sessions") -Force | Out-Null

            try {
                Set-Location $TempDir
                & git init --quiet 2>$null
                & git config user.email "test@test.com" 2>$null
                & git config user.name "Test" 2>$null
                "test" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "initial" --quiet 2>$null
                & git branch "origin/main" HEAD 2>$null
                "changed" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "change" --quiet 2>$null

                $Today = Get-Date -Format "yyyy-MM-dd"
                $SessionLog = Join-Path $TempDir ".agents" "sessions" "$Today-session-01.md"
                @"
# Session Log

Invoked the qa agent to verify the implementation.
"@ | Set-Content $SessionLog

                $TestInput = '{"tool_input": {"command": "gh pr create --title test"}}'
                $Output = $TestInput | & $ScriptPath
                $LASTEXITCODE | Should -Be 0
                $Output | Should -BeNullOrEmpty
            }
            finally {
                Set-Location $OriginalLocation
                Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Allows PR creation when session log has 'Test Results'" {
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents" "sessions") -Force | Out-Null

            try {
                Set-Location $TempDir
                & git init --quiet 2>$null
                & git config user.email "test@test.com" 2>$null
                & git config user.name "Test" 2>$null
                "test" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "initial" --quiet 2>$null
                & git branch "origin/main" HEAD 2>$null
                "changed" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "change" --quiet 2>$null

                $Today = Get-Date -Format "yyyy-MM-dd"
                $SessionLog = Join-Path $TempDir ".agents" "sessions" "$Today-session-01.md"
                @"
# Session Log

## Test Results

All tests passed successfully.
"@ | Set-Content $SessionLog

                $TestInput = '{"tool_input": {"command": "gh pr create --title test"}}'
                $Output = $TestInput | & $ScriptPath
                $LASTEXITCODE | Should -Be 0
                $Output | Should -BeNullOrEmpty
            }
            finally {
                Set-Location $OriginalLocation
                Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context "Bypass conditions - Documentation only" {
        BeforeEach {
            $env:SKIP_QA_GATE = $null
        }

        AfterEach {
            $env:SKIP_QA_GATE = $null
        }

        It "Allows PR creation when only .md files are changed" {
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents" "sessions") -Force | Out-Null

            try {
                Set-Location $TempDir
                & git init --quiet 2>$null
                & git config user.email "test@test.com" 2>$null
                & git config user.name "Test" 2>$null
                "# Initial" | Set-Content "README.md"
                & git add . 2>$null
                & git commit -m "initial" --quiet 2>$null
                & git branch "origin/main" HEAD 2>$null
                "# Updated" | Set-Content "README.md"
                & git add . 2>$null
                & git commit -m "change" --quiet 2>$null

                $TestInput = '{"tool_input": {"command": "gh pr create --title \"Update docs\""}}'
                $Output = $TestInput | & $ScriptPath
                $LASTEXITCODE | Should -Be 0
                $Output | Should -BeNullOrEmpty
            }
            finally {
                Set-Location $OriginalLocation
                Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Blocks PR creation when code files are changed alongside docs" {
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents" "sessions") -Force | Out-Null

            try {
                Set-Location $TempDir
                & git init --quiet 2>$null
                & git config user.email "test@test.com" 2>$null
                & git config user.name "Test" 2>$null
                "# Initial" | Set-Content "README.md"
                "test" | Set-Content "script.ps1"
                & git add . 2>$null
                & git commit -m "initial" --quiet 2>$null
                & git branch "origin/main" HEAD 2>$null
                "# Updated" | Set-Content "README.md"
                "changed" | Set-Content "script.ps1"
                & git add . 2>$null
                & git commit -m "change" --quiet 2>$null

                $TestInput = '{"tool_input": {"command": "gh pr create --title \"Update\""}}'
                $Output = ($TestInput | & $ScriptPath) -join "`n"
                $Output | Should -Match "QA VALIDATION GATE"
            }
            finally {
                Set-Location $OriginalLocation
                Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context "Bypass conditions - Environment variable" {
        It "Allows PR creation when SKIP_QA_GATE is set" {
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents" "sessions") -Force | Out-Null

            try {
                Set-Location $TempDir
                & git init --quiet 2>$null
                & git config user.email "test@test.com" 2>$null
                & git config user.name "Test" 2>$null
                "test" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "initial" --quiet 2>$null
                & git branch "origin/main" HEAD 2>$null
                "changed" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "change" --quiet 2>$null

                $env:SKIP_QA_GATE = 'true'
                $TestInput = '{"tool_input": {"command": "gh pr create --title test"}}'
                $Output = $TestInput | & $ScriptPath
                $LASTEXITCODE | Should -Be 0
                $Output | Should -BeNullOrEmpty
            }
            finally {
                $env:SKIP_QA_GATE = $null
                Set-Location $OriginalLocation
                Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context "Error message content" {
        BeforeEach {
            $env:SKIP_QA_GATE = $null
        }

        AfterEach {
            $env:SKIP_QA_GATE = $null
        }

        It "Includes guidance to run qa agent" {
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents" "sessions") -Force | Out-Null

            try {
                Set-Location $TempDir
                & git init --quiet 2>$null
                & git config user.email "test@test.com" 2>$null
                & git config user.name "Test" 2>$null
                "test" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "initial" --quiet 2>$null
                & git branch "origin/main" HEAD 2>$null
                "changed" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "change" --quiet 2>$null

                $TestInput = '{"tool_input": {"command": "gh pr create"}}'
                $Output = ($TestInput | & $ScriptPath) -join "`n"
                $Output | Should -Match "qa"
                $Output | Should -Match "subagentType"
            }
            finally {
                Set-Location $OriginalLocation
                Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Includes guidance to create QA report" {
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents" "sessions") -Force | Out-Null

            try {
                Set-Location $TempDir
                & git init --quiet 2>$null
                & git config user.email "test@test.com" 2>$null
                & git config user.name "Test" 2>$null
                "test" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "initial" --quiet 2>$null
                & git branch "origin/main" HEAD 2>$null
                "changed" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "change" --quiet 2>$null

                $TestInput = '{"tool_input": {"command": "gh pr create"}}'
                $Output = ($TestInput | & $ScriptPath) -join "`n"
                $Output | Should -Match "\.agents/qa/"
            }
            finally {
                Set-Location $OriginalLocation
                Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Output is valid JSON" {
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents" "sessions") -Force | Out-Null

            try {
                Set-Location $TempDir
                & git init --quiet 2>$null
                & git config user.email "test@test.com" 2>$null
                & git config user.name "Test" 2>$null
                "test" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "initial" --quiet 2>$null
                & git branch "origin/main" HEAD 2>$null
                "changed" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "change" --quiet 2>$null

                $TestInput = '{"tool_input": {"command": "gh pr create"}}'
                $Output = ($TestInput | & $ScriptPath) -join "`n"
                $Parsed = $Output | ConvertFrom-Json
                $Parsed.decision | Should -Be "deny"
                $Parsed.reason | Should -Not -BeNullOrEmpty
            }
            finally {
                Set-Location $OriginalLocation
                Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context "Documentation-only detection hardening" {
        BeforeEach {
            $env:SKIP_QA_GATE = $null
        }

        AfterEach {
            $env:SKIP_QA_GATE = $null
        }

        It "Blocks PR creation when git diff base comparison fails (fail safely)" {
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TempDir ".agents" "sessions") -Force | Out-Null

            try {
                Set-Location $TempDir
                & git init --quiet 2>$null
                & git config user.email "test@test.com" 2>$null
                & git config user.name "Test" 2>$null

                "test" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "initial" --quiet 2>$null

                # Commit a code change, but do NOT create origin/main ref.
                "changed" | Set-Content "test.ps1"
                & git add . 2>$null
                & git commit -m "change" --quiet 2>$null

                $TestInput = '{"tool_input": {"command": "gh pr create --title test"}}'
                $Output = ($TestInput | & $ScriptPath) -join "`n"
                $Output | Should -Match "QA VALIDATION GATE"
            }
            finally {
                Set-Location $OriginalLocation
                Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }
}
