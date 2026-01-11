#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Invoke-SkillFirstGuard.ps1

.DESCRIPTION
    Tests the PreToolUse hook that blocks raw gh commands when validated
    skill scripts exist for that operation.
#>

BeforeAll {
    # Import shared test utilities (Issue #859 Thread 4: DRY violation fix)
    Import-Module "$PSScriptRoot/TestUtilities.psm1" -Force

    $Script:HookPath = Join-Path $PSScriptRoot ".." ".claude" "hooks" "PreToolUse" "Invoke-SkillFirstGuard.ps1"

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

Describe "Invoke-SkillFirstGuard" {
    Context "Non-gh commands pass through" {
        It "Allows git commands (exit 0)" {
            $result = Invoke-HookWithInput -Command "git status"
            $result.ExitCode | Should -Be 0
        }

        It "Allows npm commands (exit 0)" {
            $result = Invoke-HookWithInput -Command "npm install"
            $result.ExitCode | Should -Be 0
        }

        It "Allows ls commands (exit 0)" {
            $result = Invoke-HookWithInput -Command "ls -la"
            $result.ExitCode | Should -Be 0
        }

        It "Allows pwsh commands (exit 0)" {
            $result = Invoke-HookWithInput -Command "pwsh -c 'Write-Host test'"
            $result.ExitCode | Should -Be 0
        }
    }

    Context "gh commands without matching skills pass through" {
        BeforeAll {
            # Create test environment WITHOUT skill scripts
            $Script:TestRootNoSkill = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-no-skill-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootNoSkill -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootNoSkill ".claude/hooks/PreToolUse") -Force | Out-Null

            # Copy hook
            $Script:TempHookPathNoSkill = Join-Path $Script:TestRootNoSkill ".claude/hooks/PreToolUse/Invoke-SkillFirstGuard.ps1"
            Copy-Item -Path $Script:HookPath -Destination $Script:TempHookPathNoSkill -Force
        }

        AfterAll {
            if (Test-Path $Script:TestRootNoSkill) {
                Remove-Item -Path $Script:TestRootNoSkill -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Allows gh pr view when no skill exists (exit 0)" {
            $result = Invoke-HookWithInput -Command "gh pr view 123" -HookPath $Script:TempHookPathNoSkill -ProjectDir $Script:TestRootNoSkill
            $result.ExitCode | Should -Be 0
        }

        It "Allows gh issue list when no skill exists (exit 0)" {
            $result = Invoke-HookWithInput -Command "gh issue list" -HookPath $Script:TempHookPathNoSkill -ProjectDir $Script:TestRootNoSkill
            $result.ExitCode | Should -Be 0
        }

        It "Allows gh repo clone (no mapped skill) (exit 0)" {
            $result = Invoke-HookWithInput -Command "gh repo clone owner/repo" -HookPath $Script:TempHookPathNoSkill -ProjectDir $Script:TestRootNoSkill
            $result.ExitCode | Should -Be 0
        }
    }

    Context "gh commands with matching skills block" {
        BeforeAll {
            # Create test environment WITH skill scripts
            $Script:TestRootWithSkill = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-with-skill-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootWithSkill -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootWithSkill ".claude/hooks/PreToolUse") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootWithSkill ".claude/skills/github/scripts/pr") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootWithSkill ".claude/skills/github/scripts/issue") -Force | Out-Null

            # Copy hook
            $Script:TempHookPathWithSkill = Join-Path $Script:TestRootWithSkill ".claude/hooks/PreToolUse/Invoke-SkillFirstGuard.ps1"
            Copy-Item -Path $Script:HookPath -Destination $Script:TempHookPathWithSkill -Force

            # Create skill scripts (exact mapping names)
            Set-Content -Path (Join-Path $Script:TestRootWithSkill ".claude/skills/github/scripts/pr/Get-PRContext.ps1") -Value "# Stub"
            Set-Content -Path (Join-Path $Script:TestRootWithSkill ".claude/skills/github/scripts/pr/Get-PullRequests.ps1") -Value "# Stub"
            Set-Content -Path (Join-Path $Script:TestRootWithSkill ".claude/skills/github/scripts/issue/Get-IssueContext.ps1") -Value "# Stub"
        }

        AfterAll {
            if (Test-Path $Script:TestRootWithSkill) {
                Remove-Item -Path $Script:TestRootWithSkill -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Blocks gh pr view when skill exists (exit 2)" {
            $result = Invoke-HookWithInput -Command "gh pr view 123" -HookPath $Script:TempHookPathWithSkill -ProjectDir $Script:TestRootWithSkill
            $result.ExitCode | Should -Be 2
        }

        It "Blocks gh pr list when skill exists (exit 2)" {
            $result = Invoke-HookWithInput -Command "gh pr list" -HookPath $Script:TempHookPathWithSkill -ProjectDir $Script:TestRootWithSkill
            $result.ExitCode | Should -Be 2
        }

        It "Blocks gh issue view when skill exists (exit 2)" {
            $result = Invoke-HookWithInput -Command "gh issue view 456" -HookPath $Script:TempHookPathWithSkill -ProjectDir $Script:TestRootWithSkill
            $result.ExitCode | Should -Be 2
        }

        It "Outputs blocking message with skill path" {
            $result = Invoke-HookWithInput -Command "gh pr view 123" -HookPath $Script:TempHookPathWithSkill -ProjectDir $Script:TestRootWithSkill
            $output = $result.Output -join "`n"
            $output | Should -Match "BLOCKED"
            $output | Should -Match "Get-PRContext"
        }

        It "Includes example usage in blocking message" {
            $result = Invoke-HookWithInput -Command "gh pr view 123" -HookPath $Script:TempHookPathWithSkill -ProjectDir $Script:TestRootWithSkill
            $output = $result.Output -join "`n"
            $output | Should -Match "pwsh"
            $output | Should -Match "PullRequest"
        }
    }

    Context "Fuzzy matching fallback" {
        BeforeAll {
            # Create test environment with fuzzy-matchable skill
            $Script:TestRootFuzzy = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-fuzzy-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRootFuzzy -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootFuzzy ".claude/hooks/PreToolUse") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRootFuzzy ".claude/skills/github/scripts/pr") -Force | Out-Null

            # Copy hook
            $Script:TempHookPathFuzzy = Join-Path $Script:TestRootFuzzy ".claude/hooks/PreToolUse/Invoke-SkillFirstGuard.ps1"
            Copy-Item -Path $Script:HookPath -Destination $Script:TempHookPathFuzzy -Force

            # Create a script with "diff" in name but not in exact mapping
            Set-Content -Path (Join-Path $Script:TestRootFuzzy ".claude/skills/github/scripts/pr/Get-PRDiff.ps1") -Value "# Stub for diff"
        }

        AfterAll {
            if (Test-Path $Script:TestRootFuzzy) {
                Remove-Item -Path $Script:TestRootFuzzy -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Blocks gh pr diff via fuzzy match (exit 2)" {
            $result = Invoke-HookWithInput -Command "gh pr diff 123" -HookPath $Script:TempHookPathFuzzy -ProjectDir $Script:TestRootFuzzy
            $result.ExitCode | Should -Be 2
        }

        It "Fuzzy match output includes matched script name" {
            $result = Invoke-HookWithInput -Command "gh pr diff 123" -HookPath $Script:TempHookPathFuzzy -ProjectDir $Script:TestRootFuzzy
            $output = $result.Output -join "`n"
            $output | Should -Match "Get-PRDiff"
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

        It "Handles gh with single word only (exit 0)" {
            $result = Invoke-HookWithInput -Command "gh auth login"
            $result.ExitCode | Should -Be 0
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
