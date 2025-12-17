#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Validate-Consistency.ps1

.DESCRIPTION
    Tests the consistency validation functions that implement
    .agents/governance/consistency-protocol.md
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot ".." "Validate-Consistency.ps1"

    # Dot-source the script to get access to functions
    # We need to extract just the functions, not run the main script
    $scriptContent = Get-Content -Path $scriptPath -Raw

    # Extract function definitions
    $functionPattern = '(?ms)(function\s+[\w-]+\s*\{.*?\n\})'
    $matches = [regex]::Matches($scriptContent, $functionPattern)

    # Create a temporary module with just the functions
    $functionsOnly = @"
`$ColorReset = '``e[0m'
`$ColorRed = '``e[31m'
`$ColorYellow = '``e[33m'
`$ColorGreen = '``e[32m'
`$ColorCyan = '``e[36m'
`$ColorMagenta = '``e[35m'
`$Format = 'console'

"@

    foreach ($match in $matches) {
        $functionsOnly += $match.Value + "`n`n"
    }

    # Execute the functions in current scope
    Invoke-Expression $functionsOnly

    # Create temp directory structure for tests
    $script:TestRoot = Join-Path $TestDrive "test-project"
    $script:AgentsPath = Join-Path $TestRoot ".agents"
    $script:RoadmapPath = Join-Path $AgentsPath "roadmap"
    $script:PlanningPath = Join-Path $AgentsPath "planning"

    New-Item -ItemType Directory -Path $RoadmapPath -Force | Out-Null
    New-Item -ItemType Directory -Path $PlanningPath -Force | Out-Null
}

Describe "Test-NamingConvention" {
    It "Accepts valid EPIC naming" {
        $result = Test-NamingConvention -FilePath "EPIC-001-user-auth.md" -ExpectedPattern "epic"
        $result | Should -BeTrue
    }

    It "Accepts valid EPIC with longer number" {
        $result = Test-NamingConvention -FilePath "EPIC-123-feature-name.md" -ExpectedPattern "epic"
        $result | Should -BeTrue
    }

    It "Rejects invalid EPIC naming - missing number" {
        $result = Test-NamingConvention -FilePath "EPIC-user-auth.md" -ExpectedPattern "epic"
        $result | Should -BeFalse
    }

    It "Rejects invalid EPIC naming - wrong prefix" {
        $result = Test-NamingConvention -FilePath "Epic-001-user-auth.md" -ExpectedPattern "epic"
        $result | Should -BeFalse
    }

    It "Accepts valid PRD naming" {
        $result = Test-NamingConvention -FilePath "prd-user-authentication.md" -ExpectedPattern "prd"
        $result | Should -BeTrue
    }

    It "Rejects invalid PRD naming - uppercase" {
        $result = Test-NamingConvention -FilePath "PRD-user-auth.md" -ExpectedPattern "prd"
        $result | Should -BeFalse
    }

    It "Accepts valid tasks naming" {
        $result = Test-NamingConvention -FilePath "tasks-user-authentication.md" -ExpectedPattern "tasks"
        $result | Should -BeTrue
    }

    It "Accepts valid ADR naming" {
        $result = Test-NamingConvention -FilePath "ADR-001-architecture-decision.md" -ExpectedPattern "adr"
        $result | Should -BeTrue
    }

    It "Accepts valid TM naming" {
        $result = Test-NamingConvention -FilePath "TM-001-threat-model.md" -ExpectedPattern "tm"
        $result | Should -BeTrue
    }

    It "Accepts implementation-plan naming" {
        $result = Test-NamingConvention -FilePath "implementation-plan-user-auth.md" -ExpectedPattern "plan"
        $result | Should -BeTrue
    }

    It "Accepts plan- prefix naming" {
        $result = Test-NamingConvention -FilePath "plan-user-auth.md" -ExpectedPattern "plan"
        $result | Should -BeTrue
    }

    It "Returns true for unknown patterns" {
        $result = Test-NamingConvention -FilePath "random-file.md" -ExpectedPattern "unknown"
        $result | Should -BeTrue
    }
}

Describe "Test-CrossReferences" {
    BeforeEach {
        # Create test files
        $testFile = Join-Path $PlanningPath "test-doc.md"
        $existingFile = Join-Path $PlanningPath "existing.md"
        New-Item -ItemType File -Path $existingFile -Force | Out-Null
    }

    It "Passes when all references exist" {
        $content = @"
# Test Document

See [existing doc](existing.md) for details.
"@
        Set-Content -Path (Join-Path $PlanningPath "test-doc.md") -Value $content

        $result = Test-CrossReferences -FilePath (Join-Path $PlanningPath "test-doc.md") -BasePath $TestRoot
        $result.Passed | Should -BeTrue
        $result.Issues.Count | Should -Be 0
    }

    It "Fails when reference is broken" {
        $content = @"
# Test Document

See [missing doc](nonexistent.md) for details.
"@
        Set-Content -Path (Join-Path $PlanningPath "test-doc.md") -Value $content

        $result = Test-CrossReferences -FilePath (Join-Path $PlanningPath "test-doc.md") -BasePath $TestRoot
        $result.Passed | Should -BeFalse
        $result.Issues | Should -Contain "Broken reference: nonexistent.md"
    }

    It "Ignores HTTP URLs" {
        $content = @"
# Test Document

See [external](https://example.com) for details.
"@
        Set-Content -Path (Join-Path $PlanningPath "test-doc.md") -Value $content

        $result = Test-CrossReferences -FilePath (Join-Path $PlanningPath "test-doc.md") -BasePath $TestRoot
        $result.Passed | Should -BeTrue
    }

    It "Ignores anchor-only links" {
        $content = @"
# Test Document

See [section](#section-name) below.
"@
        Set-Content -Path (Join-Path $PlanningPath "test-doc.md") -Value $content

        $result = Test-CrossReferences -FilePath (Join-Path $PlanningPath "test-doc.md") -BasePath $TestRoot
        $result.Passed | Should -BeTrue
    }

    It "Handles paths with anchors" {
        $content = @"
# Test Document

See [existing doc](existing.md#section) for details.
"@
        Set-Content -Path (Join-Path $PlanningPath "test-doc.md") -Value $content

        $result = Test-CrossReferences -FilePath (Join-Path $PlanningPath "test-doc.md") -BasePath $TestRoot
        $result.Passed | Should -BeTrue
    }
}

Describe "Test-TaskCompletion" {
    It "Passes when all P0 tasks are complete" {
        $content = @"
## P0 Tasks

- [x] Critical task 1
- [x] Critical task 2

## P1 Tasks

- [ ] Nice to have
"@
        $taskFile = Join-Path $PlanningPath "tasks-test.md"
        Set-Content -Path $taskFile -Value $content

        $result = Test-TaskCompletion -TasksPath $taskFile
        $result.Passed | Should -BeTrue
        $result.P0Incomplete.Count | Should -Be 0
    }

    It "Fails when P0 tasks are incomplete" {
        $content = @"
## P0 Tasks

- [x] Critical task 1
- [ ] Critical task 2 not done

## P1 Tasks

- [ ] Nice to have
"@
        $taskFile = Join-Path $PlanningPath "tasks-test.md"
        Set-Content -Path $taskFile -Value $content

        $result = Test-TaskCompletion -TasksPath $taskFile
        $result.Passed | Should -BeFalse
        $result.P0Incomplete.Count | Should -Be 1
    }

    It "Counts tasks correctly" {
        $content = @"
## Tasks

- [x] Task 1
- [x] Task 2
- [ ] Task 3
"@
        $taskFile = Join-Path $PlanningPath "tasks-test.md"
        Set-Content -Path $taskFile -Value $content

        $result = Test-TaskCompletion -TasksPath $taskFile
        $result.Total | Should -Be 3
        $result.Completed | Should -Be 2
    }

    It "Returns empty result for missing file" {
        $result = Test-TaskCompletion -TasksPath "nonexistent.md"
        $result.Total | Should -Be 0
        $result.Passed | Should -BeTrue
    }
}

Describe "Test-RequirementCoverage" {
    It "Passes when tasks cover requirements" {
        $prdContent = @"
## Requirements

- [ ] Requirement 1
- [ ] Requirement 2
"@
        $tasksContent = @"
## Tasks

- [ ] Task for req 1
- [ ] Task for req 2
- [ ] Additional task
"@
        $prdFile = Join-Path $PlanningPath "prd-test.md"
        $tasksFile = Join-Path $PlanningPath "tasks-test.md"
        Set-Content -Path $prdFile -Value $prdContent
        Set-Content -Path $tasksFile -Value $tasksContent

        $result = Test-RequirementCoverage -PRDPath $prdFile -TasksPath $tasksFile
        $result.Passed | Should -BeTrue
    }

    It "Fails when tasks are fewer than requirements" {
        $prdContent = @"
## Requirements

- [ ] Requirement 1
- [ ] Requirement 2
- [ ] Requirement 3
"@
        $tasksContent = @"
## Tasks

- [ ] Task 1
"@
        $prdFile = Join-Path $PlanningPath "prd-test.md"
        $tasksFile = Join-Path $PlanningPath "tasks-test.md"
        Set-Content -Path $prdFile -Value $prdContent
        Set-Content -Path $tasksFile -Value $tasksContent

        $result = Test-RequirementCoverage -PRDPath $prdFile -TasksPath $tasksFile
        $result.Passed | Should -BeFalse
        $result.Issues | Should -Contain "Fewer tasks (1) than requirements (3)"
    }

    It "Fails when tasks file is missing" {
        $prdFile = Join-Path $PlanningPath "prd-test.md"
        Set-Content -Path $prdFile -Value "## Requirements`n- [ ] Req 1"

        $result = Test-RequirementCoverage -PRDPath $prdFile -TasksPath "nonexistent.md"
        $result.Passed | Should -BeFalse
        $result.Issues | Should -Contain "Tasks file not found for PRD"
    }
}

Describe "Find-FeatureArtifacts" {
    BeforeEach {
        # Create test artifacts
        New-Item -ItemType File -Path (Join-Path $RoadmapPath "EPIC-001-test-feature.md") -Force | Out-Null
        New-Item -ItemType File -Path (Join-Path $PlanningPath "prd-test-feature.md") -Force | Out-Null
        New-Item -ItemType File -Path (Join-Path $PlanningPath "tasks-test-feature.md") -Force | Out-Null
    }

    It "Finds all artifacts for a feature" {
        $artifacts = Find-FeatureArtifacts -FeatureName "test-feature" -BasePath $TestRoot

        $artifacts.Epic | Should -Not -BeNullOrEmpty
        $artifacts.PRD | Should -Not -BeNullOrEmpty
        $artifacts.Tasks | Should -Not -BeNullOrEmpty
    }

    It "Returns null for missing artifacts" {
        $artifacts = Find-FeatureArtifacts -FeatureName "nonexistent" -BasePath $TestRoot

        $artifacts.Epic | Should -BeNullOrEmpty
        $artifacts.PRD | Should -BeNullOrEmpty
        $artifacts.Tasks | Should -BeNullOrEmpty
    }
}

Describe "Get-AllFeatures" {
    BeforeEach {
        New-Item -ItemType File -Path (Join-Path $PlanningPath "prd-feature-one.md") -Force | Out-Null
        New-Item -ItemType File -Path (Join-Path $PlanningPath "prd-feature-two.md") -Force | Out-Null
        New-Item -ItemType File -Path (Join-Path $PlanningPath "tasks-feature-three.md") -Force | Out-Null
    }

    It "Discovers features from prd files" {
        $features = Get-AllFeatures -BasePath $TestRoot

        $features | Should -Contain "feature-one"
        $features | Should -Contain "feature-two"
    }

    It "Discovers features from tasks files" {
        $features = Get-AllFeatures -BasePath $TestRoot

        $features | Should -Contain "feature-three"
    }

    It "Returns unique features" {
        # Add duplicate
        New-Item -ItemType File -Path (Join-Path $PlanningPath "tasks-feature-one.md") -Force | Out-Null

        $features = Get-AllFeatures -BasePath $TestRoot
        $duplicates = $features | Group-Object | Where-Object { $_.Count -gt 1 }

        $duplicates | Should -BeNullOrEmpty
    }
}

Describe "Test-NamingConventions" {
    It "Passes for correctly named artifacts" {
        $artifacts = @{
            Epic = "EPIC-001-test.md"
            PRD = "prd-test.md"
            Tasks = "tasks-test.md"
            Plan = "implementation-plan-test.md"
        }

        # Create mock files with correct paths
        $epicPath = Join-Path $RoadmapPath "EPIC-001-test.md"
        $prdPath = Join-Path $PlanningPath "prd-test.md"
        $tasksPath = Join-Path $PlanningPath "tasks-test.md"
        $planPath = Join-Path $PlanningPath "implementation-plan-test.md"

        New-Item -ItemType File -Path $epicPath -Force | Out-Null
        New-Item -ItemType File -Path $prdPath -Force | Out-Null
        New-Item -ItemType File -Path $tasksPath -Force | Out-Null
        New-Item -ItemType File -Path $planPath -Force | Out-Null

        $artifacts = @{
            Epic = $epicPath
            PRD = $prdPath
            Tasks = $tasksPath
            Plan = $planPath
        }

        $result = Test-NamingConventions -Artifacts $artifacts
        $result.Passed | Should -BeTrue
    }

    It "Fails for incorrectly named PRD" {
        $artifacts = @{
            PRD = Join-Path $PlanningPath "PRD-Test.md"
        }
        New-Item -ItemType File -Path $artifacts.PRD -Force | Out-Null

        $result = Test-NamingConventions -Artifacts $artifacts
        $result.Passed | Should -BeFalse
        $result.Issues | Should -Match "PRD naming violation"
    }
}
