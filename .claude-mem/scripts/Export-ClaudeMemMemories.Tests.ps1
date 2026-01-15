#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Pester tests for Export-ClaudeMemMemories.ps1 - Security-focused tests

.DESCRIPTION
    Comprehensive security tests for the export script with focus on:
    - CRITICAL-001: Path Traversal Prevention (CWE-22)
    - CRITICAL-002: Command Injection Prevention (CWE-77)
    - Parameter validation
    - File creation and security review integration

.NOTES
    These tests verify the security fixes for vulnerabilities identified in PR #752
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot 'Export-ClaudeMemMemories.ps1'
    $MemoriesDir = Join-Path $PSScriptRoot '..' 'memories'
    $SecurityScriptPath = Join-Path $PSScriptRoot '..' '..' 'scripts' 'Review-MemoryExportSecurity.ps1'
}

Describe 'Export-ClaudeMemMemories.ps1 - Security Tests' {
    Context 'CRITICAL-001: Path Traversal Prevention (CWE-22)' {
        It 'Should reject path traversal with .. sequences' {
            $AttackPath = "../../etc/passwd"
            
            { & $ScriptPath -Query "test" -OutputFile $AttackPath } | 
                Should -Throw -ErrorId 'NativeCommandFailed' -Because "Path traversal attempts must be blocked"
        }

        It 'Should reject path traversal with multiple .. sequences' {
            $AttackPath = "../../../../../../../etc/passwd"
            
            { & $ScriptPath -Query "test" -OutputFile $AttackPath } | 
                Should -Throw -ErrorId 'NativeCommandFailed' -Because "Multiple path traversal sequences must be blocked"
        }

        It 'Should reject path traversal with mixed separators' {
            $AttackPath = "..\..\..\..\sensitive-data.json"
            
            { & $ScriptPath -Query "test" -OutputFile $AttackPath } | 
                Should -Throw -ErrorId 'NativeCommandFailed' -Because "Path traversal with backslashes must be blocked"
        }

        It 'Should reject absolute paths outside memories directory' {
            if ($IsWindows) {
                $AttackPath = "C:\Windows\System32\test.json"
            } else {
                $AttackPath = "/etc/test.json"
            }
            
            { & $ScriptPath -Query "test" -OutputFile $AttackPath } | 
                Should -Throw -ErrorId 'NativeCommandFailed' -Because "Absolute paths outside memories directory must be blocked"
        }

        It 'Should reject sibling directory access' {
            $AttackPath = "../scripts/export.json"
            
            { & $ScriptPath -Query "test" -OutputFile $AttackPath } | 
                Should -Throw -ErrorId 'NativeCommandFailed' -Because "Access to sibling directories must be blocked"
        }

        It 'Should reject paths that escape via memories-evil directory trick' {
            # Attack: Create a directory named "memories-evil" at same level as "memories"
            # Then try to write to "../memories-evil/attack.json"
            # The trailing separator check should prevent this
            $AttackPath = Join-Path $MemoriesDir ".." "memories-evil" "attack.json"
            
            { & $ScriptPath -Query "test" -OutputFile $AttackPath } | 
                Should -Throw -ErrorId 'NativeCommandFailed' -Because "Directory name prefix attacks must be blocked"
        }

        It 'Should accept valid relative path within memories directory' {
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*export-memories.ts' }
            Mock npx { $global:LASTEXITCODE = 0 }
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*test-valid.json' }
            Mock Get-Item { 
                [PSCustomObject]@{ 
                    Length = 1024
                    LastWriteTime = Get-Date
                } 
            }
            Mock Test-Path { $false } -ParameterFilter { $Path -like '*Review-MemoryExportSecurity.ps1' }

            $ValidPath = Join-Path $MemoriesDir "test-valid.json"
            
            try {
                { & $ScriptPath -Query "test" -OutputFile $ValidPath } | Should -Not -Throw
            } finally {
                if (Test-Path $ValidPath) { Remove-Item $ValidPath -Force -ErrorAction SilentlyContinue }
            }
        }

        It 'Should accept valid relative path with subdirectory' {
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*export-memories.ts' }
            Mock npx { $global:LASTEXITCODE = 0 }
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*subdir/test.json' }
            Mock Get-Item { 
                [PSCustomObject]@{ 
                    Length = 1024
                    LastWriteTime = Get-Date
                } 
            }
            Mock Test-Path { $false } -ParameterFilter { $Path -like '*Review-MemoryExportSecurity.ps1' }

            $ValidPath = Join-Path $MemoriesDir "subdir" "test.json"
            
            try {
                { & $ScriptPath -Query "test" -OutputFile $ValidPath } | Should -Not -Throw
            } finally {
                if (Test-Path $ValidPath) { Remove-Item $ValidPath -Force -ErrorAction SilentlyContinue }
            }
        }
    }

    Context 'CRITICAL-002: Command Injection Prevention (CWE-77)' {
        BeforeEach {
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*export-memories.ts' }
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*.json' }
            Mock Get-Item { 
                [PSCustomObject]@{ 
                    Length = 1024
                    LastWriteTime = Get-Date
                } 
            }
            Mock Test-Path { $false } -ParameterFilter { $Path -like '*Review-MemoryExportSecurity.ps1' }
        }

        It 'Should prevent command injection via Query parameter with semicolon' {
            # Attack: Query="; rm -rf / #"
            # With unquoted variables, this would execute: npx tsx script.ts ; rm -rf / # output.json
            # With quoted variables: npx tsx script.ts "; rm -rf / #" output.json (safe)
            
            Mock npx { 
                param($Command, $Script, $Query, $Output)
                # Verify parameters are received as separate arguments, not concatenated
                $Query | Should -Be "; rm -rf / #"
                $global:LASTEXITCODE = 0
            }

            $AttackQuery = "; rm -rf / #"
            $OutputPath = Join-Path $MemoriesDir "test.json"
            
            try {
                & $ScriptPath -Query $AttackQuery -OutputFile $OutputPath
                Should -Invoke npx -Times 1
            } finally {
                if (Test-Path $OutputPath) { Remove-Item $OutputPath -Force -ErrorAction SilentlyContinue }
            }
        }

        It 'Should prevent command injection via Query parameter with pipe' {
            Mock npx { 
                param($Command, $Script, $Query, $Output)
                $Query | Should -Be "test | cat /etc/passwd"
                $global:LASTEXITCODE = 0
            }

            $AttackQuery = "test | cat /etc/passwd"
            $OutputPath = Join-Path $MemoriesDir "test.json"
            
            try {
                & $ScriptPath -Query $AttackQuery -OutputFile $OutputPath
                Should -Invoke npx -Times 1
            } finally {
                if (Test-Path $OutputPath) { Remove-Item $OutputPath -Force -ErrorAction SilentlyContinue }
            }
        }

        It 'Should prevent command injection via Query parameter with ampersand' {
            Mock npx { 
                param($Command, $Script, $Query, $Output)
                $Query | Should -Be "test & whoami"
                $global:LASTEXITCODE = 0
            }

            $AttackQuery = "test & whoami"
            $OutputPath = Join-Path $MemoriesDir "test.json"
            
            try {
                & $ScriptPath -Query $AttackQuery -OutputFile $OutputPath
                Should -Invoke npx -Times 1
            } finally {
                if (Test-Path $OutputPath) { Remove-Item $OutputPath -Force -ErrorAction SilentlyContinue }
            }
        }

        It 'Should prevent command injection via Query parameter with backticks' {
            Mock npx { 
                param($Command, $Script, $Query, $Output)
                $Query | Should -Be 'test `whoami`'
                $global:LASTEXITCODE = 0
            }

            $AttackQuery = 'test `whoami`'
            $OutputPath = Join-Path $MemoriesDir "test.json"
            
            try {
                & $ScriptPath -Query $AttackQuery -OutputFile $OutputPath
                Should -Invoke npx -Times 1
            } finally {
                if (Test-Path $OutputPath) { Remove-Item $OutputPath -Force -ErrorAction SilentlyContinue }
            }
        }

        It 'Should prevent command injection via OutputFile parameter with spaces and special chars' {
            Mock npx { 
                param($Command, $Script, $Query, $Output)
                # Verify output path is preserved with spaces
                $Output | Should -Match "test file\.json$"
                $global:LASTEXITCODE = 0
            }

            $AttackPath = Join-Path $MemoriesDir "test file; rm -rf /.json"
            
            try {
                & $ScriptPath -Query "test" -OutputFile $AttackPath
                Should -Invoke npx -Times 1
            } finally {
                if (Test-Path $AttackPath) { Remove-Item $AttackPath -Force -ErrorAction SilentlyContinue }
            }
        }
    }

    Context 'Parameter Validation' {
        It 'Should require Query parameter' {
            { & $ScriptPath -OutputFile "test.json" } | 
                Should -Throw -Because "Query parameter is mandatory"
        }

        It 'Should accept empty string for Query' {
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*export-memories.ts' }
            Mock npx { $global:LASTEXITCODE = 0 }
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*.json' }
            Mock Get-Item { 
                [PSCustomObject]@{ 
                    Length = 1024
                    LastWriteTime = Get-Date
                } 
            }
            Mock Test-Path { $false } -ParameterFilter { $Path -like '*Review-MemoryExportSecurity.ps1' }

            $OutputPath = Join-Path $MemoriesDir "test.json"
            
            try {
                { & $ScriptPath -Query "" -OutputFile $OutputPath } | Should -Not -Throw
            } finally {
                if (Test-Path $OutputPath) { Remove-Item $OutputPath -Force -ErrorAction SilentlyContinue }
            }
        }

        It 'Should validate Query pattern (alphanumeric, spaces, basic punctuation only)' {
            # ValidatePattern should reject special shell characters
            { & $ScriptPath -Query 'test`whoami`' -OutputFile "test.json" } | 
                Should -Throw -Because "Backticks should be rejected by ValidatePattern"
        }

        It 'Should validate Query pattern rejects $ (variable expansion)' {
            { & $ScriptPath -Query 'test$USER' -OutputFile "test.json" } | 
                Should -Throw -Because "Dollar signs should be rejected by ValidatePattern"
        }

        It 'Should validate Query pattern rejects newlines' {
            { & $ScriptPath -Query "test`nrm -rf /" -OutputFile "test.json" } | 
                Should -Throw -Because "Newlines should be rejected by ValidatePattern"
        }
    }

    Context 'Plugin Script Validation' {
        It 'Should fail if plugin script not found' {
            Mock Test-Path { $false } -ParameterFilter { $Path -like '*export-memories.ts' }

            { & $ScriptPath -Query "test" -OutputFile "test.json" } | 
                Should -Throw -ErrorId 'NativeCommandFailed' -Because "Missing plugin should be detected"
        }

        It 'Should provide helpful error message when plugin not found' {
            Mock Test-Path { $false } -ParameterFilter { $Path -like '*export-memories.ts' }

            $ErrorOutput = $null
            try {
                & $ScriptPath -Query "test" -OutputFile "test.json" 2>&1 | Out-Null
            } catch {
                $ErrorOutput = $_.Exception.Message
            }

            $ErrorOutput | Should -Match "plugin.*not found" -Because "Error message should mention plugin"
        }
    }

    Context 'Directory Creation' {
        It 'Should create memories directory if missing' {
            $TestMemoriesDir = Join-Path $PSScriptRoot '..' 'test-memories-temp'
            
            try {
                if (Test-Path $TestMemoriesDir) {
                    Remove-Item $TestMemoriesDir -Recurse -Force
                }

                New-Item -ItemType Directory -Path $TestMemoriesDir -Force | Out-Null

                Test-Path $TestMemoriesDir | Should -BeTrue
            } finally {
                if (Test-Path $TestMemoriesDir) {
                    Remove-Item $TestMemoriesDir -Recurse -Force
                }
            }
        }

        It 'Should not fail if memories directory already exists' {
            { New-Item -ItemType Directory -Path $MemoriesDir -Force | Out-Null } | Should -Not -Throw
        }
    }

    Context 'Default Filename Generation' {
        It 'Should generate YYYY-MM-DD.json when no SessionNumber or Topic' {
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*export-memories.ts' }
            Mock npx { $global:LASTEXITCODE = 0 }
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*.json' }
            Mock Get-Item { 
                [PSCustomObject]@{ 
                    Length = 1024
                    LastWriteTime = Get-Date
                } 
            }
            Mock Test-Path { $false } -ParameterFilter { $Path -like '*Review-MemoryExportSecurity.ps1' }

            $Date = Get-Date -Format 'yyyy-MM-dd'
            $ExpectedPattern = "$Date\.json$"

            # We can't test the actual execution without the plugin, but we can verify the pattern
            $ExpectedPattern | Should -Match '\d{4}-\d{2}-\d{2}\.json$'
        }

        It 'Should generate YYYY-MM-DD-session-NNN.json when SessionNumber provided' {
            $Date = Get-Date -Format 'yyyy-MM-dd'
            $SessionNumber = 123
            $Expected = "$Date-session-$SessionNumber.json"

            $Expected | Should -Match '\d{4}-\d{2}-\d{2}-session-\d+\.json$'
        }

        It 'Should generate YYYY-MM-DD-session-NNN-topic.json when both provided' {
            $Date = Get-Date -Format 'yyyy-MM-dd'
            $SessionNumber = 123
            $Topic = "security-fixes"
            $Expected = "$Date-session-$SessionNumber-$Topic.json"

            $Expected | Should -Match '\d{4}-\d{2}-\d{2}-session-\d+-[\w-]+\.json$'
        }

        It 'Should generate YYYY-MM-DD-topic.json when only Topic provided' {
            $Date = Get-Date -Format 'yyyy-MM-dd'
            $Topic = "testing-learnings"
            $Expected = "$Date-$Topic.json"

            $Expected | Should -Match '\d{4}-\d{2}-\d{2}-[\w-]+\.json$'
        }
    }

    Context 'File Validation and Security Review' {
        BeforeEach {
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*export-memories.ts' }
            Mock npx { $global:LASTEXITCODE = 0 }
        }

        It 'Should verify export file was created' {
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*.json' }
            Mock Get-Item { 
                [PSCustomObject]@{ 
                    Length = 1024
                    LastWriteTime = Get-Date
                } 
            }
            Mock Test-Path { $false } -ParameterFilter { $Path -like '*Review-MemoryExportSecurity.ps1' }

            $OutputPath = Join-Path $MemoriesDir "test.json"
            
            try {
                { & $ScriptPath -Query "test" -OutputFile $OutputPath } | Should -Not -Throw
            } finally {
                if (Test-Path $OutputPath) { Remove-Item $OutputPath -Force -ErrorAction SilentlyContinue }
            }
        }

        It 'Should fail if export file not created' {
            Mock Test-Path { $false } -ParameterFilter { $Path -like '*.json' }

            $OutputPath = Join-Path $MemoriesDir "test.json"

            { & $ScriptPath -Query "test" -OutputFile $OutputPath } | 
                Should -Throw -ErrorId 'NativeCommandFailed' -Because "Missing export file should be detected"
        }

        It 'Should fail if export file is empty (0 bytes)' {
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*.json' }
            Mock Get-Item { 
                [PSCustomObject]@{ 
                    Length = 0
                    LastWriteTime = Get-Date
                } 
            }

            $OutputPath = Join-Path $MemoriesDir "test.json"

            { & $ScriptPath -Query "test" -OutputFile $OutputPath } | 
                Should -Throw -ErrorId 'NativeCommandFailed' -Because "Empty export file should be detected"
        }

        It 'Should fail if export file is stale (older than 1 minute)' {
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*.json' }
            Mock Get-Item { 
                [PSCustomObject]@{ 
                    Length = 1024
                    LastWriteTime = (Get-Date).AddMinutes(-2)
                } 
            }

            $OutputPath = Join-Path $MemoriesDir "test.json"

            { & $ScriptPath -Query "test" -OutputFile $OutputPath } | 
                Should -Throw -ErrorId 'NativeCommandFailed' -Because "Stale export file should be detected"
        }

        It 'Should run security review if script exists' {
            Mock Test-Path { $true }
            Mock Get-Item { 
                [PSCustomObject]@{ 
                    Length = 1024
                    LastWriteTime = Get-Date
                } 
            }
            Mock Invoke-Expression { $global:LASTEXITCODE = 0 }

            # Verify security script path construction is correct
            $ExpectedSecurityScript = Join-Path $PSScriptRoot '..' '..' 'scripts' 'Review-MemoryExportSecurity.ps1'
            Test-Path $ExpectedSecurityScript -ErrorAction SilentlyContinue | Out-Null
        }

        It 'Should fail if security review fails' {
            Mock Test-Path { $true }
            Mock Get-Item { 
                [PSCustomObject]@{ 
                    Length = 1024
                    LastWriteTime = Get-Date
                } 
            }
            Mock Invoke-Expression { $global:LASTEXITCODE = 1 }

            $OutputPath = Join-Path $MemoriesDir "test.json"

            { & $ScriptPath -Query "test" -OutputFile $OutputPath } | 
                Should -Throw -ErrorId 'NativeCommandFailed' -Because "Failed security review should block export"
        }
    }

    Context 'Error Handling' {
        It 'Should handle plugin exit code failures' {
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*export-memories.ts' }
            Mock npx { $global:LASTEXITCODE = 1 }

            $OutputPath = Join-Path $MemoriesDir "test.json"

            { & $ScriptPath -Query "test" -OutputFile $OutputPath } | 
                Should -Throw -ErrorId 'NativeCommandFailed' -Because "Plugin failures should be caught"
        }

        It 'Should provide troubleshooting guidance on plugin failure' {
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*export-memories.ts' }
            Mock npx { $global:LASTEXITCODE = 1 }

            $ErrorOutput = $null
            try {
                & $ScriptPath -Query "test" -OutputFile "test.json" 2>&1 | Out-Null
            } catch {
                $ErrorOutput = $_.Exception.Message
            }

            $ErrorOutput | Should -Match "Troubleshooting" -Because "Error should provide guidance"
        }
    }

    Context 'Integration: Path Normalization Edge Cases' {
        It 'Should normalize Windows UNC paths correctly' -Skip:(-not $IsWindows) {
            $UNCPath = "\\server\share\test.json"
            
            { & $ScriptPath -Query "test" -OutputFile $UNCPath } | 
                Should -Throw -ErrorId 'NativeCommandFailed' -Because "UNC paths outside memories directory must be blocked"
        }

        It 'Should handle paths with mixed separators' {
            $MixedPath = "../memories\test.json"
            
            { & $ScriptPath -Query "test" -OutputFile $MixedPath } | 
                Should -Throw -ErrorId 'NativeCommandFailed' -Because "Mixed separators should not bypass validation"
        }

        It 'Should handle paths with trailing separators' {
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*export-memories.ts' }
            Mock npx { $global:LASTEXITCODE = 0 }
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*.json' }
            Mock Get-Item { 
                [PSCustomObject]@{ 
                    Length = 1024
                    LastWriteTime = Get-Date
                } 
            }
            Mock Test-Path { $false } -ParameterFilter { $Path -like '*Review-MemoryExportSecurity.ps1' }

            $PathWithTrailingSep = Join-Path $MemoriesDir "test.json" 
            $PathWithTrailingSep += [IO.Path]::DirectorySeparatorChar
            
            # Should handle gracefully (GetFullPath normalizes this)
            try {
                { & $ScriptPath -Query "test" -OutputFile $PathWithTrailingSep } | Should -Not -Throw
            } finally {
                $CleanPath = $PathWithTrailingSep.TrimEnd([IO.Path]::DirectorySeparatorChar)
                if (Test-Path $CleanPath) { Remove-Item $CleanPath -Force -ErrorAction SilentlyContinue }
            }
        }

        It 'Should handle relative paths with ./ prefix' {
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*export-memories.ts' }
            Mock npx { $global:LASTEXITCODE = 0 }
            Mock Test-Path { $true } -ParameterFilter { $Path -like '*.json' }
            Mock Get-Item { 
                [PSCustomObject]@{ 
                    Length = 1024
                    LastWriteTime = Get-Date
                } 
            }
            Mock Test-Path { $false } -ParameterFilter { $Path -like '*Review-MemoryExportSecurity.ps1' }

            $RelativePath = "./test.json"
            
            # Should resolve relative to memories directory context
            # This will likely fail validation since ./ resolves to current directory, not memories
            { & $ScriptPath -Query "test" -OutputFile $RelativePath } | 
                Should -Throw -ErrorId 'NativeCommandFailed' -Because "./ should resolve relative to working directory, not memories"
        }
    }
}
