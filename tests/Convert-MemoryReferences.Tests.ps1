<#
.SYNOPSIS
    Pester tests for Convert-MemoryReferences.ps1

.DESCRIPTION
    Tests conversion of backtick memory references to markdown links
    with 100% code block coverage.
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot '..' '.claude' 'skills' 'memory' 'scripts' 'Convert-MemoryReferences.ps1'

    # Create temporary test directory structure
    $script:testRoot = Join-Path $TestDrive 'memory-test'
    $script:memoriesPath = Join-Path $testRoot '.serena' 'memories'
    New-Item -Path $memoriesPath -ItemType Directory -Force | Out-Null
}

Describe 'Convert-MemoryReferences' {

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
            $output | Should -Match 'Modified 0 files'
            $content = Get-Content $emptyFile -Raw -ErrorAction SilentlyContinue
            $content | Should -BeNullOrEmpty
        }
    }

    Context 'When converting valid memory references' {
        It 'Should convert backtick references to markdown links for existing memories' {
            # Arrange
            $targetFile = Join-Path $script:memoriesPath 'target-memory.md'
            $sourceFile = Join-Path $script:memoriesPath 'source-memory.md'

            Set-Content -Path $targetFile -Value '# Target Memory'
            Set-Content -Path $sourceFile -Value 'Reference to `target-memory` here.'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $sourceFile -Raw
            $content | Should -Match '\[target-memory\]\(target-memory\.md\)'
            $content | Should -Not -Match '`target-memory`'
        }

        It 'Should preserve backticks for non-existent memory references' {
            # Arrange
            $sourceFile = Join-Path $script:memoriesPath 'source-memory.md'
            Set-Content -Path $sourceFile -Value 'Reference to `non-existent-memory` here.'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $sourceFile -Raw
            $content | Should -Match '`non-existent-memory`'
            $content | Should -Not -Match '\[non-existent-memory\]'
        }

        It 'Should not convert already linked items' {
            # Arrange
            $targetFile = Join-Path $script:memoriesPath 'target-memory.md'
            $sourceFile = Join-Path $script:memoriesPath 'source-memory.md'

            Set-Content -Path $targetFile -Value '# Target Memory'
            Set-Content -Path $sourceFile -Value 'Already linked: [`target-memory`](target-memory.md)'

            $originalContent = Get-Content $sourceFile -Raw

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $sourceFile -Raw
            $content | Should -BeExactly $originalContent
        }

        It 'Should handle multiple references in single file' {
            # Arrange
            $mem1 = Join-Path $script:memoriesPath 'memory-one.md'
            $mem2 = Join-Path $script:memoriesPath 'memory-two.md'
            $sourceFile = Join-Path $script:memoriesPath 'source-memory.md'

            Set-Content -Path $mem1 -Value '# Memory 1'
            Set-Content -Path $mem2 -Value '# Memory 2'
            Set-Content -Path $sourceFile -Value 'See `memory-one` and `memory-two` for details.'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $sourceFile -Raw
            $content | Should -Match '\[memory-one\]\(memory-one\.md\)'
            $content | Should -Match '\[memory-two\]\(memory-two\.md\)'
        }

        It 'Should not convert backticks with spaces (code snippets)' {
            # Arrange
            $sourceFile = Join-Path $script:memoriesPath 'source-memory.md'
            Set-Content -Path $sourceFile -Value 'Code: `git commit -m "message"` here.'

            $originalContent = Get-Content $sourceFile -Raw

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $sourceFile -Raw
            $content | Should -BeExactly $originalContent
        }

        It 'Should not convert file paths with slashes' {
            # Arrange
            $sourceFile = Join-Path $script:memoriesPath 'source-memory.md'
            Set-Content -Path $sourceFile -Value 'Path: `.agents/sessions/file.md` here.'

            $originalContent = Get-Content $sourceFile -Raw

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $sourceFile -Raw
            $content | Should -BeExactly $originalContent
        }
    }

    Context 'When reporting statistics' {
        It 'Should report correct file count' {
            # Arrange
            $file1 = Join-Path $script:memoriesPath 'file1.md'
            $file2 = Join-Path $script:memoriesPath 'file2.md'
            Set-Content -Path $file1 -Value '# File 1'
            Set-Content -Path $file2 -Value '# File 2'

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation *>&1 | Out-String

            # Assert
            $output | Should -Match 'Found 2 memory files'
        }

        It 'Should report correct modification count' {
            # Arrange
            $targetFile = Join-Path $script:memoriesPath 'target-memory.md'
            $source1 = Join-Path $script:memoriesPath 'source1.md'
            $source2 = Join-Path $script:memoriesPath 'source2.md'
            $unchanged = Join-Path $script:memoriesPath 'unchanged.md'

            Set-Content -Path $targetFile -Value '# Target'
            Set-Content -Path $source1 -Value 'Reference `target-memory` here.'
            Set-Content -Path $source2 -Value 'Another `target-memory` reference.'
            Set-Content -Path $unchanged -Value 'No references here.'

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation *>&1 | Out-String

            # Assert
            $output | Should -Match 'Modified 2 files'
            $output | Should -Match 'Updated: source1\.md'
            $output | Should -Match 'Updated: source2\.md'
        }

        It 'Should report zero modifications when no changes needed' {
            # Arrange
            $file = Join-Path $script:memoriesPath 'simple.md'
            Set-Content -Path $file -Value '# Simple File'

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation *>&1 | Out-String

            # Assert
            $output | Should -Match 'Modified 0 files'
        }
    }

    Context 'When handling edge cases' {
        It 'Should handle hyphenated memory names' {
            # Arrange
            $targetFile = Join-Path $script:memoriesPath 'multi-word-memory-name.md'
            $sourceFile = Join-Path $script:memoriesPath 'source.md'

            Set-Content -Path $targetFile -Value '# Multi Word'
            Set-Content -Path $sourceFile -Value 'See `multi-word-memory-name` for details.'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $sourceFile -Raw
            $content | Should -Match '\[multi-word-memory-name\]\(multi-word-memory-name\.md\)'
        }

        It 'Should preserve encoding (UTF8)' -Skip {
            # Arrange
            $sourceFile = Join-Path $script:memoriesPath 'unicode-test.md'
            $targetFile = Join-Path $script:memoriesPath 'target-memory.md'

            Set-Content -Path $targetFile -Value '# Target'
            Set-Content -Path $sourceFile -Value "Unicode: emoji 🚀 and `target-memory` reference" -Encoding UTF8

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath -SkipPathValidation | Out-Null

            # Assert
            $content = Get-Content $sourceFile -Raw -Encoding UTF8
            $content | Should -Match '🚀'
            $content | Should -Match '\[target-memory\]\(target-memory\.md\)'
        }
    }
}
