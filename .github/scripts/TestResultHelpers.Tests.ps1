#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for TestResultHelpers module.

.DESCRIPTION
    Tests the New-SkippedTestResult function for generating JUnit XML files
    when tests are skipped in CI workflows.
#>

BeforeAll {
    # Import the module under test
    $modulePath = Join-Path $PSScriptRoot "TestResultHelpers.psm1"
    Import-Module $modulePath -Force
}

Describe "New-SkippedTestResult" {
    BeforeEach {
        # Create a temporary directory for test outputs
        $script:testDir = Join-Path ([System.IO.Path]::GetTempPath()) "TestResultHelpers_$(Get-Random)"
        New-Item -Path $script:testDir -ItemType Directory -Force | Out-Null
    }

    AfterEach {
        # Cleanup temporary directory
        if (Test-Path -Path $script:testDir) {
            Remove-Item -Path $script:testDir -Recurse -Force
        }
    }

    Context "File Creation" {
        It "Creates the output file at the specified path" {
            $outputPath = Join-Path $script:testDir "results.xml"

            $result = New-SkippedTestResult -OutputPath $outputPath

            $result | Should -Not -BeNullOrEmpty
            Test-Path -Path $outputPath | Should -BeTrue
        }

        It "Creates parent directories if they do not exist" {
            $outputPath = Join-Path $script:testDir "nested/subdir/results.xml"

            $result = New-SkippedTestResult -OutputPath $outputPath

            Test-Path -Path $outputPath | Should -BeTrue
        }

        It "Returns a FileInfo object" {
            $outputPath = Join-Path $script:testDir "results.xml"

            $result = New-SkippedTestResult -OutputPath $outputPath

            $result | Should -BeOfType [System.IO.FileInfo]
            $result.Name | Should -Be "results.xml"
        }

        It "Overwrites existing file" {
            $outputPath = Join-Path $script:testDir "results.xml"
            "existing content" | Out-File -FilePath $outputPath

            New-SkippedTestResult -OutputPath $outputPath

            $content = Get-Content -Path $outputPath -Raw
            $content | Should -Not -Match "existing content"
            $content | Should -Match "testsuites"
        }
    }

    Context "XML Content" {
        It "Produces valid XML" {
            $outputPath = Join-Path $script:testDir "results.xml"

            New-SkippedTestResult -OutputPath $outputPath

            $content = Get-Content -Path $outputPath -Raw
            { [xml]$content } | Should -Not -Throw
        }

        It "Contains correct XML declaration" {
            $outputPath = Join-Path $script:testDir "results.xml"

            New-SkippedTestResult -OutputPath $outputPath

            $content = Get-Content -Path $outputPath -Raw
            $content | Should -Match '^\s*<\?xml version="1\.0" encoding="utf-8"\?>'
        }

        It "Contains testsuites element with zero counts" {
            $outputPath = Join-Path $script:testDir "results.xml"

            New-SkippedTestResult -OutputPath $outputPath

            [xml]$xml = Get-Content -Path $outputPath
            $xml.testsuites.tests | Should -Be "0"
            $xml.testsuites.failures | Should -Be "0"
            $xml.testsuites.errors | Should -Be "0"
            $xml.testsuites.time | Should -Be "0"
        }

        It "Contains testsuite element with zero counts" {
            $outputPath = Join-Path $script:testDir "results.xml"

            New-SkippedTestResult -OutputPath $outputPath

            [xml]$xml = Get-Content -Path $outputPath
            $xml.testsuites.testsuite.tests | Should -Be "0"
            $xml.testsuites.testsuite.failures | Should -Be "0"
            $xml.testsuites.testsuite.errors | Should -Be "0"
            $xml.testsuites.testsuite.time | Should -Be "0"
        }

        It "Uses default TestSuiteName when not specified" {
            $outputPath = Join-Path $script:testDir "results.xml"

            New-SkippedTestResult -OutputPath $outputPath

            [xml]$xml = Get-Content -Path $outputPath
            $xml.testsuites.testsuite.name | Should -Be "Tests (Skipped)"
        }

        It "Uses custom TestSuiteName when specified" {
            $outputPath = Join-Path $script:testDir "results.xml"

            New-SkippedTestResult -OutputPath $outputPath -TestSuiteName "Pester Tests (Skipped)"

            [xml]$xml = Get-Content -Path $outputPath
            $xml.testsuites.testsuite.name | Should -Be "Pester Tests (Skipped)"
        }

        It "Uses default SkipReason when not specified" {
            $outputPath = Join-Path $script:testDir "results.xml"

            New-SkippedTestResult -OutputPath $outputPath

            $content = Get-Content -Path $outputPath -Raw
            $content | Should -Match "No testable files changed - tests skipped"
        }

        It "Uses custom SkipReason when specified" {
            $outputPath = Join-Path $script:testDir "results.xml"

            New-SkippedTestResult -OutputPath $outputPath -SkipReason "Custom skip reason"

            $content = Get-Content -Path $outputPath -Raw
            $content | Should -Match "Custom skip reason"
        }

        It "Escapes double-hyphen in SkipReason for XML comment compliance" {
            $outputPath = Join-Path $script:testDir "results.xml"

            New-SkippedTestResult -OutputPath $outputPath -SkipReason "Test--reason--with--hyphens"

            $content = Get-Content -Path $outputPath -Raw
            # XML comments forbid "--" sequence within content; should be escaped to "- -"
            # The escaped content should appear, proving double-hyphens were replaced
            $content | Should -Match 'Test- -reason- -with- -hyphens'
            # Original unescaped content should NOT appear
            $content | Should -Not -Match 'Test--reason'
            # Verify still valid XML
            { [xml]$content } | Should -Not -Throw
        }
    }

    Context "Parameter Validation" {
        It "Throws when OutputPath is null" {
            { New-SkippedTestResult -OutputPath $null } | Should -Throw
        }

        It "Throws when OutputPath is empty" {
            { New-SkippedTestResult -OutputPath "" } | Should -Throw
        }

        It "Throws when TestSuiteName is empty" {
            $outputPath = Join-Path $script:testDir "results.xml"
            { New-SkippedTestResult -OutputPath $outputPath -TestSuiteName "" } | Should -Throw
        }

        It "Throws when SkipReason is empty" {
            $outputPath = Join-Path $script:testDir "results.xml"
            { New-SkippedTestResult -OutputPath $outputPath -SkipReason "" } | Should -Throw
        }
    }

    Context "Real-world Usage Patterns" {
        It "Matches expected Pester skip output format" {
            $outputPath = Join-Path $script:testDir "pester-results.xml"

            New-SkippedTestResult `
                -OutputPath $outputPath `
                -TestSuiteName "Pester Tests (Skipped)" `
                -SkipReason "No testable files changed - tests skipped"

            $content = Get-Content -Path $outputPath -Raw
            $content | Should -Match 'name="Pester Tests \(Skipped\)"'
            $content | Should -Match "No testable files changed - tests skipped"
        }

        It "Matches expected PSScriptAnalyzer skip output format" {
            $outputPath = Join-Path $script:testDir "psscriptanalyzer-results.xml"

            New-SkippedTestResult `
                -OutputPath $outputPath `
                -TestSuiteName "PSScriptAnalyzer (Skipped)" `
                -SkipReason "No PowerShell files changed - analysis skipped"

            $content = Get-Content -Path $outputPath -Raw
            $content | Should -Match 'name="PSScriptAnalyzer \(Skipped\)"'
            $content | Should -Match "No PowerShell files changed - analysis skipped"
        }
    }
}
