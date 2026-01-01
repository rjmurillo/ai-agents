#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Validate-Traceability.ps1

.DESCRIPTION
    Tests the traceability validation functionality for the spec layer.
    Validates cross-references between requirements, designs, and tasks
    following the traceability schema defined in .agents/governance/traceability-schema.md.
#>

BeforeAll {
    $script:scriptPath = Join-Path $PSScriptRoot ".." "scripts" "Validate-Traceability.ps1"

    # Enable external paths for test isolation (allows temp directories outside repo root)
    $env:TRACEABILITY_ALLOW_EXTERNAL_PATHS = "1"

    # Create temp directory for test data
    $script:testRoot = Join-Path ([System.IO.Path]::GetTempPath()) "validate-traceability-tests-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
    New-Item -Path $script:testRoot -ItemType Directory -Force | Out-Null

    # Helper to create test spec structure
    # Using Initialize- verb instead of New- to avoid PSUseShouldProcessForStateChangingFunctions
    function Initialize-TestSpecStructure {
        param(
            [string]$BasePath,
            [hashtable]$Requirements,
            [hashtable]$Designs,
            [hashtable]$Tasks
        )

        # Create subdirectories
        $reqPath = Join-Path $BasePath "requirements"
        $designPath = Join-Path $BasePath "design"
        $taskPath = Join-Path $BasePath "tasks"

        New-Item -Path $reqPath -ItemType Directory -Force | Out-Null
        New-Item -Path $designPath -ItemType Directory -Force | Out-Null
        New-Item -Path $taskPath -ItemType Directory -Force | Out-Null

        # Create requirement files
        foreach ($file in $Requirements.Keys) {
            $filePath = Join-Path $reqPath $file
            $Requirements[$file] | Set-Content -Path $filePath -Encoding UTF8
        }

        # Create design files
        foreach ($file in $Designs.Keys) {
            $filePath = Join-Path $designPath $file
            $Designs[$file] | Set-Content -Path $filePath -Encoding UTF8
        }

        # Create task files
        foreach ($file in $Tasks.Keys) {
            $filePath = Join-Path $taskPath $file
            $Tasks[$file] | Set-Content -Path $filePath -Encoding UTF8
        }
    }
}

AfterAll {
    # Clean up test root
    if (Test-Path $script:testRoot) {
        Remove-Item -Path $script:testRoot -Recurse -Force -ErrorAction SilentlyContinue
    }

    # Reset environment variable
    $env:TRACEABILITY_ALLOW_EXTERNAL_PATHS = $null
}

Describe "Validate-Traceability" {
    BeforeEach {
        # Create fresh test directory for each test
        $script:testSpecsPath = Join-Path $script:testRoot "specs-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
        New-Item -Path $script:testSpecsPath -ItemType Directory -Force | Out-Null
    }

    AfterEach {
        # Clean up test directory
        if (Test-Path $script:testSpecsPath) {
            Remove-Item -Path $script:testSpecsPath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Context "When specs path does not exist" {
        It "Throws error with descriptive message for non-existent path" {
            # With $ErrorActionPreference = "Stop", Write-Error becomes terminating
            { & $script:scriptPath -SpecsPath "/non/existent/path" -Format "json" } |
                Should -Throw -ExpectedMessage "*Specs path not found*"
        }

        It "Error message includes the path that was not found" {
            try {
                & $script:scriptPath -SpecsPath "/non/existent/path" -Format "json" 2>&1
            }
            catch {
                $_.Exception.Message | Should -Match "non/existent/path"
            }
        }
    }

    Context "When no spec files exist" {
        It "Reports zero specs found" {
            # Create empty structure
            Initialize-TestSpecStructure -BasePath $script:testSpecsPath -Requirements @{} -Designs @{} -Tasks @{}

            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.stats.requirements | Should -Be 0
            $result.stats.designs | Should -Be 0
            $result.stats.tasks | Should -Be 0
        }

        It "Passes validation with no specs" {
            Initialize-TestSpecStructure -BasePath $script:testSpecsPath -Requirements @{} -Designs @{} -Tasks @{}

            & $script:scriptPath -SpecsPath $script:testSpecsPath 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "When validating complete traceability chain" {
        BeforeEach {
            # Create valid traceability chain: REQ-001 -> DESIGN-001 -> TASK-001
            $requirements = @{
                "REQ-001-feature.md" = @"
---
type: requirement
id: REQ-001
status: approved
related:
  - DESIGN-001
---
# REQ-001: Feature Requirement
"@
            }
            $designs = @{
                "DESIGN-001-feature.md" = @"
---
type: design
id: DESIGN-001
status: approved
related:
  - REQ-001
---
# DESIGN-001: Feature Design
"@
            }
            $tasks = @{
                "TASK-001-implement.md" = @"
---
type: task
id: TASK-001
status: pending
related:
  - DESIGN-001
---
# TASK-001: Implement Feature
"@
            }
            Initialize-TestSpecStructure -BasePath $script:testSpecsPath -Requirements $requirements -Designs $designs -Tasks $tasks
        }

        It "Finds all spec files" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.stats.requirements | Should -Be 1
            $result.stats.designs | Should -Be 1
            $result.stats.tasks | Should -Be 1
        }

        It "Reports valid chain" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.stats.validChains | Should -Be 1
        }

        It "Reports no errors" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.errors.Count | Should -Be 0
        }

        It "Reports no warnings" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.warnings.Count | Should -Be 0
        }

        It "Passes validation" {
            & $script:scriptPath -SpecsPath $script:testSpecsPath 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "When task has broken reference (Rule 4)" {
        BeforeEach {
            $requirements = @{}
            $designs = @{}
            $tasks = @{
                "TASK-001-broken.md" = @"
---
type: task
id: TASK-001
status: pending
related:
  - DESIGN-999
---
# TASK-001: References non-existent design
"@
            }
            Initialize-TestSpecStructure -BasePath $script:testSpecsPath -Requirements $requirements -Designs $designs -Tasks $tasks
        }

        It "Detects broken reference" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            # Expect 1 error for broken reference
            ($result.errors | Where-Object { $_.target -eq "DESIGN-999" }).Count | Should -Be 1
        }

        It "Reports Rule 4 violation" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.errors[0].rule | Should -Match "Rule 4"
        }

        It "Identifies source and target" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.errors[0].source | Should -Be "TASK-001"
            $result.errors[0].target | Should -Be "DESIGN-999"
        }

        It "Returns exit code 1" {
            & $script:scriptPath -SpecsPath $script:testSpecsPath 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 1
        }
    }

    Context "When task has no design reference (Rule 2)" {
        BeforeEach {
            $requirements = @{}
            $designs = @{}
            $tasks = @{
                "TASK-001-untraced.md" = @"
---
type: task
id: TASK-001
status: pending
related: []
---
# TASK-001: Untraced task
"@
            }
            Initialize-TestSpecStructure -BasePath $script:testSpecsPath -Requirements $requirements -Designs $designs -Tasks $tasks
        }

        It "Detects untraced task" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.errors.Count | Should -Be 1
        }

        It "Reports Rule 2 violation" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.errors[0].rule | Should -Match "Rule 2"
        }

        It "Returns exit code 1" {
            & $script:scriptPath -SpecsPath $script:testSpecsPath 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 1
        }
    }

    Context "When requirement has no design referencing it (Rule 1)" {
        BeforeEach {
            $requirements = @{
                "REQ-001-orphan.md" = @"
---
type: requirement
id: REQ-001
status: approved
related: []
---
# REQ-001: Orphaned requirement
"@
            }
            $designs = @{}
            $tasks = @{}
            Initialize-TestSpecStructure -BasePath $script:testSpecsPath -Requirements $requirements -Designs $designs -Tasks $tasks
        }

        It "Detects orphaned requirement" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.warnings.Count | Should -Be 1
        }

        It "Reports Rule 1 violation" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.warnings[0].rule | Should -Match "Rule 1"
        }

        It "Returns exit code 0 without -Strict" {
            & $script:scriptPath -SpecsPath $script:testSpecsPath 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 0
        }

        It "Returns exit code 2 with -Strict" {
            & $script:scriptPath -SpecsPath $script:testSpecsPath -Strict 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 2
        }
    }

    Context "When design has no task referencing it (Rule 3)" {
        BeforeEach {
            $requirements = @{
                "REQ-001-feature.md" = @"
---
type: requirement
id: REQ-001
status: approved
related: []
---
# REQ-001
"@
            }
            $designs = @{
                "DESIGN-001-orphan.md" = @"
---
type: design
id: DESIGN-001
status: approved
related:
  - REQ-001
---
# DESIGN-001: Orphaned design (no tasks)
"@
            }
            $tasks = @{}
            Initialize-TestSpecStructure -BasePath $script:testSpecsPath -Requirements $requirements -Designs $designs -Tasks $tasks
        }

        It "Detects orphaned design" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            # Should have warning for design with no tasks
            ($result.warnings | Where-Object { $_.source -eq "DESIGN-001" -and $_.rule -match "Rule 3" }) | Should -Not -BeNullOrEmpty
        }

        It "Reports valid chains as 0" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.stats.validChains | Should -Be 0
        }
    }

    Context "When design has no REQ reference (Rule 3)" {
        BeforeEach {
            $requirements = @{}
            $designs = @{
                "DESIGN-001-noreq.md" = @"
---
type: design
id: DESIGN-001
status: approved
related: []
---
# DESIGN-001: Design without REQ reference
"@
            }
            $tasks = @{
                "TASK-001-impl.md" = @"
---
type: task
id: TASK-001
status: pending
related:
  - DESIGN-001
---
# TASK-001
"@
            }
            Initialize-TestSpecStructure -BasePath $script:testSpecsPath -Requirements $requirements -Designs $designs -Tasks $tasks
        }

        It "Detects design missing REQ reference" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            ($result.warnings | Where-Object { $_.source -eq "DESIGN-001" -and $_.message -match "no REQ reference" }) | Should -Not -BeNullOrEmpty
        }
    }

    Context "When using different output formats" {
        BeforeEach {
            $requirements = @{
                "REQ-001-test.md" = @"
---
type: requirement
id: REQ-001
status: approved
related:
  - DESIGN-001
---
# REQ-001
"@
            }
            $designs = @{
                "DESIGN-001-test.md" = @"
---
type: design
id: DESIGN-001
status: approved
related:
  - REQ-001
---
# DESIGN-001
"@
            }
            $tasks = @{
                "TASK-001-test.md" = @"
---
type: task
id: TASK-001
status: pending
related:
  - DESIGN-001
---
# TASK-001
"@
            }
            Initialize-TestSpecStructure -BasePath $script:testSpecsPath -Requirements $requirements -Designs $designs -Tasks $tasks
        }

        It "Outputs valid JSON with -Format json" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json"
            { $result | ConvertFrom-Json } | Should -Not -Throw
        }

        It "Outputs markdown with -Format markdown" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "markdown"
            $result | Should -Match "# Traceability Validation Report"
        }

        It "Includes summary table in markdown output" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "markdown"
            $result | Should -Match "\| Metric \| Count \|"
        }

        It "Produces console output with -Format console" {
            # Console output goes to host, not return value - just verify no throw
            { & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "console" } | Should -Not -Throw
        }
    }

    Context "When validating multiple complete chains" {
        BeforeEach {
            $requirements = @{
                "REQ-001-feature.md" = @"
---
type: requirement
id: REQ-001
status: approved
related:
  - DESIGN-001
---
# REQ-001
"@
                "REQ-002-feature.md" = @"
---
type: requirement
id: REQ-002
status: approved
related:
  - DESIGN-001
---
# REQ-002
"@
            }
            $designs = @{
                "DESIGN-001-feature.md" = @"
---
type: design
id: DESIGN-001
status: approved
related:
  - REQ-001
  - REQ-002
---
# DESIGN-001
"@
            }
            $tasks = @{
                "TASK-001-impl.md" = @"
---
type: task
id: TASK-001
status: pending
related:
  - DESIGN-001
---
# TASK-001
"@
                "TASK-002-impl.md" = @"
---
type: task
id: TASK-002
status: pending
related:
  - DESIGN-001
---
# TASK-002
"@
            }
            Initialize-TestSpecStructure -BasePath $script:testSpecsPath -Requirements $requirements -Designs $designs -Tasks $tasks
        }

        It "Finds all specs" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.stats.requirements | Should -Be 2
            $result.stats.designs | Should -Be 1
            $result.stats.tasks | Should -Be 2
        }

        It "Reports valid chain" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.stats.validChains | Should -Be 1
        }

        It "Reports no errors or warnings" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.errors.Count | Should -Be 0
            $result.warnings.Count | Should -Be 0
        }
    }

    Context "When design references non-existent requirement" {
        BeforeEach {
            $requirements = @{}
            $designs = @{
                "DESIGN-001-brokenref.md" = @"
---
type: design
id: DESIGN-001
status: approved
related:
  - REQ-999
---
# DESIGN-001: References non-existent REQ
"@
            }
            $tasks = @{
                "TASK-001-impl.md" = @"
---
type: task
id: TASK-001
status: pending
related:
  - DESIGN-001
---
# TASK-001
"@
            }
            Initialize-TestSpecStructure -BasePath $script:testSpecsPath -Requirements $requirements -Designs $designs -Tasks $tasks
        }

        It "Detects broken reference from design" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            ($result.errors | Where-Object { $_.source -eq "DESIGN-001" -and $_.target -eq "REQ-999" }) | Should -Not -BeNullOrEmpty
        }

        It "Reports Rule 4 violation" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            ($result.errors | Where-Object { $_.rule -match "Rule 4" }) | Should -Not -BeNullOrEmpty
        }
    }

    Context "When spec file has malformed YAML" {
        BeforeEach {
            $requirements = @{
                "REQ-001-malformed.md" = @"
---
type: requirement
id REQ-001
status: approved
---
# REQ-001: Malformed YAML (missing colon)
"@
            }
            $designs = @{}
            $tasks = @{}
            Initialize-TestSpecStructure -BasePath $script:testSpecsPath -Requirements $requirements -Designs $designs -Tasks $tasks
        }

        It "Handles malformed YAML gracefully" {
            { & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" } | Should -Not -Throw
        }

        It "Does not crash on parse errors" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            # Malformed file might not be parsed, so count could be 0
            $result.stats.requirements | Should -BeIn @(0, 1)
        }
    }

    Context "When spec file has no YAML front matter" {
        BeforeEach {
            $requirements = @{
                "REQ-001-nofrontmatter.md" = @"
# REQ-001: No YAML Front Matter

This requirement has no YAML front matter at all.
"@
            }
            $designs = @{}
            $tasks = @{}
            Initialize-TestSpecStructure -BasePath $script:testSpecsPath -Requirements $requirements -Designs $designs -Tasks $tasks
        }

        It "Handles missing front matter gracefully" {
            { & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" } | Should -Not -Throw
        }

        It "Does not count file without front matter" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.stats.requirements | Should -Be 0
        }
    }

    Context "When validating status consistency (Rule 5)" {
        BeforeEach {
            $requirements = @{
                "REQ-001-feature.md" = @"
---
type: requirement
id: REQ-001
status: approved
related:
  - DESIGN-001
---
# REQ-001
"@
            }
            $designs = @{
                "DESIGN-001-feature.md" = @"
---
type: design
id: DESIGN-001
status: draft
related:
  - REQ-001
---
# DESIGN-001: Status is draft
"@
            }
            $tasks = @{
                "TASK-001-complete.md" = @"
---
type: task
id: TASK-001
status: complete
related:
  - DESIGN-001
---
# TASK-001: Status is complete but design is draft
"@
            }
            Initialize-TestSpecStructure -BasePath $script:testSpecsPath -Requirements $requirements -Designs $designs -Tasks $tasks
        }

        It "Detects status inconsistency" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.info.Count | Should -BeGreaterThan 0
        }

        It "Reports Rule 5 in info" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            ($result.info | Where-Object { $_.rule -match "Rule 5" }) | Should -Not -BeNullOrEmpty
        }

        It "Does not fail validation for status inconsistency" {
            & $script:scriptPath -SpecsPath $script:testSpecsPath 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 0
        }
    }
}

Describe "Edge Cases" {
    BeforeEach {
        $script:testSpecsPath = Join-Path $script:testRoot "edge-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
        New-Item -Path $script:testSpecsPath -ItemType Directory -Force | Out-Null
    }

    AfterEach {
        if (Test-Path $script:testSpecsPath) {
            Remove-Item -Path $script:testSpecsPath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Context "When related field is missing entirely" {
        BeforeEach {
            $tasks = @{
                "TASK-001-norelated.md" = @"
---
type: task
id: TASK-001
status: pending
---
# TASK-001: No related field
"@
            }
            Initialize-TestSpecStructure -BasePath $script:testSpecsPath -Requirements @{} -Designs @{} -Tasks $tasks
        }

        It "Treats missing related as empty" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            # Should be treated as untraced task
            ($result.errors | Where-Object { $_.rule -match "Rule 2" }) | Should -Not -BeNullOrEmpty
        }
    }

    Context "When ID pattern is non-standard (alphanumeric)" {
        BeforeEach {
            $requirements = @{
                "REQ-ABC-feature.md" = @"
---
type: requirement
id: REQ-ABC
status: approved
related: []
---
# REQ-ABC: Non-numeric ID
"@
            }
            # File pattern REQ-*.md matches REQ-ABC-feature.md; regex pattern [A-Z]+-[A-Z0-9]+ parses alphanumeric IDs
            Initialize-TestSpecStructure -BasePath $script:testSpecsPath -Requirements $requirements -Designs @{} -Tasks @{}
        }

        It "Parses alphanumeric IDs correctly" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            # Should find the requirement with alphanumeric ID
            $result.stats.requirements | Should -Be 1
        }
    }

    Context "When multiple designs implement same requirement" {
        BeforeEach {
            $requirements = @{
                "REQ-001-feature.md" = @"
---
type: requirement
id: REQ-001
status: approved
related:
  - DESIGN-001
  - DESIGN-002
---
# REQ-001
"@
            }
            $designs = @{
                "DESIGN-001-option-a.md" = @"
---
type: design
id: DESIGN-001
status: approved
related:
  - REQ-001
---
# DESIGN-001: Option A
"@
                "DESIGN-002-option-b.md" = @"
---
type: design
id: DESIGN-002
status: approved
related:
  - REQ-001
---
# DESIGN-002: Option B
"@
            }
            $tasks = @{
                "TASK-001-impl.md" = @"
---
type: task
id: TASK-001
status: pending
related:
  - DESIGN-001
---
# TASK-001
"@
                "TASK-002-impl.md" = @"
---
type: task
id: TASK-002
status: pending
related:
  - DESIGN-002
---
# TASK-002
"@
            }
            Initialize-TestSpecStructure -BasePath $script:testSpecsPath -Requirements $requirements -Designs $designs -Tasks $tasks
        }

        It "Counts multiple valid chains" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.stats.validChains | Should -Be 2
        }

        It "Reports no errors for valid multi-chain" {
            $result = & $script:scriptPath -SpecsPath $script:testSpecsPath -Format "json" | ConvertFrom-Json
            $result.errors.Count | Should -Be 0
        }
    }
}
