#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Invoke-ADRReviewGuard.ps1

.DESCRIPTION
    Tests the PreToolUse hook that blocks git commit with ADR changes
    unless adr-review skill was executed.
#>

BeforeAll {
    # Import shared test utilities (Issue #859 Thread 4: DRY violation fix)
    Import-Module "$PSScriptRoot/TestUtilities.psm1" -Force

    $Script:HookPath = Join-Path $PSScriptRoot ".." ".claude" "hooks" "PreToolUse" "Invoke-ADRReviewGuard.ps1"
    $Script:CommonModulePath = Join-Path $PSScriptRoot ".." ".claude" "hooks" "Common" "HookUtilities.psm1"

    if (-not (Test-Path $Script:HookPath)) {
        throw "Hook script not found at: $Script:HookPath"
    }

    if (-not (Test-Path $Script:CommonModulePath)) {
        throw "Common module not found at: $Script:CommonModulePath"
    }

    # Wrapper function for backward compatibility with existing tests
    function Invoke-HookWithInput {
        param(
            [string]$Command,
            [string]$HookPath = $Script:HookPath,
            [string]$ProjectDir = $null,
            [string]$WorkingDir = $null
        )
        Invoke-HookInNewProcess -Command $Command -HookPath $HookPath -ProjectDir $ProjectDir -WorkingDir $WorkingDir
    }

    # Helper to copy hook and dependencies to test directory
    function Copy-HookWithDependencies {
        param(
            [string]$TestRoot,
            [string]$HookRelativePath = ".claude/hooks/PreToolUse/Invoke-ADRReviewGuard.ps1"
        )

        $hookDestDir = Split-Path (Join-Path $TestRoot $HookRelativePath) -Parent
        $commonDestDir = Join-Path $TestRoot ".claude/hooks/Common"

        New-Item -ItemType Directory -Path $hookDestDir -Force | Out-Null
        New-Item -ItemType Directory -Path $commonDestDir -Force | Out-Null

        Copy-Item -Path $Script:HookPath -Destination (Join-Path $TestRoot $HookRelativePath) -Force
        Copy-Item -Path $Script:CommonModulePath -Destination (Join-Path $commonDestDir "HookUtilities.psm1") -Force

        return Join-Path $TestRoot $HookRelativePath
    }
}

Describe "Invoke-ADRReviewGuard" {
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

        It "Allows non-git commands (exit 0)" {
            $result = Invoke-HookWithInput -Command "ls -la"
            $result.ExitCode | Should -Be 0
        }
    }

    Context "Commit without ADR changes passes through" {
        BeforeAll {
            # Create a test git repo without ADR files staged
            $Script:TestRoot = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-no-adr-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRoot -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRoot ".agents/sessions") -Force | Out-Null

            # Copy hook with dependencies
            $Script:TempHookPath = Copy-HookWithDependencies -TestRoot $Script:TestRoot

            # Init git repo and stage non-ADR file
            Push-Location $Script:TestRoot
            git init --quiet
            git config user.email "test@test.com"
            git config user.name "Test"
            Set-Content -Path (Join-Path $Script:TestRoot "README.md") -Value "# Test"
            git add README.md
            Pop-Location
        }

        AfterAll {
            if (Test-Path $Script:TestRoot) {
                Remove-Item -Path $Script:TestRoot -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Allows commit when no ADR files are staged (exit 0)" {
            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPath -ProjectDir $Script:TestRoot -WorkingDir $Script:TestRoot
            $result.ExitCode | Should -Be 0
        }
    }

    Context "ADR changes without review blocks commit" {
        BeforeAll {
            # Create a test git repo WITH ADR file staged but NO review evidence
            $Script:TestRootADR = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-adr-no-review-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootADR -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootADR ".agents/sessions") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootADR ".agents/architecture") -Force | Out-Null

            # Copy hook with dependencies
            $Script:TempHookPathADR = Copy-HookWithDependencies -TestRoot $Script:TestRootADR

            # Create session log WITHOUT review evidence
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                protocolCompliance = @{
                    sessionStart = @{ branchVerification = @{ complete = $true; level = "MUST"; evidence = "test" } }
                    sessionEnd = @{ commitMade = @{ complete = $true; level = "MUST"; evidence = "test" } }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootADR ".agents/sessions/$today-session-999.json") -Value $sessionLog

            # Init git repo and stage ADR file
            Push-Location $Script:TestRootADR
            git init --quiet
            git config user.email "test@test.com"
            git config user.name "Test"
            Set-Content -Path (Join-Path $Script:TestRootADR ".agents/architecture/ADR-999.md") -Value "# ADR-999: Test"
            git add .agents/architecture/ADR-999.md
            Pop-Location
        }

        AfterAll {
            if (Test-Path $Script:TestRootADR) {
                Remove-Item -Path $Script:TestRootADR -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Blocks commit when ADR files staged without review (exit 2)" {
            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathADR -ProjectDir $Script:TestRootADR -WorkingDir $Script:TestRootADR
            $result.ExitCode | Should -Be 2
        }

        It "Outputs blocking message with adr-review instruction" {
            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathADR -ProjectDir $Script:TestRootADR -WorkingDir $Script:TestRootADR
            $output = $result.Output -join "`n"
            $output | Should -Match "BLOCKED"
            $output | Should -Match "adr-review"
        }
    }

    Context "ADR evidence pattern matching" {
        BeforeAll {
            # Create test environment with ADR file staged
            $Script:TestRootPatterns = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-adr-patterns-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootPatterns -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootPatterns ".agents/sessions") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootPatterns ".agents/architecture") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootPatterns ".agents/analysis") -Force | Out-Null

            # Copy hook with dependencies
            $Script:TempHookPathPatterns = Copy-HookWithDependencies -TestRoot $Script:TestRootPatterns

            # Create debate log artifact (required by hook per rjmurillo #2679845429)
            Set-Content -Path (Join-Path $Script:TestRootPatterns ".agents/analysis/ADR-999-debate-log.md") -Value "# ADR-999 Debate Log`n`nConsensus achieved."

            # Init git repo and stage ADR file
            Push-Location $Script:TestRootPatterns
            git init --quiet
            git config user.email "test@test.com"
            git config user.name "Test"
            Set-Content -Path (Join-Path $Script:TestRootPatterns ".agents/architecture/ADR-999.md") -Value "# ADR-999: Test"
            git add .agents/architecture/ADR-999.md
            Pop-Location
        }

        AfterAll {
            if (Test-Path $Script:TestRootPatterns) {
                Remove-Item -Path $Script:TestRootPatterns -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Pattern 1: /adr-review skill invocation" {
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                workLog = @(
                    @{ action = "Invoked /adr-review"; result = "success" }
                )
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootPatterns ".agents/sessions/$today-session-999.json") -Value $sessionLog

            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathPatterns -ProjectDir $Script:TestRootPatterns -WorkingDir $Script:TestRootPatterns
            $result.ExitCode | Should -Be 0
        }

        It "Pattern 2: adr-review skill explicit reference" {
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                workLog = @(
                    @{ action = "Executed adr-review skill"; result = "consensus achieved" }
                )
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootPatterns ".agents/sessions/$today-session-999.json") -Value $sessionLog

            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathPatterns -ProjectDir $Script:TestRootPatterns -WorkingDir $Script:TestRootPatterns
            $result.ExitCode | Should -Be 0
        }

        It "Pattern 3: ADR Review Protocol header" {
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                workLog = @(
                    @{ action = "ADR Review Protocol initiated"; result = "completed" }
                )
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootPatterns ".agents/sessions/$today-session-999.json") -Value $sessionLog

            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathPatterns -ProjectDir $Script:TestRootPatterns -WorkingDir $Script:TestRootPatterns
            $result.ExitCode | Should -Be 0
        }

        It "Pattern 4: multi-agent consensus.*ADR" {
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                workLog = @(
                    @{ action = "Review"; result = "multi-agent consensus achieved for ADR change" }
                )
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootPatterns ".agents/sessions/$today-session-999.json") -Value $sessionLog

            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathPatterns -ProjectDir $Script:TestRootPatterns -WorkingDir $Script:TestRootPatterns
            $result.ExitCode | Should -Be 0
        }

        It "Pattern 5: architect.*planner.*qa workflow" {
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                workLog = @(
                    @{ action = "Review"; result = "architect analyzed, planner validated, qa approved" }
                )
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootPatterns ".agents/sessions/$today-session-999.json") -Value $sessionLog

            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathPatterns -ProjectDir $Script:TestRootPatterns -WorkingDir $Script:TestRootPatterns
            $result.ExitCode | Should -Be 0
        }
    }

    Context "ADR changes with review evidence allows commit" {
        BeforeAll {
            # Create a test git repo WITH ADR file AND review evidence
            $Script:TestRootReviewed = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-adr-reviewed-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootReviewed -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootReviewed ".agents/sessions") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootReviewed ".agents/architecture") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootReviewed ".agents/analysis") -Force | Out-Null

            # Copy hook with dependencies
            $Script:TempHookPathReviewed = Copy-HookWithDependencies -TestRoot $Script:TestRootReviewed

            # Create debate log artifact (required by hook per rjmurillo #2679845429)
            Set-Content -Path (Join-Path $Script:TestRootReviewed ".agents/analysis/ADR-999-debate-log.md") -Value "# ADR-999 Debate Log`n`nConsensus achieved."

            # Create session log WITH review evidence
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test ADR review" }
                protocolCompliance = @{
                    sessionStart = @{ branchVerification = @{ complete = $true; level = "MUST"; evidence = "test" } }
                    sessionEnd = @{ commitMade = @{ complete = $true; level = "MUST"; evidence = "test" } }
                }
                workLog = @(
                    @{ action = "Executed /adr-review skill"; result = "multi-agent consensus achieved" }
                )
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootReviewed ".agents/sessions/$today-session-999.json") -Value $sessionLog

            # Init git repo and stage ADR file
            Push-Location $Script:TestRootReviewed
            git init --quiet
            git config user.email "test@test.com"
            git config user.name "Test"
            Set-Content -Path (Join-Path $Script:TestRootReviewed ".agents/architecture/ADR-999.md") -Value "# ADR-999: Test"
            git add .agents/architecture/ADR-999.md
            Pop-Location
        }

        AfterAll {
            if (Test-Path $Script:TestRootReviewed) {
                Remove-Item -Path $Script:TestRootReviewed -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Allows commit when ADR files have review evidence (exit 0)" {
            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathReviewed -ProjectDir $Script:TestRootReviewed -WorkingDir $Script:TestRootReviewed
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
    }

    Context "Script structure" {
        It "Script parses without errors" {
            $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile($Script:HookPath, [ref]$null, [ref]$errors)
            $errors | Should -BeNullOrEmpty
        }
    }
}
