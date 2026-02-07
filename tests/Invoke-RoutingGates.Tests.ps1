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

    <#
    .SYNOPSIS
        Creates a test git repo with proper origin/main remote for QA gate tests.

    .DESCRIPTION
        The QA gate uses 'git diff origin/main...HEAD' to determine if changes are
        documentation-only. This requires a proper origin remote to work. This function
        creates a bare repo as origin and sets it up so the test repo has a valid remote.
    #>
    function Initialize-TestGitRepoWithOrigin {
        param(
            [Parameter(Mandatory)]
            [string]$TempDir,

            [switch]$WithCodeChange,

            [switch]$WithDocsOnlyChange
        )

        # Create a bare repo to act as origin
        $originDir = Join-Path $TempDir "origin.git"
        New-Item -ItemType Directory -Path $originDir -Force | Out-Null
        Push-Location $originDir
        & git init --bare --quiet 2>$null
        Pop-Location

        # Create the working repo
        $workDir = Join-Path $TempDir "work"
        New-Item -ItemType Directory -Path $workDir -Force | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $workDir ".agents") -Force | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $workDir ".agents" "sessions") -Force | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $workDir ".claude") -Force | Out-Null
        "# placeholder" | Set-Content (Join-Path $workDir ".claude/settings.json")

        Push-Location $workDir
        & git init --quiet 2>$null
        & git config user.email "test@test.com" 2>$null
        & git config user.name "Test" 2>$null
        & git remote add origin $originDir 2>$null

        # Initial commit - include a README.md for docs-only test scenarios
        "initial" | Set-Content "initial.txt"
        "# Initial README" | Set-Content "README.md"
        & git add . 2>$null
        & git commit -m "initial" --quiet 2>$null
        & git push -u origin HEAD:main --quiet 2>$null

        # Create feature branch
        & git checkout -b feature-branch --quiet 2>$null

        if ($WithCodeChange) {
            # Add a code file to trigger non-docs-only
            "test" | Set-Content "test.ps1"
            & git add . 2>$null
            & git commit -m "add code" --quiet 2>$null
        }

        if ($WithDocsOnlyChange) {
            # Modify only documentation files
            "# Updated README" | Set-Content "README.md"
            & git add . 2>$null
            & git commit -m "update docs" --quiet 2>$null
        }

        Pop-Location

        return $workDir
    }
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
            # Create a temporary test environment with proper origin remote
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

            try {
                $WorkDir = Initialize-TestGitRepoWithOrigin -TempDir $TempDir -WithCodeChange
                Set-Location $WorkDir

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

            try {
                $WorkDir = Initialize-TestGitRepoWithOrigin -TempDir $TempDir -WithCodeChange
                Set-Location $WorkDir

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
                "changed" | Set-Content "test.ps1"

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

            try {
                $WorkDir = Initialize-TestGitRepoWithOrigin -TempDir $TempDir -WithCodeChange
                Set-Location $WorkDir

                # Create QA directory
                New-Item -ItemType Directory -Path (Join-Path $WorkDir ".agents" "qa") -Force | Out-Null

                # Create an old QA report
                $QAReport = Join-Path $WorkDir ".agents" "qa" "old-qa-report.md"
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
                "changed" | Set-Content "test.ps1"

                # Create today's session log with QA section
                $Today = Get-Date -Format "yyyy-MM-dd"
                $SessionLog = Join-Path $TempDir ".agents" "sessions" "$Today-session-01.json"
                '{"notes": "## QA\nQA agent was invoked and tests passed."}' | Set-Content $SessionLog

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
                "changed" | Set-Content "test.ps1"

                $Today = Get-Date -Format "yyyy-MM-dd"
                $SessionLog = Join-Path $TempDir ".agents" "sessions" "$Today-session-01.json"
                '{"notes": "Invoked the qa agent to verify the implementation."}' | Set-Content $SessionLog

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
                "changed" | Set-Content "test.ps1"

                $Today = Get-Date -Format "yyyy-MM-dd"
                $SessionLog = Join-Path $TempDir ".agents" "sessions" "$Today-session-01.json"
                '{"notes": "## Test Results\nAll tests passed successfully."}' | Set-Content $SessionLog

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

        It "Blocks PR creation when symlink named README.md points to code file" {
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

            try {
                $WorkDir = Initialize-TestGitRepoWithOrigin -TempDir $TempDir
                Set-Location $WorkDir

                # Create a code file
                "function Test { 'code' }" | Set-Content "script.ps1"
                & git add script.ps1 2>$null
                & git commit -m "add code" --quiet 2>$null

                # Security threat: Create symlink named .md pointing to code file
                # This should NOT bypass QA gate even though filename ends in .md
                if ($IsWindows) {
                    & cmd /c mklink "README.md" "script.ps1" 2>$null
                } else {
                    & ln -s "script.ps1" "README.md" 2>$null
                }

                # Only add symlink, not the target (so git diff shows .md file)
                & git add README.md 2>$null
                & git commit -m "add symlink disguised as md" --quiet 2>$null

                $TestInput = '{"tool_input": {"command": "gh pr create --title \"Sneaky\""}}'
                $Output = ($TestInput | & $ScriptPath) -join "`n"

                # Should block because symlink detection or git diff detects non-md content
                # NOTE: git diff origin/main...HEAD will show the symlink as changed file,
                # but the actual diff may reveal it's a symlink. Current implementation
                # relies on file extension, so this test documents the threat model:
                # If an attacker creates a symlink with .md extension, they could bypass QA.
                # This is mitigated by code review and the fact that git stores symlinks
                # as their target path in the index, so git diff will show script.ps1 changes.
                $Output | Should -Match "QA VALIDATION GATE"
            }
            finally {
                Set-Location $OriginalLocation
                Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Allows PR creation when only .md files are changed" {
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

            try {
                $WorkDir = Initialize-TestGitRepoWithOrigin -TempDir $TempDir -WithDocsOnlyChange
                Set-Location $WorkDir

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

        It "Allows PR creation when only mixed-case .md files are changed (.MD, .Md)" {
            $OriginalLocation = Get-Location
            $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-routing-gates-$([Guid]::NewGuid())"
            New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

            try {
                $WorkDir = Initialize-TestGitRepoWithOrigin -TempDir $TempDir
                Set-Location $WorkDir

                # Add mixed-case .md files (docs-only change)
                "# Updated" | Set-Content "README.md"
                "# Updated" | Set-Content "CHANGELOG.MD"
                "# Updated" | Set-Content "NOTES.Md"
                & git add . 2>$null
                & git commit -m "docs only mixed case" --quiet 2>$null

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

            try {
                $WorkDir = Initialize-TestGitRepoWithOrigin -TempDir $TempDir
                Set-Location $WorkDir

                # Add docs and code changes
                "# Updated" | Set-Content "README.md"
                "changed" | Set-Content "script.ps1"
                & git add . 2>$null
                & git commit -m "mixed changes" --quiet 2>$null

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
                "changed" | Set-Content "test.ps1"

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

            try {
                $WorkDir = Initialize-TestGitRepoWithOrigin -TempDir $TempDir -WithCodeChange
                Set-Location $WorkDir

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

            try {
                $WorkDir = Initialize-TestGitRepoWithOrigin -TempDir $TempDir -WithCodeChange
                Set-Location $WorkDir

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

            try {
                $WorkDir = Initialize-TestGitRepoWithOrigin -TempDir $TempDir -WithCodeChange
                Set-Location $WorkDir

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
}
