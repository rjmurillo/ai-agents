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
| alpha | skill-with-dashes |
| beta | skill_with_underscores |
"@
                "skill-with-dashes.md" = "Content"
                "skill_with_underscores.md" = "Content"
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
}
