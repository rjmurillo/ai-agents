#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Check-SkillExists.ps1

.DESCRIPTION
    Tests the skill existence checking functionality for the Phase 1.5 BLOCKING gate.
    Validates operation/action matching and skill listing capabilities.
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot ".." "scripts" "Check-SkillExists.ps1"
}

Describe "Check-SkillExists" {
    Context "When checking for existing skills" {
        It "Returns true for known pr skill" {
            $result = & $scriptPath -Operation "pr" -Action "PRContext"
            $result | Should -Be $true
        }

        It "Returns false for non-existent skill" {
            $result = & $scriptPath -Operation "pr" -Action "NonExistentAction"
            $result | Should -Be $false
        }

        It "Returns true for issue skill" {
            $result = & $scriptPath -Operation "issue" -Action "IssueContext"
            $result | Should -Be $true
        }

        It "Returns true for reactions skill" {
            $result = & $scriptPath -Operation "reactions" -Action "CommentReaction"
            $result | Should -Be $true
        }

        It "Returns false for operation with no matching directory" {
            $result = & $scriptPath -Operation "label" -Action "SomeAction"
            $result | Should -Be $false
        }

        It "Returns false for milestone operation (no skills yet)" {
            $result = & $scriptPath -Operation "milestone" -Action "SomeAction"
            $result | Should -Be $false
        }
    }

    Context "When listing available skills" {
        It "Lists skills without error" {
            { & $scriptPath -ListAvailable } | Should -Not -Throw
        }

        It "Returns output containing operation headers" {
            $output = & $scriptPath -ListAvailable
            $outputString = $output -join "`n"
            $outputString | Should -Match "=== pr ==="
        }
    }

    Context "Parameter validation" {
        It "Validates operation parameter with ValidateSet" {
            { & $scriptPath -Operation "invalid" -Action "Test" } | Should -Throw
        }

        It "Returns false when Operation is missing" {
            $result = & $scriptPath -Action "PRContext" 2>$null
            $result | Should -Be $false
        }

        It "Returns false when Action is missing" {
            $result = & $scriptPath -Operation "pr" 2>$null
            $result | Should -Be $false
        }
    }

    Context "Substring matching" {
        It "Matches partial action names" {
            # Get-PRContext.ps1 should match "Context"
            $result = & $scriptPath -Operation "pr" -Action "Context"
            $result | Should -Be $true
        }

        It "Matches with Get prefix" {
            $result = & $scriptPath -Operation "pr" -Action "Get-PRContext"
            $result | Should -Be $true
        }
    }
}
