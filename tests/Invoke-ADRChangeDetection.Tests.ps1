<#
.SYNOPSIS
    Pester tests for Invoke-ADRChangeDetection.ps1 hook.

.DESCRIPTION
    Tests the ADR change detection hook functionality including:
    - Script behavior when detection script is missing
    - Output formatting when changes are detected
    - No output when no changes detected
    - Error handling for failed detection
    - Path validation for non-git repositories
    - Exit code propagation from subprocess

.NOTES
    Requires Pester 5.x or later.
#>

BeforeAll {
    $Script:HookPath = Join-Path $PSScriptRoot ".." ".claude" "hooks" "Invoke-ADRChangeDetection.ps1"

    # Verify script exists
    if (-not (Test-Path $Script:HookPath)) {
        throw "Hook script not found at: $Script:HookPath"
    }
}

Describe "Invoke-ADRChangeDetection" {
    BeforeEach {
        # Create temp directory structure for testing
        $Script:TestRoot = Join-Path ([System.IO.Path]::GetTempPath()) "adr-hook-test-$(Get-Random)"
        New-Item -ItemType Directory -Path $Script:TestRoot -Force | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $Script:TestRoot ".git") -Force | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $Script:TestRoot ".claude/skills/adr-review/scripts") -Force | Out-Null
    }

    AfterEach {
        # Cleanup temp directory
        if (Test-Path $Script:TestRoot) {
            Remove-Item -Path $Script:TestRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Context "When detection script is missing" {
        It "Should exit 0 silently" {
            # Do not create the detection script
            $env:CLAUDE_PROJECT_DIR = $Script:TestRoot

            $result = & $Script:HookPath 2>&1
            $LASTEXITCODE | Should -Be 0
            $result | Should -BeNullOrEmpty
        }
    }

    Context "When not a git repository" {
        It "Should warn and exit 0" {
            # Remove .git directory
            Remove-Item -Path (Join-Path $Script:TestRoot ".git") -Recurse -Force
            $env:CLAUDE_PROJECT_DIR = $Script:TestRoot

            $result = & $Script:HookPath 2>&1 3>&1
            $LASTEXITCODE | Should -Be 0
            # Should contain warning about not being a git repository
            $warnings = $result | Where-Object { $_ -is [System.Management.Automation.WarningRecord] }
            $warnings | Should -Not -BeNullOrEmpty
        }
    }

    Context "When detection script returns no changes" {
        BeforeEach {
            # Create mock detection script that returns no changes
            $mockScript = @'
[CmdletBinding()]
param([string]$BasePath, [switch]$IncludeUntracked)
@{
    HasChanges = $false
    Created = @()
    Modified = @()
    Deleted = @()
} | ConvertTo-Json
exit 0
'@
            $detectScriptPath = Join-Path $Script:TestRoot ".claude/skills/adr-review/scripts/Detect-ADRChanges.ps1"
            Set-Content -Path $detectScriptPath -Value $mockScript
        }

        It "Should exit 0 with no output" {
            $env:CLAUDE_PROJECT_DIR = $Script:TestRoot

            $result = & $Script:HookPath 2>&1
            $LASTEXITCODE | Should -Be 0
            $result | Should -BeNullOrEmpty
        }
    }

    Context "When detection script returns changes" {
        BeforeEach {
            # Create mock detection script that returns changes
            $mockScript = @'
[CmdletBinding()]
param([string]$BasePath, [switch]$IncludeUntracked)
@{
    HasChanges = $true
    Created = @(".agents/architecture/ADR-999-test.md")
    Modified = @()
    Deleted = @()
} | ConvertTo-Json
exit 0
'@
            $detectScriptPath = Join-Path $Script:TestRoot ".claude/skills/adr-review/scripts/Detect-ADRChanges.ps1"
            Set-Content -Path $detectScriptPath -Value $mockScript
        }

        It "Should output blocking gate message" {
            $env:CLAUDE_PROJECT_DIR = $Script:TestRoot

            $result = & $Script:HookPath 2>&1
            $LASTEXITCODE | Should -Be 0
            $result | Should -Not -BeNullOrEmpty
            $result | Should -Match "BLOCKING GATE"
            $result | Should -Match "ADR-999-test.md"
        }

        It "Should include created files in output" {
            $env:CLAUDE_PROJECT_DIR = $Script:TestRoot

            $result = & $Script:HookPath 2>&1
            $result | Should -Match "\*\*Created\*\*:"
        }
    }

    Context "When detection script fails" {
        BeforeEach {
            # Create mock detection script that fails
            $mockScript = @'
[CmdletBinding()]
param([string]$BasePath, [switch]$IncludeUntracked)
Write-Error "Simulated failure"
exit 1
'@
            $detectScriptPath = Join-Path $Script:TestRoot ".claude/skills/adr-review/scripts/Detect-ADRChanges.ps1"
            Set-Content -Path $detectScriptPath -Value $mockScript
        }

        It "Should warn about failure but still exit 0 (non-blocking)" {
            $env:CLAUDE_PROJECT_DIR = $Script:TestRoot

            $result = & $Script:HookPath 2>&1 3>&1
            $LASTEXITCODE | Should -Be 0
            # Should contain warning about detection failure
            $warnings = $result | Where-Object { $_ -is [System.Management.Automation.WarningRecord] }
            $warnings | Should -Not -BeNullOrEmpty
        }
    }

    Context "When detection script returns invalid JSON" {
        BeforeEach {
            # Create mock detection script that returns invalid JSON
            $mockScript = @'
[CmdletBinding()]
param([string]$BasePath, [switch]$IncludeUntracked)
Write-Output "This is not valid JSON"
exit 0
'@
            $detectScriptPath = Join-Path $Script:TestRoot ".claude/skills/adr-review/scripts/Detect-ADRChanges.ps1"
            Set-Content -Path $detectScriptPath -Value $mockScript
        }

        It "Should warn about parsing failure but still exit 0" {
            $env:CLAUDE_PROJECT_DIR = $Script:TestRoot

            $result = & $Script:HookPath 2>&1 3>&1
            $LASTEXITCODE | Should -Be 0
            # ConvertFrom-Json failure should be caught
            $warnings = $result | Where-Object { $_ -is [System.Management.Automation.WarningRecord] }
            $warnings | Should -Not -BeNullOrEmpty
        }
    }

    AfterAll {
        # Reset environment variable
        Remove-Item Env:CLAUDE_PROJECT_DIR -ErrorAction SilentlyContinue
    }
}
