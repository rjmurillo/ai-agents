#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Validate-MemoryIndex.ps1

.DESCRIPTION
    Tests the memory index validation functionality for ADR-017 tiered memory architecture.
    Validates index parsing, file reference checking, keyword density, and orphan detection.
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot ".." "scripts" "Validate-MemoryIndex.ps1"

    # Create temp directory for test data
    $testRoot = Join-Path ([System.IO.Path]::GetTempPath()) "validate-memory-index-tests-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
    New-Item -Path $testRoot -ItemType Directory -Force | Out-Null

    # Helper to create test memory structure
    function New-TestMemoryStructure {
        param(
            [string]$BasePath,
            [hashtable]$Structure
        )

        foreach ($file in $Structure.Keys) {
            $filePath = Join-Path $BasePath $file
            $Structure[$file] | Set-Content -Path $filePath -Encoding UTF8
        }
    }

    # Helper to clean up test directory
    function Remove-TestMemoryStructure {
        param([string]$BasePath)
        if (Test-Path $BasePath) {
            Remove-Item -Path $BasePath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

AfterAll {
    # Clean up test root
    if (Test-Path $testRoot) {
        Remove-Item -Path $testRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe "Validate-MemoryIndex" {
    BeforeEach {
        # Create fresh test directory for each test
        $testMemoryPath = Join-Path $testRoot "memories-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
        New-Item -Path $testMemoryPath -ItemType Directory -Force | Out-Null
    }

    AfterEach {
        # Clean up test directory
        if (Test-Path $testMemoryPath) {
            Remove-Item -Path $testMemoryPath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Context "When memory path does not exist" {
        It "Exits gracefully with non-existent path" {
            # Script outputs error message to host, not return value
            { & $scriptPath -Path "/non/existent/path" -Format "json" } | Should -Not -Throw
        }

        It "Returns exit code 1 in CI mode for non-existent path" {
            $result = & $scriptPath -Path "/non/existent/path" -CI 2>&1
            $LASTEXITCODE | Should -Be 1
        }
    }

    Context "When no domain indices exist" {
        It "Reports zero domain indices found" {
            # Create empty memory directory
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.Summary.TotalDomains | Should -Be 0
        }

        It "Passes validation with no indices" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.Passed | Should -Be $true
        }
    }

    Context "When validating domain index with valid entries" {
        BeforeEach {
            # Create valid test structure
            $testStructure = @{
                "skills-test-index.md" = @"
| Keywords | File |
|----------|------|
| alpha beta gamma delta epsilon | test-skill-one |
| zeta eta theta iota kappa | test-skill-two |
"@
                "test-skill-one.md" = "# Test Skill One`nContent here"
                "test-skill-two.md" = "# Test Skill Two`nContent here"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Finds the domain index" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.Summary.TotalDomains | Should -Be 1
        }

        It "Parses entries correctly" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.test.Entries | Should -Be 2
        }

        It "Validates file references successfully" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.test.FileReferences.Passed | Should -Be $true
        }

        It "Reports no missing files" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.Summary.MissingFiles | Should -Be 0
        }

        It "Passes overall validation" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.Passed | Should -Be $true
        }
    }

    Context "When validating domain index with missing files" {
        BeforeEach {
            # Create index pointing to non-existent files
            $testStructure = @{
                "skills-broken-index.md" = @"
| Keywords | File |
|----------|------|
| alpha beta gamma | missing-skill |
| delta epsilon zeta | another-missing |
"@
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Detects missing files" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.Summary.MissingFiles | Should -Be 2
        }

        It "Fails validation" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.Passed | Should -Be $false
        }

        It "Lists missing file names in issues" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.broken.FileReferences.Issues | Should -Contain "Missing file: missing-skill.md"
        }

        It "Returns exit code 1 in CI mode" {
            & $scriptPath -Path $testMemoryPath -CI 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 1
        }
    }

    Context "When validating keyword density" {
        BeforeEach {
            # Create structure with overlapping keywords
            $testStructure = @{
                "skills-overlap-index.md" = @"
| Keywords | File |
|----------|------|
| shared keyword overlap common alpha | skill-one |
| shared keyword overlap common beta | skill-two |
"@
                "skill-one.md" = "Content"
                "skill-two.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Calculates keyword uniqueness" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.overlap.KeywordDensity.Densities | Should -Not -BeNullOrEmpty
        }

        It "Detects low uniqueness (below 40%)" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            # Each skill has 5 keywords, 4 shared = 20% unique
            $result.DomainResults.overlap.KeywordDensity.Passed | Should -Be $false
        }

        It "Reports keyword issues in summary" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.Summary.KeywordIssues | Should -BeGreaterThan 0
        }
    }

    Context "When validating high keyword uniqueness" {
        BeforeEach {
            # Create structure with distinct keywords
            $testStructure = @{
                "skills-unique-index.md" = @"
| Keywords | File |
|----------|------|
| alpha beta gamma delta epsilon | unique-skill-one |
| zeta eta theta iota kappa | unique-skill-two |
"@
                "unique-skill-one.md" = "Content"
                "unique-skill-two.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Passes keyword density check with unique keywords" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.unique.KeywordDensity.Passed | Should -Be $true
        }

        It "Reports 100% uniqueness for fully distinct keywords" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $density = $result.DomainResults.unique.KeywordDensity.Densities.'unique-skill-one'
            $density | Should -Be 1.0
        }
    }

    Context "When single entry in domain" {
        BeforeEach {
            $testStructure = @{
                "skills-single-index.md" = @"
| Keywords | File |
|----------|------|
| alpha beta gamma | single-skill |
"@
                "single-skill.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Passes with single entry (100% unique by definition)" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.single.KeywordDensity.Passed | Should -Be $true
        }

        It "Reports 100% density for single entry" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $density = $result.DomainResults.single.KeywordDensity.Densities.'single-skill'
            $density | Should -Be 1.0
        }
    }

    Context "When validating memory-index references" {
        BeforeEach {
            $testStructure = @{
                "memory-index.md" = @"
| Task Keywords | Essential Memories |
|---------------|-------------------|
| test domain | skills-domain-index |
"@
                "skills-domain-index.md" = @"
| Keywords | File |
|----------|------|
| alpha beta | domain-skill |
"@
                "domain-skill.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Validates memory-index exists" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.MemoryIndexResult | Should -Not -BeNullOrEmpty
        }
    }

    Context "When detecting orphaned files" {
        BeforeEach {
            $testStructure = @{
                "skills-orphan-index.md" = @"
| Keywords | File |
|----------|------|
| alpha beta | indexed-skill |
"@
                "indexed-skill.md" = "Content"
                "orphan-unindexed.md" = "Orphaned content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Runs orphan detection without error" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            # Orphan detection runs by default
            $result | Should -Not -BeNullOrEmpty
        }
    }

    Context "When using different output formats" {
        BeforeEach {
            $testStructure = @{
                "skills-format-index.md" = @"
| Keywords | File |
|----------|------|
| alpha beta gamma | format-skill |
"@
                "format-skill.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Outputs valid JSON with -Format json" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json"
            { $result | ConvertFrom-Json } | Should -Not -Throw
        }

        It "Outputs markdown with -Format markdown" {
            $result = & $scriptPath -Path $testMemoryPath -Format "markdown"
            $result | Should -Match "# Memory Index Validation Report"
        }

        It "Includes summary table in markdown output" {
            $result = & $scriptPath -Path $testMemoryPath -Format "markdown"
            $result | Should -Match "\| Metric \| Value \|"
        }

        It "Produces console output with -Format console" {
            # Console output goes to host, not return value - just verify no throw
            { & $scriptPath -Path $testMemoryPath -Format "console" } | Should -Not -Throw
        }
    }

    Context "When parsing index entries" {
        BeforeEach {
            $testStructure = @{
                "skills-parse-index.md" = @"
| Keywords | File |
|----------|------|
| keyword1 keyword2 keyword3 | skill-file |
"@
                "skill-file.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Extracts keywords correctly" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.parse.Entries | Should -Be 1
        }

        It "Skips header rows" {
            # Header row should not be counted as an entry
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.parse.Entries | Should -Be 1
        }
    }

    Context "When index has malformed entries" {
        BeforeEach {
            $testStructure = @{
                "skills-malformed-index.md" = @"
| Keywords | File |
|----------|------|
| valid keywords | valid-skill |
Not a table row
| also valid | another-skill |
"@
                "valid-skill.md" = "Content"
                "another-skill.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Skips malformed rows gracefully" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.malformed.Entries | Should -Be 2
        }
    }

    Context "When validating multiple domains" {
        BeforeEach {
            $testStructure = @{
                "skills-domain1-index.md" = @"
| Keywords | File |
|----------|------|
| alpha | domain1-skill |
"@
                "skills-domain2-index.md" = @"
| Keywords | File |
|----------|------|
| beta | domain2-skill |
"@
                "domain1-skill.md" = "Content"
                "domain2-skill.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Finds all domain indices" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.Summary.TotalDomains | Should -Be 2
        }

        It "Validates each domain separately" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.domain1 | Should -Not -BeNullOrEmpty
            $result.DomainResults.domain2 | Should -Not -BeNullOrEmpty
        }

        It "Reports total files across domains" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.Summary.TotalFiles | Should -Be 2
        }
    }

    Context "When running in CI mode" {
        BeforeEach {
            $testStructure = @{
                "skills-ci-index.md" = @"
| Keywords | File |
|----------|------|
| alpha | ci-skill |
"@
                "ci-skill.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Returns exit code 0 on success" {
            & $scriptPath -Path $testMemoryPath -CI 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "When entry has no keywords" {
        BeforeEach {
            $testStructure = @{
                "skills-empty-index.md" = @"
| Keywords | File |
|----------|------|
| | empty-keywords |
"@
                "empty-keywords.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Handles empty keywords gracefully" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            # Entry with no keywords - density calculation should complete without error
            $result.DomainResults.empty | Should -Not -BeNullOrEmpty
        }
    }

    Context "When using FixOrphans switch" {
        BeforeEach {
            $testStructure = @{
                "skills-fix-index.md" = @"
| Keywords | File |
|----------|------|
| alpha | fix-indexed |
"@
                "fix-indexed.md" = "Content"
                "fix-orphaned.md" = "Should be detected"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Reports orphans with FixOrphans switch" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" -FixOrphans | ConvertFrom-Json
            # Orphan detection checks if file matches domain prefix
            # fix-orphaned.md matches pattern fix-*
            $result | Should -Not -BeNullOrEmpty
        }
    }
}

Describe "ADR-017 Gap 1/2: Index Entry Naming Validation" {
    <#
    .SYNOPSIS
        Tests for detecting deprecated 'skill-' prefix in index table entries
    .DESCRIPTION
        ADR-017 requires files use {domain}-{description} format.
        Index entries referencing 'skill-' prefixed files must fail validation.
    #>

    BeforeEach {
        $testMemoryPath = Join-Path $testRoot "gap12-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
        New-Item -Path $testMemoryPath -ItemType Directory -Force | Out-Null
    }

    AfterEach {
        if (Test-Path $testMemoryPath) {
            Remove-Item -Path $testMemoryPath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Context "When index entry references skill- prefixed file" {
        BeforeEach {
            $testStructure = @{
                "skills-pr-index.md" = @"
| Keywords | File |
|----------|------|
| pr review verification | skill-pr-001 |
"@
                "skill-pr-001.md" = "Deprecated naming content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Fails validation when index references skill- prefixed file" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.pr.FileReferences.Passed | Should -Be $false
        }

        It "Reports ADR-017 violation in issues" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $issues = $result.DomainResults.pr.FileReferences.Issues
            $issues | Should -Contain "Index references deprecated 'skill-' prefix: skill-pr-001.md (ADR-017 violation)"
        }

        It "Populates NamingViolations array" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.pr.FileReferences.NamingViolations | Should -Contain "skill-pr-001"
        }

        It "Returns exit code 1 in CI mode" {
            & $scriptPath -Path $testMemoryPath -CI 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 1
        }

        It "Fails overall validation" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.Passed | Should -Be $false
        }
    }

    Context "When index entry uses correct naming convention" {
        BeforeEach {
            $testStructure = @{
                "skills-pr-index.md" = @"
| Keywords | File |
|----------|------|
| pr review verification | pr-review-001 |
"@
                "pr-review-001.md" = "Correct naming content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Passes validation with correct naming" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.pr.FileReferences.Passed | Should -Be $true
        }

        It "Has empty NamingViolations array" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.pr.FileReferences.NamingViolations | Should -BeNullOrEmpty
        }

        It "Returns exit code 0 in CI mode" {
            & $scriptPath -Path $testMemoryPath -CI 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "When index has mixed valid and invalid entries" {
        BeforeEach {
            $testStructure = @{
                "skills-mixed-index.md" = @"
| Keywords | File |
|----------|------|
| valid entry keywords | mixed-valid-entry |
| invalid prefix entry | skill-mixed-invalid |
| another valid one | mixed-another-valid |
"@
                "mixed-valid-entry.md" = "Valid"
                "skill-mixed-invalid.md" = "Invalid prefix"
                "mixed-another-valid.md" = "Also valid"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Fails validation due to single invalid entry" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.mixed.FileReferences.Passed | Should -Be $false
        }

        It "Reports only the invalid entry in NamingViolations" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.mixed.FileReferences.NamingViolations | Should -HaveCount 1
            $result.DomainResults.mixed.FileReferences.NamingViolations | Should -Contain "skill-mixed-invalid"
        }

        It "Includes valid files in ValidFiles" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.mixed.FileReferences.ValidFiles | Should -Contain "mixed-valid-entry"
            $result.DomainResults.mixed.FileReferences.ValidFiles | Should -Contain "mixed-another-valid"
        }
    }

    Context "When index references skill- file that does not exist" {
        BeforeEach {
            $testStructure = @{
                "skills-ghost-index.md" = @"
| Keywords | File |
|----------|------|
| ghost skill entry | skill-ghost-missing |
"@
            }
            # Note: skill-ghost-missing.md is NOT created
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Reports both naming violation AND missing file" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $issues = $result.DomainResults.ghost.FileReferences.Issues
            $issues | Should -HaveCount 2
            ($issues | Where-Object { $_ -match "ADR-017 violation" }) | Should -Not -BeNullOrEmpty
            ($issues | Where-Object { $_ -match "Missing file" }) | Should -Not -BeNullOrEmpty
        }

        It "Includes file in both NamingViolations and MissingFiles" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.ghost.FileReferences.NamingViolations | Should -Contain "skill-ghost-missing"
            $result.DomainResults.ghost.FileReferences.MissingFiles | Should -Contain "skill-ghost-missing"
        }
    }

    Context "When file name starts with 'skill' but not 'skill-'" {
        BeforeEach {
            $testStructure = @{
                "skills-skillbook-index.md" = @"
| Keywords | File |
|----------|------|
| skillbook patterns | skillbook-management |
"@
                "skillbook-management.md" = "Valid - 'skillbook' is not 'skill-' prefix"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Passes validation - 'skillbook' is not 'skill-' prefix" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.skillbook.FileReferences.Passed | Should -Be $true
        }

        It "Has no naming violations" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.skillbook.FileReferences.NamingViolations | Should -BeNullOrEmpty
        }
    }

    Context "When multiple domains have skill- prefix violations" {
        BeforeEach {
            $testStructure = @{
                "skills-domain1-index.md" = @"
| Keywords | File |
|----------|------|
| domain1 keywords | skill-domain1-bad |
"@
                "skills-domain2-index.md" = @"
| Keywords | File |
|----------|------|
| domain2 keywords | skill-domain2-bad |
"@
                "skill-domain1-bad.md" = "Bad"
                "skill-domain2-bad.md" = "Also bad"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Fails validation for both domains" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.domain1.FileReferences.Passed | Should -Be $false
            $result.DomainResults.domain2.FileReferences.Passed | Should -Be $false
        }

        It "Reports failed domains in summary" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.Summary.FailedDomains | Should -Be 2
        }
    }
}

Describe "ADR-017 Gap 4: Orphan Prefix Detection" {
    <#
    .SYNOPSIS
        Tests for detecting orphaned files with deprecated 'skill-' prefix
    .DESCRIPTION
        ADR-017 requires detecting 'skill-' prefixed files not in any index.
        These are flagged with Domain='INVALID' and rename guidance.
    #>

    BeforeEach {
        $testMemoryPath = Join-Path $testRoot "gap4-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
        New-Item -Path $testMemoryPath -ItemType Directory -Force | Out-Null
    }

    AfterEach {
        if (Test-Path $testMemoryPath) {
            Remove-Item -Path $testMemoryPath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Context "When skill- prefixed file exists but is not in any index" {
        BeforeEach {
            $testStructure = @{
                "skills-pr-index.md" = @"
| Keywords | File |
|----------|------|
| valid entry | pr-valid-skill |
"@
                "pr-valid-skill.md" = "Indexed and valid"
                "skill-pr-001.md" = "Orphaned with deprecated prefix"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Detects skill- prefixed orphan" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $orphans = $result.Orphans
            ($orphans | Where-Object { $_.File -eq "skill-pr-001" }) | Should -Not -BeNullOrEmpty
        }

        It "Marks orphan with Domain=INVALID" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $orphan = $result.Orphans | Where-Object { $_.File -eq "skill-pr-001" }
            $orphan.Domain | Should -Be "INVALID"
        }

        It "Provides ADR-017 rename guidance in ExpectedIndex" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $orphan = $result.Orphans | Where-Object { $_.File -eq "skill-pr-001" }
            $orphan.ExpectedIndex | Should -Match "ADR-017"
            $orphan.ExpectedIndex | Should -Match "\{domain\}-\{description\}"
        }
    }

    Context "When multiple skill- prefixed orphans exist" {
        BeforeEach {
            $testStructure = @{
                "skills-test-index.md" = @"
| Keywords | File |
|----------|------|
| indexed | test-indexed |
"@
                "test-indexed.md" = "Valid indexed file"
                "skill-orphan-one.md" = "First orphan"
                "skill-orphan-two.md" = "Second orphan"
                "skill-orphan-three.md" = "Third orphan"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Detects all skill- prefixed orphans" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $skillOrphans = $result.Orphans | Where-Object { $_.Domain -eq "INVALID" }
            $skillOrphans | Should -HaveCount 3
        }

        It "All orphans have correct metadata" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            foreach ($orphan in ($result.Orphans | Where-Object { $_.Domain -eq "INVALID" })) {
                $orphan.ExpectedIndex | Should -Match "ADR-017"
            }
        }
    }

    Context "When domain-prefixed orphan exists alongside skill- orphan" {
        BeforeEach {
            $testStructure = @{
                "skills-test-index.md" = @"
| Keywords | File |
|----------|------|
| indexed | test-indexed |
"@
                "test-indexed.md" = "Valid indexed"
                "test-unindexed.md" = "Valid domain prefix but not indexed"
                "skill-legacy.md" = "Legacy skill- prefix"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Distinguishes skill- orphan from domain orphan" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json

            $skillOrphan = $result.Orphans | Where-Object { $_.File -eq "skill-legacy" }
            $domainOrphan = $result.Orphans | Where-Object { $_.File -eq "test-unindexed" }

            $skillOrphan.Domain | Should -Be "INVALID"
            $domainOrphan.Domain | Should -Be "test"
        }

        It "Provides different guidance for each orphan type" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json

            $skillOrphan = $result.Orphans | Where-Object { $_.File -eq "skill-legacy" }
            $domainOrphan = $result.Orphans | Where-Object { $_.File -eq "test-unindexed" }

            $skillOrphan.ExpectedIndex | Should -Match "ADR-017"
            $domainOrphan.ExpectedIndex | Should -Be "skills-test-index"
        }
    }

    Context "When no skill- prefixed files exist" {
        BeforeEach {
            $testStructure = @{
                "skills-clean-index.md" = @"
| Keywords | File |
|----------|------|
| clean domain | clean-skill |
"@
                "clean-skill.md" = "Valid"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Reports no INVALID domain orphans" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $invalidOrphans = $result.Orphans | Where-Object { $_.Domain -eq "INVALID" }
            $invalidOrphans | Should -BeNullOrEmpty
        }
    }

    Context "When skill- file is referenced in index (caught by Gap 1/2)" {
        BeforeEach {
            $testStructure = @{
                "skills-indexed-index.md" = @"
| Keywords | File |
|----------|------|
| indexed skill | skill-indexed-bad |
"@
                "skill-indexed-bad.md" = "Referenced but still bad naming"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Is NOT reported as orphan (file is indexed)" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $orphan = $result.Orphans | Where-Object { $_.File -eq "skill-indexed-bad" }
            $orphan | Should -BeNullOrEmpty
        }

        It "Is caught by Gap 1/2 naming validation instead" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.indexed.FileReferences.NamingViolations | Should -Contain "skill-indexed-bad"
        }
    }

    Context "When file starts with 'skillbook' not 'skill-'" {
        BeforeEach {
            $testStructure = @{
                "skills-skill-index.md" = @"
| Keywords | File |
|----------|------|
| indexed | skill-valid |
"@
                "skill-valid.md" = "Indexed"
                "skillbook-unindexed.md" = "Not skill- prefix"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Does not flag 'skillbook' as INVALID (not skill- prefix)" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $invalidOrphans = $result.Orphans | Where-Object { $_.Domain -eq "INVALID" }
            # skillbook-unindexed should NOT be in INVALID orphans
            ($invalidOrphans | Where-Object { $_.File -eq "skillbook-unindexed" }) | Should -BeNullOrEmpty
        }
    }

    Context "When skill- file exists in empty domain (no index)" {
        BeforeEach {
            $testStructure = @{
                "skill-no-domain.md" = "Orphan with no domain index at all"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Detects skill- orphan even without domain indices" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $orphan = $result.Orphans | Where-Object { $_.File -eq "skill-no-domain" }
            $orphan | Should -Not -BeNullOrEmpty
            $orphan.Domain | Should -Be "INVALID"
        }
    }
}

Describe "ADR-017 Pure Lookup Table Format Validation" {
    <#
    .SYNOPSIS
        Tests for enforcing pure lookup table format in domain index files
    .DESCRIPTION
        ADR-017 requires index files contain ONLY the keywords table.
        No titles, metadata, prose, or navigation sections allowed.
        This is a P0 requirement for token efficiency.
    #>

    BeforeEach {
        $testMemoryPath = Join-Path $testRoot "format-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
        New-Item -Path $testMemoryPath -ItemType Directory -Force | Out-Null
    }

    AfterEach {
        if (Test-Path $testMemoryPath) {
            Remove-Item -Path $testMemoryPath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Context "When index file is a pure lookup table" {
        BeforeEach {
            $testStructure = @{
                "skills-pure-index.md" = @"
| Keywords | File |
|----------|------|
| alpha beta gamma | pure-skill-one |
| delta epsilon | pure-skill-two |
"@
                "pure-skill-one.md" = "Content"
                "pure-skill-two.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Passes format validation" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.pure.IndexFormat.Passed | Should -Be $true
        }

        It "Has no format violations" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.pure.IndexFormat.Issues | Should -BeNullOrEmpty
        }

        It "Passes overall validation" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.pure.Passed | Should -Be $true
        }
    }

    Context "When index file has a title" {
        BeforeEach {
            $testStructure = @{
                "skills-titled-index.md" = @"
# Skills Index - Titled Domain

| Keywords | File |
|----------|------|
| alpha beta | titled-skill |
"@
                "titled-skill.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Fails format validation" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.titled.IndexFormat.Passed | Should -Be $false
        }

        It "Reports title as violation" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $issues = $result.DomainResults.titled.IndexFormat.Issues
            ($issues | Where-Object { $_ -match "Title detected" }) | Should -Not -BeNullOrEmpty
        }

        It "Reports line number of violation" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.titled.IndexFormat.ViolationLines | Should -Contain 1
        }

        It "Fails overall domain validation" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.titled.Passed | Should -Be $false
        }

        It "Returns exit code 1 in CI mode" {
            & $scriptPath -Path $testMemoryPath -CI 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 1
        }
    }

    Context "When index file has metadata blocks" {
        BeforeEach {
            $testStructure = @{
                "skills-meta-index.md" = @"
**Last Updated**: 2025-12-28
**Status**: Active

| Keywords | File |
|----------|------|
| alpha beta | meta-skill |
"@
                "meta-skill.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Fails format validation" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.meta.IndexFormat.Passed | Should -Be $false
        }

        It "Reports metadata block as violation" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $issues = $result.DomainResults.meta.IndexFormat.Issues
            ($issues | Where-Object { $_ -match "Metadata block detected" }) | Should -Not -BeNullOrEmpty
        }

        It "Reports all metadata lines" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.meta.IndexFormat.ViolationLines | Should -HaveCount 2
        }
    }

    Context "When index file has prose/explanatory text" {
        BeforeEach {
            $testStructure = @{
                "skills-prose-index.md" = @"
| Keywords | File |
|----------|------|
| alpha beta | prose-skill |

This index provides keyword-based routing to skills in the prose domain.
Use the keywords above to find the appropriate skill file.
"@
                "prose-skill.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Fails format validation" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.prose.IndexFormat.Passed | Should -Be $false
        }

        It "Reports non-table content as violation" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $issues = $result.DomainResults.prose.IndexFormat.Issues
            ($issues | Where-Object { $_ -match "Non-table content detected" }) | Should -Not -BeNullOrEmpty
        }
    }

    Context "When index file has navigation section" {
        BeforeEach {
            $testStructure = @{
                "skills-nav-index.md" = @"
Parent: memory-index

| Keywords | File |
|----------|------|
| alpha beta | nav-skill |
"@
                "nav-skill.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Fails format validation" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.nav.IndexFormat.Passed | Should -Be $false
        }

        It "Reports navigation section as violation" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $issues = $result.DomainResults.nav.IndexFormat.Issues
            ($issues | Where-Object { $_ -match "Navigation section detected" }) | Should -Not -BeNullOrEmpty
        }
    }

    Context "When index file has multiple violation types" {
        BeforeEach {
            $testStructure = @{
                "skills-multi-index.md" = @"
# Multi-Violation Index

**Status**: Active

| Keywords | File |
|----------|------|
| alpha beta | multi-skill |

This is some prose text that shouldn't be here.
"@
                "multi-skill.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Reports all violation types" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $issues = $result.DomainResults.multi.IndexFormat.Issues
            ($issues | Where-Object { $_ -match "Title detected" }) | Should -Not -BeNullOrEmpty
            ($issues | Where-Object { $_ -match "Metadata block detected" }) | Should -Not -BeNullOrEmpty
            ($issues | Where-Object { $_ -match "Non-table content detected" }) | Should -Not -BeNullOrEmpty
        }

        It "Reports all violation line numbers" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.multi.IndexFormat.ViolationLines.Count | Should -BeGreaterThan 2
        }
    }

    Context "When index file has empty lines between table rows" {
        BeforeEach {
            $testStructure = @{
                "skills-spaces-index.md" = @"
| Keywords | File |
|----------|------|
| alpha beta | spaces-skill-one |

| gamma delta | spaces-skill-two |
"@
                "spaces-skill-one.md" = "Content"
                "spaces-skill-two.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Allows empty lines between table rows" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.spaces.IndexFormat.Passed | Should -Be $true
        }
    }

    Context "When index file uses different heading levels" {
        BeforeEach {
            $testStructure = @{
                "skills-heading-index.md" = @"
## Secondary Heading

| Keywords | File |
|----------|------|
| alpha | heading-skill |
"@
                "heading-skill.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Detects any heading level as violation" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.heading.IndexFormat.Passed | Should -Be $false
            $issues = $result.DomainResults.heading.IndexFormat.Issues
            ($issues | Where-Object { $_ -match "Title detected" }) | Should -Not -BeNullOrEmpty
        }
    }
}

Describe "Edge Cases" {
    BeforeEach {
        $testMemoryPath = Join-Path $testRoot "edge-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
        New-Item -Path $testMemoryPath -ItemType Directory -Force | Out-Null
    }

    AfterEach {
        if (Test-Path $testMemoryPath) {
            Remove-Item -Path $testMemoryPath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Context "When keywords have mixed case" {
        BeforeEach {
            $testStructure = @{
                "skills-case-index.md" = @"
| Keywords | File |
|----------|------|
| Alpha BETA gamma | case-skill-one |
| ALPHA beta GAMMA | case-skill-two |
"@
                "case-skill-one.md" = "Content"
                "case-skill-two.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Treats keywords case-insensitively for density" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            # With case-insensitive matching, all 3 keywords overlap = 0% unique
            $result.DomainResults.case.KeywordDensity.Passed | Should -Be $false
        }
    }

    Context "When file names have special characters" {
        BeforeEach {
            $testStructure = @{
                "skills-special-index.md" = @"
| Keywords | File |
|----------|------|
| alpha | special-with-dashes |
| beta | special_with_underscores |
"@
                "special-with-dashes.md" = "Content"
                "special_with_underscores.md" = "Content"
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Handles file names with dashes" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.special.FileReferences.Passed | Should -Be $true
        }
    }

    Context "When index has only header and separator" {
        BeforeEach {
            $testStructure = @{
                "skills-headeronly-index.md" = @"
| Keywords | File |
|----------|------|
"@
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Reports zero entries for header-only index" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.headeronly.Entries | Should -Be 0
        }

        It "Passes validation with empty index" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.headeronly.Passed | Should -Be $true
        }
    }

    Context "When index files use markdown link syntax" {
        BeforeEach {
            $testStructure = @{
                "skills-markdown-links-index.md" = @"
| Keywords | File |
|----------|------|
| alpha beta | [link-test-1](link-test-1.md) |
| gamma delta | [link-test-2](link-test-2.md) |
"@
                "link-test-1.md" = "Content 1"
                "link-test-2.md" = "Content 2"
                "memory-index.md" = @"
| Task Keywords | Essential Memories |
|---------------|-------------------|
| test | [skills-markdown-links-index](skills-markdown-links-index.md) |
"@
            }
            New-TestMemoryStructure -BasePath $testMemoryPath -Structure $testStructure
        }

        It "Parses markdown links in domain index files correctly" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.DomainResults.'markdown-links'.FileReferences.Passed | Should -Be $true
            $result.DomainResults.'markdown-links'.FileReferences.ValidFiles.Count | Should -Be 2
            $result.DomainResults.'markdown-links'.FileReferences.MissingFiles.Count | Should -Be 0
        }

        It "Parses markdown links in memory-index.md correctly" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            $result.MemoryIndexResult.Passed | Should -Be $true
            $result.MemoryIndexResult.BrokenReferences.Count | Should -Be 0
        }

        It "Does not append duplicate .md extension" {
            $result = & $scriptPath -Path $testMemoryPath -Format "json" | ConvertFrom-Json
            # Should not have errors like "link-test-1.md.md"
            $result.DomainResults.'markdown-links'.FileReferences.Issues |
                Should -Not -Contain "Missing file: [link-test-1](link-test-1.md).md"
        }
    }
}
