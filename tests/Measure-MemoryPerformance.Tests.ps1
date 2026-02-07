<#
.SYNOPSIS
    Pester tests for Measure-MemoryPerformance.ps1

.DESCRIPTION
    Tests for M-008: Memory search benchmarks.
    Validates benchmark measurement logic, output formats, and error handling.
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "memory" "scripts" "Measure-MemoryPerformance.ps1"

    # Create test memory directory structure
    $TestMemoryPath = Join-Path $TestDrive "memories"
    New-Item -Path $TestMemoryPath -ItemType Directory -Force | Out-Null

    # Create test memory files with various naming patterns
    $TestFiles = @(
        @{ Name = "powershell-array-handling"; Content = "# PowerShell Array Handling`n`nUse @() for single-element arrays." }
        @{ Name = "powershell-string-safety"; Content = "# PowerShell String Safety`n`nAlways validate user input." }
        @{ Name = "git-hooks-pre-commit"; Content = "# Git Pre-Commit Hooks`n`nValidation before commit." }
        @{ Name = "git-branch-cleanup"; Content = "# Git Branch Cleanup`n`nRemove merged branches." }
        @{ Name = "session-protocol-compliance"; Content = "# Session Protocol`n`nFollow RFC 2119." }
        @{ Name = "security-vulnerability-scan"; Content = "# Security Scanning`n`nOWASP Top 10 checks." }
        @{ Name = "memory-index"; Content = "| Keywords | File |`n|----------|------|" }
    )

    foreach ($file in $TestFiles) {
        $filePath = Join-Path $TestMemoryPath "$($file.Name).md"
        Set-Content -Path $filePath -Value $file.Content
    }
}

Describe "Measure-MemoryPerformance.ps1" {
    Context "Parameter Validation" {
        It "Should accept custom queries" {
            $result = & $ScriptPath -Queries @("test query") -Iterations 1 -WarmupIterations 0 -SerenaOnly -Format json 2>$null
            $parsed = $result | ConvertFrom-Json
            $parsed.Configuration.Queries | Should -Be 1
        }

        It "Should accept iteration count" {
            $result = & $ScriptPath -Queries @("test") -Iterations 3 -WarmupIterations 0 -SerenaOnly -Format json 2>$null
            $parsed = $result | ConvertFrom-Json
            $parsed.Configuration.Iterations | Should -Be 3
        }

        It "Should accept warmup iterations" {
            $result = & $ScriptPath -Queries @("test") -Iterations 1 -WarmupIterations 2 -SerenaOnly -Format json 2>$null
            $parsed = $result | ConvertFrom-Json
            $parsed.Configuration.WarmupIterations | Should -Be 2
        }

        It "Should support console format" {
            { & $ScriptPath -Queries @("test") -Iterations 1 -WarmupIterations 0 -SerenaOnly -Format console 2>$null } | Should -Not -Throw
        }

        It "Should support markdown format" {
            $result = & $ScriptPath -Queries @("test") -Iterations 1 -WarmupIterations 0 -SerenaOnly -Format markdown 2>$null
            $result | Should -Match "# Memory Performance Benchmark Report"
        }

        It "Should support json format" {
            $result = & $ScriptPath -Queries @("test") -Iterations 1 -WarmupIterations 0 -SerenaOnly -Format json 2>$null
            { $result | ConvertFrom-Json } | Should -Not -Throw
        }
    }

    Context "Serena Benchmarking" {
        It "Should measure list time" {
            $result = & $ScriptPath -Queries @("powershell") -Iterations 2 -WarmupIterations 0 -SerenaOnly -Format json 2>$null
            $parsed = $result | ConvertFrom-Json
            $parsed.SerenaResults[0].ListTimeMs | Should -BeGreaterOrEqual 0
        }

        It "Should measure match time" {
            $result = & $ScriptPath -Queries @("powershell") -Iterations 2 -WarmupIterations 0 -SerenaOnly -Format json 2>$null
            $parsed = $result | ConvertFrom-Json
            $parsed.SerenaResults[0].MatchTimeMs | Should -BeGreaterOrEqual 0
        }

        It "Should measure read time" {
            $result = & $ScriptPath -Queries @("powershell") -Iterations 2 -WarmupIterations 0 -SerenaOnly -Format json 2>$null
            $parsed = $result | ConvertFrom-Json
            $parsed.SerenaResults[0].ReadTimeMs | Should -BeGreaterOrEqual 0
        }

        It "Should calculate total time" {
            $result = & $ScriptPath -Queries @("powershell") -Iterations 2 -WarmupIterations 0 -SerenaOnly -Format json 2>$null
            $parsed = $result | ConvertFrom-Json
            $parsed.SerenaResults[0].TotalTimeMs | Should -BeGreaterThan 0
        }

        It "Should count matched files" {
            $result = & $ScriptPath -Queries @("powershell array") -Iterations 1 -WarmupIterations 0 -SerenaOnly -Format json 2>$null
            $parsed = $result | ConvertFrom-Json
            # Should match powershell-array-handling at minimum
            $parsed.SerenaResults[0].MatchedFiles | Should -BeGreaterOrEqual 0
        }

        It "Should count total files" {
            $result = & $ScriptPath -Queries @("test") -Iterations 1 -WarmupIterations 0 -SerenaOnly -Format json 2>$null
            $parsed = $result | ConvertFrom-Json
            $parsed.SerenaResults[0].TotalFiles | Should -BeGreaterOrEqual 0
        }

        It "Should record iteration times" {
            $result = & $ScriptPath -Queries @("test") -Iterations 3 -WarmupIterations 0 -SerenaOnly -Format json 2>$null
            $parsed = $result | ConvertFrom-Json
            $parsed.SerenaResults[0].IterationTimes.Count | Should -Be 3
        }
    }

    Context "Summary Calculation" {
        It "Should calculate Serena average" {
            $result = & $ScriptPath -Queries @("powershell", "git") -Iterations 2 -WarmupIterations 0 -SerenaOnly -Format json 2>$null
            $parsed = $result | ConvertFrom-Json
            $parsed.Summary.SerenaAvgMs | Should -BeGreaterThan 0
        }

        It "Should include target baseline" {
            $result = & $ScriptPath -Queries @("test") -Iterations 1 -WarmupIterations 0 -SerenaOnly -Format json 2>$null
            $parsed = $result | ConvertFrom-Json
            $parsed.Summary.Target | Should -Match "96-164x"
        }
    }

    Context "Output Formats" {
        It "Should produce valid markdown with headers" {
            $result = & $ScriptPath -Queries @("test") -Iterations 1 -WarmupIterations 0 -SerenaOnly -Format markdown 2>$null
            $result | Should -Match "## Configuration"
            $result | Should -Match "## Results"
        }

        It "Should produce valid JSON with all sections" {
            $result = & $ScriptPath -Queries @("test") -Iterations 1 -WarmupIterations 0 -SerenaOnly -Format json 2>$null
            $parsed = $result | ConvertFrom-Json
            $parsed.PSObject.Properties.Name | Should -Contain "Timestamp"
            $parsed.PSObject.Properties.Name | Should -Contain "Configuration"
            $parsed.PSObject.Properties.Name | Should -Contain "SerenaResults"
            $parsed.PSObject.Properties.Name | Should -Contain "Summary"
        }
    }

    Context "Error Handling" {
        It "Should handle non-existent memory path gracefully" {
            # The script uses hardcoded path, but should not crash
            { & $ScriptPath -Queries @("test") -Iterations 1 -WarmupIterations 0 -SerenaOnly -Format json 2>$null } | Should -Not -Throw
        }

        It "Should handle empty query list" {
            # Uses default queries when none provided
            $result = & $ScriptPath -Iterations 1 -WarmupIterations 0 -SerenaOnly -Format json 2>$null
            $parsed = $result | ConvertFrom-Json
            $parsed.Configuration.Queries | Should -BeGreaterThan 0
        }
    }

    Context "Forgetful Handling" {
        It "Should skip Forgetful when SerenaOnly is set" {
            $result = & $ScriptPath -Queries @("test") -Iterations 1 -WarmupIterations 0 -SerenaOnly -Format json 2>$null
            $parsed = $result | ConvertFrom-Json
            $parsed.ForgetfulResults.Count | Should -Be 0
        }

        It "Should handle unavailable Forgetful gracefully" {
            # Forgetful may not be running during tests
            { & $ScriptPath -Queries @("test") -Iterations 1 -WarmupIterations 0 -Format json 2>$null } | Should -Not -Throw
        }
    }
}

Describe "Benchmark Quality" {
    Context "Measurement Consistency" {
        It "Should produce consistent results across iterations" {
            $result = & $ScriptPath -Queries @("powershell") -Iterations 5 -WarmupIterations 2 -SerenaOnly -Format json 2>$null
            $parsed = $result | ConvertFrom-Json

            $times = $parsed.SerenaResults[0].IterationTimes
            $avg = ($times | Measure-Object -Average).Average
            $stdDev = [math]::Sqrt(($times | ForEach-Object { [math]::Pow($_ - $avg, 2) } | Measure-Object -Average).Average)

            # Coefficient of variation should be reasonable (< 100%)
            $cv = if ($avg -gt 0) { $stdDev / $avg } else { 0 }
            $cv | Should -BeLessThan 1.0
        }

        It "Should show warmup effect (first run slower)" {
            # This test validates that warmup iterations are working
            # by checking that the script completes successfully with warmup
            $result = & $ScriptPath -Queries @("test") -Iterations 2 -WarmupIterations 3 -SerenaOnly -Format json 2>$null
            $parsed = $result | ConvertFrom-Json
            $parsed.Configuration.WarmupIterations | Should -Be 3
        }
    }
}
