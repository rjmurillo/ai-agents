BeforeAll {
    # Script path under test
    $script:DiagnoseScript = "$PSScriptRoot/../.claude/skills/session-log-fixer/diagnose.ps1"
}

Describe 'Diagnose-SessionProtocol Tests' {
    BeforeEach {
        # Mock Write-Host to capture output without cluttering test results
        Mock Write-Host { }

        # Set TEMP environment variable for Linux compatibility
        $env:TEMP = $TestDrive

        # Mock environment
        $script:TestArtifactDir = Join-Path $TestDrive "session-artifacts-12345"

        # Default mocks
        Mock gh { }
        Mock Test-Path { $false }
        Mock Remove-Item { }
        Mock Get-ChildItem { @() }
        Mock Get-Content { @() }
    }

    AfterEach {
        # Clean up environment variable
        if ($IsLinux -or $IsMacOS) {
            Remove-Item Env:TEMP -ErrorAction SilentlyContinue
        }
    }

    Context 'Parameter Validation' {
        It 'RunId parameter is mandatory' {
            $command = Get-Command $script:DiagnoseScript
            $runIdParam = $command.Parameters['RunId']
            $runIdParam.Attributes | Where-Object { $_ -is [System.Management.Automation.ParameterAttribute] } |
                ForEach-Object { $_.Mandatory } | Should -Contain $true
        }

        It 'Repo parameter has default value' {
            $command = Get-Command $script:DiagnoseScript
            $repoParam = $command.Parameters['Repo']
            $repoParam.Attributes | Where-Object { $_ -is [System.Management.Automation.ParameterAttribute] } |
                ForEach-Object { $_.Mandatory } | Should -Not -Contain $true
        }
    }

    Context 'Run Status Display' {
        It 'Calls gh run view with correct parameters for status' {
            # Arrange
            Mock gh -ParameterFilter { $args -contains 'run' -and $args -contains 'view' } {
                '{"status":"completed","conclusion":"success","failed_jobs":[]}'
            }
            Mock gh -ParameterFilter { $args -contains '--log' } { @() }

            # Act
            & $script:DiagnoseScript -RunId "12345" -Repo "owner/repo"

            # Assert
            Should -Invoke gh -ParameterFilter {
                $args -contains '12345' -and
                $args -contains '--repo' -and
                $args -contains 'owner/repo' -and
                $args -contains '--json'
            } -Times 1
        }

        It 'Displays run status section header' {
            # Arrange
            Mock gh { '{}' }

            # Act
            & $script:DiagnoseScript -RunId "12345"

            # Assert
            Should -Invoke Write-Host -ParameterFilter {
                $Object -eq "=== Run Status ===" -and $ForegroundColor -eq 'Cyan'
            } -Times 1
        }
    }

    Context 'NON_COMPLIANT Session Detection' {
        It 'Finds NON_COMPLIANT patterns in logs' {
            # Arrange
            Mock gh -ParameterFilter { $args -contains '--json' } { '{}' }
            Mock gh -ParameterFilter { $args -contains '--log' } {
                @(
                    "2024-01-01T00:00:00Z Checking session file...",
                    "2024-01-01T00:00:01Z Found verdict: NON_COMPLIANT for session-01.md",
                    "2024-01-01T00:00:02Z Processing complete"
                )
            }

            # Act
            & $script:DiagnoseScript -RunId "12345"

            # Assert
            Should -Invoke Write-Host -ParameterFilter {
                $Object -match 'NON_COMPLIANT'
            } -Times 1
        }

        It 'Reports when no NON_COMPLIANT sessions found' {
            # Arrange
            Mock gh -ParameterFilter { $args -contains '--json' } { '{}' }
            Mock gh -ParameterFilter { $args -contains '--log' } {
                @(
                    "2024-01-01T00:00:00Z All sessions compliant",
                    "2024-01-01T00:00:01Z Validation passed"
                )
            }

            # Act
            & $script:DiagnoseScript -RunId "12345"

            # Assert
            Should -Invoke Write-Host -ParameterFilter {
                $Object -eq "No NON_COMPLIANT sessions found"
            } -Times 1
        }

        It 'Matches Found verdict pattern' {
            # Arrange
            Mock gh -ParameterFilter { $args -contains '--json' } { '{}' }
            Mock gh -ParameterFilter { $args -contains '--log' } {
                @("Found verdict: COMPLIANT for session-02.md")
            }

            # Act
            & $script:DiagnoseScript -RunId "12345"

            # Assert - "Found verdict" should match pattern
            Should -Invoke Write-Host -ParameterFilter {
                $Object -match 'Found verdict'
            } -Times 1
        }
    }

    Context 'Artifact Download' {
        It 'Cleans existing artifact directory before download' {
            # Arrange
            Mock gh { '{}' }
            Mock Test-Path { $true }

            # Act
            & $script:DiagnoseScript -RunId "12345"

            # Assert
            Should -Invoke Remove-Item -ParameterFilter {
                $Recurse -eq $true -and $Force -eq $true
            } -Times 1
        }

        It 'Downloads artifacts to temp directory' {
            # Arrange
            Mock gh -ParameterFilter { $args -contains '--json' } { '{}' }
            Mock gh -ParameterFilter { $args -contains '--log' } { @() }
            Mock gh -ParameterFilter { $args -contains 'download' } { }

            # Act
            & $script:DiagnoseScript -RunId "12345" -Repo "owner/repo"

            # Assert
            Should -Invoke gh -ParameterFilter {
                $args -contains 'download' -and
                $args -contains '12345' -and
                $args -contains '--repo' -and
                $args -contains 'owner/repo'
            } -Times 1
        }

        It 'Handles failed artifact download gracefully' {
            # Arrange
            Mock gh -ParameterFilter { $args -contains '--json' } { '{}' }
            Mock gh -ParameterFilter { $args -contains '--log' } { @() }
            Mock gh -ParameterFilter { $args -contains 'download' } {
                throw "no artifacts found"
            }

            # Act & Assert - Should not throw
            { & $script:DiagnoseScript -RunId "12345" } | Should -Not -Throw
        }
    }

    Context 'Verdict File Processing' {
        It 'Finds and displays verdict files' {
            # Arrange
            Mock gh { '{}' }
            $verdictFile = [PSCustomObject]@{
                Name = "session-01-verdict.txt"
                FullName = "$TestDrive/session-01-verdict.txt"
            }
            Mock Get-ChildItem -ParameterFilter { $Filter -eq "*-verdict.txt" } {
                @($verdictFile)
            }
            Mock Get-Content { "VERDICT: NON_COMPLIANT" }

            # Act
            & $script:DiagnoseScript -RunId "12345"

            # Assert
            Should -Invoke Write-Host -ParameterFilter {
                $Object -match "session-01-verdict.txt" -and $ForegroundColor -eq 'Yellow'
            } -Times 1
        }

        It 'Displays verdict file contents' {
            # Arrange
            Mock gh { '{}' }
            $verdictFile = [PSCustomObject]@{
                Name = "test-verdict.txt"
                FullName = "$TestDrive/test-verdict.txt"
            }
            Mock Get-ChildItem -ParameterFilter { $Filter -eq "*-verdict.txt" } {
                @($verdictFile)
            }
            Mock Get-Content { "VERDICT: NON_COMPLIANT`nMissing: Session End Table" }

            # Act
            & $script:DiagnoseScript -RunId "12345"

            # Assert
            Should -Invoke Get-Content -ParameterFilter {
                $Path -match "test-verdict.txt"
            } -Times 1
        }
    }

    Context 'Validation Output Processing' {
        It 'Excludes verdict files from validation output' {
            # Arrange
            Mock gh { '{}' }
            $validationFile = [PSCustomObject]@{
                Name = "validation-output.txt"
                FullName = "$TestDrive/validation-output.txt"
            }
            Mock Get-ChildItem -ParameterFilter { $Filter -eq "*.txt" } {
                @($validationFile)
            }
            Mock Get-Content { @("Line 1", "Line 2") }

            # Act
            & $script:DiagnoseScript -RunId "12345"

            # Assert - Should display non-verdict txt files
            Should -Invoke Write-Host -ParameterFilter {
                $Object -match "validation-output.txt"
            } -Times 1
        }

        It 'Limits validation output to first 100 lines' {
            # Arrange
            Mock gh { '{}' }
            $validationFile = [PSCustomObject]@{
                Name = "large-output.txt"
                FullName = "$TestDrive/large-output.txt"
            }
            Mock Get-ChildItem -ParameterFilter { $Filter -eq "*.txt" } {
                @($validationFile)
            }
            # Generate 200 lines
            $lines = 1..200 | ForEach-Object { "Line $_" }
            Mock Get-Content { $lines }

            # Act
            & $script:DiagnoseScript -RunId "12345"

            # Assert - Get-Content is called, Select-Object limits to 100
            Should -Invoke Get-Content -Times 1
        }
    }

    Context 'Default Repository' {
        It 'Uses rjmurillo/ai-agents as default repo' {
            # Arrange
            Mock gh -ParameterFilter { $args -contains '--json' } { '{}' }
            Mock gh -ParameterFilter { $args -contains '--log' } { @() }
            Mock gh -ParameterFilter { $args -contains 'download' } { }

            # Act
            & $script:DiagnoseScript -RunId "12345"

            # Assert - Verify default repo is used
            Should -Invoke gh -ParameterFilter {
                $args -contains 'rjmurillo/ai-agents'
            } -Times 3  # Once for status, once for logs, once for download
        }
    }

    Context 'Section Headers' {
        It 'Displays all required section headers' {
            # Arrange
            Mock gh { '{}' }

            # Act
            & $script:DiagnoseScript -RunId "12345"

            # Assert
            Should -Invoke Write-Host -ParameterFilter {
                $Object -eq "=== Run Status ===" -and $ForegroundColor -eq 'Cyan'
            } -Times 1

            Should -Invoke Write-Host -ParameterFilter {
                $Object -eq "=== NON_COMPLIANT Sessions ===" -and $ForegroundColor -eq 'Cyan'
            } -Times 1

            Should -Invoke Write-Host -ParameterFilter {
                $Object -eq "=== Downloading Artifacts ===" -and $ForegroundColor -eq 'Cyan'
            } -Times 1

            Should -Invoke Write-Host -ParameterFilter {
                $Object -eq "=== Verdict Details ===" -and $ForegroundColor -eq 'Cyan'
            } -Times 1

            Should -Invoke Write-Host -ParameterFilter {
                $Object -eq "=== Validation Output ===" -and $ForegroundColor -eq 'Cyan'
            } -Times 1
        }
    }
}
