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
            # Current behavior: Test-ADRReviewEvidence checks debate log existence only
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
            # Current behavior: Test-ADRReviewEvidence searches for ANY file matching *debate*.md
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
            # Current behavior: Test-ADRReviewEvidence checks debate log existence only
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

        It "Currently allows commit when staging multiple ADRs without matching debate logs for each (SECURITY GAP - documents multi-ADR bypass threat)" {
            # SECURITY GAP DOCUMENTATION:
            # Threat model: Agent stages ADR-001.md, ADR-002.md, ADR-003.md but only one debate log exists (ADR-001)
            # Current behavior: Test-ADRReviewEvidence checks for ANY debate log, doesn't verify matching
            # Desired behavior: Require debate log for EACH staged ADR file
            # Mitigation priority: P0 (HIGH risk - obvious semantic bypass)
            # Risk: HIGH - Multiple ADRs can bypass review by having only one debate log
            #
            # Expected future behavior:
            #   1. Extract all ADR numbers from staged files (e.g., "001", "002", "003")
            #   2. For each staged ADR, verify matching debate log exists (ADR-001-debate-log.md, ADR-002-debate-log.md, etc.)
            #   3. Block if ANY staged ADR lacks matching debate log
            #   4. Return list of missing debate logs in error message

            # Stage multiple ADR files
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/architecture/ADR-001.md") -Value "# ADR-001: First Decision"
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/architecture/ADR-002.md") -Value "# ADR-002: Second Decision"
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/architecture/ADR-003.md") -Value "# ADR-003: Third Decision"

            # Only ONE debate log exists (for ADR-001), others missing
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/analysis/ADR-001-debate-log.md") -Value "# ADR-001 Debate Log`n`nConsensus achieved for ADR-001."

            # Stage all three ADR files
            Push-Location $Script:TestRootDebateLog
            git add .agents/architecture/ADR-001.md
            git add .agents/architecture/ADR-002.md
            git add .agents/architecture/ADR-003.md
            Pop-Location

            # Session log claims review (doesn't specify which ADRs)
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                workLog = @(
                    @{ action = "Executed /adr-review skill"; result = "multi-agent consensus achieved" }
                )
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/sessions/$today-session-999.json") -Value $sessionLog

            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathDebateLog -ProjectDir $Script:TestRootDebateLog -WorkingDir $Script:TestRootDebateLog
            # Current behavior: allows (exit 0) because ANY debate log exists (Test-ADRReviewEvidence uses wildcard filter)
            # Future: should block (exit 2) when per-ADR matching added
            # Expected error: "Missing debate logs: ADR-002-debate-log.md, ADR-003-debate-log.md"
            $result.ExitCode | Should -Be 0 -Because "Current implementation only checks for ANY debate log, doesn't verify one exists for each staged ADR (P0 security gap)"
        }

        It "Future: Should reject debate log with sufficient length but missing agent sections (when content parser implemented)" -Skip {
            # SECURITY GAP DOCUMENTATION:
            # Threat model: Agent creates 300-byte debate log with Lorem Ipsum + "Consensus achieved"
            # Current behavior: Test-ADRReviewEvidence only checks file existence, no content validation
            # Desired behavior: Validate debate log has:
            #   - Required sections: ## Architect, ## Critic, ## Independent-Thinker, etc.
            #   - Multiple consensus rounds (Round 1, Round 2)
            #   - Minimum length per section (50+ bytes)
            #   - No Lorem Ipsum or placeholder text
            # Mitigation priority: P0 (HIGH risk - bypasses consensus requirement with plausible content)
            # Risk: HIGH - Looks legitimate in quick review but has zero multi-agent participation
            #
            # Expected future behavior:
            #   1. Parse debate log markdown structure
            #   2. Verify presence of required agent headers (## Architect, ## Critic, ## Independent-Thinker, ## Security, ## Analyst, ## High-Level-Advisor)
            #   3. Verify each section has substantive content (minimum 50 bytes after header)
            #   4. Verify multiple consensus rounds exist (Round 1, Round 2, etc.)
            #   5. Detect placeholder text patterns (Lorem Ipsum, "placeholder", "TODO", etc.)
            #   6. Block if any validation fails with specific error message

            # Create debate log with sufficient length but missing agent sections
            $fakeContent = @"
# ADR-999 Debate Log

Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.

Consensus achieved after thorough review.
"@
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/analysis/ADR-999-debate-log.md") -Value $fakeContent

            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                workLog = @(
                    @{ action = "Executed /adr-review skill"; result = "multi-agent consensus achieved" }
                )
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/sessions/$today-session-999.json") -Value $sessionLog

            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathDebateLog -ProjectDir $Script:TestRootDebateLog -WorkingDir $Script:TestRootDebateLog
            # Future: should block (exit 2) when content structure parser implemented
            # Expected error: "Debate log missing required agent sections: ## Architect, ## Critic, ## Independent-Thinker"
            $result.ExitCode | Should -Be 2 -Because "Future implementation should validate debate log has proper multi-agent structure"
            $result.Output | Should -Match "missing required agent sections"
        }

        It "Future: Should block when debate log timestamp is 10+ days older than session log (when timestamp correlation implemented)" -Skip {
            # SECURITY GAP DOCUMENTATION (P1 Issue 3: Timestamp correlation test missing):
            # Threat model: Debate log from ADR-999 created 10 days ago is reused for new session today,
            # bypassing temporal correlation check. Stale consensus evidence should not validate fresh ADR changes.
            # Current behavior: Hook does not validate timestamp correlation between debate log and session log
            # Desired behavior: Reject if debate log creation date differs from session date by more than 1 day
            # Mitigation priority: P1 (Criticality: 7/10) - Prevents stale consensus reuse
            # Risk: MEDIUM - Allows reusing old debate logs for new ADR changes without re-review
            #
            # Expected future behavior:
            #   1. Extract debate log creation date from file metadata or embedded timestamp
            #   2. Extract session date from session log JSON
            #   3. Calculate delta between dates
            #   4. Block if delta > 1 day (allows same-day or next-day commits)
            #   5. Error message: "Debate log ADR-999-debate-log.md is 10 days old but session is today; re-run adr-review skill"

            # Create debate log dated 10 days ago (simulate old file)
            $oldDate = (Get-Date).AddDays(-10)
            $debateLogPath = Join-Path $Script:TestRootDebateLog ".agents/analysis/ADR-999-debate-log.md"
            Set-Content -Path $debateLogPath -Value "# ADR-999 Debate Log`n`nConsensus achieved on $($oldDate.ToString('yyyy-MM-dd'))."
            # Set file modification time to 10 days ago
            (Get-Item $debateLogPath).LastWriteTime = $oldDate

            # Session log created today
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                workLog = @(
                    @{ action = "Executed /adr-review skill"; result = "multi-agent consensus achieved" }
                )
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/sessions/$today-session-999.json") -Value $sessionLog

            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathDebateLog -ProjectDir $Script:TestRootDebateLog -WorkingDir $Script:TestRootDebateLog
            # Future: should block (exit 2) when timestamp correlation check implemented
            # Expected error: "Debate log is 10 days old but session is today"
            $result.ExitCode | Should -Be 2 -Because "Debate log 10 days old should not validate session today"
            $result.Output | Should -Match "debate log.*10 days old"
        }

        It "Future: Should extract ADR number from staged file and require matching debate log (when ADR number extraction implemented)" -Skip {
            # SECURITY GAP DOCUMENTATION (P1 Issue 4: ADR number extraction test missing):
            # Threat model: Hook should extract ADR number from staged file path (e.g., "999" from ".agents/architecture/ADR-999.md")
            # and verify matching debate log exists (e.g., ".agents/analysis/ADR-999-debate-log.md").
            # Current behavior: Hook searches for ANY file matching *debate*.md without verifying ADR number match
            # Desired behavior: Extract ADR number, lookup matching debate log, block if no match
            # Mitigation priority: P1 (Criticality: 7/10) - Prevents mismatched debate logs
            # Risk: MEDIUM - Allows using ADR-001 debate log for ADR-999 changes
            #
            # Expected future behavior:
            #   1. Parse staged file path: ".agents/architecture/ADR-999.md" -> extract "999"
            #   2. Construct expected debate log path: ".agents/analysis/ADR-999-debate-log.md"
            #   3. Verify file exists at exact path
            #   4. Parse debate log header: "# ADR-999 Debate Log" -> extract "999"
            #   5. Verify staged ADR number matches debate log ADR number
            #   6. Block if numbers don't match or debate log missing
            #   7. Error message: "ADR-999 requires debate log ADR-999-debate-log.md, found only ADR-001-debate-log.md"

            # Stage ADR-999
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/architecture/ADR-999.md") -Value "# ADR-999: Test Decision"
            Push-Location $Script:TestRootDebateLog
            git add .agents/architecture/ADR-999.md
            Pop-Location

            # Only ADR-001 debate log exists (wrong number)
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/analysis/ADR-001-debate-log.md") -Value "# ADR-001 Debate Log`n`nConsensus for different ADR."

            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                workLog = @(
                    @{ action = "Executed /adr-review skill"; result = "multi-agent consensus achieved" }
                )
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/sessions/$today-session-999.json") -Value $sessionLog

            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathDebateLog -ProjectDir $Script:TestRootDebateLog -WorkingDir $Script:TestRootDebateLog
            # Future: should block (exit 2) when ADR number extraction and matching implemented
            # Expected error: "ADR-999 requires debate log ADR-999-debate-log.md, found only ADR-001-debate-log.md"
            $result.ExitCode | Should -Be 2 -Because "Mismatched ADR numbers should be rejected"
            $result.Output | Should -Match "ADR-999 requires.*ADR-999-debate-log\.md"
        }

        It "Future: Should block when debate log has future timestamp (when temporal validation implemented)" -Skip {
            # SECURITY GAP DOCUMENTATION (P1 Issue 5: Debate log future timestamp test missing):
            # Threat model: Debate log dated tomorrow should be rejected as temporal anomaly.
            # A debate log from the future indicates either system clock manipulation or test data injection.
            # Current behavior: Hook does not validate debate log timestamp against current date
            # Desired behavior: Reject debate logs with creation date > current date
            # Mitigation priority: P1 (Criticality: 7/10) - Prevents temporal bypass threats
            # Risk: LOW - Future timestamp is obvious anomaly, but should be caught programmatically
            #
            # Expected future behavior:
            #   1. Extract debate log creation date from file metadata
            #   2. Compare to current system date
            #   3. Block if debate log date > current date
            #   4. Error message: "Debate log ADR-999-debate-log.md has future timestamp (tomorrow), rejecting as temporal anomaly"

            # Create debate log dated tomorrow
            $futureDate = (Get-Date).AddDays(1)
            $debateLogPath = Join-Path $Script:TestRootDebateLog ".agents/analysis/ADR-999-debate-log.md"
            Set-Content -Path $debateLogPath -Value "# ADR-999 Debate Log`n`nConsensus achieved on $($futureDate.ToString('yyyy-MM-dd'))."
            # Set file modification time to tomorrow
            (Get-Item $debateLogPath).LastWriteTime = $futureDate

            # Session log created today
            $today = Get-Date -Format "yyyy-MM-dd"
            $sessionLog = @{
                session = @{ number = 999; date = $today; branch = "test"; startingCommit = "abc"; objective = "Test" }
                workLog = @(
                    @{ action = "Executed /adr-review skill"; result = "multi-agent consensus achieved" }
                )
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRootDebateLog ".agents/sessions/$today-session-999.json") -Value $sessionLog

            $result = Invoke-HookWithInput -Command "git commit -m 'test'" -HookPath $Script:TempHookPathDebateLog -ProjectDir $Script:TestRootDebateLog -WorkingDir $Script:TestRootDebateLog
            # Future: should block (exit 2) when temporal validation implemented
            # Expected error: "Debate log has future timestamp, rejecting as temporal anomaly"
            $result.ExitCode | Should -Be 2 -Because "Future timestamp indicates temporal anomaly"
            $result.Output | Should -Match "future timestamp.*temporal anomaly"
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
