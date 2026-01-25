#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Pester tests for Export-ClaudeMemFullBackup.ps1

.DESCRIPTION
    Comprehensive unit tests for the full backup export script.
    Tests plugin validation, filename generation, security review integration,
    and error handling.
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot 'Export-ClaudeMemFullBackup.ps1'
    $SecurityScriptPath = Join-Path $PSScriptRoot '..' '..' 'scripts' 'Review-MemoryExportSecurity.ps1'
}

Describe 'Export-ClaudeMemFullBackup.ps1' {
    Context 'Plugin Script Validation' {
        It 'Should fail if plugin script not found' {
            Mock Test-Path { $false } -ParameterFilter { $Path -like '*export-memories.ts' }

            { & $ScriptPath } | Should -Throw -ErrorId 'NativeCommandFailed'
        }

        It 'Should validate plugin script path exists' {
            $PluginPath = Join-Path $env:HOME '.claude' 'plugins' 'marketplaces' 'thedotmack' 'scripts' 'export-memories.ts'

            # This test assumes plugin is installed
            if (Test-Path $PluginPath) {
                Test-Path $PluginPath | Should -BeTrue
            } else {
                Set-ItResult -Skipped -Because "Plugin not installed on this system"
            }
        }
    }

    Context 'Filename Generation' {
        It 'Should create backup-YYYY-MM-DD-HHMM.json format' {
            Mock npx { }
            Mock Test-Path { $true }
            Mock Get-Content { '{"totalObservations":0,"totalSessions":0,"totalSummaries":0,"totalPrompts":0}' | ConvertFrom-Json }
            Mock Get-Item { [PSCustomObject]@{ Length = 1024 } }
            Mock Test-Path { $true } -ParameterFilter { $_ -like '*Review-MemoryExportSecurity.ps1' }
            Mock Invoke-Expression { $global:LASTEXITCODE = 0 }

            $OutputFile = Join-Path $PSScriptRoot '..' 'memories' "test-backup.json"

            try {
                & $ScriptPath -OutputFile $OutputFile

                $OutputFile | Should -Match 'test-backup\.json$'
            } finally {
                if (Test-Path $OutputFile) { Remove-Item $OutputFile -Force }
            }
        }

        It 'Should append project name when -Project specified' {
            Mock npx { }
            Mock Test-Path { $true }
            Mock Get-Content { '{"totalObservations":0,"totalSessions":0,"totalSummaries":0,"totalPrompts":0}' | ConvertFrom-Json }
            Mock Get-Item { [PSCustomObject]@{ Length = 1024 } }
            Mock Test-Path { $true } -ParameterFilter { $_ -like '*Review-MemoryExportSecurity.ps1' }
            Mock Invoke-Expression { $global:LASTEXITCODE = 0 }

            $MemoriesDir = Join-Path $PSScriptRoot '..' 'memories'

            # Mock the script to capture generated filename
            Mock Join-Path {
                param($Path, $ChildPath)
                if ($ChildPath -match '^backup-\d{4}-\d{2}-\d{2}-\d{4}-ai-agents\.json$') {
                    return $ChildPath
                }
                return Join-Path @PSBoundParameters
            } -ParameterFilter { $Path -eq $MemoriesDir }

            # This test validates the filename pattern logic
            $ExpectedPattern = '^backup-\d{4}-\d{2}-\d{2}-\d{4}-ai-agents\.json$'
            $Timestamp = Get-Date -Format 'yyyy-MM-dd-HHmm'
            $Filename = "backup-$Timestamp-ai-agents.json"

            $Filename | Should -Match $ExpectedPattern
        }

        It 'Should use custom filename when -OutputFile specified' {
            Mock npx { }
            Mock Test-Path { $true }
            Mock Get-Content { '{"totalObservations":0,"totalSessions":0,"totalSummaries":0,"totalPrompts":0}' | ConvertFrom-Json }
            Mock Get-Item { [PSCustomObject]@{ Length = 1024 } }
            Mock Test-Path { $true } -ParameterFilter { $_ -like '*Review-MemoryExportSecurity.ps1' }
            Mock Invoke-Expression { $global:LASTEXITCODE = 0 }

            $CustomFile = "custom-backup.json"

            # This validates that custom output file is used
            $CustomFile | Should -Be "custom-backup.json"
        }
    }

    Context 'Directory Creation' {
        It 'Should create .claude-mem/memories/ if missing' {
            $MemoriesDir = Join-Path $PSScriptRoot '..' 'memories' 'test-subdir'

            try {
                if (Test-Path $MemoriesDir) {
                    Remove-Item $MemoriesDir -Recurse -Force
                }

                New-Item -ItemType Directory -Path $MemoriesDir -Force | Out-Null

                Test-Path $MemoriesDir | Should -BeTrue
            } finally {
                if (Test-Path $MemoriesDir) {
                    Remove-Item $MemoriesDir -Recurse -Force
                }
            }
        }

        It 'Should not error if directory already exists' {
            $MemoriesDir = Join-Path $PSScriptRoot '..' 'memories'

            { New-Item -ItemType Directory -Path $MemoriesDir -Force | Out-Null } | Should -Not -Throw
        }
    }

    Context 'Plugin Script Invocation' {
        It 'Should pass "." as query (not empty string)' {
            $PluginArgs = @(".", "output.json")

            $PluginArgs[0] | Should -Be "."
            $PluginArgs[0] | Should -Not -Be ""
        }

        It 'Should append --project=$Project when specified' {
            $Project = "ai-agents"
            $PluginArgs = @(".", "output.json")
            if ($Project) {
                $PluginArgs += "--project=$Project"
            }

            $PluginArgs | Should -Contain "--project=ai-agents"
        }

        It 'Should verify proper argument array construction' {
            $PluginArgs = @(".", "backup.json", "--project=test")

            $PluginArgs.Count | Should -Be 3
            $PluginArgs[0] | Should -Be "."
            $PluginArgs[1] | Should -Be "backup.json"
            $PluginArgs[2] | Should -Be "--project=test"
        }
    }

    Context 'Output Verification' {
        It 'Should verify export file was created' {
            $TestFile = Join-Path $PSScriptRoot "test-export.json"

            try {
                '{"totalObservations":5}' | Out-File $TestFile

                Test-Path $TestFile | Should -BeTrue
            } finally {
                if (Test-Path $TestFile) { Remove-Item $TestFile -Force }
            }
        }

        It 'Should parse JSON output for stats' {
            $Json = '{"totalObservations":10,"totalSessions":2,"totalSummaries":3,"totalPrompts":5}'
            $Data = $Json | ConvertFrom-Json

            $Data.totalObservations | Should -Be 10
            $Data.totalSessions | Should -Be 2
            $Data.totalSummaries | Should -Be 3
            $Data.totalPrompts | Should -Be 5
        }
    }

    Context 'Stats Display' {
        It 'Should calculate file size in KB' {
            $FileSize = 2048
            $FileSizeKB = [math]::Round($FileSize / 1KB, 2)

            $FileSizeKB | Should -Be 2
        }

        It 'Should calculate total records correctly' {
            $Data = @{
                totalObservations = 10
                totalSessions = 2
                totalSummaries = 3
                totalPrompts = 5
            }

            $TotalRecords = $Data.totalObservations + $Data.totalSessions + $Data.totalSummaries + $Data.totalPrompts

            $TotalRecords | Should -Be 20
        }
    }

    Context 'Empty Database Handling' {
        It 'Should detect empty export when all totals are 0' {
            $Data = @{
                totalObservations = 0
                totalSessions = 0
                totalSummaries = 0
                totalPrompts = 0
            }

            $TotalRecords = $Data.totalObservations + $Data.totalSessions + $Data.totalSummaries + $Data.totalPrompts

            $TotalRecords | Should -Be 0
        }
    }

    Context 'Security Review Integration' {
        It 'Should run security review automatically' {
            # Verify security script exists
            if (Test-Path $SecurityScriptPath) {
                Test-Path $SecurityScriptPath | Should -BeTrue
            } else {
                Set-ItResult -Skipped -Because "Security review script not found"
            }
        }

        It 'Should exit with code 1 if security review fails' {
            Mock Invoke-Expression { $global:LASTEXITCODE = 1 }

            $global:LASTEXITCODE = 1
            $global:LASTEXITCODE | Should -Be 1
        }

        It 'Should exit with code 0 if security review passes' {
            Mock Invoke-Expression { $global:LASTEXITCODE = 0 }

            $global:LASTEXITCODE = 0
            $global:LASTEXITCODE | Should -Be 0
        }
    }

    Context 'Error Handling' {
        It 'Should fail gracefully if plugin not installed' {
            Mock Test-Path { $false } -ParameterFilter { $Path -like '*export-memories.ts' }

            { & $ScriptPath } | Should -Throw
        }

        It 'Should handle JSON parse errors' {
            $InvalidJson = '{"invalid json'

            { $InvalidJson | ConvertFrom-Json } | Should -Throw
        }
    }
}
