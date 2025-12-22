<#
.SYNOPSIS
    Pester tests for Invoke-BatchPRReview.ps1 script.

.DESCRIPTION
    Tests the git worktree management functions for batch PR review operations.
    Uses structural verification and integration tests with real git repos.

.NOTES
    Requires Pester 5.x or later.
# >

BeforeAll {
    $Script:ScriptPath = Join-Path $PSScriptRoot "..\Invoke-BatchPRReview.ps1"
    $Script:TestDir = Join-Path $TestDrive "worktree-test"
}

Describe "Invoke-BatchPRReview.ps1" {
    BeforeEach {
        # Create fresh test directory for each test
        New-Item -ItemType Directory -Path $Script:TestDir -Force | Out-Null
    }

    AfterEach {
        # Clean up test directory
        if (Test-Path $Script:TestDir) {
            Remove-Item -Path $Script:TestDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Context "Script Structure Validation" {
        It "Script file exists and is valid PowerShell" {
            $Script:ScriptPath | Should -Exist
            { Get-Command $Script:ScriptPath } | Should -Not -Throw
        }

        It "Script has required parameters" {
            $cmd = Get-Command $Script:ScriptPath
            $cmd.Parameters.Keys | Should -Contain "PRNumbers"
            $cmd.Parameters.Keys | Should -Contain "Operation"
            $cmd.Parameters.Keys | Should -Contain "WorktreeRoot"
            $cmd.Parameters.Keys | Should -Contain "Force"
        }

        It "PRNumbers parameter is mandatory" {
            $cmd = Get-Command $Script:ScriptPath
            $param = $cmd.Parameters['PRNumbers']
            $mandatory = $param.Attributes | Where-Object { $_ -is [System.Management.Automation.ParameterAttribute] }
            $mandatory.Mandatory | Should -Be $true
        }

        It "Operation parameter has correct ValidateSet" {
            $cmd = Get-Command $Script:ScriptPath
            $validSet = $cmd.Parameters['Operation'].Attributes |
                Where-Object { $_ -is [System.Management.Automation.ValidateSetAttribute] }
            $validSet.ValidValues | Should -Contain "Setup"
            $validSet.ValidValues | Should -Contain "Status"
            $validSet.ValidValues | Should -Contain "Cleanup"
            $validSet.ValidValues | Should -Contain "All"
        }
    }

    Context "Error Handling Verification" {
        It "Get-PRBranch checks LASTEXITCODE after gh command" {
            $scriptContent = Get-Content -Path $Script:ScriptPath -Raw

            # The fix should capture gh output and check LASTEXITCODE
            $scriptContent | Should -Match 'gh pr view.*2>&1'
            $scriptContent | Should -Match 'if\s*\(\s*\$LASTEXITCODE\s*-ne\s*0\s*\)'
        }

        It "Get-WorktreeStatus checks upstream before git log" {
            $scriptContent = Get-Content -Path $Script:ScriptPath -Raw

            # The fix should check for upstream before using @{u}
            $scriptContent | Should -Match "git rev-parse --abbrev-ref.*@\{u\}"
            $scriptContent | Should -Match '\$hasUpstream'
        }

        It "Push-WorktreeChanges checks LASTEXITCODE after git add" {
            $scriptContent = Get-Content -Path $Script:ScriptPath -Raw

            # Should check LASTEXITCODE after git add
            $scriptContent | Should -Match 'git add \.'
            $scriptContent | Should -Match "git add.*[\r\n]+.*if.*\`$LASTEXITCODE"
        }

        It "Push-WorktreeChanges checks LASTEXITCODE after git commit" {
            $scriptContent = Get-Content -Path $Script:ScriptPath -Raw

            # Should check LASTEXITCODE after git commit
            $scriptContent | Should -Match "git commit -m"
            $scriptContent | Should -Match "git commit.*[\r\n]+.*if.*\`$LASTEXITCODE"
        }

        It "Push-WorktreeChanges checks LASTEXITCODE after git push" {
            $scriptContent = Get-Content -Path $Script:ScriptPath -Raw

            # Should check LASTEXITCODE after git push
            $scriptContent | Should -Match 'git push[\r\n]'
            $scriptContent | Should -Match "git push[\r\n]+.*if.*\`$LASTEXITCODE"
        }

        It "Get-PRBranch has enhanced warning message with troubleshooting" {
            $scriptContent = Get-Content -Path $Script:ScriptPath -Raw

            # Warning should include troubleshooting guidance
            $scriptContent | Should -Match "gh auth status"
            $scriptContent | Should -Match "not accessible"
        }
    }

    Context "Parameter Combinations" {
        It "Script fails when PRNumbers is missing" {
            { & $Script:ScriptPath -Operation Status 2>&1 } | Should -Throw
        }

        It "Script fails when Operation is missing" {
            { & $Script:ScriptPath -PRNumbers 123 2>&1 } | Should -Throw
        }

        It "Script fails with invalid Operation value" {
            { & $Script:ScriptPath -PRNumbers 123 -Operation "Invalid" 2>&1 } | Should -Throw
        }
    }

    Context "Function Definitions" {
        BeforeAll {
            $Script:ScriptContent = Get-Content -Path $Script:ScriptPath -Raw
        }

        It "Defines Get-PRBranch function" {
            $Script:ScriptContent | Should -Match 'function Get-PRBranch'
        }

        It "Defines New-PRWorktree function" {
            $Script:ScriptContent | Should -Match 'function New-PRWorktree'
        }

        It "Defines Get-WorktreeStatus function" {
            $Script:ScriptContent | Should -Match 'function Get-WorktreeStatus'
        }

        It "Defines Remove-PRWorktree function" {
            $Script:ScriptContent | Should -Match 'function Remove-PRWorktree'
        }

        It "Defines Push-WorktreeChanges function" {
            $Script:ScriptContent | Should -Match 'function Push-WorktreeChanges'
        }
    }

    Context "Code Quality" {
        BeforeAll {
            $Script:ScriptContent = Get-Content -Path $Script:ScriptPath -Raw
        }

        It "Uses ErrorActionPreference Stop" {
            $Script:ScriptContent | Should -Match "\`$ErrorActionPreference\s*=\s*'Stop'"
        }

        It "Uses CmdletBinding for proper parameter handling" {
            $Script:ScriptContent | Should -Match '\[CmdletBinding\(\)\]'
        }

        It "Does not use hardcoded origin remote in push" {
            # The push should use default remote, not hardcoded origin
            $Script:ScriptContent | Should -Not -Match 'git push origin \$branch'
            $Script:ScriptContent | Should -Match 'git push[\r\n]'
        }

        It "Uses try/finally for Push-Location cleanup" {
            $Script:ScriptContent | Should -Match 'Push-Location'
            $Script:ScriptContent | Should -Match 'finally\s*\{[\s\S]*?Pop-Location'
        }
    }

    Context "Integration - Status Operation" {
        It "Status operation handles non-existent worktrees gracefully" -Skip:(-not (Get-Command git -ErrorAction SilentlyContinue)) {
            # Create a minimal git repo to run from
            $repoPath = Join-Path $Script:TestDir "repo"
            New-Item -ItemType Directory -Path $repoPath -Force | Out-Null

            Push-Location $repoPath
            try {
                git init --quiet 2>$null
                git config user.email "test@test.com" 2>$null
                git config user.name "Test" 2>$null
                New-Item -ItemType File -Path "test.txt" -Value "test" -Force | Out-Null
                git add . 2>$null
                git commit -m "Initial" --quiet 2>$null

                # Run Status operation for non-existent PR
                $output = & $Script:ScriptPath -PRNumbers 99999 -Operation Status 2>&1

                # Should complete without throwing
                $LASTEXITCODE | Should -Be 0
            }
            finally {
                Pop-Location
            }
        }
    }
}
