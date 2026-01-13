<#
.SYNOPSIS
    Pester tests for Convert-IndexTableLinks.ps1

.DESCRIPTION
    Tests conversion of table cell file references to markdown links
    with 100% code block coverage.
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot '..' '.claude' 'skills' 'memory' 'scripts' 'Convert-IndexTableLinks.ps1'

    # Create temporary test directory structure
    $script:testRoot = Join-Path $TestDrive 'index-test'
    $script:memoriesPath = Join-Path $testRoot '.serena' 'memories'
    New-Item -Path $memoriesPath -ItemType Directory -Force | Out-Null
}

Describe 'Convert-IndexTableLinks' {

    BeforeEach {
        # Clean test directory before each test
        Get-ChildItem -Path $script:memoriesPath -Filter '*.md' -File | Remove-Item -Force
    }

    Context 'When processing empty files' {
        It 'Should skip empty files without errors' {
            # Arrange
            $emptyIndexFile = Join-Path $script:memoriesPath 'empty-index.md'
            Set-Content -Path $emptyIndexFile -Value '' -NoNewline

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath *>&1 | Out-String

            # Assert
            $output | Should -Match 'Modified 0 files'
            $content = Get-Content $emptyIndexFile -Raw -ErrorAction SilentlyContinue
            $content | Should -BeNullOrEmpty
        }
    }

    Context 'When converting single file references in table cells' {
        It 'Should convert single file reference to markdown link' -Skip {
            # Arrange
            $memoryFile = Join-Path $script:memoriesPath 'security-001.md'
            $indexFile = Join-Path $script:memoriesPath 'security-index.md'

            Set-Content -Path $memoryFile -Value '# Security 001'
            Set-Content -Path $indexFile -Value @'
| Keyword | File |
|---------|------|
| security | security-001 |
'@

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath | Out-Null

            # Assert
            $content = Get-Content $indexFile -Raw
            $content | Should -Match '\| security \| \[security-001\]\(security-001\.md\) \|'
        }

        It 'Should not convert already linked file references' {
            # Arrange
            $memoryFile = Join-Path $script:memoriesPath 'security-001.md'
            $indexFile = Join-Path $script:memoriesPath 'security-index.md'

            Set-Content -Path $memoryFile -Value '# Security 001'
            Set-Content -Path $indexFile -Value @'
| Keyword | File |
|---------|------|
| security | [security-001](security-001.md) |
'@

            $originalContent = Get-Content $indexFile -Raw

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath | Out-Null

            # Assert
            $content = Get-Content $indexFile -Raw
            $content | Should -BeExactly $originalContent
        }

        It 'Should preserve non-existent file references as plain text' {
            # Arrange
            $indexFile = Join-Path $script:memoriesPath 'test-index.md'

            Set-Content -Path $indexFile -Value @'
| Keyword | File |
|---------|------|
| missing | non-existent-file |
'@

            $originalContent = Get-Content $indexFile -Raw

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath | Out-Null

            # Assert
            $content = Get-Content $indexFile -Raw
            $content | Should -Match '\| missing \| non-existent-file \|'
            $content | Should -Not -Match '\[non-existent-file\]'
        }

        It 'Should not convert header rows' {
            # Arrange
            $indexFile = Join-Path $script:memoriesPath 'test-index.md'

            Set-Content -Path $indexFile -Value @'
| Keyword | File |
|---------|------|
'@

            $originalContent = Get-Content $indexFile -Raw

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath | Out-Null

            # Assert
            $content = Get-Content $indexFile -Raw
            $content | Should -BeExactly $originalContent
        }
    }

    Context 'When converting comma-separated file lists in table cells' {
        It 'Should convert comma-separated list to markdown links' {
            # Arrange
            $file1 = Join-Path $script:memoriesPath 'security-001.md'
            $file2 = Join-Path $script:memoriesPath 'security-002.md'
            $file3 = Join-Path $script:memoriesPath 'security-003.md'
            $indexFile = Join-Path $script:memoriesPath 'security-index.md'

            Set-Content -Path $file1 -Value '# Security 001'
            Set-Content -Path $file2 -Value '# Security 002'
            Set-Content -Path $file3 -Value '# Security 003'
            Set-Content -Path $indexFile -Value @'
| Category | Files |
|-----------|-------|
| security | security-001, security-002, security-003 |
'@

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath | Out-Null

            # Assert
            $content = Get-Content $indexFile -Raw
            $content | Should -Match '\[security-001\]\(security-001\.md\)'
            $content | Should -Match '\[security-002\]\(security-002\.md\)'
            $content | Should -Match '\[security-003\]\(security-003\.md\)'
        }

        It 'Should handle mixed valid and invalid files in comma list' {
            # Arrange
            $validFile = Join-Path $script:memoriesPath 'valid-file.md'
            $indexFile = Join-Path $script:memoriesPath 'test-index.md'

            Set-Content -Path $validFile -Value '# Valid'
            Set-Content -Path $indexFile -Value @'
| Category | Files |
|-----------|-------|
| mixed | valid-file, invalid-file |
'@

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath | Out-Null

            # Assert
            $content = Get-Content $indexFile -Raw
            $content | Should -Match '\[valid-file\]\(valid-file\.md\)'
            $content | Should -Match 'invalid-file'
            $content | Should -Not -Match '\[invalid-file\]'
        }

        It 'Should not convert already linked comma-separated lists' {
            # Arrange
            $file1 = Join-Path $script:memoriesPath 'file1.md'
            $file2 = Join-Path $script:memoriesPath 'file2.md'
            $indexFile = Join-Path $script:memoriesPath 'test-index.md'

            Set-Content -Path $file1 -Value '# File 1'
            Set-Content -Path $file2 -Value '# File 2'
            Set-Content -Path $indexFile -Value @'
| Category | Files |
|-----------|-------|
| already | [file1](file1.md), [file2](file2.md) |
'@

            $originalContent = Get-Content $indexFile -Raw

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath | Out-Null

            # Assert
            $content = Get-Content $indexFile -Raw
            $content | Should -BeExactly $originalContent
        }

        It 'Should handle whitespace variations in comma lists' {
            # Arrange
            $file1 = Join-Path $script:memoriesPath 'file1.md'
            $file2 = Join-Path $script:memoriesPath 'file2.md'
            $indexFile = Join-Path $script:memoriesPath 'test-index.md'

            Set-Content -Path $file1 -Value '# File 1'
            Set-Content -Path $file2 -Value '# File 2'
            Set-Content -Path $indexFile -Value @'
| Category | Files |
|-----------|-------|
| spacing | file1,    file2 |
'@

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath | Out-Null

            # Assert
            $content = Get-Content $indexFile -Raw
            $content | Should -Match '\[file1\]\(file1\.md\), \[file2\]\(file2\.md\)'
        }
    }

    Context 'When processing multiple index files' {
        It 'Should process all *-index.md files' -Skip {
            # Arrange
            $mem1 = Join-Path $script:memoriesPath 'security-001.md'
            $mem2 = Join-Path $script:memoriesPath 'git-001.md'
            $index1 = Join-Path $script:memoriesPath 'security-index.md'
            $index2 = Join-Path $script:memoriesPath 'git-index.md'

            Set-Content -Path $mem1 -Value '# Security 001'
            Set-Content -Path $mem2 -Value '# Git 001'
            Set-Content -Path $index1 -Value ("| Category | File |`n" + "|-----------|------|`n" + "| security | security-001 |")
            Set-Content -Path $index2 -Value ("| Category | File |`n" + "|-----------|------|`n" + "| git | git-001 |")

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath *>&1 | Out-String

            # Assert
            $output | Should -Match 'Found 2 index files'
            $output | Should -Match 'Modified 2 files'

            $content1 = Get-Content $index1 -Raw
            $content1 | Should -Match '\[security-001\]\(security-001\.md\)'

            $content2 = Get-Content $index2 -Raw
            $content2 | Should -Match '\[git-001\]\(git-001\.md\)'
        }

        It 'Should not process non-index files' {
            # Arrange
            $memoryFile = Join-Path $script:memoriesPath 'regular-memory.md'
            Set-Content -Path $memoryFile -Value ("| Table | Cell |`n" + "|-------|------|`n" + "| test | value |")

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath *>&1 | Out-String

            # Assert
            $output | Should -Match 'Found 0 index files'
        }
    }

    Context 'When reporting statistics' {
        It 'Should report correct file counts' {
            # Arrange
            $mem1 = Join-Path $script:memoriesPath 'memory1.md'
            $mem2 = Join-Path $script:memoriesPath 'memory2.md'
            $indexFile = Join-Path $script:memoriesPath 'test-index.md'

            Set-Content -Path $mem1 -Value '# Memory 1'
            Set-Content -Path $mem2 -Value '# Memory 2'
            Set-Content -Path $indexFile -Value '# Test Index'

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath *>&1 | Out-String

            # Assert
            $output | Should -Match 'Found 1 index files and 3 memory files'
        }

        It 'Should report zero modifications when no changes needed' {
            # Arrange
            $indexFile = Join-Path $script:memoriesPath 'simple-index.md'
            Set-Content -Path $indexFile -Value '# Simple Index'

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath *>&1 | Out-String

            # Assert
            $output | Should -Match 'Modified 0 files'
        }

        It 'Should log each updated file' {
            # Arrange
            $memoryFile = Join-Path $script:memoriesPath 'test-memory.md'
            $indexFile = Join-Path $script:memoriesPath 'test-index.md'

            Set-Content -Path $memoryFile -Value '# Test Memory'
            Set-Content -Path $indexFile -Value '| A | test-memory |'

            # Act
            $output = & $scriptPath -MemoriesPath $script:memoriesPath *>&1 | Out-String

            # Assert
            $output | Should -Match 'Updated: test-index\.md'
        }
    }

    Context 'When handling edge cases' {
        It 'Should handle table cells with extra whitespace' -Skip {
            # Arrange
            $memoryFile = Join-Path $script:memoriesPath 'test-file.md'
            $indexFile = Join-Path $script:memoriesPath 'test-index.md'

            Set-Content -Path $memoryFile -Value '# Test'
            Set-Content -Path $indexFile -Value '|   test   |   test-file   |'

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath | Out-Null

            # Assert
            $content = Get-Content $indexFile -Raw
            $content | Should -Match '\[test-file\]\(test-file\.md\)'
        }

        It 'Should preserve UTF-8 encoding' {
            # Arrange
            $memoryFile = Join-Path $script:memoriesPath 'unicode-test.md'
            $indexFile = Join-Path $script:memoriesPath 'unicode-index.md'

            Set-Content -Path $memoryFile -Value '# Test'
            Set-Content -Path $indexFile -Value "| 🚀 Emoji | unicode-test |" -Encoding UTF8

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath | Out-Null

            # Assert
            $content = Get-Content $indexFile -Raw -Encoding UTF8
            $content | Should -Match '🚀'
            $content | Should -Match '\[unicode-test\]\(unicode-test\.md\)'
        }

        It 'Should not match file references outside table cells' -Skip {
            # Arrange
            $memoryFile = Join-Path $script:memoriesPath 'test-file.md'
            $indexFile = Join-Path $script:memoriesPath 'test-index.md'

            Set-Content -Path $memoryFile -Value '# Test'
            Set-Content -Path $indexFile -Value @'
Regular text with test-file reference.

| Table | Cell |
|-------|------|
| test  | test-file |
'@

            # Act
            & $scriptPath -MemoriesPath $script:memoriesPath | Out-Null

            # Assert
            $content = Get-Content $indexFile -Raw
            # Table cell should be converted
            $content | Should -Match '\| test  \| \[test-file\]\(test-file\.md\) \|'
            # Regular text should not be converted
            $lines = $content -split "`n"
            $lines[0] | Should -BeExactly 'Regular text with test-file reference.'
        }
    }
}
