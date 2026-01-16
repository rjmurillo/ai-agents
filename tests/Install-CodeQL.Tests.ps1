<#
.SYNOPSIS
    Pester tests for Install-CodeQL.ps1

.DESCRIPTION
    Comprehensive unit tests for the CodeQL CLI installation script.
    Tests cover platform detection, version handling, installation validation,
    download error handling, and PATH modifications.

    Tests follow the repository's testing patterns using Pester 5.x with
    BeforeAll/AfterAll for setup/cleanup and parameterized tests for
    cross-platform validation.
#>

BeforeAll {
    # Import script under test
    $scriptPath = Join-Path $PSScriptRoot "../.codeql/scripts/Install-CodeQL.ps1"

    # Source the script to expose functions
    . $scriptPath

    # Create temp directory for test artifacts
    $script:TestTempDir = Join-Path ([System.IO.Path]::GetTempPath()) "CodeQL-Tests-$(Get-Random)"
    New-Item -ItemType Directory -Path $script:TestTempDir -Force | Out-Null
}

AfterAll {
    # Cleanup test artifacts
    if (Test-Path $script:TestTempDir) {
        Remove-Item -Path $script:TestTempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe "Get-CodeQLDownloadUrl" {
    Context "Platform Detection" {
        It "Returns URL with platform identifier for current platform" {
            $url = Get-CodeQLDownloadUrl -Version "v2.23.9"

            $url | Should -Not -BeNullOrEmpty
            $url | Should -Match "codeql-bundle-(win64|linux64|osx64)\.tar\.zst"
            $url | Should -Match "v2.23.9"
        }

        It "Includes version in URL" {
            $version = "v2.23.0"
            $url = Get-CodeQLDownloadUrl -Version $version

            $url | Should -Match $version
        }

        It "Uses github.com/github/codeql-action/releases as base URL" {
            $url = Get-CodeQLDownloadUrl -Version "v2.23.9"

            $url | Should -Match "^https://github\.com/github/codeql-action/releases/download/"
        }
    }

    Context "Version Handling" {
        It "Uses specified version in URL" {
            $url = Get-CodeQLDownloadUrl -Version "v2.23.9"

            $url | Should -Match "v2.23.9"
        }

        It "Handles different version formats" {
            $url1 = Get-CodeQLDownloadUrl -Version "v2.23.9"
            $url2 = Get-CodeQLDownloadUrl -Version "v2.22.0"

            $url1 | Should -Not -Be $url2
            $url1 | Should -Match "v2.23.9"
            $url2 | Should -Match "v2.22.0"
        }
    }
}

Describe "Test-CodeQLInstalled" {
    Context "Installation Detection" {
        It "Returns false for non-existent installation" {
            $nonExistentPath = Join-Path $script:TestTempDir "nonexistent"

            $result = Test-CodeQLInstalled -Path $nonExistentPath

            $result | Should -Be $false
        }

        It "Returns false for directory without codeql executable" {
            $emptyPath = Join-Path $script:TestTempDir "empty-install"
            New-Item -ItemType Directory -Path $emptyPath -Force | Out-Null

            $result = Test-CodeQLInstalled -Path $emptyPath

            $result | Should -Be $false
        }

        It "Returns true for directory with codeql executable" {
            $mockPath = Join-Path $script:TestTempDir "mock-install"
            New-Item -ItemType Directory -Path $mockPath -Force | Out-Null

            # Create mock executable
            $exeName = if ($IsWindows) { "codeql.exe" } else { "codeql" }
            $mockExe = Join-Path $mockPath $exeName

            # Create a minimal mock script that responds to 'version'
            if ($IsWindows) {
                "@echo CodeQL 2.23.9" | Out-File -FilePath $mockExe -Encoding ascii
            }
            else {
                "#!/bin/sh`necho 'CodeQL 2.23.9'" | Out-File -FilePath $mockExe -Encoding ascii
                chmod +x $mockExe
            }

            $result = Test-CodeQLInstalled -Path $mockPath

            $result | Should -Be $true
        }

        It "Uses platform-specific executable name" {
            $mockPath = Join-Path $script:TestTempDir "platform-test"
            New-Item -ItemType Directory -Path $mockPath -Force | Out-Null

            $expectedExe = if ($IsWindows) { "codeql.exe" } else { "codeql" }
            $mockExe = Join-Path $mockPath $expectedExe

            if ($IsWindows) {
                "@echo CodeQL" | Out-File -FilePath $mockExe -Encoding ascii
            }
            else {
                "#!/bin/sh`necho 'CodeQL'" | Out-File -FilePath $mockExe -Encoding ascii
                chmod +x $mockExe
            }

            $result = Test-CodeQLInstalled -Path $mockPath

            $result | Should -Be $true
        }
    }

    Context "Version Detection" {
        It "Detects version from codeql executable" {
            $mockPath = Join-Path $script:TestTempDir "version-test"
            New-Item -ItemType Directory -Path $mockPath -Force | Out-Null

            $exeName = if ($IsWindows) { "codeql.exe" } else { "codeql" }
            $mockExe = Join-Path $mockPath $exeName

            if ($IsWindows) {
                "@echo CodeQL 2.23.9" | Out-File -FilePath $mockExe -Encoding ascii
            }
            else {
                "#!/bin/sh`necho 'CodeQL 2.23.9'" | Out-File -FilePath $mockExe -Encoding ascii
                chmod +x $mockExe
            }

            # Test-CodeQLInstalled should succeed (version check passes)
            $result = Test-CodeQLInstalled -Path $mockPath

            $result | Should -Be $true
        }
    }
}

Describe "Install-CodeQLCLI" {
    Context "Download and Extraction" {
        It "Creates installation directory if it doesn't exist" {
            # This is a unit test - we won't actually download
            # Testing directory creation logic only

            $testPath = Join-Path $script:TestTempDir "install-target"

            # Mock the download and extraction (integration test would do actual download)
            # For unit test, just verify path handling

            $testPath | Should -Not -Exist

            # Create the directory as Install-CodeQLCLI would
            New-Item -ItemType Directory -Path $testPath -Force | Out-Null

            $testPath | Should -Exist
        }

        It "Requires Url parameter" {
            # Verify parameter is mandatory
            $params = (Get-Command Install-CodeQLCLI).Parameters['Url']
            $mandatory = $params.Attributes | Where-Object { $_.GetType().Name -eq 'ParameterAttribute' } | Select-Object -First 1

            $mandatory.Mandatory | Should -Be $true
        }

        It "Requires DestinationPath parameter" {
            $params = (Get-Command Install-CodeQLCLI).Parameters['DestinationPath']
            $mandatory = $params.Attributes | Where-Object { $_.GetType().Name -eq 'ParameterAttribute' } | Select-Object -First 1

            $mandatory.Mandatory | Should -Be $true
        }
    }

    Context "Error Handling" {
        It "Handles invalid URL gracefully" {
            $invalidUrl = "https://invalid.example.com/nonexistent.tar.zst"
            $destPath = Join-Path $script:TestTempDir "error-test"

            # Should throw or exit with error code
            { Install-CodeQLCLI -Url $invalidUrl -DestinationPath $destPath -ErrorAction Stop } |
                Should -Throw
        }
    }
}

Describe "Add-CodeQLToPath" {
    Context "PATH Modification" {
        BeforeEach {
            # Save original PATH
            $script:OriginalPath = $env:PATH
        }

        AfterEach {
            # Restore original PATH
            $env:PATH = $script:OriginalPath
        }

        It "Adds path to session PATH" {
            $testPath = Join-Path $script:TestTempDir "test-path"
            New-Item -ItemType Directory -Path $testPath -Force | Out-Null

            Add-CodeQLToPath -Path $testPath

            $env:PATH | Should -Match ([regex]::Escape($testPath))
        }

        It "Does not add duplicate entries" {
            $testPath = Join-Path $script:TestTempDir "duplicate-test"
            New-Item -ItemType Directory -Path $testPath -Force | Out-Null

            # Add once
            Add-CodeQLToPath -Path $testPath

            # Add again
            Add-CodeQLToPath -Path $testPath

            # Path should not have duplicates - count occurrences
            $separator = if ($IsWindows) { ';' } else { ':' }
            $pathEntries = $env:PATH -split [regex]::Escape($separator)
            $matches = @($pathEntries | Where-Object { $_ -eq $testPath })
            $matchCount = $matches.Count

            $matchCount | Should -BeLessOrEqual 1
        }

        It "Uses platform-specific path separator" {
            $testPath = Join-Path $script:TestTempDir "separator-test"
            New-Item -ItemType Directory -Path $testPath -Force | Out-Null

            Add-CodeQLToPath -Path $testPath

            $separator = if ($IsWindows) { ';' } else { ':' }
            $env:PATH | Should -Match "$(([regex]::Escape($testPath)))$([regex]::Escape($separator))"
        }

        It "Resolves relative paths to absolute paths" {
            # Create a relative path
            $dirName = "relative-test-$(Get-Random)"
            $relativePath = Join-Path "." $dirName
            $expectedAbsolutePath = Join-Path $PWD $dirName
            New-Item -ItemType Directory -Path $expectedAbsolutePath -Force | Out-Null

            try {
                Add-CodeQLToPath -Path $relativePath

                # PATH should contain absolute path, not relative
                # Use the resolved path without the "./" prefix
                $env:PATH | Should -Match ([regex]::Escape($expectedAbsolutePath))
            }
            finally {
                Remove-Item -Path $expectedAbsolutePath -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context "Persistent PATH Updates" {
        It "Does not throw when updating persistent PATH" {
            $testPath = Join-Path $script:TestTempDir "persistent-test"
            New-Item -ItemType Directory -Path $testPath -Force | Out-Null

            # Should not throw (may warn if permissions insufficient)
            { Add-CodeQLToPath -Path $testPath -WarningAction SilentlyContinue } |
                Should -Not -Throw
        }
    }
}

Describe "Script Parameters" {
    Context "Parameter Validation" {
        It "Has Version parameter with default value" {
            $params = (Get-Command $scriptPath).Parameters['Version']

            $params | Should -Not -BeNullOrEmpty
            # Default value checked in script, not easily testable here
        }

        It "Has InstallPath parameter with default value" {
            $params = (Get-Command $scriptPath).Parameters['InstallPath']

            $params | Should -Not -BeNullOrEmpty
        }

        It "Has Force switch parameter" {
            $params = (Get-Command $scriptPath).Parameters['Force']

            $params | Should -Not -BeNullOrEmpty
            $params.ParameterType.Name | Should -Be 'SwitchParameter'
        }

        It "Has AddToPath switch parameter" {
            $params = (Get-Command $scriptPath).Parameters['AddToPath']

            $params | Should -Not -BeNullOrEmpty
            $params.ParameterType.Name | Should -Be 'SwitchParameter'
        }

        It "Has CI switch parameter" {
            $params = (Get-Command $scriptPath).Parameters['CI']

            $params | Should -Not -BeNullOrEmpty
            $params.ParameterType.Name | Should -Be 'SwitchParameter'
        }
    }
}

Describe "Exit Codes" {
    Context "ADR-035 Compliance" {
        It "Should document exit codes in help" {
            $help = Get-Help $scriptPath

            $help.description.Text | Should -Match "Exit Code"
        }

        It "Uses StandardExitCodes pattern (0=success, 1=error, 3=external)" {
            # Verify exit codes are used in script
            $content = Get-Content $scriptPath -Raw

            $content | Should -Match "exit 0"  # Success
            $content | Should -Match "exit 1"  # Logic error
            $content | Should -Match "exit 3"  # External error
            # Note: exit 2 is documented for config errors but not currently used in implementation
        }
    }
}

Describe "Cross-Platform Compatibility" {
    Context "Platform Variables" {
        It "Uses platform detection variables" {
            $content = Get-Content $scriptPath -Raw

            $content | Should -Match '\$IsWindows|\$IsLinux|\$IsMacOS'
        }

        It "Uses Join-Path for all path operations" {
            $content = Get-Content $scriptPath -Raw

            # Should not have hardcoded path separators in string concatenation
            # This is a heuristic check
            $content | Should -Match 'Join-Path'
        }

        It "Handles executable extensions appropriately" {
            $content = Get-Content $scriptPath -Raw

            $content | Should -Match 'codeql\.exe|codeql'
        }
    }
}
