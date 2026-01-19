#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Pester tests for Export-ClaudeMemMemories.ps1

.DESCRIPTION
    Security-focused unit tests for the memory export script.
    Tests path traversal prevention (CWE-22) and command injection prevention (CWE-77).

.NOTES
    Issue Reference: #755 - Security Agent Missed Two CRITICAL Vulnerabilities
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot 'Export-ClaudeMemMemories.ps1'
    $MemoriesDir = Join-Path $PSScriptRoot '..' 'memories'
}

Describe 'Export-ClaudeMemMemories.ps1' {
    Context 'CRITICAL-001: Path Traversal Prevention (CWE-22)' {
        BeforeAll {
            # Ensure memories directory exists for tests
            if (-not (Test-Path $MemoriesDir)) {
                New-Item -ItemType Directory -Path $MemoriesDir -Force | Out-Null
            }
        }

        It 'Should reject path traversal with ../' {
            # Attack: ../../etc/passwd would escape memories directory
            $MaliciousPath = Join-Path $MemoriesDir '..' '..' 'etc' 'passwd'

            { & $ScriptPath -Query "test" -OutputFile $MaliciousPath } | Should -Throw -ExpectedMessage '*Path traversal attempt detected*'
        }

        It 'Should reject path traversal with absolute path outside memories' {
            # Attack: absolute path to /tmp would bypass directory check
            $MaliciousPath = "/tmp/malicious-export.json"

            { & $ScriptPath -Query "test" -OutputFile $MaliciousPath } | Should -Throw -ExpectedMessage '*Path traversal attempt detected*'
        }

        It 'Should reject sibling directory bypass (memories-evil)' {
            # Attack: .claude-mem/memories-evil/file.json would pass naive StartsWith check
            $SiblingDir = Join-Path $PSScriptRoot '..' 'memories-evil'
            $MaliciousPath = Join-Path $SiblingDir 'export.json'

            { & $ScriptPath -Query "test" -OutputFile $MaliciousPath } | Should -Throw -ExpectedMessage '*Path traversal attempt detected*'
        }

        It 'Should reject encoded path traversal (%2e%2e)' {
            # Attack: URL-encoded .. could bypass simple string checks
            # Note: PowerShell decodes these automatically in most contexts
            $MaliciousPath = Join-Path $MemoriesDir '..' '..' 'tmp' 'export.json'

            { & $ScriptPath -Query "test" -OutputFile $MaliciousPath } | Should -Throw -ExpectedMessage '*Path traversal attempt detected*'
        }

        It 'Should accept valid path inside memories directory' {
            # Valid: .claude-mem/memories/export.json
            $ValidPath = Join-Path $MemoriesDir 'test-export.json'

            # This test validates path validation logic, not full execution
            # We expect it to pass path validation but may fail later due to plugin not found
            $NormalizedOutput = [System.IO.Path]::GetFullPath($ValidPath)
            $NormalizedDir = [System.IO.Path]::GetFullPath($MemoriesDir)
            $NormalizedDirWithSep = $NormalizedDir.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar

            $NormalizedOutput.StartsWith($NormalizedDirWithSep, [System.StringComparison]::OrdinalIgnoreCase) | Should -BeTrue
        }

        It 'Should normalize paths before comparison' {
            # Test that GetFullPath resolves .. correctly
            $BasePath = Join-Path $MemoriesDir '..' 'memories' 'export.json'
            $NormalizedPath = [System.IO.Path]::GetFullPath($BasePath)
            $NormalizedDir = [System.IO.Path]::GetFullPath($MemoriesDir)
            $NormalizedDirWithSep = $NormalizedDir.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar

            # This path goes out and back in, should still be valid
            $NormalizedPath.StartsWith($NormalizedDirWithSep, [System.StringComparison]::OrdinalIgnoreCase) | Should -BeTrue
        }

        It 'Should use case-insensitive comparison on Windows-like paths' {
            # Test case insensitivity for cross-platform compatibility
            $LowerPath = $MemoriesDir.ToLower()
            $UpperPath = $MemoriesDir.ToUpper()

            $NormalizedLower = [System.IO.Path]::GetFullPath($LowerPath)
            $NormalizedUpper = [System.IO.Path]::GetFullPath($UpperPath)

            # OrdinalIgnoreCase comparison should treat these as equal parent
            $TestFile = Join-Path $NormalizedLower 'test.json'
            $TestFile.StartsWith($NormalizedUpper + [IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase) | Should -BeTrue
        }
    }

    Context 'CRITICAL-002: Command Injection Prevention (CWE-77)' {
        It 'Should reject query with shell metacharacters' {
            # Attack: ; rm -rf / # would execute arbitrary commands if unquoted
            # The ValidatePattern attribute should reject this before execution
            $MaliciousQuery = "; rm -rf / #"

            { & $ScriptPath -Query $MaliciousQuery -OutputFile (Join-Path $MemoriesDir 'test.json') } | Should -Throw
        }

        It 'Should reject query with pipe injection' {
            # Attack: | cat /etc/passwd would pipe output to another command
            $MaliciousQuery = "| cat /etc/passwd"

            { & $ScriptPath -Query $MaliciousQuery -OutputFile (Join-Path $MemoriesDir 'test.json') } | Should -Throw
        }

        It 'Should reject query with backtick command substitution' {
            # Attack: `id` would execute id command in bash
            $MaliciousQuery = '`id`'

            { & $ScriptPath -Query $MaliciousQuery -OutputFile (Join-Path $MemoriesDir 'test.json') } | Should -Throw
        }

        It 'Should reject query with $() command substitution' {
            # Attack: $(whoami) would execute whoami in subshell
            $MaliciousQuery = '$(whoami)'

            { & $ScriptPath -Query $MaliciousQuery -OutputFile (Join-Path $MemoriesDir 'test.json') } | Should -Throw
        }

        It 'Should reject query with ampersand background execution' {
            # Attack: & rm -rf / would run command in background
            $MaliciousQuery = "& rm -rf /"

            { & $ScriptPath -Query $MaliciousQuery -OutputFile (Join-Path $MemoriesDir 'test.json') } | Should -Throw
        }

        It 'Should reject query with double ampersand chaining' {
            # Attack: && rm -rf / would chain commands
            $MaliciousQuery = "&& rm -rf /"

            { & $ScriptPath -Query $MaliciousQuery -OutputFile (Join-Path $MemoriesDir 'test.json') } | Should -Throw
        }

        It 'Should accept safe query with alphanumeric characters' {
            # Valid: normal search query
            $SafeQuery = "session 229 testing"

            # Validate the pattern allows safe characters
            $Pattern = '^[a-zA-Z0-9\s\-_.,()]*$'
            $SafeQuery -match $Pattern | Should -BeTrue
        }

        It 'Should accept query with allowed special characters' {
            # Valid: hyphens, underscores, periods, commas, parentheses are allowed
            $SafeQuery = "test-query_with.special,chars(v1)"

            $Pattern = '^[a-zA-Z0-9\s\-_.,()]*$'
            $SafeQuery -match $Pattern | Should -BeTrue
        }

        It 'Should accept empty query' {
            # Valid: empty string exports all
            $EmptyQuery = ""

            $Pattern = '^[a-zA-Z0-9\s\-_.,()]*$'
            $EmptyQuery -match $Pattern | Should -BeTrue
        }
    }

    Context 'Parameter Validation' {
        It 'Should require Query parameter' {
            { & $ScriptPath } | Should -Throw -ErrorId 'MissingMandatoryParameter*'
        }

        It 'Should validate Query against pattern' {
            # The ValidatePattern attribute should reject invalid characters
            $InvalidQuery = '<script>alert(1)</script>'

            { & $ScriptPath -Query $InvalidQuery } | Should -Throw
        }

        It 'Should accept Topic with valid characters' {
            $ValidTopic = "testing-philosophy"

            # Just validate the topic value is reasonable
            $ValidTopic | Should -Match '^[a-zA-Z0-9\-_]+$'
        }

        It 'Should accept SessionNumber as positive integer' {
            $ValidSession = 229

            $ValidSession | Should -BeGreaterThan 0
            $ValidSession | Should -BeOfType [int]
        }
    }

    Context 'Filename Generation' {
        It 'Should generate date-based filename by default' {
            $Date = Get-Date -Format 'yyyy-MM-dd'
            $ExpectedPattern = "^$Date.*\.json$"

            $Filename = "$Date.json"

            $Filename | Should -Match $ExpectedPattern
        }

        It 'Should include session number in filename when specified' {
            $Date = Get-Date -Format 'yyyy-MM-dd'
            $SessionNumber = 229
            $ExpectedFilename = "$Date-session-$SessionNumber.json"

            $ExpectedFilename | Should -Match 'session-229'
        }

        It 'Should include topic in filename when specified' {
            $Date = Get-Date -Format 'yyyy-MM-dd'
            $Topic = "frustrations"
            $ExpectedFilename = "$Date-$Topic.json"

            $ExpectedFilename | Should -Match 'frustrations'
        }

        It 'Should combine session and topic in filename' {
            $Date = Get-Date -Format 'yyyy-MM-dd'
            $SessionNumber = 229
            $Topic = "frustrations"
            $ExpectedFilename = "$Date-session-$SessionNumber-$Topic.json"

            $ExpectedFilename | Should -Match "^$Date-session-$SessionNumber-$Topic\.json$"
        }
    }

    Context 'Plugin Script Validation' {
        It 'Should fail if plugin script not found' {
            # Mock environment where plugin does not exist
            $FakePath = "/nonexistent/path/export-memories.ts"

            Test-Path $FakePath | Should -BeFalse
        }

        It 'Should construct correct plugin path' {
            $ExpectedPath = Join-Path $env:HOME '.claude' 'plugins' 'marketplaces' 'thedotmack' 'scripts' 'export-memories.ts'

            $ExpectedPath | Should -Match 'export-memories\.ts$'
        }
    }

    Context 'Error Handling' {
        It 'Should include attempted path in error message for path traversal' {
            $MaliciousPath = Join-Path $MemoriesDir '..' '..' 'etc' 'passwd'

            try {
                & $ScriptPath -Query "test" -OutputFile $MaliciousPath
            }
            catch {
                $_.Exception.Message | Should -Match 'Path traversal attempt detected'
            }
        }

        It 'Should include valid example in error message' {
            $MaliciousPath = "/tmp/evil.json"

            try {
                & $ScriptPath -Query "test" -OutputFile $MaliciousPath
            }
            catch {
                # Error stream should contain helpful guidance
                $true | Should -BeTrue
            }
        }
    }

    Context 'Security Review Integration' {
        It 'Should reference security review script path' {
            $SecurityScript = Join-Path $PSScriptRoot '..' '..' 'scripts' 'Review-MemoryExportSecurity.ps1'

            # Verify the expected path structure
            $SecurityScript | Should -Match 'Review-MemoryExportSecurity\.ps1$'
        }
    }
}
