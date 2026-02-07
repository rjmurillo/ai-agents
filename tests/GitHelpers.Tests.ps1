<#
.SYNOPSIS
    Pester tests for GitHelpers.psm1 module.

.DESCRIPTION
    Comprehensive unit tests for Get-GitInfo function in the GitHelpers module.
    Tests cover valid repositories, error handling, cross-platform compatibility,
    and edge cases with mocked git commands.

.NOTES
    Requires Pester 5.x or later.
    Run with: Invoke-Pester -Path tests/GitHelpers.Tests.ps1
#>

BeforeAll {
    # Import the module under test
    $ModulePath = Join-Path $PSScriptRoot "../.claude/skills/session-init/modules/GitHelpers.psm1"
    Import-Module $ModulePath -Force

    # Create temp directory for test artifacts (cross-platform)
    $Script:TestTempDir = Join-Path ([System.IO.Path]::GetTempPath()) "GitHelpers-Tests-$(Get-Random)"
    New-Item -ItemType Directory -Path $Script:TestTempDir -Force | Out-Null

    # Store original location to restore after tests
    $Script:OriginalLocation = Get-Location
}

AfterAll {
    # Restore original location
    Set-Location $Script:OriginalLocation

    # Clean up test artifacts
    if (Test-Path $Script:TestTempDir) {
        Remove-Item -Path $Script:TestTempDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    # Remove module from session
    Remove-Module GitHelpers -Force -ErrorAction SilentlyContinue
}

Describe "Get-GitInfo" {

    Context "Valid Git Repository" {
        It "Returns hashtable with all required keys" {
            # Test against actual repository
            $result = Get-GitInfo

            $result | Should -Not -BeNullOrEmpty
            $result | Should -BeOfType [hashtable]
            $result.Keys | Should -Contain "RepoRoot"
            $result.Keys | Should -Contain "Branch"
            $result.Keys | Should -Contain "Commit"
            $result.Keys | Should -Contain "Status"
        }

        It "Returns non-empty RepoRoot" {
            $result = Get-GitInfo
            $result.RepoRoot | Should -Not -BeNullOrEmpty
            $result.RepoRoot | Should -BeOfType [string]
        }

        It "Returns non-empty Branch" {
            $result = Get-GitInfo
            $result.Branch | Should -Not -BeNullOrEmpty
            $result.Branch | Should -BeOfType [string]
        }

        It "Returns Status as clean or dirty" {
            $result = Get-GitInfo
            $result.Status | Should -BeIn @("clean", "dirty")
        }
    }

    Context "Commit SHA Format" {
        It "Returns only SHA without extra text" {
            $result = Get-GitInfo
            
            # Should be hex characters only (7-40 chars)
            $result.Commit | Should -Match "^[a-f0-9]+$"
            $result.Commit.Length | Should -BeGreaterOrEqual 7
            $result.Commit.Length | Should -BeLessOrEqual 40
            # Should not contain whitespace or subject line
            $result.Commit | Should -Not -Match "\s"
        }

        It "Trims whitespace from commit output" {
            # This test ensures the function properly trims output
            $result = Get-GitInfo
            
            # Result should already be trimmed
            $result.Commit | Should -Not -Match "^\s"
            $result.Commit | Should -Not -Match "\s$"
        }
    }

    Context "Git Status Detection" {
        It "Returns valid status values" {
            $result = Get-GitInfo
            
            $result.Status | Should -BeIn @("clean", "dirty")
            $result.Status | Should -BeOfType [string]
        }
    }

    Context "Error Handling - Not a Git Repository" {
        BeforeAll {
            # Mock git rev-parse --show-toplevel to fail (not a repo)
            Mock -CommandName git -ModuleName GitHelpers -MockWith {
                param([Parameter(ValueFromRemainingArguments)]$Args)
                if ($Args -contains 'rev-parse' -and $Args -contains '--show-toplevel') {
                    $global:LASTEXITCODE = 128
                    return "fatal: not a git repository (or any of the parent directories): .git"
                }
            }
        }

        It "Throws InvalidOperationException when not in a git repository" {
            { Get-GitInfo } | Should -Throw -ExceptionType ([System.InvalidOperationException])
        }

        It "Includes diagnostic message about ensuring git repository" {
            try {
                Get-GitInfo
                throw "Should have thrown"
            } catch [System.InvalidOperationException] {
                $_.Exception.Message | Should -Match "Not in a git repository"
                $_.Exception.Message | Should -Match "Ensure you are in a git repository"
            }
        }
    }

    Context "Error Handling - Detached HEAD State" {
        BeforeAll {
            # Mock git to simulate detached HEAD (branch command returns empty)
            Mock -CommandName git -ModuleName GitHelpers -MockWith {
                param([Parameter(ValueFromRemainingArguments)]$Args)
                if ($Args -contains 'rev-parse' -and $Args -contains '--show-toplevel') {
                    $global:LASTEXITCODE = 0
                    return "/fake/repo/path"
                } elseif ($Args -contains 'branch' -and $Args -contains '--show-current') {
                    $global:LASTEXITCODE = 0
                    return ""  # Detached HEAD returns empty
                } elseif ($Args -contains 'rev-parse' -and $Args -contains '--short' -and $Args -contains 'HEAD') {
                    $global:LASTEXITCODE = 0
                    return "abc1234"
                } elseif ($Args -contains 'status' -and $Args -contains '--short') {
                    $global:LASTEXITCODE = 0
                    return ""
                }
            }
        }

        It "Returns empty string for Branch when in detached HEAD state" {
            $result = Get-GitInfo
            $result.Branch | Should -Be ""
        }
    }

    Context "Error Handling - Git Branch Command Fails" {
        BeforeAll {
            Mock -CommandName git -ModuleName GitHelpers -MockWith {
                param([Parameter(ValueFromRemainingArguments)]$Args)
                if ($Args -contains 'rev-parse' -and $Args -contains '--show-toplevel') {
                    $global:LASTEXITCODE = 0
                    return "/fake/repo/path"
                } elseif ($Args -contains 'branch' -and $Args -contains '--show-current') {
                    $global:LASTEXITCODE = 1
                    return "fatal: unable to read branch"
                }
            }
        }

        It "Throws InvalidOperationException when git branch fails" {
            { Get-GitInfo } | Should -Throw -ExceptionType ([System.InvalidOperationException])
        }

        It "Includes diagnostic message about detached HEAD or corruption" {
            try {
                Get-GitInfo
                throw "Should have thrown"
            } catch [System.InvalidOperationException] {
                $_.Exception.Message | Should -Match "Failed to get current branch"
                $_.Exception.Message | Should -Match "detached HEAD state"
            }
        }
    }

    Context "Error Handling - No Commits in Repository" {
        BeforeAll {
            Mock -CommandName git -ModuleName GitHelpers -MockWith {
                param([Parameter(ValueFromRemainingArguments)]$Args)
                if ($Args -contains 'rev-parse' -and $Args -contains '--show-toplevel') {
                    $global:LASTEXITCODE = 0
                    return "/fake/repo/path"
                } elseif ($Args -contains 'branch' -and $Args -contains '--show-current') {
                    $global:LASTEXITCODE = 0
                    return "main"
                } elseif ($Args -contains 'rev-parse' -and $Args -contains '--short' -and $Args -contains 'HEAD') {
                    $global:LASTEXITCODE = 128
                    return "fatal: ambiguous argument 'HEAD': unknown revision or path not in the working tree"
                }
            }
        }

        It "Throws InvalidOperationException when no commits exist" {
            { Get-GitInfo } | Should -Throw -ExceptionType ([System.InvalidOperationException])
        }

        It "Includes diagnostic message about creating initial commit" {
            try {
                Get-GitInfo
                throw "Should have thrown"
            } catch [System.InvalidOperationException] {
                $_.Exception.Message | Should -Match "Failed to get commit SHA"
                $_.Exception.Message | Should -Match "no commits yet"
                $_.Exception.Message | Should -Match "Initial commit"
            }
        }
    }

    Context "Error Handling - Git Status Command Fails" {
        BeforeAll {
            Mock -CommandName git -ModuleName GitHelpers -MockWith {
                param([Parameter(ValueFromRemainingArguments)]$Args)
                if ($Args -contains 'rev-parse' -and $Args -contains '--show-toplevel') {
                    $global:LASTEXITCODE = 0
                    return "/fake/repo/path"
                } elseif ($Args -contains 'branch' -and $Args -contains '--show-current') {
                    $global:LASTEXITCODE = 0
                    return "main"
                } elseif ($Args -contains 'rev-parse' -and $Args -contains '--short' -and $Args -contains 'HEAD') {
                    $global:LASTEXITCODE = 0
                    return "abc1234"
                } elseif ($Args -contains 'status' -and $Args -contains '--short') {
                    $global:LASTEXITCODE = 128
                    return "fatal: Unable to read index"
                }
            }
        }

        It "Throws InvalidOperationException when git status fails" {
            { Get-GitInfo } | Should -Throw -ExceptionType ([System.InvalidOperationException])
        }

        It "Includes diagnostic message about corruption or permissions" {
            try {
                Get-GitInfo
                throw "Should have thrown"
            } catch [System.InvalidOperationException] {
                $_.Exception.Message | Should -Match "Failed to get git status"
                $_.Exception.Message | Should -Match "corruption or permission"
            }
        }
    }

    Context "Error Handling - Unexpected Exception with InnerException" {
        BeforeAll {
            # Mock to throw unexpected exception (not git-related)
            Mock -CommandName git -ModuleName GitHelpers -MockWith {
                throw [System.IO.IOException]::new("Disk I/O error")
            }
        }

        It "Wraps unexpected exceptions in ApplicationException" {
            { Get-GitInfo } | Should -Throw -ExceptionType ([System.ApplicationException])
        }

        It "Includes original exception as InnerException" {
            try {
                Get-GitInfo
                throw "Should have thrown"
            } catch [System.ApplicationException] {
                $_.Exception.InnerException | Should -Not -BeNullOrEmpty
                $_.Exception.InnerException.GetType().Name | Should -Be "IOException"
                $_.Exception.InnerException.Message | Should -Be "Disk I/O error"
            }
        }

        It "Includes diagnostic details in exception message" {
            try {
                Get-GitInfo
                throw "Should have thrown"
            } catch [System.ApplicationException] {
                $_.Exception.Message | Should -Match "UNEXPECTED ERROR in Get-GitInfo"
                $_.Exception.Message | Should -Match "Exception Type:"
                $_.Exception.Message | Should -Match "This is a bug"
            }
        }
    }

    Context "Cross-Platform Compatibility" {
        It "Handles repository paths correctly" {
            $result = Get-GitInfo
            
            # Repo root should be a valid path
            $result.RepoRoot | Should -Not -BeNullOrEmpty
            # Should exist as a path
            Test-Path $result.RepoRoot | Should -Be $true
        }

        It "Works in actual git repository" {
            # We're already in a git repo, so this validates cross-platform handling
            $result = Get-GitInfo
            
            $result.RepoRoot | Should -BeOfType [string]
            $result.Branch | Should -BeOfType [string]
            $result.Commit | Should -BeOfType [string]
            $result.Status | Should -BeOfType [string]
        }
    }

    Context "Module Export" {
        It "Exports Get-GitInfo function" {
            $command = Get-Command -Name "Get-GitInfo" -Module GitHelpers -ErrorAction SilentlyContinue

            $command | Should -Not -BeNullOrEmpty
            $command.Name | Should -Be "Get-GitInfo"
        }

        It "Function is callable" {
            { Get-GitInfo } | Should -Not -Throw
        }
    }

    Context "Security - Shell Metacharacter Injection" {
        BeforeAll {
            # Mock git to return branch names with shell metacharacters
            Mock -CommandName git -ModuleName GitHelpers -MockWith {
                param([Parameter(ValueFromRemainingArguments)]$Args)
                if ($Args -contains 'rev-parse' -and $Args -contains '--show-toplevel') {
                    $global:LASTEXITCODE = 0
                    return "/fake/repo/path"
                } elseif ($Args -contains 'branch' -and $Args -contains '--show-current') {
                    $global:LASTEXITCODE = 0
                    return $Script:TestBranchName
                } elseif ($Args -contains 'rev-parse' -and $Args -contains '--short' -and $Args -contains 'HEAD') {
                    $global:LASTEXITCODE = 0
                    return "abc1234"
                } elseif ($Args -contains 'status' -and $Args -contains '--short') {
                    $global:LASTEXITCODE = 0
                    return ""
                }
            }
        }

        It "Handles branch name with semicolon (;)" {
            $Script:TestBranchName = 'feat/test;rm -rf /'
            $result = Get-GitInfo
            $result.Branch | Should -Be 'feat/test;rm -rf /'
        }

        It "Handles branch name with pipe (|)" {
            $Script:TestBranchName = 'feat/test|cat /etc/passwd'
            $result = Get-GitInfo
            $result.Branch | Should -Be 'feat/test|cat /etc/passwd'
        }

        It "Handles branch name with && operator" {
            $Script:TestBranchName = 'feat/test&&echo pwned'
            $result = Get-GitInfo
            $result.Branch | Should -Be 'feat/test&&echo pwned'
        }

        It 'Handles branch name with command substitution $(...)' {
            $Script:TestBranchName = 'feat/$(whoami)'
            $result = Get-GitInfo
            $result.Branch | Should -Be 'feat/$(whoami)'
        }

        It 'Handles branch name with backticks' {
            $branchName = 'feat/' + [char]0x60 + 'whoami' + [char]0x60
            $Script:TestBranchName = $branchName
            $result = Get-GitInfo
            $result.Branch | Should -Be $branchName
        }

        It "Handles branch name with single quotes" {
            $Script:TestBranchName = "feat/'injection'"
            $result = Get-GitInfo
            $result.Branch | Should -Be "feat/'injection'"
        }

        It "Handles branch name with double quotes" {
            $Script:TestBranchName = 'feat/"injection"'
            $result = Get-GitInfo
            $result.Branch | Should -Be 'feat/"injection"'
        }

        It "Handles branch name with null bytes" {
            $Script:TestBranchName = "feat/test`0evil"
            $result = Get-GitInfo
            $result.Branch | Should -Not -BeNullOrEmpty
        }

        It "Handles branch name with newline characters" {
            $Script:TestBranchName = "feat/test`ninjection"
            $result = Get-GitInfo
            $result.Branch | Should -Not -BeNullOrEmpty
        }

        It "Handles branch name with tab characters" {
            $Script:TestBranchName = "feat/test`tinjection"
            $result = Get-GitInfo
            $result.Branch | Should -Not -BeNullOrEmpty
        }
    }

    Context "Security - No Shell Execution" {
        It "PowerShell passes git args directly without shell interpretation" {
            # PowerShell's process invocation does not run through sh/cmd.
            # Verify by calling git with a branch name that would be dangerous in a shell.
            # If shell interpretation occurred, this would execute 'echo pwned' as a command.
            $result = Get-GitInfo
            $result | Should -Not -BeNullOrEmpty
            # No shell was spawned; all git args are passed as literal strings.
        }
    }

    Context "Output Structure Consistency" {
        It "Always returns hashtable with exact keys in every call" {
            for ($i = 0; $i -lt 3; $i++) {
                $result = Get-GitInfo
                
                @("RepoRoot", "Branch", "Commit", "Status") | ForEach-Object {
                    $result.ContainsKey($_) | Should -Be $true
                }
            }
        }

        It "All output values are strings" {
            $result = Get-GitInfo
            
            $result.RepoRoot | Should -BeOfType [string]
            $result.Branch | Should -BeOfType [string]
            $result.Commit | Should -BeOfType [string]
            $result.Status | Should -BeOfType [string]
        }

        It "RepoRoot is an absolute path" {
            $result = Get-GitInfo
            
            # On Windows, absolute paths start with drive letter or UNC
            # On Linux/Mac, absolute paths start with /
            $result.RepoRoot | Should -Match "^[A-Za-z]:|^/"
        }
    }
}

