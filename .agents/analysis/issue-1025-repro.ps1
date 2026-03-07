#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Repro case for Issue #1025: Path traversal StartsWith vulnerability

.DESCRIPTION
    Demonstrates how the current StartsWith check can be bypassed using
    prefix-based directory attacks (e.g., /allowed/dir-evil bypasses /allowed/dir)

.NOTES
    CWE-22: Improper Limitation of a Pathname to a Restricted Directory
    Attack Vector: Directory prefix collision
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "Issue #1025: Path Traversal StartsWith Vulnerability Repro" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""

# Simulate the vulnerable code from templates/agents/security.shared.md:644
function Test-VulnerableCode {
    param(
        [string]$MemoriesDir,
        [string]$UserInput
    )

    $MemoriesDirFull = [System.IO.Path]::GetFullPath($MemoriesDir)
    $OutputFile = [System.IO.Path]::GetFullPath((Join-Path $MemoriesDirFull $UserInput))

    # VULNERABLE: No directory separator appended
    $isValid = $OutputFile.StartsWith($MemoriesDirFull, [System.StringComparison]::OrdinalIgnoreCase)

    return @{
        MemoriesDir = $MemoriesDirFull
        OutputFile = $OutputFile
        IsValid = $isValid
    }
}

# Simulate the FIXED code with directory separator
function Test-FixedCode {
    param(
        [string]$MemoriesDir,
        [string]$UserInput
    )

    $MemoriesDirFull = [System.IO.Path]::GetFullPath($MemoriesDir)
    $OutputFile = [System.IO.Path]::GetFullPath((Join-Path $MemoriesDirFull $UserInput))

    # FIXED: Append directory separator before StartsWith check
    $MemoriesDirWithSep = $MemoriesDirFull + [System.IO.Path]::DirectorySeparatorChar
    $isValid = $OutputFile.StartsWith($MemoriesDirWithSep, [System.StringComparison]::OrdinalIgnoreCase)

    return @{
        MemoriesDir = $MemoriesDirFull
        MemoriesDirWithSep = $MemoriesDirWithSep
        OutputFile = $OutputFile
        IsValid = $isValid
    }
}

# Test cases
$testCases = @(
    @{
        Name = "LEGITIMATE: File in allowed directory"
        MemoriesDir = "/tmp/memories"
        UserInput = "secret.txt"
        ExpectedVulnerable = $true
        ExpectedFixed = $true
    },
    @{
        Name = "LEGITIMATE: Nested file in allowed directory"
        MemoriesDir = "/tmp/memories"
        UserInput = "subdir/secret.txt"
        ExpectedVulnerable = $true
        ExpectedFixed = $true
    },
    @{
        Name = "ATTACK: Prefix-based directory escape"
        MemoriesDir = "/tmp/memories"
        UserInput = "../memories-evil/malicious.txt"
        ExpectedVulnerable = $true   # BUG: Should be $false
        ExpectedFixed = $false       # Correctly blocked
    },
    @{
        Name = "ATTACK: Adjacent directory with same prefix"
        MemoriesDir = "/tmp/allowed"
        UserInput = "../allowed-evil/steal.txt"
        ExpectedVulnerable = $true   # BUG: Should be $false
        ExpectedFixed = $false       # Correctly blocked
    },
    @{
        Name = "LEGITIMATE: Path traversal correctly blocked by GetFullPath"
        MemoriesDir = "/tmp/memories"
        UserInput = "../../etc/passwd"
        ExpectedVulnerable = $false  # GetFullPath resolves .. sequences
        ExpectedFixed = $false
    }
)

$vulnerableFailures = 0
$fixedFailures = 0

foreach ($test in $testCases) {
    Write-Host ""
    Write-Host "Test: $($test.Name)" -ForegroundColor Yellow
    Write-Host "-" * 60

    # Test vulnerable code
    $vulnResult = Test-VulnerableCode -MemoriesDir $test.MemoriesDir -UserInput $test.UserInput
    $vulnStatus = if ($vulnResult.IsValid -eq $test.ExpectedVulnerable) { "PASS" } else { "FAIL"; $vulnerableFailures++ }
    $vulnColor = if ($vulnStatus -eq "PASS") { "Green" } else { "Red" }

    Write-Host "  Vulnerable Code:" -ForegroundColor White
    Write-Host "    Base Dir:   $($vulnResult.MemoriesDir)"
    Write-Host "    Output:     $($vulnResult.OutputFile)"
    Write-Host "    Allowed:    $($vulnResult.IsValid)"
    Write-Host "    Expected:   $($test.ExpectedVulnerable)"
    Write-Host "    Status:     [$vulnStatus]" -ForegroundColor $vulnColor

    # Test fixed code
    $fixedResult = Test-FixedCode -MemoriesDir $test.MemoriesDir -UserInput $test.UserInput
    $fixedStatus = if ($fixedResult.IsValid -eq $test.ExpectedFixed) { "PASS" } else { "FAIL"; $fixedFailures++ }
    $fixedColor = if ($fixedStatus -eq "PASS") { "Green" } else { "Red" }

    Write-Host "  Fixed Code:" -ForegroundColor White
    Write-Host "    Base Dir:   $($fixedResult.MemoriesDirWithSep)"
    Write-Host "    Output:     $($fixedResult.OutputFile)"
    Write-Host "    Allowed:    $($fixedResult.IsValid)"
    Write-Host "    Expected:   $($test.ExpectedFixed)"
    Write-Host "    Status:     [$fixedStatus]" -ForegroundColor $fixedColor
}

Write-Host ""
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "SUMMARY" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""
Write-Host "Vulnerable Code: $($testCases.Count - $vulnerableFailures)/$($testCases.Count) tests passed"
Write-Host "Fixed Code:      $($testCases.Count - $fixedFailures)/$($testCases.Count) tests passed"
Write-Host ""

if ($vulnerableFailures -gt 0) {
    Write-Host "VULNERABILITY CONFIRMED: Vulnerable code incorrectly allows attack paths" -ForegroundColor Red
    Write-Host ""
    Write-Host "The vulnerability occurs because:" -ForegroundColor Yellow
    Write-Host '  1. StartsWith("/tmp/memories") returns true for "/tmp/memories-evil/file.txt"'
    Write-Host "  2. The attacker creates a sibling directory with the same prefix"
    Write-Host "  3. Using '../memories-evil/file.txt' as input, GetFullPath resolves to '/tmp/memories-evil/file.txt'"
    Write-Host "  4. This path starts with '/tmp/memories' (string match) but is OUTSIDE the directory"
    Write-Host ""
    Write-Host "FIX: Append directory separator before comparison:" -ForegroundColor Green
    Write-Host '  $MemoriesDirFull + [System.IO.Path]::DirectorySeparatorChar'
    Write-Host '  Now StartsWith("/tmp/memories/") returns FALSE for "/tmp/memories-evil/file.txt"'
    exit 1
} else {
    Write-Host "All tests passed - vulnerability NOT confirmed" -ForegroundColor Green
    exit 0
}
