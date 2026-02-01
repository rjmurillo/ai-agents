<#
.SYNOPSIS
    Pester tests for Validate-Traceability.ps1 caching and performance optimizations.
#>

BeforeAll {
    $script:ScriptPath = Join-Path $PSScriptRoot "../scripts/Validate-Traceability.ps1"
    $script:TestFixturesPath = Join-Path $PSScriptRoot "fixtures/traceability"
}

Describe "Validate-Traceability.ps1 with Caching" {
    BeforeAll {
        # Create test fixtures
        $specsPath = Join-Path $TestDrive "specs"
        New-Item -Path "$specsPath/requirements" -ItemType Directory -Force | Out-Null
        New-Item -Path "$specsPath/design" -ItemType Directory -Force | Out-Null
        New-Item -Path "$specsPath/tasks" -ItemType Directory -Force | Out-Null

        @"
---
type: requirement
id: REQ-001
status: draft
related:
  - DESIGN-001
---
# Test Requirement
"@ | Out-File -FilePath "$specsPath/requirements/REQ-001.md"

        @"
---
type: design
id: DESIGN-001
status: draft
related:
  - REQ-001
---
# Test Design
"@ | Out-File -FilePath "$specsPath/design/DESIGN-001.md"

        @"
---
type: task
id: TASK-001
status: todo
related:
  - DESIGN-001
---
# Test Task
"@ | Out-File -FilePath "$specsPath/tasks/TASK-001.md"
    }

    It "Runs successfully with caching enabled" {
        & $script:ScriptPath -SpecsPath $specsPath

        $LASTEXITCODE | Should -Be 0
    }

    It "Runs successfully with caching disabled" {
        & $script:ScriptPath -SpecsPath $specsPath -NoCache

        $LASTEXITCODE | Should -Be 0
    }

    It "Runs with benchmark flag without errors" {
        & $script:ScriptPath -SpecsPath $specsPath -Benchmark | Out-Null

        $LASTEXITCODE | Should -Be 0
    }
}
