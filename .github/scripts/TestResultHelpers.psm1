<#
.SYNOPSIS
    Helper functions for test result generation in CI workflows.

.DESCRIPTION
    PowerShell module containing utility functions for generating test result
    XML files in CI workflows. Used when tests are skipped but required status
    checks need a valid result file.

.NOTES
    Import this module in workflow scripts:
        Import-Module .github/scripts/TestResultHelpers.psm1

    Related:
        - ADR-006: Thin workflows, testable modules
        - ADR-005: PowerShell-only scripting
#>

function New-SkippedTestResult {
    <#
    .SYNOPSIS
        Creates an empty JUnit XML file for skipped test runs.

    .DESCRIPTION
        Generates a valid JUnit XML result file indicating tests were skipped.
        This is used when no testable files changed but required status checks
        still need a valid test result artifact.

    .PARAMETER OutputPath
        Path to the output XML file. Parent directories will be created if needed.

    .PARAMETER TestSuiteName
        Name of the test suite to use in the XML output.
        Defaults to "Tests (Skipped)".

    .PARAMETER SkipReason
        Comment text explaining why tests were skipped.
        Defaults to "No testable files changed - tests skipped".

    .EXAMPLE
        New-SkippedTestResult -OutputPath "./artifacts/pester-results.xml" -TestSuiteName "Pester Tests (Skipped)"

    .EXAMPLE
        New-SkippedTestResult -OutputPath "./artifacts/psscriptanalyzer-results.xml" -TestSuiteName "PSScriptAnalyzer (Skipped)" -SkipReason "No PowerShell files changed - analysis skipped"

    .OUTPUTS
        System.IO.FileInfo
        Returns the FileInfo object for the created file.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    [OutputType([System.IO.FileInfo])]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$OutputPath,

        [Parameter()]
        [ValidateNotNullOrEmpty()]
        [string]$TestSuiteName = "Tests (Skipped)",

        [Parameter()]
        [ValidateNotNullOrEmpty()]
        [string]$SkipReason = "No testable files changed - tests skipped"
    )

    # Generate JUnit XML content
    $xmlContent = @"
<?xml version="1.0" encoding="utf-8"?>
<testsuites tests="0" failures="0" errors="0" time="0">
  <testsuite name="$TestSuiteName" tests="0" failures="0" errors="0" time="0">
    <!-- $SkipReason -->
  </testsuite>
</testsuites>
"@

    if ($PSCmdlet.ShouldProcess($OutputPath, "Create skipped test result XML")) {
        # Ensure output directory exists
        $parentDir = Split-Path -Path $OutputPath -Parent
        if ($parentDir -and -not (Test-Path -Path $parentDir)) {
            New-Item -Path $parentDir -ItemType Directory -Force | Out-Null
        }

        # Write to file with UTF-8 encoding (no BOM for compatibility)
        $xmlContent | Out-File -FilePath $OutputPath -Encoding utf8NoBOM -Force

        # Return the created file info
        Get-Item -Path $OutputPath
    }
}

Export-ModuleMember -Function New-SkippedTestResult
