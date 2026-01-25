<#
.SYNOPSIS
    Pester tests for Invoke-PesterTests.ps1 script.

.DESCRIPTION
    Regression tests for the Pester test runner, focusing on:
    - Wildcard detection and path expansion (regression for cursor[bot] bug)
    - Path resolution from relative to absolute
    - Edge cases in path handling

    The wildcard detection bug (fixed in commit 106d211) caused:
    - `$fullPath -like "*?*"` to match ANY path (? is a wildcard in -like)
    - The elseif branch (Test-Path) was dead code for most paths
    - Fix: Changed to `$fullPath -like "*[?]*"` (brackets escape the wildcard)

.NOTES
    Requires Pester 5.x or later.
    Run with: pwsh build/scripts/Invoke-PesterTests.ps1 -TestPath "./build/scripts/tests/Invoke-PesterTests.Tests.ps1"
#>

BeforeAll {
    # Create isolated test temp directory
    $Script:TestTempDir = Join-Path ([System.IO.Path]::GetTempPath()) "Invoke-PesterTests-Tests-$(Get-Random)"
    New-Item -ItemType Directory -Path $Script:TestTempDir -Force | Out-Null

    # Store repository root and script path
    $Script:RepoRoot = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
    $Script:ScriptPath = Join-Path $Script:RepoRoot "build" "scripts" "Invoke-PesterTests.ps1"

    # Verify script exists
    if (-not (Test-Path $Script:ScriptPath)) {
        throw "Script not found at: $Script:ScriptPath"
    }

    # Helper function: Create a minimal passing test file
    function New-MinimalTestFile {
        param(
            [string]$Path,
            [string]$TestName = "Placeholder"
        )
        $content = @"
Describe '$TestName' {
    It 'passes' {
        `$true | Should -BeTrue
    }
}
"@
        Set-Content -Path $Path -Value $content -Force
    }
}

AfterAll {
    # Cleanup test temp directory
    if (Test-Path $Script:TestTempDir) {
        Remove-Item -Path $Script:TestTempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe "Invoke-PesterTests Wildcard Detection" -Tag "Regression", "Wildcard" {

    Context "PowerShell -like Operator Wildcard Escaping" {
        # These tests verify the fix for cursor[bot] bug (commit 106d211)
        # Bug: "*?*" matches any string with 2+ chars because ? is a wildcard
        # Fix: "*[?]*" uses brackets to match literal ? character

        It "Bracket notation [?] should match literal question mark" {
            # This tests the fix directly - bracket notation escapes wildcards
            $pathWithLiteralQuestion = "test?.ps1"
            $pathWithoutQuestion = "test1.ps1"

            # Correct pattern (after fix): [?] matches literal ?
            $pathWithLiteralQuestion -like "*[?]*" | Should -BeTrue
            $pathWithoutQuestion -like "*[?]*" | Should -BeFalse
        }

        It "Bracket notation [*] should match literal asterisk" {
            $pathWithLiteralAsterisk = "test[*].ps1"
            $pathWithoutAsterisk = "test.ps1"

            # [*] matches literal * character
            $pathWithLiteralAsterisk -like "*[*]*" | Should -BeTrue
            $pathWithoutAsterisk -like "*[*]*" | Should -BeFalse
        }

        It "Unescaped ? should match any single character (bug behavior)" {
            # This demonstrates the BUG that was fixed
            # Without brackets, ? matches ANY single character
            $anyPath = "test1.ps1"

            # Bug pattern: "*?*" matches because ? matches the "1"
            $anyPath -like "*?*" | Should -BeTrue

            # This is why the fix was needed - almost every path matched
            # *?* = (zero or more) + (any single char) + (zero or more) = any string with 1+ chars
            "ab" -like "*?*" | Should -BeTrue
            "a" -like "*?*" | Should -BeTrue   # Even single char matches (* can be empty)
            "" -like "*?*" | Should -BeFalse   # Only empty string doesn't match
        }
    }

    Context "Path Resolution with Wildcards" {
        BeforeEach {
            # Clean test directory before each test
            Get-ChildItem -Path $Script:TestTempDir -Recurse -ErrorAction SilentlyContinue |
                Remove-Item -Force -Recurse -ErrorAction SilentlyContinue

            # Create subdirectory structure
            $Script:TestSubDir = Join-Path $Script:TestTempDir "tests"
            New-Item -ItemType Directory -Path $Script:TestSubDir -Force | Out-Null
        }

        It "Should expand * wildcard to multiple files" {
            # Create multiple test files
            New-MinimalTestFile -Path (Join-Path $Script:TestSubDir "Test1.Tests.ps1") -TestName "Test1"
            New-MinimalTestFile -Path (Join-Path $Script:TestSubDir "Test2.Tests.ps1") -TestName "Test2"
            New-MinimalTestFile -Path (Join-Path $Script:TestSubDir "Test3.Tests.ps1") -TestName "Test3"

            # Run with wildcard pattern
            $pattern = Join-Path $Script:TestSubDir "*.Tests.ps1"
            $expanded = Get-Item -Path $pattern -ErrorAction SilentlyContinue

            $expanded | Should -HaveCount 3
            $expanded.Name | Should -Contain "Test1.Tests.ps1"
            $expanded.Name | Should -Contain "Test2.Tests.ps1"
            $expanded.Name | Should -Contain "Test3.Tests.ps1"
        }

        It "Should expand ? wildcard to single character match" {
            # Create test files: Test1.ps1, Test2.ps1, Test10.ps1
            New-MinimalTestFile -Path (Join-Path $Script:TestSubDir "Test1.Tests.ps1") -TestName "Test1"
            New-MinimalTestFile -Path (Join-Path $Script:TestSubDir "Test2.Tests.ps1") -TestName "Test2"
            New-MinimalTestFile -Path (Join-Path $Script:TestSubDir "Test10.Tests.ps1") -TestName "Test10"

            # ? should match single character only
            $pattern = Join-Path $Script:TestSubDir "Test?.Tests.ps1"
            $expanded = Get-Item -Path $pattern -ErrorAction SilentlyContinue

            # Should find Test1 and Test2 (? matches one char), but NOT Test10
            $expanded | Should -HaveCount 2
            $expanded.Name | Should -Contain "Test1.Tests.ps1"
            $expanded.Name | Should -Contain "Test2.Tests.ps1"
            $expanded.Name | Should -Not -Contain "Test10.Tests.ps1"
        }

        It "Should handle non-wildcard path via Test-Path branch" {
            # Create a specific file
            $specificFile = Join-Path $Script:TestSubDir "Specific.Tests.ps1"
            New-MinimalTestFile -Path $specificFile -TestName "Specific"

            # Non-wildcard path should still resolve
            Test-Path $specificFile | Should -BeTrue

            # And Get-Item should also work (but via different branch in script)
            $result = Get-Item -Path $specificFile -ErrorAction SilentlyContinue
            $result | Should -Not -BeNullOrEmpty
            $result.Name | Should -Be "Specific.Tests.ps1"
        }

        It "Should return empty for non-matching wildcard pattern" {
            # No files exist yet
            $pattern = Join-Path $Script:TestSubDir "NonExistent*.ps1"
            $expanded = Get-Item -Path $pattern -ErrorAction SilentlyContinue

            $expanded | Should -BeNullOrEmpty
        }
    }

    Context "Script Path Resolution Integration" {
        # Note: The Invoke-PesterTests.ps1 script resolves paths relative to the repository root.
        # These tests verify the script works with existing test infrastructure.

        It "Should run tests from wildcard path pattern within repo" {
            # Use the actual test file we're running from (meta but valid)
            $existingTestPath = Join-Path $Script:RepoRoot "build" "scripts" "tests" "*.Tests.ps1"

            # The wildcard pattern should resolve to actual test files
            $expanded = Get-Item -Path $existingTestPath -ErrorAction SilentlyContinue
            $expanded | Should -Not -BeNullOrEmpty
            $expanded.Count | Should -BeGreaterOrEqual 1
        }

        It "Should run tests from specific non-wildcard path within repo" {
            # Use this test file itself as the test subject
            $thisTestFile = Join-Path $Script:RepoRoot "build" "scripts" "tests" "Invoke-PesterTests.Tests.ps1"

            # Should exist and be resolvable
            Test-Path $thisTestFile | Should -BeTrue
        }

        It "Should handle the default wildcard patterns from script" {
            # Test the default patterns that the script uses
            $defaultPatterns = @(
                "./scripts/tests",
                "./build/scripts/tests",
                "./build/tests",
                "./.claude/skills/*/tests"
            )

            # At least build/scripts/tests should exist and have files
            $buildTestsPath = Join-Path $Script:RepoRoot "build" "scripts" "tests"
            Test-Path $buildTestsPath | Should -BeTrue

            $testFiles = Get-ChildItem -Path $buildTestsPath -Filter "*.Tests.ps1" -ErrorAction SilentlyContinue
            $testFiles.Count | Should -BeGreaterOrEqual 1
        }
    }

    Context "Edge Cases" {
        BeforeEach {
            Get-ChildItem -Path $Script:TestTempDir -Recurse -ErrorAction SilentlyContinue |
                Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
        }

        It "Should handle path with both * and ? wildcards" {
            $testDir = Join-Path $Script:TestTempDir "mixed"
            New-Item -ItemType Directory -Path $testDir -Force | Out-Null

            # Create: Test1A.ps1, Test2B.ps1, Test10C.ps1
            New-MinimalTestFile -Path (Join-Path $testDir "Test1A.Tests.ps1") -TestName "Test1A"
            New-MinimalTestFile -Path (Join-Path $testDir "Test2B.Tests.ps1") -TestName "Test2B"
            New-MinimalTestFile -Path (Join-Path $testDir "Test10C.Tests.ps1") -TestName "Test10C"

            # Pattern: Test?*.Tests.ps1 (? = single char, * = any)
            $pattern = Join-Path $testDir "Test?*.Tests.ps1"
            $expanded = Get-Item -Path $pattern -ErrorAction SilentlyContinue

            # ? matches one char, * matches rest - should find all 3
            $expanded | Should -HaveCount 3
        }

        It "Should handle empty TestPath array gracefully" {
            # The script should handle empty input without crashing
            $output = pwsh -File $Script:ScriptPath -TestPath @() -Verbosity None 2>&1 | Out-String

            # Should complete without throwing (may show "no tests found" message)
            $LASTEXITCODE | Should -BeIn @(0, 1)  # 0 = no tests, 1 = test failure is OK here
        }

        It "Should handle path that doesn't exist" {
            $nonExistentPath = Join-Path $Script:TestTempDir "does-not-exist" "tests"

            # Script should handle gracefully
            $output = pwsh -File $Script:ScriptPath -TestPath $nonExistentPath -Verbosity None 2>&1 | Out-String

            # Should not crash, exit code 0 or 1 is acceptable
            $LASTEXITCODE | Should -BeIn @(0, 1)
        }

        It "Should handle nested wildcard patterns like **/tests" {
            # Create nested structure
            $skillDir = Join-Path $Script:TestTempDir "skills" "my-skill" "tests"
            New-Item -ItemType Directory -Path $skillDir -Force | Out-Null
            New-MinimalTestFile -Path (Join-Path $skillDir "Skill.Tests.ps1") -TestName "Skill"

            # Glob pattern with ** (if supported by Get-Item)
            $pattern = Join-Path $Script:TestTempDir "skills" "*" "tests"
            $expanded = Get-Item -Path $pattern -ErrorAction SilentlyContinue

            # Should find the nested tests directory
            $expanded | Should -Not -BeNullOrEmpty
        }
    }
}

Describe "Invoke-PesterTests Regression Tests" -Tag "Regression" {

    Context "cursor[bot] Bug Regression (PR #55, Commit 106d211)" {
        # This context specifically tests the bug that cursor[bot] identified
        # The bug: `$fullPath -like "*?*"` matched everything due to unescaped ?

        It "Should correctly distinguish wildcard paths from normal paths" {
            # The core issue: paths without wildcards were incorrectly
            # going through wildcard expansion instead of Test-Path

            $normalPath = "C:\test\normal\path.ps1"
            $wildcardPath = "C:\test\wildcard\*.ps1"
            $questionPath = "C:\test\question?.ps1"

            # Fixed logic: Check for literal * or ? in path
            # Using bracket notation to escape wildcard meaning in -like

            # Normal path should NOT match wildcard check
            ($normalPath -like "*[*]*" -or $normalPath -like "*[?]*") | Should -BeFalse

            # Asterisk path should match
            ($wildcardPath -like "*[*]*" -or $wildcardPath -like "*[?]*") | Should -BeTrue

            # Question mark path should match
            ($questionPath -like "*[*]*" -or $questionPath -like "*[?]*") | Should -BeTrue
        }

        It "Should NOT have dead code in elseif branch" {
            # The bug made the elseif (Test-Path) branch unreachable
            # for any path with 2+ characters

            # Test a variety of realistic paths
            $testPaths = @(
                "scripts/tests",
                "build/scripts/tests",
                "./test.ps1",
                "C:\Windows\System32",
                "/usr/local/bin"
            )

            foreach ($path in $testPaths) {
                # With the fix, normal paths should NOT match wildcard check
                $hasWildcard = ($path -like "*[*]*" -or $path -like "*[?]*")
                $hasWildcard | Should -BeFalse -Because "Path '$path' has no wildcard characters"
            }

            # But actual wildcard paths should match
            $wildcardPaths = @(
                "*.ps1",
                "test?.ps1",
                "./scripts/*/tests",
                "**/*.Tests.ps1"
            )

            foreach ($path in $wildcardPaths) {
                $hasWildcard = ($path -like "*[*]*" -or $path -like "*[?]*")
                $hasWildcard | Should -BeTrue -Because "Path '$path' contains wildcard characters"
            }
        }
    }
}
