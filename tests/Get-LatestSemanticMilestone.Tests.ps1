#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Tests for Get-LatestSemanticMilestone.ps1

.DESCRIPTION
    Pester tests for milestone detection logic including:
    - Multiple semantic version milestones (returns latest)
    - Mix of semantic and non-semantic milestones (filters correctly)
    - No semantic milestones (returns error)
    - No milestones (returns error)
    - Version sorting (10 > 2, not string comparison)
    - API error handling

.NOTES
    Run with: Invoke-Pester scripts/Get-LatestSemanticMilestone.Tests.ps1
#>

BeforeAll {
    $script:ScriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "github" "scripts" "milestone" "Get-LatestSemanticMilestone.ps1"

    # Mock gh command globally
    function global:gh {
        throw "Mock not configured for 'gh $args'"
    }
}

Describe "Get-LatestSemanticMilestone" {
    Context "When multiple semantic version milestones exist" {
        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    return $null
                }
                elseif ($args[0] -eq 'api' -and $args[1] -match 'milestones') {
                    return @(
                        @{ title = "0.2.0"; number = 42; state = "open" }
                        @{ title = "0.3.0"; number = 43; state = "open" }
                        @{ title = "0.1.0"; number = 41; state = "open" }
                    ) | ConvertTo-Json
                }
            }
            $global:LASTEXITCODE = 0
        }

        It "Returns the latest semantic version milestone" {
            $result = & $script:ScriptPath -Owner "test" -Repo "repo"

            $result.Title | Should -Be "0.3.0"
            $result.Number | Should -Be 43
            $result.Found | Should -Be $true
        }
    }

    Context "When version numbers require proper sorting (not string comparison)" {
        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    return $null
                }
                elseif ($args[0] -eq 'api' -and $args[1] -match 'milestones') {
                    return @(
                        @{ title = "0.2.0"; number = 42; state = "open" }
                        @{ title = "0.10.0"; number = 50; state = "open" }
                        @{ title = "0.3.0"; number = 43; state = "open" }
                    ) | ConvertTo-Json
                }
            }
            $global:LASTEXITCODE = 0
        }

        It "Uses version comparison not string comparison (0.10.0 > 0.3.0 > 0.2.0)" {
            $result = & $script:ScriptPath -Owner "test" -Repo "repo"

            $result.Title | Should -Be "0.10.0"
            $result.Number | Should -Be 50
            $result.Found | Should -Be $true
        }
    }

    Context "When semantic and non-semantic milestones are mixed" {
        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    return $null
                }
                elseif ($args[0] -eq 'api' -and $args[1] -match 'milestones') {
                    return @(
                        @{ title = "Future"; number = 99; state = "open" }
                        @{ title = "0.2.0"; number = 42; state = "open" }
                        @{ title = "Backlog"; number = 98; state = "open" }
                        @{ title = "1.0.0"; number = 100; state = "open" }
                    ) | ConvertTo-Json
                }
            }
            $global:LASTEXITCODE = 0
        }

        It "Filters to semantic versions only and returns latest" {
            $result = & $script:ScriptPath -Owner "test" -Repo "repo"

            $result.Title | Should -Be "1.0.0"
            $result.Number | Should -Be 100
            $result.Found | Should -Be $true
        }
    }

    Context "When only non-semantic milestones exist" {
        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    return $null
                }
                elseif ($args[0] -eq 'api' -and $args[1] -match 'milestones') {
                    return @(
                        @{ title = "Future"; number = 99; state = "open" }
                        @{ title = "Backlog"; number = 98; state = "open" }
                    ) | ConvertTo-Json
                }
            }
            $global:LASTEXITCODE = 0
        }

        It "Returns not found with exit code 2" {
            $result = & $script:ScriptPath -Owner "test" -Repo "repo" 2>&1

            $LASTEXITCODE | Should -Be 2
            # Script writes warning and exits, capture that
        }
    }

    Context "When no milestones exist" {
        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    return $null
                }
                elseif ($args[0] -eq 'api' -and $args[1] -match 'milestones') {
                    return @() | ConvertTo-Json
                }
            }
            $global:LASTEXITCODE = 0
        }

        It "Returns not found with exit code 2" {
            $result = & $script:ScriptPath -Owner "test" -Repo "repo" 2>&1

            $LASTEXITCODE | Should -Be 2
        }
    }

    Context "When API returns error" {
        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    return $null
                }
                elseif ($args[0] -eq 'api') {
                    $global:LASTEXITCODE = 1
                    return "API error: rate limit exceeded"
                }
            }
        }

        It "Exits with error code 3" {
            { & $script:ScriptPath -Owner "test" -Repo "repo" } | Should -Throw
            $LASTEXITCODE | Should -Be 3
        }
    }

    Context "When not authenticated" {
        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    $global:LASTEXITCODE = 1
                    return "not logged in"
                }
            }
        }

        It "Exits with error code 4 (auth error)" {
            { & $script:ScriptPath -Owner "test" -Repo "repo" } | Should -Throw
            $LASTEXITCODE | Should -Be 4
        }
    }

    Context "Repository parameter inference" {
        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    return $null
                }
                elseif ($args[0] -eq 'api' -and $args[1] -match 'milestones') {
                    return @(
                        @{ title = "0.2.0"; number = 42; state = "open" }
                    ) | ConvertTo-Json
                }
            }
            $global:LASTEXITCODE = 0

            # Mock git command for repo inference
            Mock -CommandName git -MockWith {
                if ($args[0] -eq 'remote' -and $args[1] -eq 'get-url') {
                    return "https://github.com/test-owner/test-repo.git"
                }
            }
        }

        It "Infers owner and repo from git remote when not provided" {
            $result = & $script:ScriptPath

            $result.Title | Should -Be "0.2.0"
            $result.Number | Should -Be 42
            $result.Found | Should -Be $true

            Should -Invoke gh -Times 1 -ParameterFilter {
                $args -join ' ' -match 'repos/test-owner/test-repo/milestones'
            }
        }
    }

    Context "GITHUB_OUTPUT integration" {
        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    return $null
                }
                elseif ($args[0] -eq 'api' -and $args[1] -match 'milestones') {
                    return @(
                        @{ title = "1.2.3"; number = 456; state = "open" }
                    ) | ConvertTo-Json
                }
            }
            $global:LASTEXITCODE = 0

            $tempOutput = New-TemporaryFile
            $env:GITHUB_OUTPUT = $tempOutput.FullName
        }

        AfterEach {
            if ($env:GITHUB_OUTPUT -and (Test-Path $env:GITHUB_OUTPUT)) {
                Remove-Item $env:GITHUB_OUTPUT -ErrorAction SilentlyContinue
            }
            $env:GITHUB_OUTPUT = $null
        }

        It "Writes milestone details to GITHUB_OUTPUT" {
            & $script:ScriptPath -Owner "test" -Repo "repo" | Out-Null

            $outputContent = Get-Content $env:GITHUB_OUTPUT -Raw
            $outputContent | Should -Match 'milestone_title=1\.2\.3'
            $outputContent | Should -Match 'milestone_number=456'
            $outputContent | Should -Match 'found=true'
        }
    }
}
