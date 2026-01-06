<#
.SYNOPSIS
    Pester tests for SchemaValidation.psm1

.DESCRIPTION
    Unit tests for the schema validation module.
    Tests schema loading, caching, validation, and write operations.

.NOTES
    Task: Fix #821 (Episode extractor schema validation)
    Coverage Target: All 4 exported functions
#>

BeforeAll {
    $ModulePath = Join-Path $PSScriptRoot ".." "modules" "SchemaValidation.psm1"
    Import-Module $ModulePath -Force

    # Create test directory
    $script:TestDir = Join-Path ([System.IO.Path]::GetTempPath()) "SchemaValidation-Tests-$(Get-Random)"
    New-Item -Path $script:TestDir -ItemType Directory -Force | Out-Null

    # Create a minimal test schema
    $script:TestSchemaDir = Join-Path $script:TestDir "schemas"
    New-Item -Path $script:TestSchemaDir -ItemType Directory -Force | Out-Null

    $testSchema = @{
        '$schema' = "http://json-schema.org/draft-07/schema#"
        'type' = "object"
        'required' = @("id", "name", "items")
        'properties' = @{
            'id' = @{
                'type' = "string"
                'pattern' = "^test-\d+$"
            }
            'name' = @{
                'type' = "string"
            }
            'count' = @{
                'type' = "integer"
            }
            'active' = @{
                'type' = "boolean"
            }
            'status' = @{
                'type' = "string"
                'enum' = @("pending", "active", "complete")
            }
            'items' = @{
                'type' = "array"
            }
            'metadata' = @{
                'type' = "object"
            }
        }
    } | ConvertTo-Json -Depth 10

    $script:TestSchemaPath = Join-Path $script:TestSchemaDir "test.schema.json"
    Set-Content -Path $script:TestSchemaPath -Value $testSchema -Encoding UTF8
}

AfterAll {
    Remove-Module SchemaValidation -Force -ErrorAction SilentlyContinue
    if (Test-Path $script:TestDir) {
        Remove-Item $script:TestDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe "Get-SchemaPath" {
    BeforeEach {
        # Clear cache before each test
        Clear-SchemaCache
    }

    Context "Schema loading" {
        It "Loads schema file successfully" {
            $result = Get-SchemaPath -SchemaName "test" -SchemaDirectory $script:TestSchemaDir
            $result | Should -Be $script:TestSchemaPath
        }

        It "Caches schema path for reuse" {
            $first = Get-SchemaPath -SchemaName "test" -SchemaDirectory $script:TestSchemaDir
            $second = Get-SchemaPath -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $first | Should -Be $second
            $first | Should -Be $script:TestSchemaPath
        }

        It "Throws when schema file not found" {
            { Get-SchemaPath -SchemaName "nonexistent" -SchemaDirectory $script:TestSchemaDir } |
                Should -Throw "*Schema file not found*"
        }

        It "Uses git root for default directory" -Skip:(-not (git rev-parse --show-toplevel 2>$null)) {
            # This test only works when run from within a git repo
            $gitRoot = git rev-parse --show-toplevel
            $expectedPath = Join-Path $gitRoot ".claude" "skills" "memory" "resources" "schemas" "episode.schema.json"

            if (Test-Path $expectedPath) {
                $result = Get-SchemaPath -SchemaName "episode"
                $result | Should -Match "[\\/]episode\.schema\.json$"
            }
        }
    }

    Context "Error handling" {
        It "Throws when not in git repo and no directory provided" {
            # Save current directory
            $originalDir = Get-Location

            try {
                # Move to temp (not a git repo)
                Set-Location $script:TestDir
                { Get-SchemaPath -SchemaName "test" } | Should -Throw "*Cannot determine git root*"
            }
            finally {
                Set-Location $originalDir
            }
        }
    }
}

Describe "Test-SchemaValid" {
    Context "Valid data" {
        It "Validates valid data successfully" {
            $data = @{
                id = "test-123"
                name = "Test Item"
                items = @()
            }

            $result = Test-SchemaValid -JsonContent $data -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Valid | Should -BeTrue
            $result.Errors | Should -BeNullOrEmpty
        }

        It "Accepts data with all fields" {
            $data = @{
                id = "test-456"
                name = "Full Test"
                count = 10
                active = $true
                status = "active"
                items = @(1, 2, 3)
                metadata = @{ key = "value" }
            }

            $result = Test-SchemaValid -JsonContent $data -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Valid | Should -BeTrue
        }

        It "Accepts JSON string input" {
            $json = '{"id":"test-789","name":"JSON String","items":[]}'

            $result = Test-SchemaValid -JsonContent $json -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Valid | Should -BeTrue
        }
    }

    Context "Missing required fields" {
        It "Detects missing 'id' field" {
            $data = @{
                name = "Missing ID"
                items = @()
            }

            $result = Test-SchemaValid -JsonContent $data -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Valid | Should -BeFalse
            $result.Errors | Should -Contain "Missing required field: 'id'"
        }

        It "Detects missing 'items' array" {
            $data = @{
                id = "test-001"
                name = "Missing Items"
            }

            $result = Test-SchemaValid -JsonContent $data -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Valid | Should -BeFalse
            $result.Errors | Should -Contain "Missing required field: 'items'"
        }

        It "Reports multiple missing fields" {
            $data = @{
                name = "Only Name"
            }

            $result = Test-SchemaValid -JsonContent $data -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Valid | Should -BeFalse
            $result.Errors.Count | Should -BeGreaterOrEqual 2
        }
    }

    Context "Type validation" {
        It "Detects incorrect string type" {
            $data = @{
                id = 999  # Should be string and will also fail pattern
                name = "Test"
                items = @()
            }

            $result = Test-SchemaValid -JsonContent $data -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Valid | Should -BeFalse
            # Will catch either type error or pattern mismatch
            $result.Errors.Count | Should -BeGreaterThan 0
        }

        It "Detects incorrect integer type" {
            $data = @{
                id = "test-123"
                name = "Test"
                count = "not-a-number"  # Should be integer
                items = @()
            }

            $result = Test-SchemaValid -JsonContent $data -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Valid | Should -BeFalse
            $result.Errors | Should -Match "Field 'count' should be integer"
        }

        It "Detects incorrect boolean type" {
            $data = @{
                id = "test-123"
                name = "Test"
                active = "yes"  # Should be boolean
                items = @()
            }

            $result = Test-SchemaValid -JsonContent $data -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Valid | Should -BeFalse
            $result.Errors | Should -Match "Field 'active' should be boolean"
        }

        It "Detects null instead of array (regression test for #821)" {
            $data = @{
                id = "test-123"
                name = "Test"
                items = $null  # Should be array
            }

            $result = Test-SchemaValid -JsonContent $data -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Valid | Should -BeFalse
            $result.Errors | Should -Match "Field 'items' is null"
        }

        It "Detects scalar instead of array (regression test for #821)" {
            $data = @{
                id = "test-123"
                name = "Test"
                items = "single-item"  # Should be array
            }

            $result = Test-SchemaValid -JsonContent $data -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Valid | Should -BeFalse
            $result.Errors | Should -Match "Field 'items' should be array"
        }
    }

    Context "Constraint validation" {
        It "Detects enum violation" {
            $data = @{
                id = "test-123"
                name = "Test"
                status = "invalid-status"  # Not in enum
                items = @()
            }

            $result = Test-SchemaValid -JsonContent $data -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Valid | Should -BeFalse
            $result.Errors | Should -Match "Field 'status' value.*not in allowed values"
        }

        It "Detects pattern violation" {
            $data = @{
                id = "invalid-format"  # Should match ^test-\d+$
                name = "Test"
                items = @()
            }

            $result = Test-SchemaValid -JsonContent $data -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Valid | Should -BeFalse
            $result.Errors | Should -Match "Field 'id' value.*does not match pattern"
        }
    }

    Context "Error handling" {
        It "Handles invalid JSON string gracefully" {
            $invalidJson = '{"id":invalid json}'

            $result = Test-SchemaValid -JsonContent $invalidJson -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Valid | Should -BeFalse
            $result.Errors | Should -Match "Failed to parse JSON content"
        }

        It "Handles missing schema file" {
            $data = @{ id = "test-123"; name = "Test"; items = @() }

            $result = Test-SchemaValid -JsonContent $data -SchemaName "nonexistent" -SchemaDirectory $script:TestSchemaDir

            $result.Valid | Should -BeFalse
            $result.Errors | Should -Match "Failed to load schema"
        }
    }
}

Describe "Write-ValidatedJson" {
    BeforeEach {
        $script:OutputFile = Join-Path $script:TestDir "output-$(Get-Random).json"
    }

    AfterEach {
        if (Test-Path $script:OutputFile) {
            Remove-Item $script:OutputFile -Force
        }
    }

    Context "Successful writes" {
        It "Writes valid data to file" {
            $data = @{
                id = "test-123"
                name = "Test Item"
                items = @()
            }

            $result = Write-ValidatedJson -Data $data -FilePath $script:OutputFile -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Success | Should -BeTrue
            $result.FilePath | Should -Be $script:OutputFile
            Test-Path $script:OutputFile | Should -BeTrue
        }

        It "Creates valid JSON file" {
            $data = @{
                id = "test-456"
                name = "Valid JSON"
                items = @(1, 2, 3)
            }

            Write-ValidatedJson -Data $data -FilePath $script:OutputFile -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $content = Get-Content $script:OutputFile -Raw | ConvertFrom-Json
            $content.id | Should -Be "test-456"
            $content.items.Count | Should -Be 3
        }

        It "Overwrites file with -Force" {
            # Write first time
            $data1 = @{ id = "test-111"; name = "First"; items = @() }
            Write-ValidatedJson -Data $data1 -FilePath $script:OutputFile -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            # Overwrite with Force
            $data2 = @{ id = "test-222"; name = "Second"; items = @() }
            $result = Write-ValidatedJson -Data $data2 -FilePath $script:OutputFile -SchemaName "test" -SchemaDirectory $script:TestSchemaDir -Force

            $result.Success | Should -BeTrue
            $content = Get-Content $script:OutputFile -Raw | ConvertFrom-Json
            $content.id | Should -Be "test-222"
        }
    }

    Context "Validation failures" {
        It "Fails when data missing required fields" {
            $data = @{
                name = "Missing ID and items"
            }

            $result = Write-ValidatedJson -Data $data -FilePath $script:OutputFile -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Success | Should -BeFalse
            $result.ValidationResult.Valid | Should -BeFalse
            $result.ValidationResult.Errors | Should -Not -BeNullOrEmpty
            Test-Path $script:OutputFile | Should -BeFalse
        }

        It "Fails when data has wrong types" {
            $data = @{
                id = 123  # Should be string
                name = "Test"
                items = @()
            }

            $result = Write-ValidatedJson -Data $data -FilePath $script:OutputFile -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Success | Should -BeFalse
            Test-Path $script:OutputFile | Should -BeFalse
        }

        It "Fails when file exists without -Force" {
            # Create file
            $data = @{ id = "test-111"; name = "First"; items = @() }
            Write-ValidatedJson -Data $data -FilePath $script:OutputFile -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            # Try to write again without Force
            $result = Write-ValidatedJson -Data $data -FilePath $script:OutputFile -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            $result.Success | Should -BeFalse
            $result.ValidationResult.Errors | Should -Match "File already exists"
        }
    }

    Context "Regression tests for #821" {
        It "Preserves empty arrays in output" {
            $data = @{
                id = "test-999"  # Use valid pattern
                name = "Empty Arrays"
                items = @()  # Empty array
            }

            $result = Write-ValidatedJson -Data $data -FilePath $script:OutputFile -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            if (-not $result.Success) {
                Write-Host "Validation errors: $($result.ValidationResult.Errors -join ', ')"
            }
            $result.Success | Should -BeTrue

            # Read back and verify it's still an array
            $content = Get-Content $script:OutputFile -Raw | ConvertFrom-Json
            # Empty arrays should have count 0, not be null
            @($content.items).Count | Should -Be 0
        }

        It "Preserves single-element arrays in output" {
            $data = @{
                id = "test-888"  # Use valid pattern
                name = "Single Item Array"
                items = @("one-item")  # Single-element array
            }

            $result = Write-ValidatedJson -Data $data -FilePath $script:OutputFile -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

            if (-not $result.Success) {
                Write-Host "Validation errors: $($result.ValidationResult.Errors -join ', ')"
            }
            $result.Success | Should -BeTrue

            # Read back and verify it's still an array
            $content = Get-Content $script:OutputFile -Raw | ConvertFrom-Json
            # Single element should have count 1, not be a scalar
            @($content.items).Count | Should -Be 1
        }
    }
}

Describe "Clear-SchemaCache" {
    It "Clears the schema cache" {
        # Load a schema to populate cache
        Get-SchemaPath -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

        # Clear cache
        Clear-SchemaCache

        # Load again should work (cache was cleared)
        $result = Get-SchemaPath -SchemaName "test" -SchemaDirectory $script:TestSchemaDir
        $result | Should -Be $script:TestSchemaPath
    }
}

Describe "Integration Test" -Tag "Integration" {
    It "End-to-end: validate and write episode-like data" {
        $outputFile = Join-Path $script:TestDir "episode-integration-test.json"

        # Create episode-like data structure
        $data = @{
            id = "test-777"  # Use valid pattern
            name = "Integration Test Episode"
            status = "complete"
            items = @(
                @{ type = "event"; content = "First event" }
                @{ type = "event"; content = "Second event" }
            )
            metadata = @{
                created = (Get-Date).ToString("o")
                version = "1.0"
            }
        }

        $result = Write-ValidatedJson -Data $data -FilePath $outputFile -SchemaName "test" -SchemaDirectory $script:TestSchemaDir

        if (-not $result.Success) {
            Write-Host "Validation errors: $($result.ValidationResult.Errors -join ', ')"
        }
        $result.Success | Should -BeTrue
        Test-Path $outputFile | Should -BeTrue

        # Verify content
        $content = Get-Content $outputFile -Raw | ConvertFrom-Json
        $content.id | Should -Be "test-777"
        $content.items.Count | Should -Be 2

        # Cleanup
        Remove-Item $outputFile -Force
    }
}
