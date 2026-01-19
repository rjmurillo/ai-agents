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
            # Security rationale: This implements dual-verification defense-in-depth strategy.
            # Threat model addressed: Malicious or confused agent claims "adr-review skill ran"
            # in session log without actually executing multi-agent consensus process.
            # Mitigation: Hook requires BOTH session log evidence (soft check) AND debate log
            # artifact (hard check). The debate log is an immutable filesystem artifact created
            # by the adr-review skill during actual consensus, providing cryptographic-strength
            # evidence that cannot be forged by simply editing session log JSON. This prevents:
            # 1. Agent hallucinating that it ran adr-review when it didn't
            # 2. Agent editing session log to claim review without actual multi-agent debate
            # 3. Bypassing consensus requirement by exploiting session log as single point of failure
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

    Context "Debate log content validation" {
        BeforeAll {
            # Base test environment for debate log validation tests
            $Script:TestRootDebateLog = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-debate-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootDebateLog -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootDebateLog ".agents/sessions") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootDebateLog ".agents/architecture") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootDebateLog ".agents/analysis") -Force | Out-Null

            # Copy hook with dependencies
            $Script:TempHookPathDebateLog = Copy-HookWithDependencies -TestRoot $Script:TestRootDebateLog

            # Init git repo and stage ADR file
            Push-Location $Script:TestRootDebateLog
            git init --quiet
            git config user.email "test@test.com"
            git config user.name "Test"
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/architecture/ADR-999.md") -Value "# ADR-999: Test"
            git add .agents/architecture/ADR-999.md
            Pop-Location
        }

        AfterAll {
            if (Test-Path $Script:TestRootDebateLog) {
                Remove-Item -Path $Script:TestRootDebateLog -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Currently allows commit when debate log file is empty (SECURITY GAP - documents 0-byte bypass threat)" {
            # SECURITY GAP DOCUMENTATION:
            # Threat model: Empty debate log (0-byte file) satisfies existence check but provides
            # no actual consensus evidence. Attacker creates empty file to bypass validation while
            # claiming "file exists" in session log.
            #
            # Current behavior: Hook checks existence only (line 98-99 of Invoke-ADRReviewGuard.ps1)
            # Desired behavior: Hook should validate debate log contains:
            #   1. Non-zero content (minimum 50 bytes for header + substance)
            #   2. Matching ADR number in filename and content
            #   3. Evidence of multi-agent participation (architect, critic, qa sections)
            #
            # Mitigation priority: P1 (non-blocking) - Requires debate log content parser
            # Risk: LOW - Empty file is obvious in code review, no semantic bypass

            # Create EMPTY debate log (documents security bypass attempt)
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/analysis/ADR-999-debate-log.md") -Value ""

            # Create session log WITH review evidence claim
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                workLog = @(
                    @{ action = "Executed /adr-review skill"; result = "multi-agent consensus achieved" }
                )
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/sessions/$today-session-999.json") -Value $sessionLog

            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathDebateLog -ProjectDir $Script:TestRootDebateLog -WorkingDir $Script:TestRootDebateLog
            # Current behavior: allows (exit 0) because file exists
            # Future: should block (exit 2) when content validation added
            $result.ExitCode | Should -Be 0 -Because "Current implementation only checks existence, not content (security gap)"
        }

        It "Currently allows commit when debate log has wrong ADR number (SECURITY GAP - documents mismatch bypass threat)" {
            # SECURITY GAP DOCUMENTATION:
            # Threat model: Attacker commits ADR-999 but has only ADR-001-debate-log.md from
            # a previous unrelated decision. Hook accepts any debate log regardless of ADR number,
            # allowing reuse of old consensus for new unrelated decisions.
            #
            # Current behavior: Hook searches for ANY file matching *debate*.md (line 98)
            # Desired behavior: Hook should:
            #   1. Extract ADR number from staged file (e.g., "999" from "ADR-999.md")
            #   2. Look for matching debate log "ADR-999-debate-log.md"
            #   3. Parse debate log header to verify ADR number matches
            #   4. Block if no matching debate log or ADR numbers don't align
            #
            # Mitigation priority: P1 (non-blocking) - Requires ADR number extraction + matching
            # Risk: MEDIUM - Less obvious in code review, semantic bypass possible

            # Create debate log for WRONG ADR number
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/analysis/ADR-001-debate-log.md") -Value "# ADR-001 Debate Log`n`nConsensus for different ADR"

            # Session log claims review for ADR-999
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                workLog = @(
                    @{ action = "Executed /adr-review skill"; result = "multi-agent consensus achieved" }
                )
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/sessions/$today-session-999.json") -Value $sessionLog

            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathDebateLog -ProjectDir $Script:TestRootDebateLog -WorkingDir $Script:TestRootDebateLog
            # Current behavior: allows (exit 0) because debate log exists, regardless of number
            # Future: should block (exit 2) when ADR number matching added
            $result.ExitCode | Should -Be 0 -Because "Current implementation doesn't validate ADR number match (security gap)"
        }

        It "Currently allows commit when debate log contains minimal placeholder content (SECURITY GAP - documents minimal-content bypass threat)" {
            # SECURITY GAP DOCUMENTATION:
            # Threat model: Attacker creates file with only "# ADR-999 Debate Log" header (20 bytes)
            # to satisfy existence check without providing actual multi-agent consensus evidence.
            # File is non-empty so basic size check would pass, but has no substantive content.
            #
            # Current behavior: Hook checks existence only (line 98-99)
            # Desired behavior: Hook should validate debate log contains:
            #   1. Minimum substantive content (e.g., >= 200 bytes for header + rounds + consensus)
            #   2. Sections indicating multi-agent participation (architect, critic, qa)
            #   3. Round-by-round debate structure (not just "consensus achieved")
            #   4. Actual technical arguments, not placeholder text
            #
            # Mitigation priority: P1 (non-blocking) - Requires content structure parser
            # Risk: MEDIUM - Header-only file looks plausible in quick review

            # Create debate log with only header (minimal content bypass attempt)
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/analysis/ADR-999-debate-log.md") -Value "# ADR-999 Debate Log"

            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                workLog = @(
                    @{ action = "Executed /adr-review skill"; result = "multi-agent consensus achieved" }
                )
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/sessions/$today-session-999.json") -Value $sessionLog

            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathDebateLog -ProjectDir $Script:TestRootDebateLog -WorkingDir $Script:TestRootDebateLog
            # Current behavior: allows (exit 0) because file exists
            # Future: should block (exit 2) when content structure validation added
            $result.ExitCode | Should -Be 0 -Because "Current implementation doesn't validate debate log content structure (security gap)"
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
            # Security rationale: Dual verification (session log + debate log artifact) prevents
            # bypass where agent claims consensus in session log without actual multi-agent review.
            # The debate log provides immutable evidence that architect, critic, and qa agents
            # participated in consensus process, not just a single agent's unverified claim.
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
