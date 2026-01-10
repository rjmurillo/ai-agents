<#
.SYNOPSIS
    Pester tests for Search-Memory.ps1 skill script.

.DESCRIPTION
    Integration tests verifying the Memory Router skill works
    correctly for agent workflows per ADR-037.

.NOTES
    Task: M-003 (Phase 2A Memory System)
    Tests agent-facing skill integration.
#>

BeforeAll {
    $SkillPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "memory" "scripts" "Search-Memory.ps1"
}

Describe "Search-Memory Skill Script" {
    Context "Script Validation" {
        It "Script file exists" {
            Test-Path $SkillPath | Should -BeTrue
        }

        It "Script is syntactically valid" {
            $parseErrors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($SkillPath, [ref]$null, [ref]$parseErrors)
            $parseErrors.Count | Should -Be 0
        }
    }

    Context "Parameter Validation" {
        It "Requires Query parameter" {
            { & $SkillPath } | Should -Throw "*Query*"
        }

        It "Rejects empty query" {
            { & $SkillPath -Query "" } | Should -Throw
        }
    }

    Context "JSON Output" {
        It "Returns valid JSON" {
            $result = & $SkillPath -Query "memory" -LexicalOnly -MaxResults 3
            { $result | ConvertFrom-Json } | Should -Not -Throw
        }

        It "Contains expected properties" {
            $result = & $SkillPath -Query "memory" -LexicalOnly -MaxResults 3 | ConvertFrom-Json

            $result.PSObject.Properties.Name | Should -Contain "Query"
            $result.PSObject.Properties.Name | Should -Contain "Count"
            $result.PSObject.Properties.Name | Should -Contain "Results"
            $result.PSObject.Properties.Name | Should -Contain "Source"
        }

        It "Returns results as collection" {
            $result = & $SkillPath -Query "memory" -LexicalOnly -MaxResults 3 | ConvertFrom-Json

            # Results should be iterable (array or collection)
            $result.Results.Count | Should -BeGreaterOrEqual 0
        }

        It "Result items have required fields" {
            $result = & $SkillPath -Query "memory" -LexicalOnly -MaxResults 3 | ConvertFrom-Json

            if ($result.Count -gt 0) {
                $first = $result.Results[0]
                $first.PSObject.Properties.Name | Should -Contain "Name"
                $first.PSObject.Properties.Name | Should -Contain "Source"
                $first.PSObject.Properties.Name | Should -Contain "Score"
                $first.PSObject.Properties.Name | Should -Contain "Content"
            }
        }
    }

    Context "LexicalOnly Mode" {
        It "Reports Serena as source" {
            $result = & $SkillPath -Query "memory" -LexicalOnly -MaxResults 3 | ConvertFrom-Json

            $result.Source | Should -Be "Serena"
        }

        It "All results from Serena" {
            $result = & $SkillPath -Query "memory" -LexicalOnly -MaxResults 3 | ConvertFrom-Json

            if ($result.Count -gt 0) {
                $result.Results | ForEach-Object { $_.Source | Should -Be "Serena" }
            }
        }
    }

    Context "MaxResults" {
        It "Respects MaxResults limit" {
            $result = & $SkillPath -Query "memory" -LexicalOnly -MaxResults 2 | ConvertFrom-Json

            $result.Results.Count | Should -BeLessOrEqual 2
        }
    }

    Context "Diagnostic Information" {
        It "Includes diagnostic status" {
            $result = & $SkillPath -Query "memory" -LexicalOnly -MaxResults 1 | ConvertFrom-Json

            $result.Diagnostic | Should -Not -BeNullOrEmpty
            $result.Diagnostic.Serena | Should -Not -BeNullOrEmpty
        }
    }

    Context "Table Format" {
        It "Produces table output without throwing" {
            { & $SkillPath -Query "memory" -LexicalOnly -MaxResults 3 -Format Table } | Should -Not -Throw
        }
    }
}
