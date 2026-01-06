BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot '../.claude/skills/session/init/scripts/Extract-SessionTemplate.ps1'
}

Describe 'Extract-SessionTemplate' {
    Context 'When protocol file exists with valid template' {
        BeforeAll {
            # Create temporary test directory
            $testRoot = New-Item -ItemType Directory -Path (Join-Path $TestDrive 'repo') -Force
            Push-Location $testRoot

            # Initialize git repo
            git init *>$null
            git config user.name "Test User" *>$null
            git config user.email "test@example.com" *>$null

            # Create .agents directory
            $agentsDir = New-Item -ItemType Directory -Path (Join-Path $testRoot '.agents') -Force

            # Create mock SESSION-PROTOCOL.md with template
            $protocolContent = @'
# Session Protocol

## Session Log Template

Create at: `.agents/sessions/YYYY-MM-DD-session-NN.md`

```markdown
# Session NN - YYYY-MM-DD

## Session Info

- **Date**: YYYY-MM-DD
- **Branch**: [branch name]
- **Starting Commit**: [SHA]
- **Objective**: [What this session aims to accomplish]

## Protocol Compliance

### Session Start (COMPLETE ALL before work)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena | [ ] | Tool output present |
```

## Other Section
'@
            $protocolPath = Join-Path $agentsDir 'SESSION-PROTOCOL.md'
            Set-Content -Path $protocolPath -Value $protocolContent
        }

        AfterAll {
            Pop-Location
        }

        It 'Should extract template successfully' {
            $result = & $scriptPath
            $LASTEXITCODE | Should -Be 0
            $result | Should -Not -BeNullOrEmpty
        }

        It 'Should extract correct template content' {
            $result = & $scriptPath
            $result | Should -Match '# Session NN - YYYY-MM-DD'
            $result | Should -Match '## Session Info'
            $result | Should -Match 'MUST \| Initialize Serena'
        }

        It 'Should not include markdown code fence markers' {
            $result = & $scriptPath
            $result | Should -Not -Match '```markdown'
            $result | Should -Not -Match '```$'
        }

        It 'Should accept custom protocol path' {
            # Create alternate protocol file
            $customPath = Join-Path $testRoot 'custom-protocol.md'
            Copy-Item -Path (Join-Path $testRoot '.agents/SESSION-PROTOCOL.md') -Destination $customPath

            $result = & $scriptPath -ProtocolPath 'custom-protocol.md'
            $LASTEXITCODE | Should -Be 0
            $result | Should -Not -BeNullOrEmpty
        }
    }

    Context 'When protocol file does not exist' {
        BeforeAll {
            # Create temporary test directory without protocol file
            $testRoot = New-Item -ItemType Directory -Path (Join-Path $TestDrive 'repo-no-file') -Force
            Push-Location $testRoot

            # Initialize git repo
            git init *>$null
            git config user.name "Test User" *>$null
            git config user.email "test@example.com" *>$null
        }

        AfterAll {
            Pop-Location
        }

        It 'Should exit with code 1' {
            & $scriptPath 2>$null
            $LASTEXITCODE | Should -Be 1
        }

        It 'Should output error message' {
            $result = & $scriptPath 2>&1
            $result | Should -Match 'Protocol file not found'
        }
    }

    Context 'When template section is missing' {
        BeforeAll {
            # Create temporary test directory
            $testRoot = New-Item -ItemType Directory -Path (Join-Path $TestDrive 'repo-no-template') -Force
            Push-Location $testRoot

            # Initialize git repo
            git init *>$null
            git config user.name "Test User" *>$null
            git config user.email "test@example.com" *>$null

            # Create .agents directory
            $agentsDir = New-Item -ItemType Directory -Path (Join-Path $testRoot '.agents') -Force

            # Create protocol file WITHOUT template section
            $protocolContent = @'
# Session Protocol

## Some Other Section

This file has no template section.
'@
            $protocolPath = Join-Path $agentsDir 'SESSION-PROTOCOL.md'
            Set-Content -Path $protocolPath -Value $protocolContent
        }

        AfterAll {
            Pop-Location
        }

        It 'Should exit with code 2' {
            & $scriptPath 2>$null
            $LASTEXITCODE | Should -Be 2
        }

        It 'Should output error message' {
            $result = & $scriptPath 2>&1
            $result | Should -Match 'Template section not found'
        }
    }

    Context 'When not in a git repository' {
        BeforeAll {
            # Create temporary test directory without git
            $testRoot = New-Item -ItemType Directory -Path (Join-Path $TestDrive 'not-a-repo') -Force
            Push-Location $testRoot
        }

        AfterAll {
            Pop-Location
        }

        It 'Should exit with code 1' {
            & $scriptPath 2>$null
            $LASTEXITCODE | Should -Be 1
        }

        It 'Should output error message about git' {
            $result = & $scriptPath 2>&1
            $result | Should -Match 'Not in a git repository'
        }
    }

    Context 'Template content preservation' {
        BeforeAll {
            # Create temporary test directory
            $testRoot = New-Item -ItemType Directory -Path (Join-Path $TestDrive 'repo-preserve') -Force
            Push-Location $testRoot

            # Initialize git repo
            git init *>$null
            git config user.name "Test User" *>$null
            git config user.email "test@example.com" *>$null

            # Create .agents directory
            $agentsDir = New-Item -ItemType Directory -Path (Join-Path $testRoot '.agents') -Force

            # Create protocol with multi-line template including special chars
            $protocolContent = @'
## Session Log Template

```markdown
# Session NN - YYYY-MM-DD

Special characters: | # * - [ ]

## Table

| Col1 | Col2 |
|------|------|
| [ ]  | Item |

<!-- Comment -->
```
'@
            $protocolPath = Join-Path $agentsDir 'SESSION-PROTOCOL.md'
            Set-Content -Path $protocolPath -Value $protocolContent
        }

        AfterAll {
            Pop-Location
        }

        It 'Should preserve special markdown characters' {
            $result = & $scriptPath
            $result | Should -Match '\|'
            $result | Should -Match '\#'
            $result | Should -Match '\*'
            $result | Should -Match '\[ \]'
        }

        It 'Should preserve comments' {
            $result = & $scriptPath
            $result | Should -Match '<!-- Comment -->'
        }

        It 'Should preserve table structure' {
            $result = & $scriptPath
            $result | Should -Match '\| Col1 \| Col2 \|'
            $result | Should -Match '\|------|------\|'
        }
    }
}
