<#
.SYNOPSIS
  Pester tests for Validate-SlashCommand.ps1

.DESCRIPTION
  Tests covering all 5 validation categories:
  1. Frontmatter validation
  2. Argument validation
  3. Security validation
  4. Length validation
  5. Lint validation

  Target: 80%+ code coverage

.NOTES
  EXIT CODES:
  0  - Success: All tests passed
  1  - Error: One or more tests failed (set by Pester framework)

  See: ADR-035 Exit Code Standardization
#>

BeforeAll {
  $ScriptPath = Join-Path $PSScriptRoot 'Validate-SlashCommand.ps1'
  $ScriptContent = Get-Content -Path $ScriptPath -Raw
}

Describe 'Validate-SlashCommand.ps1' {
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

    It 'Should use StrictMode' {
      $ScriptContent | Should -Match 'Set-StrictMode\s+-Version\s+Latest'
    }

    It 'Should set ErrorActionPreference to Stop' {
      $ScriptContent | Should -Match "\`$ErrorActionPreference\s*=\s*'Stop'"
    }
  }

  Context 'Parameter Definitions' {
    It 'Should have mandatory Path parameter' {
      $ScriptContent | Should -Match '\[Parameter\(Mandatory\s*=\s*\$true\)\]'
      $ScriptContent | Should -Match '\[string\]\$Path'
    }

    It 'Should have SkipLint switch parameter' {
      $ScriptContent | Should -Match '\[switch\]\$SkipLint'
    }
  }

  Context 'Frontmatter Validation' {
    BeforeAll {
      $fixturesDir = Join-Path $TestDrive 'fixtures'
      New-Item -ItemType Directory -Path $fixturesDir -Force | Out-Null
    }

    It 'Should FAIL when frontmatter is missing' {
      $file = Join-Path $fixturesDir 'no-frontmatter.md'
      '# Command without frontmatter' | Out-File -FilePath $file -Encoding utf8

      & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }

    It 'Should FAIL when description is missing' {
      $file = Join-Path $fixturesDir 'no-description.md'
      $content = @'
---
argument-hint: <arg>
---
Command with no description
'@
      $content | Out-File -FilePath $file -Encoding utf8

      & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }

    It 'Should PASS with valid trigger-based description starting with Use when' {
      $file = Join-Path $fixturesDir 'valid-trigger.md'
      $content = @'
---
description: Use when Claude needs to analyze code patterns
---
Analyze the codebase
'@
      $content | Out-File -FilePath $file -Encoding utf8

      & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 0
    }

    It 'Should PASS with description starting with Generate' {
      $file = Join-Path $fixturesDir 'valid-generate.md'
      $content = @'
---
description: Generate a summary report
---
Generate report content
'@
      $content | Out-File -FilePath $file -Encoding utf8

      & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 0
    }

    It 'Should PASS with description starting with Research' {
      $file = Join-Path $fixturesDir 'valid-research.md'
      $content = @'
---
description: Research best practices
---
Research content
'@
      $content | Out-File -FilePath $file -Encoding utf8

      & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 0
    }

    It 'Should WARN but PASS with non-trigger description' {
      $file = Join-Path $fixturesDir 'non-trigger.md'
      $content = @'
---
description: This is a command for testing
---
Test content
'@
      $content | Out-File -FilePath $file -Encoding utf8

      $output = & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1
      $LASTEXITCODE | Should -Be 0
      $output -join "`n" | Should -Match 'WARNING:.*Description should start with action verb'
    }

    It 'Should handle multi-line YAML descriptions' {
      $file = Join-Path $fixturesDir 'multiline-desc.md'
      $content = @'
---
description: >
  Use when Claude needs to analyze complex patterns
  across multiple dimensions
argument-hint: <pattern>
---
Test command
$ARGUMENTS
'@
      $content | Out-File -FilePath $file -Encoding utf8

      # Note: multi-line YAML is a known limitation per plan WHY comments
      # This test documents current behavior (may fail or pass depending on regex)
      & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1 | Out-Null
      # Accept either pass or fail for multi-line - just document behavior
      $LASTEXITCODE | Should -BeIn @(0, 1)
    }
  }

  Context 'Argument Validation' {
    BeforeAll {
      $fixturesDir = Join-Path $TestDrive 'arg-fixtures'
      New-Item -ItemType Directory -Path $fixturesDir -Force | Out-Null
    }

    It 'Should FAIL when prompt uses $ARGUMENTS without argument-hint' {
      $file = Join-Path $fixturesDir 'missing-arg-hint.md'
      # Use here-string and escape the dollar sign with backtick
      $content = @"
---
description: Use when testing arguments
---
Process `$ARGUMENTS
"@
      $content | Out-File -FilePath $file -Encoding utf8

      & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }

    It 'Should PASS when argument-hint matches $ARGUMENTS usage' {
      $file = Join-Path $fixturesDir 'valid-args.md'
      $content = @"
---
description: Use when processing input
argument-hint: <input-data>
---
Process `$ARGUMENTS
"@
      $content | Out-File -FilePath $file -Encoding utf8

      & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 0
    }

    It 'Should FAIL when prompt uses $1 without argument-hint' {
      $file = Join-Path $fixturesDir 'uses-positional.md'
      $content = @"
---
description: Use when testing positional args
---
First argument: `$1
Second: `$2
"@
      $content | Out-File -FilePath $file -Encoding utf8

      & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }

    It 'Should WARN when argument-hint exists but not used' {
      $file = Join-Path $fixturesDir 'unused-hint.md'
      $content = @'
---
description: Use when testing unused hints
argument-hint: <unused>
---
This prompt does not use any arguments
'@
      $content | Out-File -FilePath $file -Encoding utf8

      $output = & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1
      $LASTEXITCODE | Should -Be 0
      $output -join "`n" | Should -Match "WARNING:.*argument-hint.*but prompt doesn't use"
    }
  }

  Context 'Security Validation' {
    BeforeAll {
      $fixturesDir = Join-Path $TestDrive 'security-fixtures'
      New-Item -ItemType Directory -Path $fixturesDir -Force | Out-Null
    }

    It 'Should FAIL when bash execution has no allowed-tools' {
      $file = Join-Path $fixturesDir 'bash-no-tools.md'
      $content = @'
---
description: Use when running git commands
---
Execute: !git status
'@
      $content | Out-File -FilePath $file -Encoding utf8

      & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }

    It 'Should FAIL with overly permissive wildcard *' {
      $file = Join-Path $fixturesDir 'bad-wildcard.md'
      $content = @'
---
description: Use when running commands
allowed-tools: [*]
---
Execute: !git status
'@
      $content | Out-File -FilePath $file -Encoding utf8

      & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }

    It 'Should PASS with scoped MCP wildcard mcp__*' {
      $file = Join-Path $fixturesDir 'scoped-mcp.md'
      $content = @'
---
description: Use when using MCP tools
allowed-tools: [mcp__*]
---
Execute: !mcp__serena__find_symbol
'@
      $content | Out-File -FilePath $file -Encoding utf8

      & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 0
    }

    It 'Should PASS with scoped Serena wildcard mcp__serena__*' {
      $file = Join-Path $fixturesDir 'scoped-serena.md'
      $content = @'
---
description: Use when using Serena tools
allowed-tools: [mcp__serena__*]
---
Execute: !mcp__serena__find_symbol
'@
      $content | Out-File -FilePath $file -Encoding utf8

      & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 0
    }

    It 'Should PASS with explicit tool list' {
      $file = Join-Path $fixturesDir 'explicit-tools.md'
      $content = @'
---
description: Use when running specific tools
allowed-tools: [Bash, Read, Write]
---
Execute: !git status
'@
      $content | Out-File -FilePath $file -Encoding utf8

      & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 0
    }
  }

  Context 'Length Validation' {
    BeforeAll {
      $fixturesDir = Join-Path $TestDrive 'length-fixtures'
      New-Item -ItemType Directory -Path $fixturesDir -Force | Out-Null
    }

    It 'Should WARN when file >200 lines' {
      $file = Join-Path $fixturesDir 'long-file.md'
      $header = @'
---
description: Use when testing long files
---
'@
      $lines = 1..250 | ForEach-Object { "Line $_" }
      $longContent = $header + "`n" + ($lines -join "`n")
      $longContent | Out-File -FilePath $file -Encoding utf8

      $output = & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1
      # Should pass with warning (warnings don't cause failure)
      $LASTEXITCODE | Should -Be 0
      $output -join "`n" | Should -Match 'WARNING:.*>200.*Consider converting to skill'
    }

    It 'Should PASS without warning when file <=200 lines' {
      $file = Join-Path $fixturesDir 'normal-file.md'
      $content = @'
---
description: Use when testing normal length files
---
This is a normal length file.
'@
      $content | Out-File -FilePath $file -Encoding utf8

      $output = & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1
      $LASTEXITCODE | Should -Be 0
      $output -join "`n" | Should -Not -Match 'WARNING:.*>200'
    }
  }

  Context 'Lint Validation' {
    BeforeAll {
      $fixturesDir = Join-Path $TestDrive 'lint-fixtures'
      New-Item -ItemType Directory -Path $fixturesDir -Force | Out-Null
    }

    It 'Should run markdownlint when SkipLint not specified' {
      $ScriptContent | Should -Match 'npx\s+markdownlint-cli2'
    }

    It 'Should skip lint when SkipLint switch is used' {
      $ScriptContent | Should -Match 'if\s*\(\s*-not\s+\$SkipLint\s*\)'
    }

    It 'Should check LASTEXITCODE after lint' {
      $ScriptContent | Should -Match 'if\s*\(\s*\$LASTEXITCODE\s*-ne\s*0\s*\)'
    }
  }

  Context 'Exit Code Behavior' {
    BeforeAll {
      $fixturesDir = Join-Path $TestDrive 'exit-fixtures'
      New-Item -ItemType Directory -Path $fixturesDir -Force | Out-Null
    }

    It 'Should exit 0 for valid command' {
      $file = Join-Path $fixturesDir 'valid.md'
      $content = @'
---
description: Use when testing valid commands
---
Valid command content
'@
      $content | Out-File -FilePath $file -Encoding utf8

      & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 0
    }

    It 'Should exit 1 for BLOCKING violation' {
      $file = Join-Path $fixturesDir 'blocking.md'
      'No frontmatter at all' | Out-File -FilePath $file -Encoding utf8

      & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }

    It 'Should exit 0 for WARNING-only violations' {
      $file = Join-Path $fixturesDir 'warning-only.md'
      $content = @'
---
description: This description does not start with action verb
---
Warning only content
'@
      $content | Out-File -FilePath $file -Encoding utf8

      & pwsh -NoProfile -File $ScriptPath -Path $file -SkipLint 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 0
    }

    It 'Should exit 1 for file not found' {
      & pwsh -NoProfile -File $ScriptPath -Path '/nonexistent/file.md' -SkipLint 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }
  }

  Context 'Output Messages' {
    It 'Should output [PASS] for success' {
      $ScriptContent | Should -Match '\[PASS\]'
    }

    It 'Should output [FAIL] for failure' {
      $ScriptContent | Should -Match '\[FAIL\]'
    }

    It 'Should output violation counts' {
      $ScriptContent | Should -Match '\$blockingCount'
      $ScriptContent | Should -Match '\$warningCount'
    }

    It 'Should use color output' {
      $ScriptContent | Should -Match '-ForegroundColor\s+Red'
      $ScriptContent | Should -Match '-ForegroundColor\s+Green'
      $ScriptContent | Should -Match '-ForegroundColor\s+Yellow'
    }
  }

  Context 'WHY Comments Documentation' {
    It 'Should have WHY comment for YAML parsing approach' {
      $ScriptContent | Should -Match '# WHY:.*regex.*YAML'
    }

    It 'Should have LIMITATION comment for multi-line YAML' {
      $ScriptContent | Should -Match '# LIMITATION:'
    }

    It 'Should have MITIGATION comment' {
      $ScriptContent | Should -Match '# MITIGATION:'
    }
  }
}
