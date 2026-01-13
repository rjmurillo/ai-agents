<#
.SYNOPSIS
    Pester tests for Invoke-MemoryCrossReference.ps1

.DESCRIPTION
    Tests the orchestrator script that coordinates all memory cross-reference scripts.
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot '..' '.claude' 'skills' 'memory' 'scripts' 'Invoke-MemoryCrossReference.ps1'

    # Create temporary test directory structure
    $script:testRoot = Join-Path $TestDrive 'orchestrator-test'
    $script:memoriesPath = Join-Path $testRoot '.serena' 'memories'
    New-Item -Path $memoriesPath -ItemType Directory -Force | Out-Null
}

Describe 'Invoke-MemoryCrossReference' {

    BeforeEach {
        # Clean test directory before each test
        Get-ChildItem -Path $script:memoriesPath -Filter '*.md' -File -ErrorAction SilentlyContinue | Remove-Item -Force
    }

    Context 'When running all scripts in sequence' {
        It 'Should execute all three scripts and return aggregate statistics' {
            # Arrange - Create files that trigger all three scripts
            $indexFile = Join-Path $script:memoriesPath 'test-index.md'
            $secFile1 = Join-Path $script:memoriesPath 'security-001.md'
            $secFile2 = Join-Path $script:memoriesPath 'security-002.md'

            Set-Content -Path $indexFile -Value "| Category | File |`n|----------|------|`n| sec | security-001 |"
            Set-Content -Path $secFile1 -Value "# Security 001`n`nSee `security-002` for more."
            Set-Content -Path $secFile2 -Value '# Security 002'

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation -OutputJson

            # Assert
            $json = $output | ConvertFrom-Json
            $json.Success | Should -Be $true
            $json.FilesModified | Should -BeGreaterOrEqual 1
        }

        It 'Should process files in correct order (index, backticks, related)' {
            # Arrange
            $indexFile = Join-Path $script:memoriesPath 'test-index.md'
            $secFile1 = Join-Path $script:memoriesPath 'security-001.md'
            $secFile2 = Join-Path $script:memoriesPath 'security-002.md'

            Set-Content -Path $indexFile -Value "| Category | File |`n|----------|------|`n| sec | security-001 |"
            Set-Content -Path $secFile1 -Value '# Security 001'
            Set-Content -Path $secFile2 -Value '# Security 002'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert - Check all transformations applied
            $indexContent = Get-Content $indexFile -Raw
            $indexContent | Should -Match '\[security-001\]\(security-001\.md\)'

            $sec1Content = Get-Content $secFile1 -Raw
            $sec1Content | Should -Match '## Related'
        }
    }

    Context 'When using FilesToProcess parameter' {
        It 'Should pass FilesToProcess to child scripts' {
            # Arrange
            $secFile1 = Join-Path $script:memoriesPath 'security-001.md'
            $secFile2 = Join-Path $script:memoriesPath 'security-002.md'
            $secFile3 = Join-Path $script:memoriesPath 'security-003.md'

            Set-Content -Path $secFile1 -Value '# Security 001'
            Set-Content -Path $secFile2 -Value '# Security 002'
            Set-Content -Path $secFile3 -Value '# Security 003'

            # Act - Only process secFile1
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation -FilesToProcess @($secFile1) | Out-Null

            # Assert - Only secFile1 should have Related section
            $content1 = Get-Content $secFile1 -Raw
            $content2 = Get-Content $secFile2 -Raw

            $content1 | Should -Match '## Related'
            $content2 | Should -Not -Match '## Related'
        }
    }

    Context 'When producing output' {
        It 'Should output JSON when OutputJson is specified' {
            # Arrange
            $secFile1 = Join-Path $script:memoriesPath 'security-001.md'
            $secFile2 = Join-Path $script:memoriesPath 'security-002.md'

            Set-Content -Path $secFile1 -Value '# Security 001'
            Set-Content -Path $secFile2 -Value '# Security 002'

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation -OutputJson

            # Assert
            $json = $output | ConvertFrom-Json
            $json | Should -Not -BeNullOrEmpty
            $json.PSObject.Properties.Name | Should -Contain 'IndexLinksAdded'
            $json.PSObject.Properties.Name | Should -Contain 'BacktickLinksAdded'
            $json.PSObject.Properties.Name | Should -Contain 'RelatedSectionsAdded'
            $json.PSObject.Properties.Name | Should -Contain 'FilesModified'
            $json.PSObject.Properties.Name | Should -Contain 'Success'
        }

        It 'Should output human-readable text by default' {
            # Arrange
            $secFile1 = Join-Path $script:memoriesPath 'security-001.md'
            Set-Content -Path $secFile1 -Value '# Security 001'

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation *>&1 | Out-String

            # Assert
            $output | Should -Match 'Step 1/3'
            $output | Should -Match 'Step 2/3'
            $output | Should -Match 'Step 3/3'
            $output | Should -Match 'Summary'
        }
    }

    Context 'When handling errors' {
        It 'Should continue processing even if one script fails' {
            # Arrange - Create a minimal valid setup
            $secFile1 = Join-Path $script:memoriesPath 'security-001.md'
            Set-Content -Path $secFile1 -Value '# Security 001'

            # Act - Should not throw even with minimal input
            { & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation } | Should -Not -Throw
        }

        It 'Should always exit with code 0 (non-blocking for hooks)' {
            # Arrange
            $secFile1 = Join-Path $script:memoriesPath 'security-001.md'
            Set-Content -Path $secFile1 -Value '# Security 001'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context 'When no changes needed' {
        It 'Should report zero modifications when files already processed' {
            # Arrange - Create already processed files
            $secFile1 = Join-Path $script:memoriesPath 'security-001.md'
            $secFile2 = Join-Path $script:memoriesPath 'security-002.md'

            Set-Content -Path $secFile1 -Value @'
# Security 001

## Related

- [security-002](security-002.md)
'@
            Set-Content -Path $secFile2 -Value @'
# Security 002

## Related

- [security-001](security-001.md)
'@

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation -OutputJson

            # Assert
            $json = $output | ConvertFrom-Json
            $json.FilesModified | Should -Be 0
            $json.Success | Should -Be $true
        }
    }
}
