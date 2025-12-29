<#
.SYNOPSIS
    Tests for Resolve-PRConflicts.ps1

.DESCRIPTION
    Pester tests covering syntax validation, security validation (ADR-015),
    parameter handling, and error handling for the PR conflict resolution script.
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot '..' 'scripts' 'Resolve-PRConflicts.ps1'
    $ScriptContent = Get-Content -Path $ScriptPath -Raw
}

Describe 'Resolve-PRConflicts.ps1' {
    Context 'Script Syntax' {
        It 'Should be valid PowerShell' {
            $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$errors)
            $errors | Should -BeNullOrEmpty
        }

        It 'Should have comment-based help' {
            $ScriptContent | Should -Match '\.SYNOPSIS'
            $ScriptContent | Should -Match '\.DESCRIPTION'
            $ScriptContent | Should -Match '\.PARAMETER'
            $ScriptContent | Should -Match '\.EXAMPLE'
        }

        It 'Should reference ADR-015 for security compliance' {
            $ScriptContent | Should -Match 'ADR-015'
        }

        It 'Should set strict mode' {
            $ScriptContent | Should -Match "Set-StrictMode\s+-Version\s+Latest"
        }
    }

    Context 'Parameter Definitions' {
        It 'Should define Owner parameter' {
            $ScriptContent | Should -Match '\[string\]\$Owner'
        }

        It 'Should define Repo parameter' {
            $ScriptContent | Should -Match '\[string\]\$Repo'
        }

        It 'Should define PRNumber as mandatory long parameter' {
            $ScriptContent | Should -Match '\[Parameter\(Mandatory\)\][\s\S]*?\[long\]\$PRNumber'
        }

        It 'Should define BranchName as mandatory parameter' {
            $ScriptContent | Should -Match '\[Parameter\(Mandatory\)\][\s\S]*?\[string\]\$BranchName'
        }

        It 'Should define TargetBranch with default main' {
            $ScriptContent | Should -Match "\[string\]\`$TargetBranch\s*=\s*'main'"
        }

        It 'Should define WorktreeBasePath parameter' {
            $ScriptContent | Should -Match '\[string\]\$WorktreeBasePath'
        }

        It 'Should support WhatIf via SupportsShouldProcess' {
            $ScriptContent | Should -Match 'SupportsShouldProcess'
        }
    }

    Context 'Security Validation - ADR-015 Branch Name' {
        It 'Should define Test-SafeBranchName function' {
            $ScriptContent | Should -Match 'function\s+Test-SafeBranchName'
        }

        It 'Should check for empty or whitespace branch names' {
            $ScriptContent | Should -Match 'IsNullOrWhiteSpace'
        }

        It 'Should check for branch names starting with hyphen' {
            $ScriptContent | Should -Match "StartsWith\('-'\)"
        }

        It 'Should check for path traversal in branch names' {
            $ScriptContent | Should -Match "Contains\('\.\.'\)"
        }

        It 'Should check for control characters in branch names' {
            $ScriptContent | Should -Match '\[\\x00-\\x1f\\x7f\]'
        }

        It 'Should check for git special characters in branch names' {
            $ScriptContent | Should -Match '\[~\^:\?\*\\\[\\\]\\\\\]'
        }

        It 'Should check for shell metacharacters in branch names' {
            $ScriptContent | Should -Match '\[.*;\&\|<>\(\)\{\}'
        }
    }

    Context 'Security Validation - ADR-015 Worktree Path' {
        It 'Should define Get-SafeWorktreePath function' {
            $ScriptContent | Should -Match 'function\s+Get-SafeWorktreePath'
        }

        It 'Should validate PR number is positive' {
            $ScriptContent | Should -Match '\$PRNumber\s*-le\s*0'
        }

        It 'Should validate path stays within base directory' {
            $ScriptContent | Should -Match 'StartsWith\(\$base\.Path\)'
        }

        It 'Should use GetFullPath for path resolution' {
            $ScriptContent | Should -Match '\[System\.IO\.Path\]::GetFullPath'
        }
    }

    Context 'Auto-Resolvable Files Configuration' {
        It 'Should define auto-resolvable files list' {
            $ScriptContent | Should -Match '\$script:AutoResolvableFiles'
        }

        It 'Should include HANDOFF.md as auto-resolvable' {
            $ScriptContent | Should -Match "\.agents/HANDOFF\.md"
        }

        It 'Should include sessions directory as auto-resolvable' {
            $ScriptContent | Should -Match "\.agents/sessions/\*"
        }

        It 'Should define Test-IsAutoResolvable function' {
            $ScriptContent | Should -Match 'function\s+Test-IsAutoResolvable'
        }
    }

    Context 'GitHub Runner Detection' {
        It 'Should define Test-IsGitHubRunner function' {
            $ScriptContent | Should -Match 'function\s+Test-IsGitHubRunner'
        }

        It 'Should check GITHUB_ACTIONS environment variable' {
            $ScriptContent | Should -Match '\$env:GITHUB_ACTIONS'
        }
    }

    Context 'Conflict Resolution Logic' {
        It 'Should define Resolve-PRConflicts function' {
            $ScriptContent | Should -Match 'function\s+Resolve-PRConflicts'
        }

        It 'Should fetch both PR branch and target branch' {
            $ScriptContent | Should -Match 'git fetch origin \$BranchName'
            $ScriptContent | Should -Match 'git fetch origin \$TargetBranch'
        }

        It 'Should attempt merge with target branch' {
            $ScriptContent | Should -Match 'git merge.*origin/\$TargetBranch'
        }

        It 'Should detect conflicted files' {
            $ScriptContent | Should -Match 'git diff --name-only --diff-filter=U'
        }

        It 'Should use checkout --theirs for auto-resolvable files' {
            $ScriptContent | Should -Match 'git checkout --theirs'
        }

        It 'Should abort merge when non-auto-resolvable conflicts exist' {
            $ScriptContent | Should -Match 'git merge --abort'
        }

        It 'Should push resolved branch on success' {
            $ScriptContent | Should -Match 'git push origin \$BranchName'
        }
    }

    Context 'Result Object Structure' {
        It 'Should return PSCustomObject with Success field' {
            $ScriptContent | Should -Match 'Success\s*=\s*\$false'
        }

        It 'Should return PSCustomObject with Message field' {
            $ScriptContent | Should -Match "Message\s*=\s*''"
        }

        It 'Should return PSCustomObject with FilesResolved field' {
            $ScriptContent | Should -Match 'FilesResolved\s*=\s*@\(\)'
        }

        It 'Should return PSCustomObject with FilesBlocked field' {
            $ScriptContent | Should -Match 'FilesBlocked\s*=\s*@\(\)'
        }

        It 'Should output result as JSON' {
            $ScriptContent | Should -Match 'ConvertTo-Json\s+-Compress'
        }
    }

    Context 'Error Handling' {
        It 'Should set ErrorActionPreference to Stop' {
            $ScriptContent | Should -Match "\`$ErrorActionPreference\s*=\s*'Stop'"
        }

        It 'Should check LASTEXITCODE after git commands' {
            $ScriptContent | Should -Match '\$LASTEXITCODE\s*-ne\s*0'
        }

        It 'Should use Write-Warning for non-auto-resolvable files' {
            $ScriptContent | Should -Match 'Write-Warning.*Cannot auto-resolve'
        }

        It 'Should use Write-Error for failures' {
            $ScriptContent | Should -Match 'Write-Error'
        }

        It 'Should use try-catch for git operations' {
            $ScriptContent | Should -Match 'try\s*\{'
            $ScriptContent | Should -Match 'catch\s*\{'
        }
    }

    Context 'Worktree Management' {
        It 'Should create worktree for local execution' {
            $ScriptContent | Should -Match 'git worktree add'
        }

        It 'Should clean up worktree in finally block' {
            $ScriptContent | Should -Match 'finally\s*\{'
            $ScriptContent | Should -Match 'git.*worktree remove'
        }

        It 'Should use Push-Location and Pop-Location for directory management' {
            $ScriptContent | Should -Match 'Push-Location'
            $ScriptContent | Should -Match 'Pop-Location'
        }
    }

    Context 'WhatIf Mode' {
        It 'Should use PSCmdlet.ShouldProcess' {
            $ScriptContent | Should -Match '\$PSCmdlet\.ShouldProcess'
        }

        It 'Should have SupportsShouldProcess in CmdletBinding' {
            $ScriptContent | Should -Match '\[CmdletBinding\(SupportsShouldProcess\)\]'
        }
    }

    Context 'Exit Codes' {
        It 'Should exit with 0 on success' {
            $ScriptContent | Should -Match 'exit\s+0'
        }

        It 'Should exit with 1 on failure' {
            $ScriptContent | Should -Match 'exit\s+1'
        }
    }

    Context 'Entry Point Guard' {
        It 'Should have dot-source guard for testing' {
            $ScriptContent | Should -Match "if\s*\(\s*\`$MyInvocation\.InvocationName\s*-eq\s*'\.'\s*\)"
        }

        It 'Should auto-detect repo info' {
            $ScriptContent | Should -Match 'Get-RepoInfo'
        }
    }

    Context 'Behavioral Tests - Test-SafeBranchName' {
        BeforeAll {
            # Extract functions from script using AST (avoids mandatory parameter prompt)
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $functions = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)

            # Extract Test-SafeBranchName function
            $testSafeBranchNameAst = $functions | Where-Object { $_.Name -eq 'Test-SafeBranchName' }
            if (-not $testSafeBranchNameAst) {
                throw "Test-SafeBranchName function not found in script"
            }

            # Create the function in current scope
            Invoke-Expression $testSafeBranchNameAst.Extent.Text
        }

        # Positive test cases - valid branch names
        It 'Should accept valid branch name: feature/my-branch' {
            Test-SafeBranchName -BranchName 'feature/my-branch' | Should -Be $true
        }

        It 'Should accept valid branch name: fix/issue-123' {
            Test-SafeBranchName -BranchName 'fix/issue-123' | Should -Be $true
        }

        It 'Should accept valid branch name: main' {
            Test-SafeBranchName -BranchName 'main' | Should -Be $true
        }

        # Negative test cases - attack strings
        It 'Should reject branch name with semicolon (command injection)' {
            Test-SafeBranchName -BranchName 'main;rm -rf /' | Should -Be $false
        }

        It 'Should reject branch name with pipe (command injection)' {
            Test-SafeBranchName -BranchName 'main|cat /etc/passwd' | Should -Be $false
        }

        It 'Should reject branch name with backtick (command substitution)' {
            Test-SafeBranchName -BranchName 'main`whoami`' | Should -Be $false
        }

        It 'Should reject branch name starting with hyphen (git option injection)' {
            Test-SafeBranchName -BranchName '--exec=malicious' | Should -Be $false
        }

        It 'Should reject branch name with path traversal' {
            Test-SafeBranchName -BranchName '../../../etc/passwd' | Should -Be $false
        }

        It 'Should reject branch name with dollar sign (variable expansion)' {
            Test-SafeBranchName -BranchName 'main$HOME' | Should -Be $false
        }

        It 'Should reject branch name with ampersand (background execution)' {
            Test-SafeBranchName -BranchName 'main&whoami' | Should -Be $false
        }

        # Edge cases
        It 'Should reject empty branch name' {
            # Empty string causes parameter binding failure, which is acceptable security behavior
            # Test using a variable to bypass parameter binding validation
            $empty = ''
            { Test-SafeBranchName -BranchName $empty } | Should -Throw
        }

        It 'Should reject whitespace-only branch name' {
            Test-SafeBranchName -BranchName '   ' | Should -Be $false
        }

        It 'Should reject branch name with control characters' {
            Test-SafeBranchName -BranchName "main`0secret" | Should -Be $false
        }

        It 'Should reject branch name with git special characters' {
            Test-SafeBranchName -BranchName 'main~1' | Should -Be $false
            Test-SafeBranchName -BranchName 'main^1' | Should -Be $false
            Test-SafeBranchName -BranchName 'main:file' | Should -Be $false
        }
    }

    Context 'Behavioral Tests - TargetBranch Validation' {
        It 'Should validate TargetBranch with same rules as BranchName' {
            # The script should call Test-SafeBranchName for TargetBranch
            # Verify the pattern exists in the script
            $ScriptContent | Should -Match 'Test-SafeBranchName.*-BranchName \$TargetBranch'
        }
    }
}
