BeforeAll {
    # Script path under test
    $script:ScriptPath = "$PSScriptRoot/../.claude/skills/adr-review/scripts/Detect-ADRChanges.ps1"
}

Describe 'Detect-ADRChanges Tests' {
    BeforeAll {
        # Create a temporary git repo for testing
        $script:TestRoot = Join-Path $TestDrive "test-repo"
        New-Item -ItemType Directory -Path $script:TestRoot -Force | Out-Null

        # Initialize git repo
        Push-Location $script:TestRoot
        git init --initial-branch main 2>&1 | Out-Null
        git config user.email "test@example.com" 2>&1 | Out-Null
        git config user.name "Test User" 2>&1 | Out-Null

        # Create ADR directories and commit them
        $agentsDir = Join-Path $script:TestRoot ".agents" "architecture"
        $docsDir = Join-Path $script:TestRoot "docs" "architecture"
        New-Item -ItemType Directory -Path $agentsDir -Force | Out-Null
        New-Item -ItemType Directory -Path $docsDir -Force | Out-Null

        # Create initial commit with placeholder files to establish directories
        $readmePath = Join-Path $script:TestRoot "README.md"
        $agentsPlaceholder = Join-Path $agentsDir ".gitkeep"
        $docsPlaceholder = Join-Path $docsDir ".gitkeep"
        Set-Content -Path $readmePath -Value "# Test Repo"
        Set-Content -Path $agentsPlaceholder -Value ""
        Set-Content -Path $docsPlaceholder -Value ""
        git add -A 2>&1 | Out-Null
        git commit -m "Initial commit with directories" 2>&1 | Out-Null

        # Store base commit
        $script:BaseCommit = git rev-parse HEAD
        Pop-Location

        # Set up directory paths for tests
        $script:AgentsADRDir = $agentsDir
        $script:DocsADRDir = $docsDir
    }

    AfterAll {
        # Clean up: reset to base commit
        if ($script:TestRoot -and (Test-Path $script:TestRoot)) {
            Push-Location $script:TestRoot
            git reset --hard $script:BaseCommit 2>&1 | Out-Null
            Pop-Location
        }
    }

    Context 'Script Validation' {
        It 'Script file should exist' {
            Test-Path $script:ScriptPath | Should -Be $true
        }

        It 'Script should have valid PowerShell syntax' {
            {
                $null = [System.Management.Automation.PSParser]::Tokenize(
                    (Get-Content $script:ScriptPath -Raw),
                    [ref]$null
                )
            } | Should -Not -Throw
        }

        It 'Script should accept BasePath parameter' {
            $params = (Get-Command $script:ScriptPath).Parameters
            $params.ContainsKey('BasePath') | Should -Be $true
        }

        It 'Script should accept SinceCommit parameter' {
            $params = (Get-Command $script:ScriptPath).Parameters
            $params.ContainsKey('SinceCommit') | Should -Be $true
        }

        It 'Script should accept IncludeUntracked switch' {
            $params = (Get-Command $script:ScriptPath).Parameters
            $params.ContainsKey('IncludeUntracked') | Should -Be $true
        }
    }

    Context 'No Changes Detected' {
        It 'Should return HasChanges=false when no ADR changes exist' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot'" | ConvertFrom-Json

            $result.HasChanges | Should -Be $false
            $result.Created.Count | Should -Be 0
            $result.Modified.Count | Should -Be 0
            $result.Deleted.Count | Should -Be 0
        }

        It 'Should return RecommendedAction=none when no changes' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot'" | ConvertFrom-Json

            $result.RecommendedAction | Should -Be "none"
        }

        It 'Should include timestamp in output' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot'" | ConvertFrom-Json

            $result.Timestamp | Should -Not -BeNullOrEmpty
        }

        It 'Should include SinceCommit in output' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot'" | ConvertFrom-Json

            $result.SinceCommit | Should -Be "HEAD~1"
        }
    }

    Context 'Created ADR Detection' {
        BeforeAll {
            Push-Location $script:TestRoot

            # Create a new ADR file
            $adrContent = @"
---
status: proposed
---
# ADR-001: Test Decision
## Context
Test context
"@
            $script:CreatedADRPath = Join-Path $script:AgentsADRDir "ADR-001-test-decision.md"
            Set-Content -Path $script:CreatedADRPath -Value $adrContent

            # Stage and commit the ADR
            git add ".agents/architecture/ADR-001-test-decision.md" 2>&1 | Out-Null
            git commit -m "Add ADR-001" 2>&1 | Out-Null
            Pop-Location
        }

        AfterAll {
            # Clean up: reset to base commit
            Push-Location $script:TestRoot
            git reset --hard $script:BaseCommit 2>&1 | Out-Null
            Pop-Location
        }

        It 'Should detect created ADR in .agents/architecture/' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot'" | ConvertFrom-Json

            $result.HasChanges | Should -Be $true
            $result.Created.Count | Should -Be 1
            $result.Created[0] | Should -BeLike "*ADR-001-test-decision.md"
        }

        It 'Should return RecommendedAction=review for created ADR' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot'" | ConvertFrom-Json

            $result.RecommendedAction | Should -Be "review"
        }
    }

    Context 'Modified ADR Detection' {
        BeforeAll {
            Push-Location $script:TestRoot

            # Create initial ADR
            $adrContent = @"
---
status: proposed
---
# ADR-002: Modified Decision
## Context
Initial context
"@
            $script:ModifiedADRPath = Join-Path $script:AgentsADRDir "ADR-002-modified-decision.md"
            Set-Content -Path $script:ModifiedADRPath -Value $adrContent
            git add ".agents/architecture/ADR-002-modified-decision.md" 2>&1 | Out-Null
            git commit -m "Add ADR-002" 2>&1 | Out-Null

            # Modify the ADR
            $modifiedContent = @"
---
status: accepted
---
# ADR-002: Modified Decision
## Context
Updated context with more details
"@
            Set-Content -Path $script:ModifiedADRPath -Value $modifiedContent
            git add ".agents/architecture/ADR-002-modified-decision.md" 2>&1 | Out-Null
            git commit -m "Update ADR-002" 2>&1 | Out-Null
            Pop-Location
        }

        AfterAll {
            Push-Location $script:TestRoot
            git reset --hard $script:BaseCommit 2>&1 | Out-Null
            Pop-Location
        }

        It 'Should detect modified ADR' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot'" | ConvertFrom-Json

            $result.HasChanges | Should -Be $true
            $result.Modified.Count | Should -Be 1
            $result.Modified[0] | Should -BeLike "*ADR-002-modified-decision.md"
        }

        It 'Should return RecommendedAction=review for modified ADR' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot'" | ConvertFrom-Json

            $result.RecommendedAction | Should -Be "review"
        }
    }

    Context 'Deleted ADR Detection' {
        BeforeAll {
            Push-Location $script:TestRoot

            # Create ADR to be deleted
            $adrContent = @"
---
status: accepted
---
# ADR-003: Deleted Decision
## Context
This ADR will be deleted
"@
            $script:DeletedADRPath = Join-Path $script:AgentsADRDir "ADR-003-deleted-decision.md"
            Set-Content -Path $script:DeletedADRPath -Value $adrContent
            git add ".agents/architecture/ADR-003-deleted-decision.md" 2>&1 | Out-Null
            git commit -m "Add ADR-003" 2>&1 | Out-Null

            # Delete the ADR
            Remove-Item -Path $script:DeletedADRPath -Force
            git add ".agents/architecture/ADR-003-deleted-decision.md" 2>&1 | Out-Null
            git commit -m "Delete ADR-003" 2>&1 | Out-Null
            Pop-Location
        }

        AfterAll {
            Push-Location $script:TestRoot
            git reset --hard $script:BaseCommit 2>&1 | Out-Null
            Pop-Location
        }

        It 'Should detect deleted ADR' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot'" | ConvertFrom-Json

            $result.HasChanges | Should -Be $true
            $result.Deleted.Count | Should -Be 1
            $result.Deleted[0] | Should -BeLike "*ADR-003-deleted-decision.md"
        }

        It 'Should return RecommendedAction=archive for deleted ADR' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot'" | ConvertFrom-Json

            $result.RecommendedAction | Should -Be "archive"
        }

        It 'Should include DeletedDetails with ADRName' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot'" | ConvertFrom-Json

            $result.DeletedDetails.Count | Should -Be 1
            $result.DeletedDetails[0].ADRName | Should -Be "ADR-003-deleted-decision"
        }
    }

    Context 'Untracked Files' {
        BeforeEach {
            # Create untracked ADR file
            $script:UntrackedADRPath = Join-Path $script:AgentsADRDir "ADR-004-untracked.md"
            $adrContent = @"
---
status: proposed
---
# ADR-004: Untracked Decision
"@
            Set-Content -Path $script:UntrackedADRPath -Value $adrContent
        }

        AfterEach {
            # Clean up untracked file
            if (Test-Path $script:UntrackedADRPath) {
                Remove-Item -Path $script:UntrackedADRPath -Force
            }
        }

        It 'Should NOT include untracked files by default' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot'" | ConvertFrom-Json

            # Untracked files should not appear in Created by default
            $hasUntracked = $false
            foreach ($file in $result.Created) {
                if ($file -like "*ADR-004-untracked.md") {
                    $hasUntracked = $true
                }
            }
            $hasUntracked | Should -Be $false
        }

        It 'Should include untracked files when -IncludeUntracked is specified' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot' -IncludeUntracked" | ConvertFrom-Json

            $result.HasChanges | Should -Be $true
            $result.Created.Count | Should -Be 1
            $result.Created[0] | Should -BeLike "*ADR-004-untracked.md"
        }
    }

    Context 'Non-ADR Files Ignored' {
        BeforeAll {
            Push-Location $script:TestRoot

            # Create non-ADR file in architecture directory
            $script:NonADRPath = Join-Path $script:AgentsADRDir "README.md"
            Set-Content -Path $script:NonADRPath -Value "# Architecture README"
            git add ".agents/architecture/README.md" 2>&1 | Out-Null
            git commit -m "Add README to architecture" 2>&1 | Out-Null
            Pop-Location
        }

        AfterAll {
            Push-Location $script:TestRoot
            git reset --hard $script:BaseCommit 2>&1 | Out-Null
            Pop-Location
        }

        It 'Should NOT detect non-ADR files' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot'" | ConvertFrom-Json

            $result.HasChanges | Should -Be $false
            $result.Created.Count | Should -Be 0
        }
    }

    Context 'Custom SinceCommit Parameter' {
        BeforeAll {
            Push-Location $script:TestRoot

            # Create first ADR
            $adr1Content = @"
---
status: proposed
---
# ADR-005: First Decision
"@
            $script:ADR1Path = Join-Path $script:AgentsADRDir "ADR-005-first.md"
            Set-Content -Path $script:ADR1Path -Value $adr1Content
            git add ".agents/architecture/ADR-005-first.md" 2>&1 | Out-Null
            git commit -m "Add ADR-005" 2>&1 | Out-Null

            # Get the commit hash
            $script:FirstADRCommit = git rev-parse HEAD

            # Create second ADR
            $adr2Content = @"
---
status: proposed
---
# ADR-006: Second Decision
"@
            $script:ADR2Path = Join-Path $script:AgentsADRDir "ADR-006-second.md"
            Set-Content -Path $script:ADR2Path -Value $adr2Content
            git add ".agents/architecture/ADR-006-second.md" 2>&1 | Out-Null
            git commit -m "Add ADR-006" 2>&1 | Out-Null
            Pop-Location
        }

        AfterAll {
            Push-Location $script:TestRoot
            git reset --hard $script:BaseCommit 2>&1 | Out-Null
            Pop-Location
        }

        It 'Should detect changes since specified commit' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot' -SinceCommit '$script:FirstADRCommit'" | ConvertFrom-Json

            $result.HasChanges | Should -Be $true
            $result.Created.Count | Should -Be 1
            $result.Created[0] | Should -BeLike "*ADR-006-second.md"
        }

        It 'Should NOT include changes before specified commit' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot' -SinceCommit '$script:FirstADRCommit'" | ConvertFrom-Json

            $hasFirst = $false
            foreach ($file in $result.Created) {
                if ($file -like "*ADR-005-first.md") {
                    $hasFirst = $true
                }
            }
            $hasFirst | Should -Be $false
        }
    }

    Context 'Error Handling' {
        It 'Should exit with code 1 for non-git directory' {
            $nonGitDir = Join-Path $TestDrive "non-git-dir"
            New-Item -ItemType Directory -Path $nonGitDir -Force | Out-Null

            & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$nonGitDir'" 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 1
        }

        It 'Should exit with code 0 for valid git repo with no changes' {
            & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot'" 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context 'docs/architecture/ Directory' {
        BeforeAll {
            Push-Location $script:TestRoot

            # Create ADR in docs/architecture/
            $adrContent = @"
---
status: proposed
---
# ADR-007: Docs Decision
"@
            $script:DocsADRPath = Join-Path $script:DocsADRDir "ADR-007-docs-decision.md"
            Set-Content -Path $script:DocsADRPath -Value $adrContent
            git add "docs/architecture/ADR-007-docs-decision.md" 2>&1 | Out-Null
            git commit -m "Add ADR-007 to docs" 2>&1 | Out-Null
            Pop-Location
        }

        AfterAll {
            Push-Location $script:TestRoot
            git reset --hard $script:BaseCommit 2>&1 | Out-Null
            Pop-Location
        }

        It 'Should detect ADRs in docs/architecture/' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot'" | ConvertFrom-Json

            $result.HasChanges | Should -Be $true
            $result.Created.Count | Should -Be 1
            $result.Created[0] | Should -BeLike "*ADR-007-docs-decision.md"
        }
    }

    Context 'JSON Output Format' {
        It 'Should return valid JSON' {
            $output = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot'"

            { $output | ConvertFrom-Json } | Should -Not -Throw
        }

        It 'Should have all required properties' {
            $result = & pwsh -NoProfile -Command "& '$script:ScriptPath' -BasePath '$script:TestRoot'" | ConvertFrom-Json

            $result.PSObject.Properties.Name | Should -Contain "Created"
            $result.PSObject.Properties.Name | Should -Contain "Modified"
            $result.PSObject.Properties.Name | Should -Contain "Deleted"
            $result.PSObject.Properties.Name | Should -Contain "DeletedDetails"
            $result.PSObject.Properties.Name | Should -Contain "HasChanges"
            $result.PSObject.Properties.Name | Should -Contain "RecommendedAction"
            $result.PSObject.Properties.Name | Should -Contain "Timestamp"
            $result.PSObject.Properties.Name | Should -Contain "SinceCommit"
        }
    }
}
