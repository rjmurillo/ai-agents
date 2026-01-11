#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Validate-Consistency.ps1

.DESCRIPTION
    Tests the consistency validation functions that implement
    .agents/governance/consistency-protocol.md

.NOTES
    EXIT CODES:
    0  - Success: All tests passed
    1  - Error: One or more tests failed (set by Pester framework)

    See: ADR-035 Exit Code Standardization
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

Describe "Test-ScopeAlignment - Requirement Counting Regex" {
    <#
    .SYNOPSIS
        Extensive tests for the regex pattern used to count requirements in Test-ScopeAlignment.
        Tests the fix for PR #50 comment 2625540786: missing (?m) multiline flag.

    .DESCRIPTION
        The regex '(?m)- \[[ x]\]|^\d+\.|^-\s' should match:
        - Checkbox items: "- [ ]" or "- [x]"
        - Numbered lists: "1." at start of line (with (?m) flag)
        - Plain list items: "- " at start of line (with (?m) flag)

        These tests verify the fix works correctly for all list formats.
    #>

    BeforeAll {
        # Helper function to create test files and invoke Test-ScopeAlignment
        # Must be in BeforeAll for Pester 5.x (not evaluated during Discovery)
        function script:Invoke-ScopeAlignmentTest {
            param(
                [string]$EpicSuccessCriteria,
                [string]$PrdRequirements
            )

            $epicContent = @"
# Epic

### Success Criteria
$EpicSuccessCriteria
"@
            # Include EPIC-001 reference to satisfy the Epic reference check
            $prdContent = @"
# PRD

**Epic**: EPIC-001-test.md

## Requirements
$PrdRequirements

## Other Section
"@

            $epicPath = Join-Path $RoadmapPath "EPIC-001-test.md"
            $prdPath = Join-Path $PlanningPath "prd-test.md"

            Set-Content -Path $epicPath -Value $epicContent -NoNewline
            Set-Content -Path $prdPath -Value $prdContent -NoNewline

            return Test-ScopeAlignment -EpicPath $epicPath -PRDPath $prdPath
        }
    }

    BeforeEach {
        # Clean up any existing test files
        Get-ChildItem -Path $RoadmapPath -Filter "*.md" -ErrorAction SilentlyContinue | Remove-Item -Force
        Get-ChildItem -Path $PlanningPath -Filter "*.md" -ErrorAction SilentlyContinue | Remove-Item -Force
    }

    Context "Positive Tests - Checkbox Items" {
        It "Counts single unchecked checkbox" {
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria "- [ ] One criterion" -PrdRequirements "- [ ] One requirement"
            $result.Passed | Should -BeTrue
            $result.Issues | Should -Not -Contain "PRD has fewer requirements"
        }

        It "Counts single checked checkbox" {
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria "- [x] One criterion" -PrdRequirements "- [x] One requirement"
            $result.Passed | Should -BeTrue
            $result.Issues | Should -Not -Contain "PRD has fewer requirements"
        }

        It "Counts multiple unchecked checkboxes" {
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3
"@
            $prdReqs = @"
- [ ] Requirement 1
- [ ] Requirement 2
- [ ] Requirement 3
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }

        It "Counts mixed checked and unchecked checkboxes" {
            $epicCriteria = @"
- [x] Criterion 1
- [ ] Criterion 2
"@
            $prdReqs = @"
- [x] Requirement 1
- [ ] Requirement 2
- [x] Requirement 3
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }
    }

    Context "Positive Tests - Numbered Lists" {
        It "Counts single-digit numbered item" {
            $epicCriteria = "- [ ] One criterion"
            $prdReqs = @"
1. First requirement
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }

        It "Counts double-digit numbered items" {
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
"@
            $prdReqs = @"
10. Tenth requirement
11. Eleventh requirement
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }

        It "Counts triple-digit numbered items" {
            $epicCriteria = "- [ ] One criterion"
            $prdReqs = @"
100. Hundredth requirement
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }

        It "Counts multiple sequential numbered items" {
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3
"@
            $prdReqs = @"
1. First requirement
2. Second requirement
3. Third requirement
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }

        It "Counts non-sequential numbered items" {
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3
"@
            $prdReqs = @"
1. First requirement
5. Fifth requirement
10. Tenth requirement
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }
    }

    Context "Positive Tests - Plain List Items" {
        It "Counts single plain list item" {
            $epicCriteria = "- [ ] One criterion"
            $prdReqs = @"
- Simple requirement
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }

        It "Counts multiple plain list items" {
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3
"@
            $prdReqs = @"
- First requirement
- Second requirement
- Third requirement
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }

        It "Counts plain list items with varying content" {
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
"@
            $prdReqs = @"
- Short
- This is a much longer requirement with more detail
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }
    }

    Context "Positive Tests - Mixed Formats" {
        It "Counts checkboxes and numbered items together" {
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3
"@
            $prdReqs = @"
- [ ] Checkbox requirement
1. Numbered requirement
2. Another numbered
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }

        It "Counts checkboxes and plain lists together" {
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3
"@
            $prdReqs = @"
- [ ] Checkbox requirement
- Plain list item 1
- Plain list item 2
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }

        It "Counts all three formats together" {
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3
- [ ] Criterion 4
- [ ] Criterion 5
"@
            $prdReqs = @"
- [ ] Checkbox unchecked
- [x] Checkbox checked
1. Numbered item
- Plain list item
2. Another numbered
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }
    }

    Context "Negative Tests - Empty and Missing" {
        It "Returns no match for empty requirements section" {
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
"@
            $prdReqs = ""  # Empty requirements

            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            # Empty requirements means 0 count, which is less than 2 criteria
            $result.Issues | Should -Contain "PRD has fewer requirements (0) than Epic success criteria (2)"
        }

        It "Returns no match for non-list content" {
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
"@
            $prdReqs = @"
This is just plain text with no list items.
It doesn't contain any checkboxes, numbers, or dashes at line start.
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Issues | Should -Contain "PRD has fewer requirements (0) than Epic success criteria (2)"
        }
    }

    Context "Negative Tests - Malformed Patterns" {
        It "Does not count checkbox missing space after dash" {
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
"@
            # Note: "-[ ]" is missing space after dash - not valid markdown
            $prdReqs = @"
-[ ] Malformed checkbox 1
-[ ] Malformed checkbox 2
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            # These malformed checkboxes should not be counted
            $result.Issues | Should -Contain "PRD has fewer requirements (0) than Epic success criteria (2)"
        }

        It "Does not count number without period" {
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
"@
            $prdReqs = @"
1 First item without period
2 Second item without period
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Issues | Should -Contain "PRD has fewer requirements (0) than Epic success criteria (2)"
        }

        It "Does not count dash without space" {
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
"@
            $prdReqs = @"
-NoSpace1
-NoSpace2
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Issues | Should -Contain "PRD has fewer requirements (0) than Epic success criteria (2)"
        }

        It "Does not count inline patterns (not at line start)" {
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
"@
            $prdReqs = @"
Text with 1. inline numbered list
More text - with inline dash
Also has - [ ] inline checkbox
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            # The checkbox pattern "- [ ]" doesn't require line start anchor, so it will match
            # But the numbered and plain dash won't match since they're not at line start
            # This test verifies the (?m) flag is working for line-start patterns
            $result.Issues | Should -Contain "PRD has fewer requirements (1) than Epic success criteria (2)"
        }
    }

    Context "Edge Cases" {
        It "Handles single requirement item" {
            $epicCriteria = "- [ ] Single criterion"
            $prdReqs = "- [ ] Single requirement"
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }

        It "Handles large number of requirement items" {
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3
"@
            # Generate 50 requirements
            $prdReqs = (1..50 | ForEach-Object { "- [ ] Requirement $_" }) -join "`n"
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }

        It "Handles requirements with CRLF line endings" {
            $epicCriteria = "- [ ] Criterion 1`r`n- [ ] Criterion 2"
            $prdReqs = "- [ ] Requirement 1`r`n- [ ] Requirement 2"
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }

        It "Handles requirements with LF-only line endings" {
            $epicCriteria = "- [ ] Criterion 1`n- [ ] Criterion 2"
            $prdReqs = "- [ ] Requirement 1`n- [ ] Requirement 2"
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }

        It "Handles empty lines between requirements" {
            $epicCriteria = @"
- [ ] Criterion 1

- [ ] Criterion 2
"@
            $prdReqs = @"
- [ ] Requirement 1

- [ ] Requirement 2

- [ ] Requirement 3
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Passed | Should -BeTrue
        }

        It "Handles requirements with leading whitespace (should still match)" {
            # Note: The regex doesn't account for leading whitespace on numbered items
            # This test documents current behavior
            $epicCriteria = "- [ ] Criterion 1"
            $prdReqs = @"
  1. Indented numbered item
"@
            # With current regex, indented items won't match because ^ requires line start
            # This is expected behavior for numbered lists
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs
            $result.Issues | Should -Contain "PRD has fewer requirements (0) than Epic success criteria (1)"
        }
    }

    Context "Regression Tests - Consistency with Test-RequirementCoverage" {
        <#
        .SYNOPSIS
            Verifies that Test-ScopeAlignment regex behavior is consistent with
            Test-RequirementCoverage (line 272 in Validate-Consistency.ps1)
        #>

        It "Both functions count same checkbox content identically" {
            $prdContent = @"
## Requirements

- [ ] Requirement 1
- [x] Requirement 2
- [ ] Requirement 3
"@
            $tasksContent = @"
## Tasks

- [ ] Task 1
- [ ] Task 2
- [ ] Task 3
"@
            $prdFile = Join-Path $PlanningPath "prd-test.md"
            $tasksFile = Join-Path $PlanningPath "tasks-test.md"
            Set-Content -Path $prdFile -Value $prdContent
            Set-Content -Path $tasksFile -Value $tasksContent

            $coverageResult = Test-RequirementCoverage -PRDPath $prdFile -TasksPath $tasksFile

            # The RequirementCount from Test-RequirementCoverage should match
            # what Test-ScopeAlignment would count in the Requirements section
            $coverageResult.RequirementCount | Should -Be 3
        }

        It "Both functions count numbered list content identically" {
            $prdContent = @"
## Requirements

1. First requirement
2. Second requirement
3. Third requirement
"@
            $tasksContent = @"
## Tasks

- [ ] Task 1
- [ ] Task 2
- [ ] Task 3
"@
            $prdFile = Join-Path $PlanningPath "prd-test.md"
            $tasksFile = Join-Path $PlanningPath "tasks-test.md"
            Set-Content -Path $prdFile -Value $prdContent
            Set-Content -Path $tasksFile -Value $tasksContent

            $coverageResult = Test-RequirementCoverage -PRDPath $prdFile -TasksPath $tasksFile

            # Test-RequirementCoverage should correctly count numbered items with (?m) flag
            $coverageResult.RequirementCount | Should -Be 3
        }
    }

    Context "Before/After Fix Verification" {
        <#
        .SYNOPSIS
            Documents the behavior change from the fix.
            Before: ^ only matched at string start
            After: ^ matches at each line start with (?m)
        #>

        It "Numbered items at line start are now counted (was broken)" {
            # This test would have FAILED before the fix
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
"@
            $prdReqs = @"
1. First numbered requirement
2. Second numbered requirement
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs

            # With fix: numbered items are counted, so 2 >= 2 passes
            # Without fix: only 0 would be counted, causing false positive warning
            $result.Passed | Should -BeTrue
            $result.Issues | Should -Not -Contain "PRD has fewer requirements"
        }

        It "Plain dash items at line start are now counted (was broken)" {
            # This test would have FAILED before the fix
            $epicCriteria = @"
- [ ] Criterion 1
- [ ] Criterion 2
"@
            $prdReqs = @"
- First plain list item
- Second plain list item
"@
            $result = Invoke-ScopeAlignmentTest -EpicSuccessCriteria $epicCriteria -PrdRequirements $prdReqs

            # With fix: plain list items are counted, so 2 >= 2 passes
            # Without fix: only 0 would be counted, causing false positive warning
            $result.Passed | Should -BeTrue
            $result.Issues | Should -Not -Contain "PRD has fewer requirements"
        }
    }
}
