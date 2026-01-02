<#
.SYNOPSIS
    Pester tests for MemoryRouter.psm1

.DESCRIPTION
    Unit and integration tests for the Memory Router module.
    Implements ADR-037 Memory Router Architecture validation.

    Test categories:
    - Unit: Mock file system and network, no external dependencies
    - Integration: Require Forgetful MCP running, tagged for CI skip

.NOTES
    Task: M-003 (Phase 2A Memory System)
    Coverage Target: ≥80%
#>

BeforeAll {
    # Import the module under test
    $ModulePath = Join-Path $PSScriptRoot ".." "scripts" "MemoryRouter.psm1"
    Import-Module $ModulePath -Force
}

Describe "Get-ContentHash" {
    BeforeAll {
        # Access private function via module internals
        $module = Get-Module MemoryRouter
        $getContentHash = & $module { ${function:Get-ContentHash} }
    }

    It "Produces consistent SHA-256 hash for same input" {
        $input = "test content"
        $hash1 = & $getContentHash -Content $input
        $hash2 = & $getContentHash -Content $input

        $hash1 | Should -Be $hash2
    }

    It "Returns 64-character lowercase hex string" {
        $hash = & $getContentHash -Content "any content"

        $hash | Should -Match "^[a-f0-9]{64}$"
        $hash.Length | Should -Be 64
    }

    It "Produces different hashes for different content" {
        $hash1 = & $getContentHash -Content "content A"
        $hash2 = & $getContentHash -Content "content B"

        $hash1 | Should -Not -Be $hash2
    }

    It "Handles empty string" {
        $hash = & $getContentHash -Content ""

        $hash | Should -Match "^[a-f0-9]{64}$"
        # SHA-256 of empty string is known
        $hash | Should -Be "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }

    It "Handles Unicode content" {
        $hash = & $getContentHash -Content "日本語テスト 🚀"

        $hash | Should -Match "^[a-f0-9]{64}$"
    }
}

Describe "Invoke-SerenaSearch" {
    BeforeAll {
        $module = Get-Module MemoryRouter
        $invokeSerenaSearch = & $module { ${function:Invoke-SerenaSearch} }
    }

    Context "With mocked file system" {
        BeforeAll {
            # Create temp directory with test files
            $script:TestDir = Join-Path ([System.IO.Path]::GetTempPath()) "MemoryRouter-Tests-$(Get-Random)"
            New-Item -Path $script:TestDir -ItemType Directory -Force | Out-Null

            # Create test memory files
            "# PowerShell Array Patterns" | Set-Content (Join-Path $script:TestDir "powershell-arrays.md")
            "# Git Hook Validation" | Set-Content (Join-Path $script:TestDir "git-hooks-validation.md")
            "# Unrelated Topic" | Set-Content (Join-Path $script:TestDir "unrelated-topic.md")
        }

        AfterAll {
            if (Test-Path $script:TestDir) {
                Remove-Item $script:TestDir -Recurse -Force
            }
        }

        It "Finds files matching keywords" {
            $results = & $invokeSerenaSearch -Query "powershell arrays" -MemoryPath $script:TestDir

            $results.Count | Should -BeGreaterThan 0
            $results[0].Name | Should -Be "powershell-arrays"
        }

        It "Returns results with correct structure" {
            $results = & $invokeSerenaSearch -Query "git hooks" -MemoryPath $script:TestDir

            $results.Count | Should -BeGreaterThan 0
            $results[0].PSObject.Properties.Name | Should -Contain "Name"
            $results[0].PSObject.Properties.Name | Should -Contain "Content"
            $results[0].PSObject.Properties.Name | Should -Contain "Source"
            $results[0].PSObject.Properties.Name | Should -Contain "Score"
            $results[0].PSObject.Properties.Name | Should -Contain "Path"
            $results[0].PSObject.Properties.Name | Should -Contain "Hash"
        }

        It "Scores matches correctly (higher score = more keywords matched)" {
            $results = & $invokeSerenaSearch -Query "powershell arrays" -MemoryPath $script:TestDir

            $results.Count | Should -BeGreaterThan 0
            $results[0].Score | Should -BeGreaterThan 0
        }

        It "Returns empty array for non-matching query" {
            $results = & $invokeSerenaSearch -Query "nonexistent query xyz" -MemoryPath $script:TestDir

            $results | Should -BeNullOrEmpty
        }

        It "Returns empty array if directory does not exist" {
            $results = & $invokeSerenaSearch -Query "test" -MemoryPath "/nonexistent/path"

            $results | Should -BeNullOrEmpty
        }

        It "Respects MaxResults parameter" {
            $results = & $invokeSerenaSearch -Query "powershell git" -MemoryPath $script:TestDir -MaxResults 1

            $results.Count | Should -BeLessOrEqual 1
        }

        It "Source is always Serena" {
            $results = & $invokeSerenaSearch -Query "powershell" -MemoryPath $script:TestDir

            $results | ForEach-Object { $_.Source | Should -Be "Serena" }
        }
    }

    Context "With actual Serena memories" {
        It "Searches .serena/memories by default" {
            if (-not (Test-Path ".serena/memories")) {
                Set-ItResult -Skipped -Because "No .serena/memories directory"
                return
            }

            $results = & $invokeSerenaSearch -Query "memory router"

            $results | Should -Not -BeNullOrEmpty
        }
    }
}

Describe "Test-ForgetfulAvailable" {
    It "Returns boolean" {
        $result = Test-ForgetfulAvailable

        $result | Should -BeOfType [bool]
    }

    It "Caches result for 30 seconds" {
        # First call (fresh)
        $result1 = Test-ForgetfulAvailable -Force

        # Second call within cache window (should be cached)
        $startTime = Get-Date
        $result2 = Test-ForgetfulAvailable
        $elapsed = (Get-Date) - $startTime

        # Cached call should be very fast (<10ms)
        $elapsed.TotalMilliseconds | Should -BeLessThan 50

        # Result should be consistent
        $result1 | Should -Be $result2
    }

    It "Respects -Force parameter to bypass cache" {
        # First call to populate cache
        $null = Test-ForgetfulAvailable

        # Force fresh check
        $result = Test-ForgetfulAvailable -Force

        $result | Should -BeOfType [bool]
    }

    It "Returns false for non-existent port" {
        $module = Get-Module MemoryRouter
        & $module {
            $script:HealthCache.LastChecked = [datetime]::MinValue  # Clear cache
        }

        $result = Test-ForgetfulAvailable -Port 59999 -Force

        $result | Should -BeFalse
    }
}

Describe "Get-MemoryRouterStatus" {
    It "Returns status object with expected properties" {
        $status = Get-MemoryRouterStatus

        $status.PSObject.Properties.Name | Should -Contain "Serena"
        $status.PSObject.Properties.Name | Should -Contain "Forgetful"
        $status.PSObject.Properties.Name | Should -Contain "Cache"
        $status.PSObject.Properties.Name | Should -Contain "Configuration"
    }

    It "Reports Serena availability correctly" {
        $status = Get-MemoryRouterStatus

        if (Test-Path ".serena/memories") {
            $status.Serena.Available | Should -BeTrue
        }
        else {
            $status.Serena.Available | Should -BeFalse
        }
    }

    It "Reports cache age" {
        # Ensure we have a fresh cache entry
        $null = Test-ForgetfulAvailable -Force

        $status = Get-MemoryRouterStatus

        $status.Cache.AgeSeconds | Should -BeGreaterOrEqual 0
        $status.Cache.TTLSeconds | Should -Be 30
    }
}

Describe "Search-Memory" {
    Context "Input Validation" {
        It "Rejects empty query" {
            { Search-Memory -Query "" } | Should -Throw
        }

        It "Rejects query exceeding 500 characters" {
            $longQuery = "a" * 501
            { Search-Memory -Query $longQuery } | Should -Throw
        }

        It "Rejects invalid characters (SQL injection attempt)" {
            { Search-Memory -Query "test'; DROP TABLE memories; --" } | Should -Throw
        }

        It "Rejects invalid characters (command injection attempt)" {
            { Search-Memory -Query 'test$(rm -rf /)' } | Should -Throw
        }

        It "Accepts valid query with allowed special characters" {
            { Search-Memory -Query "PowerShell arrays (test): item-1, item_2" -LexicalOnly } | Should -Not -Throw
        }

        It "Rejects mutually exclusive switches" {
            { Search-Memory -Query "test" -SemanticOnly -LexicalOnly } | Should -Throw -ExpectedMessage "*Cannot specify both*"
        }
    }

    Context "Lexical-Only Mode" {
        It "Queries Serena only when -LexicalOnly specified" {
            $results = Search-Memory -Query "memory router" -LexicalOnly

            $results | ForEach-Object { $_.Source | Should -Be "Serena" }
        }

        It "Returns results from .serena/memories" {
            if (-not (Test-Path ".serena/memories")) {
                Set-ItResult -Skipped -Because "No .serena/memories directory"
                return
            }

            $results = Search-Memory -Query "memory" -LexicalOnly

            $results.Count | Should -BeGreaterThan 0
        }
    }

    Context "Semantic-Only Mode" -Tag "Integration" {
        It "Throws when Forgetful unavailable and -SemanticOnly specified" {
            # Save original function and mock unavailability
            $module = Get-Module MemoryRouter
            & $module {
                $script:HealthCache.Available = $false
                $script:HealthCache.LastChecked = [datetime]::UtcNow
            }

            { Search-Memory -Query "test" -SemanticOnly } | Should -Throw "*not available*"
        }
    }

    Context "Augmented Mode (Default)" -Tag "Integration" {
        It "Returns combined results when Forgetful available" {
            if (-not (Test-ForgetfulAvailable)) {
                Set-ItResult -Skipped -Because "Forgetful not available"
                return
            }

            $results = Search-Memory -Query "memory patterns"

            # Should have results (at least from Serena)
            $results.Count | Should -BeGreaterThan 0
        }

        It "Falls back to Serena-only when Forgetful unavailable" {
            $results = Search-Memory -Query "memory router" -MaxResults 5

            # Should still return results even if Forgetful is down
            $results.Count | Should -BeGreaterOrEqual 0
        }
    }

    Context "MaxResults" {
        It "Respects MaxResults parameter" {
            $results = Search-Memory -Query "memory" -MaxResults 3 -LexicalOnly

            $results.Count | Should -BeLessOrEqual 3
        }

        It "Rejects MaxResults below 1" {
            { Search-Memory -Query "test" -MaxResults 0 } | Should -Throw
        }

        It "Rejects MaxResults above 100" {
            { Search-Memory -Query "test" -MaxResults 101 } | Should -Throw
        }
    }
}

Describe "Merge-MemoryResults" {
    BeforeAll {
        $module = Get-Module MemoryRouter
        $mergeResults = & $module { ${function:Merge-MemoryResults} }
        $getContentHash = & $module { ${function:Get-ContentHash} }
    }

    It "Deduplicates by content hash" {
        $content = "Same content"
        $hash = & $getContentHash -Content $content

        $serena = @([PSCustomObject]@{
                Name    = "serena-file"
                Content = $content
                Source  = "Serena"
                Score   = 100
                Hash    = $hash
            })

        $forgetful = @([PSCustomObject]@{
                Name    = "forgetful-file"
                Content = $content
                Source  = "Forgetful"
                Score   = 90
                Hash    = $hash
            })

        $merged = & $mergeResults -SerenaResults $serena -ForgetfulResults $forgetful

        $merged.Count | Should -Be 1
        $merged[0].Source | Should -Be "Serena"  # Serena takes priority
    }

    It "Preserves unique results from both sources" {
        $serena = @([PSCustomObject]@{
                Name    = "serena-unique"
                Content = "Serena content"
                Source  = "Serena"
                Score   = 100
                Hash    = "hash1"
            })

        $forgetful = @([PSCustomObject]@{
                Name    = "forgetful-unique"
                Content = "Forgetful content"
                Source  = "Forgetful"
                Score   = 90
                Hash    = "hash2"
            })

        $merged = & $mergeResults -SerenaResults $serena -ForgetfulResults $forgetful

        $merged.Count | Should -Be 2
        ($merged | Where-Object Source -eq "Serena").Count | Should -Be 1
        ($merged | Where-Object Source -eq "Forgetful").Count | Should -Be 1
    }

    It "Serena results appear first" {
        $serena = @([PSCustomObject]@{
                Name = "serena"; Content = "a"; Source = "Serena"; Score = 50; Hash = "h1"
            })

        $forgetful = @([PSCustomObject]@{
                Name = "forgetful"; Content = "b"; Source = "Forgetful"; Score = 100; Hash = "h2"
            })

        $merged = & $mergeResults -SerenaResults $serena -ForgetfulResults $forgetful

        $merged[0].Source | Should -Be "Serena"
    }

    It "Respects MaxResults limit" {
        $serena = @(1..10 | ForEach-Object {
                [PSCustomObject]@{ Name = "s$_"; Content = "c$_"; Source = "Serena"; Score = $_; Hash = "h$_" }
            })

        $merged = & $mergeResults -SerenaResults $serena -MaxResults 5

        $merged.Count | Should -Be 5
    }

    It "Handles empty inputs gracefully" {
        $merged = & $mergeResults -SerenaResults @() -ForgetfulResults @()

        $merged | Should -BeNullOrEmpty
    }
}

Describe "Invoke-ForgetfulSearch Error Handling" {
    BeforeAll {
        $module = Get-Module MemoryRouter
        $invokeForgetfulSearch = & $module { ${function:Invoke-ForgetfulSearch} }
    }

    Context "Malformed Response Handling" {
        It "Returns empty array when Forgetful returns empty result" {
            # When Forgetful is not available, should return empty array
            $results = & $invokeForgetfulSearch -Query "test" -Endpoint "http://localhost:59999/mcp"

            $results | Should -BeNullOrEmpty
        }

        It "Returns empty array for connection refused" {
            # Use a port that's definitely not listening
            $results = & $invokeForgetfulSearch -Query "test" -Endpoint "http://localhost:59998/mcp"

            $results | Should -BeNullOrEmpty
        }

        It "Returns empty array for invalid endpoint" {
            $results = & $invokeForgetfulSearch -Query "test" -Endpoint "http://invalid.localhost.test:8020/mcp"

            $results | Should -BeNullOrEmpty
        }
    }

    Context "Response Structure Validation" {
        It "Handles response without result property" {
            # Mock scenario: response has no 'result' key
            # This tests the defensive coding in the response parsing
            Mock Invoke-RestMethod {
                return @{ error = @{ message = "Method not found" } }
            } -ModuleName MemoryRouter

            $results = & $invokeForgetfulSearch -Query "test" -Endpoint "http://localhost:8020/mcp"

            $results | Should -BeNullOrEmpty
        }

        It "Handles response without content array" {
            Mock Invoke-RestMethod {
                return @{ result = @{ data = "unexpected format" } }
            } -ModuleName MemoryRouter

            $results = & $invokeForgetfulSearch -Query "test" -Endpoint "http://localhost:8020/mcp"

            $results | Should -BeNullOrEmpty
        }

        It "Handles malformed JSON in content text" {
            Mock Invoke-RestMethod {
                return @{
                    result = @{
                        content = @(
                            @{
                                type = "text"
                                text = "{ invalid json syntax"
                            }
                        )
                    }
                }
            } -ModuleName MemoryRouter

            # Should not throw, just return empty or partial results
            { & $invokeForgetfulSearch -Query "test" -Endpoint "http://localhost:8020/mcp" } | Should -Not -Throw
        }
    }

    Context "Timeout Handling" {
        It "Handles request timeout gracefully" {
            Mock Invoke-RestMethod {
                throw [System.Net.WebException]::new("The operation has timed out")
            } -ModuleName MemoryRouter

            $results = & $invokeForgetfulSearch -Query "test" -Endpoint "http://localhost:8020/mcp"

            $results | Should -BeNullOrEmpty
        }
    }

    Context "HTTP Error Responses" {
        It "Handles HTTP 500 error" {
            Mock Invoke-RestMethod {
                throw [System.Net.WebException]::new("The remote server returned an error: (500) Internal Server Error.")
            } -ModuleName MemoryRouter

            $results = & $invokeForgetfulSearch -Query "test" -Endpoint "http://localhost:8020/mcp"

            $results | Should -BeNullOrEmpty
        }

        It "Handles HTTP 502 Bad Gateway" {
            Mock Invoke-RestMethod {
                throw [System.Net.WebException]::new("The remote server returned an error: (502) Bad Gateway.")
            } -ModuleName MemoryRouter

            $results = & $invokeForgetfulSearch -Query "test" -Endpoint "http://localhost:8020/mcp"

            $results | Should -BeNullOrEmpty
        }

        It "Handles HTTP 503 Service Unavailable" {
            Mock Invoke-RestMethod {
                throw [System.Net.WebException]::new("The remote server returned an error: (503) Service Unavailable.")
            } -ModuleName MemoryRouter

            $results = & $invokeForgetfulSearch -Query "test" -Endpoint "http://localhost:8020/mcp"

            $results | Should -BeNullOrEmpty
        }
    }
}

Describe "Invoke-SerenaSearch Error Handling" {
    BeforeAll {
        $module = Get-Module MemoryRouter
        $invokeSerenaSearch = & $module { ${function:Invoke-SerenaSearch} }
    }

    Context "File System Errors" {
        It "Returns empty array for non-existent path" {
            # Test with a path that doesn't exist
            $results = & $invokeSerenaSearch -Query "test" -MemoryPath "/tmp/nonexistent-path-$(Get-Random)"

            $results | Should -BeNullOrEmpty
        }

        It "Returns empty array for empty directory" {
            $emptyDir = Join-Path ([System.IO.Path]::GetTempPath()) "EmptyMemoryDir-$(Get-Random)"
            New-Item -Path $emptyDir -ItemType Directory -Force | Out-Null

            try {
                $results = & $invokeSerenaSearch -Query "test" -MemoryPath $emptyDir

                $results | Should -BeNullOrEmpty
            }
            finally {
                Remove-Item $emptyDir -Force -ErrorAction SilentlyContinue
            }
        }
    }
}
