<#
.SYNOPSIS
    Pester tests for Improve-MemoryGraphDensity.ps1

.DESCRIPTION
    Tests automatic Related section generation based on domain patterns
    with 100% code block coverage.
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot '..' '.claude' 'skills' 'memory' 'scripts' 'Improve-MemoryGraphDensity.ps1'

    # Create temporary test directory structure
    $script:testRoot = Join-Path $TestDrive 'density-test'
    $script:memoriesPath = Join-Path $testRoot '.serena' 'memories'
    New-Item -Path $memoriesPath -ItemType Directory -Force | Out-Null
}

Describe 'Improve-MemoryGraphDensity' {

    BeforeEach {
        # Clean test directory before each test
        Get-ChildItem -Path $script:memoriesPath -Filter '*.md' -File | Remove-Item -Force
    }

    Context 'When processing empty files' {
        It 'Should skip empty files without errors' {
            # Arrange
            $emptyFile = Join-Path $script:memoriesPath 'empty-file.md'
            Set-Content -Path $emptyFile -Value '' -NoNewline

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation *>&1 | Out-String

            # Assert
            $output | Should -Match 'Files updated: 0'
            $content = Get-Content $emptyFile -Raw -ErrorAction SilentlyContinue
            $content | Should -BeNullOrEmpty
        }
    }

    Context 'When processing files without Related sections' {
        It 'Should add Related section for files with domain pattern matches' {
            # Arrange
            $sec1 = Join-Path $script:memoriesPath 'security-001.md'
            $sec2 = Join-Path $script:memoriesPath 'security-002.md'
            $sec3 = Join-Path $script:memoriesPath 'security-003.md'

            Set-Content -Path $sec1 -Value '# Security 001'
            Set-Content -Path $sec2 -Value '# Security 002'
            Set-Content -Path $sec3 -Value '# Security 003'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content1 = Get-Content $sec1 -Raw
            $content1 | Should -Match '## Related'
            $content1 | Should -Match '\[security-002\]\(security-002\.md\)'
            $content1 | Should -Match '\[security-003\]\(security-003\.md\)'
        }

        It 'Should limit Related section to 5 files maximum' {
            # Arrange
            $files = 1..10 | ForEach-Object {
                $path = Join-Path $script:memoriesPath "adr-00$_.md"
                Set-Content -Path $path -Value "# ADR 00$_"
                $path
            }

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $files[0] -Raw
            $relatedCount = ([regex]::Matches($content, '\[adr-')).Count
            $relatedCount | Should -BeLessOrEqual 5
        }

        It 'Should add index file reference when applicable' {
            # Arrange
            $secFile = Join-Path $script:memoriesPath 'security-001.md'
            $indexFile = Join-Path $script:memoriesPath 'securitys-index.md'

            Set-Content -Path $secFile -Value '# Security 001'
            Set-Content -Path $indexFile -Value '# Security Index'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $secFile -Raw
            $content | Should -Match '\[securitys-index\]\(securitys-index\.md\)'
        }

        It 'Should not add index file reference to the index file itself' {
            # Arrange
            $indexFile = Join-Path $script:memoriesPath 'securitys-index.md'
            $sec1File = Join-Path $script:memoriesPath 'security-001.md'
            $sec2File = Join-Path $script:memoriesPath 'security-002.md'

            Set-Content -Path $indexFile -Value '# Security Index'
            Set-Content -Path $sec1File -Value '# Security 001'
            Set-Content -Path $sec2File -Value '# Security 002'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            # Index files don't match domain patterns, so they don't get Related sections
            # But domain files should reference the index
            $sec1Content = Get-Content $sec1File -Raw
            $sec1Content | Should -Match '\[securitys-index\]\(securitys-index\.md\)'

            # And the index itself shouldn't reference itself in its (non-existent) Related section
            $indexContent = Get-Content $indexFile -Raw
            $indexContent | Should -Not -Match '\[securitys-index\]\(securitys-index\.md\)'
        }

        It 'Should remove duplicate related files' {
            # Arrange
            $sec1 = Join-Path $script:memoriesPath 'security-001.md'
            $sec2 = Join-Path $script:memoriesPath 'security-002.md'
            $indexFile = Join-Path $script:memoriesPath 'securitys-index.md'

            Set-Content -Path $sec1 -Value '# Security 001'
            Set-Content -Path $sec2 -Value '# Security 002'
            Set-Content -Path $indexFile -Value '# Security Index'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $sec1 -Raw
            # Should not have duplicate references
            $security002Count = ([regex]::Matches($content, '\[security-002\]')).Count
            $security002Count | Should -Be 1
        }
    }

    Context 'When processing files with existing Related sections' {
        It 'Should not modify files that already have Related sections' {
            # Arrange
            $sec1 = Join-Path $script:memoriesPath 'security-001.md'
            $sec2 = Join-Path $script:memoriesPath 'security-002.md'

            Set-Content -Path $sec1 -Value @'
# Security 001

Content here.

## Related

- [existing-link](existing-link.md)
'@
            Set-Content -Path $sec2 -Value '# Security 002'

            $originalContent = Get-Content $sec1 -Raw

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $sec1 -Raw
            $content | Should -BeExactly $originalContent
        }

        It 'Should detect Related section case-sensitively' {
            # Arrange
            $sec1 = Join-Path $script:memoriesPath 'security-001.md'
            $sec2 = Join-Path $script:memoriesPath 'security-002.md'

            # Lowercase "related" should NOT prevent addition
            Set-Content -Path $sec1 -Value @'
# Security 001

Some content with the word related in lowercase.
'@
            Set-Content -Path $sec2 -Value '# Security 002'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $sec1 -Raw
            $content | Should -Match '## Related'
        }
    }

    Context 'When using DryRun mode' {
        It 'Should not modify files in DryRun mode' {
            # Arrange
            $sec1 = Join-Path $script:memoriesPath 'security-001.md'
            $sec2 = Join-Path $script:memoriesPath 'security-002.md'

            Set-Content -Path $sec1 -Value '# Security 001'
            Set-Content -Path $sec2 -Value '# Security 002'

            $originalContent = Get-Content $sec1 -Raw

            # Act
            $output = & $scriptPath -DryRun -MemoriesPath $script:memoriesPath -SkipPathValidation *>&1 | Out-String

            # Assert
            $content = Get-Content $sec1 -Raw
            $content | Should -BeExactly $originalContent
            $output | Should -Match '\[DRY RUN\]'
            $output | Should -Match 'This was a dry run'
        }

        It 'Should report what would be changed in DryRun mode' {
            # Arrange
            $sec1 = Join-Path $script:memoriesPath 'security-001.md'
            $sec2 = Join-Path $script:memoriesPath 'security-002.md'

            Set-Content -Path $sec1 -Value '# Security 001'
            Set-Content -Path $sec2 -Value '# Security 002'

            # Act
            $output = & $scriptPath -DryRun -MemoriesPath $script:memoriesPath -SkipPathValidation *>&1 | Out-String

            # Assert
            $output | Should -Match 'Would add Related section to: security-001\.md'
            $output | Should -Match 'Would add Related section to: security-002\.md'
        }
    }

    Context 'When matching domain patterns' {
        It 'Should match ADR prefix pattern' {
            # Arrange
            $adr1 = Join-Path $script:memoriesPath 'adr-001.md'
            $adr2 = Join-Path $script:memoriesPath 'adr-002.md'

            Set-Content -Path $adr1 -Value '# ADR 001'
            Set-Content -Path $adr2 -Value '# ADR 002'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $adr1 -Raw
            $content | Should -Match '\[adr-002\]\(adr-002\.md\)'
        }

        It 'Should match git-hooks prefix pattern' {
            # Arrange
            $hook1 = Join-Path $script:memoriesPath 'git-hooks-001.md'
            $hook2 = Join-Path $script:memoriesPath 'git-hooks-002.md'

            Set-Content -Path $hook1 -Value '# Git Hook 001'
            Set-Content -Path $hook2 -Value '# Git Hook 002'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $hook1 -Raw
            $content | Should -Match '\[git-hooks-002\]\(git-hooks-002\.md\)'
        }

        It 'Should match pr-review prefix pattern' {
            # Arrange
            $pr1 = Join-Path $script:memoriesPath 'pr-review-001.md'
            $pr2 = Join-Path $script:memoriesPath 'pr-review-002.md'

            Set-Content -Path $pr1 -Value '# PR Review 001'
            Set-Content -Path $pr2 -Value '# PR Review 002'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $pr1 -Raw
            $content | Should -Match '\[pr-review-002\]\(pr-review-002\.md\)'
        }

        It 'Should break after first matching pattern' {
            # Arrange
            $file1 = Join-Path $script:memoriesPath 'git-hooks-001.md'
            $file2 = Join-Path $script:memoriesPath 'git-hooks-002.md'
            $file3 = Join-Path $script:memoriesPath 'git-001.md'

            Set-Content -Path $file1 -Value '# Git Hooks 001'
            Set-Content -Path $file2 -Value '# Git Hooks 002'
            Set-Content -Path $file3 -Value '# Git 001'

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation *>&1 | Out-String

            # Assert
            # All files should get Related sections since they match patterns
            $output | Should -Match 'Files updated: 3'

            # Each file should have at least one related link
            $content1 = Get-Content $file1 -Raw
            $content1 | Should -Match '## Related'

            $content3 = Get-Content $file3 -Raw
            $content3 | Should -Match '## Related'
        }

        It 'Should not add Related section for files without domain matches' {
            # Arrange
            $uniqueFile = Join-Path $script:memoriesPath 'unique-standalone-file.md'
            Set-Content -Path $uniqueFile -Value '# Unique File'

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation *>&1 | Out-String

            # Assert
            $output | Should -Match 'Files updated: 0'
            $content = Get-Content $uniqueFile -Raw
            $content | Should -Not -Match '## Related'
        }
    }

    Context 'When reporting statistics' {
        It 'Should report correct files updated count' {
            # Arrange
            $sec1 = Join-Path $script:memoriesPath 'security-001.md'
            $sec2 = Join-Path $script:memoriesPath 'security-002.md'
            $sec3 = Join-Path $script:memoriesPath 'security-003.md'

            Set-Content -Path $sec1 -Value '# Security 001'
            Set-Content -Path $sec2 -Value '# Security 002'
            Set-Content -Path $sec3 -Value '# Security 003'

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation *>&1 | Out-String

            # Assert
            $output | Should -Match 'Files updated: 3'
        }

        It 'Should report correct relationships added count' {
            # Arrange
            $sec1 = Join-Path $script:memoriesPath 'security-001.md'
            $sec2 = Join-Path $script:memoriesPath 'security-002.md'
            $sec3 = Join-Path $script:memoriesPath 'security-003.md'

            Set-Content -Path $sec1 -Value '# Security 001'
            Set-Content -Path $sec2 -Value '# Security 002'
            Set-Content -Path $sec3 -Value '# Security 003'

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation *>&1 | Out-String

            # Assert
            # Each file gets 2 links (to the other 2 files)
            $output | Should -Match 'Relationships added: 6'
        }

        It 'Should report analyzing file count' {
            # Arrange
            $file1 = Join-Path $script:memoriesPath 'file1.md'
            $file2 = Join-Path $script:memoriesPath 'file2.md'

            Set-Content -Path $file1 -Value '# File 1'
            Set-Content -Path $file2 -Value '# File 2'

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation *>&1 | Out-String

            # Assert
            $output | Should -Match 'Analyzing 2 memory files'
        }

        It 'Should log each file update' {
            # Arrange
            $sec1 = Join-Path $script:memoriesPath 'security-001.md'
            $sec2 = Join-Path $script:memoriesPath 'security-002.md'

            Set-Content -Path $sec1 -Value '# Security 001'
            Set-Content -Path $sec2 -Value '# Security 002'

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation *>&1 | Out-String

            # Assert
            $output | Should -Match 'Added Related section to: security-001\.md'
            $output | Should -Match 'Added Related section to: security-002\.md'
        }
    }

    Context 'When using FilesToProcess parameter' {
        It 'Should only process specified files when FilesToProcess is provided' {
            # Arrange
            $sec1 = Join-Path $script:memoriesPath 'security-001.md'
            $sec2 = Join-Path $script:memoriesPath 'security-002.md'
            $sec3 = Join-Path $script:memoriesPath 'security-003.md'

            Set-Content -Path $sec1 -Value '# Security 001'
            Set-Content -Path $sec2 -Value '# Security 002'
            Set-Content -Path $sec3 -Value '# Security 003'

            # Act - Only process sec1
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation -FilesToProcess @($sec1) | Out-Null

            # Assert - Only sec1 should have Related section
            $content1 = Get-Content $sec1 -Raw
            $content2 = Get-Content $sec2 -Raw
            $content3 = Get-Content $sec3 -Raw

            $content1 | Should -Match '## Related'
            $content2 | Should -Not -Match '## Related'
            $content3 | Should -Not -Match '## Related'
        }

        It 'Should process all files when FilesToProcess is empty array' {
            # Arrange
            $sec1 = Join-Path $script:memoriesPath 'security-001.md'
            $sec2 = Join-Path $script:memoriesPath 'security-002.md'

            Set-Content -Path $sec1 -Value '# Security 001'
            Set-Content -Path $sec2 -Value '# Security 002'

            # Act - Empty array should process all files
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation -FilesToProcess @() | Out-Null

            # Assert
            $content1 = Get-Content $sec1 -Raw
            $content2 = Get-Content $sec2 -Raw
            $content1 | Should -Match '## Related'
            $content2 | Should -Match '## Related'
        }

        It 'Should handle FilesToProcess with non-existent files gracefully' {
            # Arrange
            $nonExistent = Join-Path $script:memoriesPath 'non-existent.md'

            # Act & Assert - Should not throw
            { & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation -FilesToProcess @($nonExistent) } | Should -Not -Throw
        }
    }

    Context 'When validating paths (CWE-22 mitigation)' {
        It 'Should reject paths outside project root' {
            # Arrange - Path outside project root
            $outsidePath = '/tmp/malicious-memories'

            # Act & Assert
            { & $scriptPath -MemoriesPath $outsidePath } | Should -Throw -ExpectedMessage '*Security: MemoriesPath must be within project directory*'
        }

        It 'Should reject sibling directory attacks' {
            # Arrange - Path that is a sibling with similar prefix
            # This tests that /home/user/project-attacker doesn't match /home/user/project
            $projectRoot = git rev-parse --show-toplevel
            $siblingPath = "$projectRoot-attacker"

            # Act & Assert
            { & $scriptPath -MemoriesPath $siblingPath } | Should -Throw -ExpectedMessage '*Security: MemoriesPath must be within project directory*'
        }
    }

    Context 'When producing structured output' {
        It 'Should output JSON statistics when OutputJson switch is used' {
            # Arrange
            $sec1 = Join-Path $script:memoriesPath 'security-001.md'
            $sec2 = Join-Path $script:memoriesPath 'security-002.md'

            Set-Content -Path $sec1 -Value '# Security 001'
            Set-Content -Path $sec2 -Value '# Security 002'

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation -OutputJson

            # Assert
            $json = $output | ConvertFrom-Json
            $json.FilesProcessed | Should -BeGreaterOrEqual 2
            $json.FilesModified | Should -Be 2
            $json.RelationshipsAdded | Should -BeGreaterOrEqual 2
        }
    }

    Context 'When handling edge cases' {
        It 'Should preserve file encoding (UTF-8)' {
            # Arrange
            $file1 = Join-Path $script:memoriesPath 'security-001.md'
            $file2 = Join-Path $script:memoriesPath 'security-002.md'

            Set-Content -Path $file1 -Value "# Security 001`nEmoji: 🔒" -Encoding UTF8
            Set-Content -Path $file2 -Value '# Security 002'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $file1 -Raw -Encoding UTF8
            $content | Should -Match '🔒'
            $content | Should -Match '## Related'
        }

        It 'Should trim trailing whitespace before adding Related section' {
            # Arrange
            $sec1 = Join-Path $script:memoriesPath 'security-001.md'
            $sec2 = Join-Path $script:memoriesPath 'security-002.md'

            Set-Content -Path $sec1 -Value "# Security 001`n`n   `n  " -NoNewline
            Set-Content -Path $sec2 -Value '# Security 002'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $sec1 -Raw
            # Should have clean newline before Related section
            $content | Should -Match '# Security 001\n\n## Related'
        }

        It 'Should handle files with complex markdown content' {
            # Arrange
            $sec1 = Join-Path $script:memoriesPath 'security-001.md'
            $sec2 = Join-Path $script:memoriesPath 'security-002.md'

            Set-Content -Path $sec1 -Value @'
# Security 001

## Description

Content with **bold** and *italic*.

```powershell
# Code block
Write-Host "Test"
```

| Table | Header |
|-------|--------|
| Cell  | Value  |
'@
            Set-Content -Path $sec2 -Value '# Security 002'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $sec1 -Raw
            $content | Should -Match '## Related'
            # Original content should be preserved
            $content | Should -Match '\*\*bold\*\*'
            $content | Should -Match 'Write-Host "Test"'
            $content | Should -Match '\| Table \| Header \|'
        }
    }
}
