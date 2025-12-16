<#
.SYNOPSIS
    Pester tests for Install-Common.psm1 module.

.DESCRIPTION
    Comprehensive unit tests for all functions in the Install-Common module.
    Tests cover configuration loading, path resolution, source validation,
    destination management, file operations, and output formatting.

.NOTES
    Requires Pester 5.x or later.
    Run with: Invoke-Pester -Path .\scripts\tests\Install-Common.Tests.ps1
#>

BeforeAll {
    # Import the module under test
    $ModulePath = Join-Path $PSScriptRoot "..\lib\Install-Common.psm1"
    Import-Module $ModulePath -Force

    # Path to test config
    $Script:ConfigPath = Join-Path $PSScriptRoot "..\lib\Config.psd1"

    # Create temp directory for test artifacts
    $Script:TestTempDir = Join-Path $env:TEMP "Install-Common-Tests-$(Get-Random)"
    New-Item -ItemType Directory -Path $Script:TestTempDir -Force | Out-Null
}

AfterAll {
    # Clean up test artifacts
    if (Test-Path $Script:TestTempDir) {
        Remove-Item -Path $Script:TestTempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe "Get-InstallConfig" {
    Context "Claude Environment" {
        It "Returns valid configuration for Claude Global scope" {
            $config = Get-InstallConfig -Environment "Claude" -Scope "Global" -ConfigPath $Script:ConfigPath

            $config | Should -Not -BeNullOrEmpty
            $config.Environment | Should -Be "Claude"
            $config.Scope | Should -Be "Global"
            $config.DisplayName | Should -Be "Claude Code"
            $config.SourceDir | Should -Be "src/claude"
            $config.FilePattern | Should -Be "*.md"
            $config.DestDir | Should -Not -BeNullOrEmpty
            $config.InstructionsFile | Should -Be "CLAUDE.md"
            $config.BeginMarker | Should -Match "BEGIN: ai-agents installer"
            $config.EndMarker | Should -Match "END: ai-agents installer"
        }

        It "Returns valid configuration for Claude Repo scope" {
            $config = Get-InstallConfig -Environment "Claude" -Scope "Repo" -ConfigPath $Script:ConfigPath

            $config.Scope | Should -Be "Repo"
            $config.DestDir | Should -Be ".claude/agents"
            $config.InstructionsDest | Should -Be ""
            $config.AgentsDirs | Should -Not -BeNullOrEmpty
            $config.AgentsDirs.Count | Should -BeGreaterThan 5
        }
    }

    Context "Copilot Environment" {
        It "Returns valid configuration for Copilot Global scope" {
            $config = Get-InstallConfig -Environment "Copilot" -Scope "Global" -ConfigPath $Script:ConfigPath

            $config.Environment | Should -Be "Copilot"
            $config.DisplayName | Should -Be "GitHub Copilot CLI"
            $config.SourceDir | Should -Be "src/copilot-cli"
            $config.FilePattern | Should -Be "*.agent.md"
            $config.KnownBug | Should -Not -BeNullOrEmpty
            $config.KnownBug.Id | Should -Be "#452"
        }

        It "Returns valid configuration for Copilot Repo scope" {
            $config = Get-InstallConfig -Environment "Copilot" -Scope "Repo" -ConfigPath $Script:ConfigPath

            $config.DestDir | Should -Be ".github/agents"
            $config.InstructionsFile | Should -Be "copilot-instructions.md"
            $config.InstructionsDest | Should -Be ".github"
        }
    }

    Context "VSCode Environment" {
        It "Returns valid configuration for VSCode Global scope" {
            $config = Get-InstallConfig -Environment "VSCode" -Scope "Global" -ConfigPath $Script:ConfigPath

            $config.Environment | Should -Be "VSCode"
            $config.DisplayName | Should -Be "VS Code / Copilot Chat"
            $config.SourceDir | Should -Be "src/vs-code-agents"
            $config.FilePattern | Should -Be "*.agent.md"
            $config.DestDir | Should -Match "Code.*User.*prompts"
        }

        It "Returns valid configuration for VSCode Repo scope" {
            $config = Get-InstallConfig -Environment "VSCode" -Scope "Repo" -ConfigPath $Script:ConfigPath

            $config.DestDir | Should -Be ".github/agents"
            $config.InstructionsFile | Should -Be "copilot-instructions.md"
        }
    }

    Context "Error Handling" {
        It "Throws error for invalid environment" {
            { Get-InstallConfig -Environment "Invalid" -Scope "Global" -ConfigPath $Script:ConfigPath } |
                Should -Throw
        }

        It "Throws error for missing config file" {
            { Get-InstallConfig -Environment "Claude" -Scope "Global" -ConfigPath "C:\nonexistent\config.psd1" } |
                Should -Throw -Because "Config file does not exist"
        }
    }

    Context "All Environment/Scope Combinations" {
        $environments = @("Claude", "Copilot", "VSCode")
        $scopes = @("Global", "Repo")

        foreach ($env in $environments) {
            foreach ($scope in $scopes) {
                It "Returns valid configuration for $env $scope" {
                    $config = Get-InstallConfig -Environment $env -Scope $scope -ConfigPath $Script:ConfigPath

                    $config | Should -Not -BeNullOrEmpty
                    $config.Environment | Should -Be $env
                    $config.Scope | Should -Be $scope
                    $config.SourceDir | Should -Not -BeNullOrEmpty
                    $config.FilePattern | Should -Not -BeNullOrEmpty
                    $config.DestDir | Should -Not -BeNullOrEmpty
                }
            }
        }
    }
}

Describe "Resolve-DestinationPath" {
    Context "Relative Paths" {
        It "Combines relative path with RepoPath" {
            $result = Resolve-DestinationPath -PathExpression ".github/agents" -RepoPath "C:\MyRepo"

            $result | Should -Be "C:\MyRepo\.github\agents"
        }

        It "Returns relative path as-is when no RepoPath provided" {
            $result = Resolve-DestinationPath -PathExpression ".github/agents"

            $result | Should -Be ".github/agents"
        }
    }

    Context "Environment Variable Paths" {
        It "Expands `$HOME variable" {
            $result = Resolve-DestinationPath -PathExpression '$HOME/.claude/agents'

            $result | Should -Match [regex]::Escape($HOME)
            $result | Should -Match "\.claude"
        }

        It "Expands `$env:APPDATA variable" {
            if ($env:APPDATA) {
                $result = Resolve-DestinationPath -PathExpression '$env:APPDATA/Code/User/prompts'

                $result | Should -Match [regex]::Escape($env:APPDATA)
            }
            else {
                Set-ItResult -Skipped -Because "APPDATA environment variable not set"
            }
        }
    }

    Context "Empty and Null Handling" {
        It "Returns RepoPath for empty PathExpression" {
            $result = Resolve-DestinationPath -PathExpression "" -RepoPath "C:\MyRepo"

            $result | Should -Be "C:\MyRepo"
        }

        It "Returns null for empty PathExpression without RepoPath" {
            $result = Resolve-DestinationPath -PathExpression ""

            $result | Should -BeNullOrEmpty
        }
    }

    Context "Path Normalization" {
        It "Normalizes forward slashes to platform separator" {
            $result = Resolve-DestinationPath -PathExpression ".github/agents" -RepoPath "C:\MyRepo"

            # On Windows, should use backslash
            if ($IsWindows -or $PSVersionTable.PSVersion.Major -lt 6) {
                $result | Should -Be "C:\MyRepo\.github\agents"
            }
        }
    }
}

Describe "Test-SourceDirectory" {
    Context "Valid Directory" {
        It "Returns true for existing directory" {
            $result = Test-SourceDirectory -Path $Script:TestTempDir

            $result | Should -Be $true
        }
    }

    Context "Invalid Directory" {
        It "Throws error for non-existent directory" {
            { Test-SourceDirectory -Path "C:\nonexistent\directory\path" } |
                Should -Throw -Because "Directory does not exist"
        }

        It "Throws error for file path (not directory)" {
            $testFile = Join-Path $Script:TestTempDir "test.txt"
            "" | Out-File -FilePath $testFile -Encoding utf8

            { Test-SourceDirectory -Path $testFile } |
                Should -Throw -Because "Path is a file, not a directory"
        }
    }
}

Describe "Get-AgentFiles" {
    BeforeAll {
        # Create test source directory with various files
        $Script:SourceTestDir = Join-Path $Script:TestTempDir "source"
        New-Item -ItemType Directory -Path $Script:SourceTestDir -Force | Out-Null

        # Create test files
        "content" | Out-File -FilePath (Join-Path $Script:SourceTestDir "agent1.md") -Encoding utf8
        "content" | Out-File -FilePath (Join-Path $Script:SourceTestDir "agent2.md") -Encoding utf8
        "content" | Out-File -FilePath (Join-Path $Script:SourceTestDir "agent1.agent.md") -Encoding utf8
        "content" | Out-File -FilePath (Join-Path $Script:SourceTestDir "other.txt") -Encoding utf8
    }

    Context "Pattern Matching" {
        It "Returns all .md files for *.md pattern" {
            $files = Get-AgentFiles -SourceDir $Script:SourceTestDir -FilePattern "*.md"

            $files.Count | Should -Be 3
        }

        It "Returns only .agent.md files for *.agent.md pattern" {
            $files = Get-AgentFiles -SourceDir $Script:SourceTestDir -FilePattern "*.agent.md"

            $files.Count | Should -Be 1
            $files[0].Name | Should -Be "agent1.agent.md"
        }

        It "Returns empty array for non-matching pattern" {
            $files = Get-AgentFiles -SourceDir $Script:SourceTestDir -FilePattern "*.json"

            $files.Count | Should -Be 0
        }
    }

    Context "Output Type" {
        It "Returns FileInfo objects" {
            $files = Get-AgentFiles -SourceDir $Script:SourceTestDir -FilePattern "*.md"

            $files[0] | Should -BeOfType [System.IO.FileInfo]
        }
    }
}

Describe "Initialize-Destination" {
    Context "Directory Creation" {
        It "Creates directory if it does not exist" {
            $newDir = Join-Path $Script:TestTempDir "new-dest-$(Get-Random)"

            $result = Initialize-Destination -Path $newDir -Description "test"

            $result | Should -Be $true
            Test-Path $newDir | Should -Be $true
        }

        It "Returns false if directory already exists" {
            $result = Initialize-Destination -Path $Script:TestTempDir -Description "test"

            $result | Should -Be $false
        }
    }

    Context "Nested Directories" {
        It "Creates nested directory structure" {
            $nestedDir = Join-Path $Script:TestTempDir "level1\level2\level3-$(Get-Random)"

            $result = Initialize-Destination -Path $nestedDir

            $result | Should -Be $true
            Test-Path $nestedDir | Should -Be $true
        }
    }
}

Describe "Test-GitRepository" {
    BeforeAll {
        # Create test directories
        $Script:GitRepoDir = Join-Path $Script:TestTempDir "git-repo"
        $Script:NonGitDir = Join-Path $Script:TestTempDir "non-git"

        New-Item -ItemType Directory -Path $Script:GitRepoDir -Force | Out-Null
        New-Item -ItemType Directory -Path $Script:NonGitDir -Force | Out-Null

        # Create .git directory to simulate git repo
        New-Item -ItemType Directory -Path (Join-Path $Script:GitRepoDir ".git") -Force | Out-Null
    }

    Context "Git Repository Detection" {
        It "Returns true for directory with .git folder" {
            $result = Test-GitRepository -Path $Script:GitRepoDir

            $result | Should -Be $true
        }

        It "Returns false for directory without .git folder (no prompt)" {
            $result = Test-GitRepository -Path $Script:NonGitDir

            $result | Should -Be $false
        }
    }
}

Describe "Initialize-AgentsDirectories" {
    BeforeAll {
        $Script:RepoTestDir = Join-Path $Script:TestTempDir "repo-test-$(Get-Random)"
        New-Item -ItemType Directory -Path $Script:RepoTestDir -Force | Out-Null
    }

    Context "Directory Creation" {
        It "Creates specified directories with .gitkeep files" {
            $dirs = @(".agents/analysis", ".agents/planning")

            $result = Initialize-AgentsDirectories -RepoPath $Script:RepoTestDir -Directories $dirs

            $result | Should -Be 2

            # Verify directories exist
            Test-Path (Join-Path $Script:RepoTestDir ".agents/analysis") | Should -Be $true
            Test-Path (Join-Path $Script:RepoTestDir ".agents/planning") | Should -Be $true

            # Verify .gitkeep files exist
            Test-Path (Join-Path $Script:RepoTestDir ".agents/analysis/.gitkeep") | Should -Be $true
            Test-Path (Join-Path $Script:RepoTestDir ".agents/planning/.gitkeep") | Should -Be $true
        }

        It "Returns 0 when all directories already exist" {
            $dirs = @(".agents/analysis", ".agents/planning")

            # Second call should return 0
            $result = Initialize-AgentsDirectories -RepoPath $Script:RepoTestDir -Directories $dirs

            $result | Should -Be 0
        }
    }
}

Describe "Copy-AgentFile" {
    BeforeAll {
        # Create source file
        $Script:CopySourceDir = Join-Path $Script:TestTempDir "copy-source"
        $Script:CopyDestDir = Join-Path $Script:TestTempDir "copy-dest-$(Get-Random)"

        New-Item -ItemType Directory -Path $Script:CopySourceDir -Force | Out-Null
        New-Item -ItemType Directory -Path $Script:CopyDestDir -Force | Out-Null

        "test content" | Out-File -FilePath (Join-Path $Script:CopySourceDir "test-agent.md") -Encoding utf8
        $Script:SourceFile = Get-Item (Join-Path $Script:CopySourceDir "test-agent.md")
    }

    Context "New File Installation" {
        It "Installs new file and returns 'Installed' status" {
            $result = Copy-AgentFile -File $Script:SourceFile -DestDir $Script:CopyDestDir -Force

            $result | Should -Be "Installed"
            Test-Path (Join-Path $Script:CopyDestDir "test-agent.md") | Should -Be $true
        }
    }

    Context "File Update with Force" {
        It "Updates existing file and returns 'Updated' status with -Force" {
            # File already exists from previous test
            $result = Copy-AgentFile -File $Script:SourceFile -DestDir $Script:CopyDestDir -Force

            $result | Should -Be "Updated"
        }
    }
}

Describe "Install-InstructionsFile" {
    BeforeAll {
        $Script:InstructionsTestDir = Join-Path $Script:TestTempDir "instructions-$(Get-Random)"
        New-Item -ItemType Directory -Path $Script:InstructionsTestDir -Force | Out-Null

        # Create source instructions file
        $Script:InstructionsSource = Join-Path $Script:InstructionsTestDir "source-CLAUDE.md"
        "# Agent Instructions`nThis is the agent content." | Out-File -FilePath $Script:InstructionsSource -Encoding utf8
    }

    Context "New File Installation" {
        It "Creates new file with markers when destination doesn't exist" {
            $destPath = Join-Path $Script:InstructionsTestDir "new-CLAUDE.md"

            $result = Install-InstructionsFile -SourcePath $Script:InstructionsSource -DestPath $destPath

            $result | Should -Be "Installed"
            Test-Path $destPath | Should -Be $true

            $content = Get-Content -Path $destPath -Raw
            $content | Should -Match "BEGIN: ai-agents installer"
            $content | Should -Match "END: ai-agents installer"
            $content | Should -Match "Agent Instructions"
        }
    }

    Context "Append to Existing File" {
        It "Appends content block to existing file without markers" {
            $destPath = Join-Path $Script:InstructionsTestDir "existing-no-markers.md"
            "# Existing Content`nSome existing documentation." | Out-File -FilePath $destPath -Encoding utf8

            $result = Install-InstructionsFile -SourcePath $Script:InstructionsSource -DestPath $destPath

            $result | Should -Be "Appended"

            $content = Get-Content -Path $destPath -Raw
            $content | Should -Match "Existing Content"
            $content | Should -Match "BEGIN: ai-agents installer"
            $content | Should -Match "Agent Instructions"
        }
    }

    Context "Upgrade Existing Block" {
        It "Replaces existing content block (upgrade scenario)" {
            $destPath = Join-Path $Script:InstructionsTestDir "existing-with-markers.md"
            @"
# My Project

<!-- BEGIN: ai-agents installer -->
# Old Agent Content
This is old content that should be replaced.
<!-- END: ai-agents installer -->

## Other sections
"@ | Out-File -FilePath $destPath -Encoding utf8

            $result = Install-InstructionsFile -SourcePath $Script:InstructionsSource -DestPath $destPath

            $result | Should -Be "Upgraded"

            $content = Get-Content -Path $destPath -Raw
            $content | Should -Match "My Project"
            $content | Should -Match "Agent Instructions"
            $content | Should -Not -Match "Old Agent Content"
            $content | Should -Match "Other sections"
        }
    }

    Context "Force Replace" {
        It "Replaces entire file with -Force" {
            $destPath = Join-Path $Script:InstructionsTestDir "force-replace.md"
            "# Existing Content" | Out-File -FilePath $destPath -Encoding utf8

            $result = Install-InstructionsFile -SourcePath $Script:InstructionsSource -DestPath $destPath -Force

            $result | Should -Be "Replaced"

            $content = Get-Content -Path $destPath -Raw
            $content | Should -Match "Agent Instructions"
            $content | Should -Not -Match "Existing Content"
        }
    }

    Context "Error Handling" {
        It "Returns 'NotFound' for missing source file" {
            $result = Install-InstructionsFile -SourcePath "C:\nonexistent\file.md" -DestPath "C:\output.md"

            $result | Should -Be "NotFound"
        }
    }
}

Describe "Write-InstallHeader" {
    It "Does not throw" {
        { Write-InstallHeader -Title "Test Installation" } | Should -Not -Throw
    }
}

Describe "Write-InstallComplete" {
    Context "Different Environments and Scopes" {
        It "Does not throw for Claude Global" {
            { Write-InstallComplete -Environment "Claude" -Scope "Global" } | Should -Not -Throw
        }

        It "Does not throw for Copilot Repo" {
            { Write-InstallComplete -Environment "Copilot" -Scope "Repo" -RepoPath "C:\Test" } | Should -Not -Throw
        }

        It "Does not throw for VSCode Global" {
            { Write-InstallComplete -Environment "VSCode" -Scope "Global" } | Should -Not -Throw
        }

        It "Does not throw with KnownBug hashtable" {
            $bug = @{
                Id = "#123"
                Description = "Test bug"
                Url = "https://example.com"
            }
            { Write-InstallComplete -Environment "Copilot" -Scope "Global" -KnownBug $bug } | Should -Not -Throw
        }
    }
}
