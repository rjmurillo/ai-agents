#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for HookUtilities.psm1

.DESCRIPTION
    Tests the shared utilities module used across Claude Code hooks,
    focusing on error handling and logging behavior.
#>

BeforeAll {
    $Script:ModulePath = Join-Path $PSScriptRoot ".." ".claude" "hooks" "Common" "HookUtilities.psm1"

    if (-not (Test-Path $Script:ModulePath)) {
        throw "Module not found at: $Script:ModulePath"
    }

    Import-Module $Script:ModulePath -Force
}

Describe "HookUtilities.psm1" {
    Context "Get-ProjectDirectory" {
        It "Returns CLAUDE_PROJECT_DIR when set" {
            $env:CLAUDE_PROJECT_DIR = "/tmp/test-project"
            try {
                $result = Get-ProjectDirectory
                $result | Should -Be "/tmp/test-project"
            }
            finally {
                $env:CLAUDE_PROJECT_DIR = $null
            }
        }

        It "Returns null when no .git directory found" {
            # Create temp dir without .git
            $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "no-git-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                Push-Location $tempDir
                $result = Get-ProjectDirectory
                $result | Should -BeNullOrEmpty
                Pop-Location
            }
            finally {
                Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Finds .git directory by walking up tree" {
            # Create temp git repo
            $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "git-repo-$(Get-Random)"
            $subDir = Join-Path $tempDir "subdir"
            New-Item -ItemType Directory -Path $subDir -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $tempDir ".git") -Force | Out-Null

            try {
                Push-Location $subDir
                $result = Get-ProjectDirectory
                $result | Should -Be $tempDir
                Pop-Location
            }
            finally {
                Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context "Get-TodaySessionLog" {
        It "Returns null when directory does not exist" {
            $result = Get-TodaySessionLog -SessionsDir "/tmp/nonexistent-$(Get-Random)"
            $result | Should -BeNullOrEmpty
        }

        It "Handles missing directory gracefully" {
            # Verify function doesn't throw and returns null
            { Get-TodaySessionLog -SessionsDir "/tmp/nonexistent-$(Get-Random)" -WarningAction SilentlyContinue } | Should -Not -Throw
            $result = Get-TodaySessionLog -SessionsDir "/tmp/nonexistent-$(Get-Random)" -WarningAction SilentlyContinue
            $result | Should -BeNullOrEmpty
        }

        It "Returns null when no session logs exist" {
            $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "sessions-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                $result = Get-TodaySessionLog -SessionsDir $tempDir
                $result | Should -BeNullOrEmpty
            }
            finally {
                Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Returns most recent session log for today" {
            $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "sessions-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            $today = Get-Date -Format "yyyy-MM-dd"

            try {
                # Create multiple session logs with controlled LastWriteTime values
                # Per Copilot #2679880627: Use explicit LastWriteTime instead of Start-Sleep
                $session1Path = Join-Path $tempDir "$today-session-001.json"
                $session2Path = Join-Path $tempDir "$today-session-002.json"

                Set-Content -Path $session1Path -Value "{}"
                Set-Content -Path $session2Path -Value "{}"

                # Ensure predictable LastWriteTime ordering
                (Get-Item $session1Path).LastWriteTime = [DateTime]::Now.AddSeconds(-10)
                (Get-Item $session2Path).LastWriteTime = [DateTime]::Now

                $result = Get-TodaySessionLog -SessionsDir $tempDir
                $result.Name | Should -Be "$today-session-002.json"
            }
            finally {
                Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context "Get-TodaySessionLogs" {
        It "Returns empty array when directory does not exist" {
            $result = @(Get-TodaySessionLogs -SessionsDir "/tmp/nonexistent-$(Get-Random)" -WarningAction SilentlyContinue)
            $result | Should -BeNullOrEmpty
            $result.Count | Should -Be 0
        }

        It "Handles missing directory gracefully" {
            # Verify function doesn't throw and returns empty array
            { Get-TodaySessionLogs -SessionsDir "/tmp/nonexistent-$(Get-Random)" -WarningAction SilentlyContinue } | Should -Not -Throw
        }

        It "Returns all session logs for today" {
            $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "sessions-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            $today = Get-Date -Format "yyyy-MM-dd"
            $yesterday = (Get-Date).AddDays(-1).ToString("yyyy-MM-dd")

            try {
                # Create logs for today and yesterday
                Set-Content -Path (Join-Path $tempDir "$today-session-001.json") -Value "{}"
                Set-Content -Path (Join-Path $tempDir "$today-session-002.json") -Value "{}"
                Set-Content -Path (Join-Path $tempDir "$yesterday-session-999.json") -Value "{}"

                $result = Get-TodaySessionLogs -SessionsDir $tempDir
                $result.Count | Should -Be 2
                $result[0].Name | Should -Match "^$today-session-"
            }
            finally {
                Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context "Test-GitCommitCommand" {
        It "Returns true for git commit" {
            $result = Test-GitCommitCommand -Command "git commit -m 'test'"
            $result | Should -Be $true
        }

        It "Returns true for git ci alias" {
            $result = Test-GitCommitCommand -Command "git ci -m 'test'"
            $result | Should -Be $true
        }

        It "Returns false for git status" {
            $result = Test-GitCommitCommand -Command "git status"
            $result | Should -Be $false
        }

        It "Returns false for empty string" {
            $result = Test-GitCommitCommand -Command ""
            $result | Should -Be $false
        }

        It "Returns false for null" {
            $result = Test-GitCommitCommand -Command $null
            $result | Should -Be $false
        }
    }

    Context "Module structure" {
        It "Module parses without errors" {
            $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile($Script:ModulePath, [ref]$null, [ref]$errors)
            $errors | Should -BeNullOrEmpty
        }

        It "Exports all expected functions" {
            $exports = (Get-Command -Module HookUtilities).Name
            $exports | Should -Contain "Get-ProjectDirectory"
            $exports | Should -Contain "Test-GitCommitCommand"
            $exports | Should -Contain "Get-TodaySessionLog"
            $exports | Should -Contain "Get-TodaySessionLogs"
        }
    }
}
