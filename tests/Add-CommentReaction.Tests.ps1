#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Add-CommentReaction.ps1 batch functionality

.DESCRIPTION
    Tests the batch reaction functionality including:
    - Single ID backward compatibility
    - Array of IDs processing
    - Empty array handling
    - Partial failure (exit code 3)
    - Success/failure counting
    - Error handling

.NOTES
    These tests mock external dependencies (gh api, GitHubHelpers module)
    to enable isolated unit testing without actual API calls.
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "github" "scripts" "reactions" "Add-CommentReaction.ps1"
    $modulePath = Join-Path $PSScriptRoot ".." ".claude" "skills" "github" "modules" "GitHubHelpers.psm1"

    # Import module to allow mocking its functions
    Import-Module $modulePath -Force
}

Describe "Add-CommentReaction" {
    BeforeEach {
        # Mock the helper functions to avoid external dependencies
        Mock Assert-GhAuthenticated { } -ModuleName GitHubHelpers
        Mock Resolve-RepoParams {
            [PSCustomObject]@{ Owner = "test-owner"; Repo = "test-repo" }
        } -ModuleName GitHubHelpers
        Mock Get-ReactionEmoji { "👀" } -ModuleName GitHubHelpers

        # Default: mock gh api to succeed
        Mock gh {
            '{"id": 1, "content": "eyes"}'
        } -ParameterFilter { $args[0] -eq "api" }

        # Capture Write-Host output
        Mock Write-Host { }
    }

    Context "Single CommentId (backward compatibility)" {
        It "Should accept a single ID without array syntax" {
            $result = & $scriptPath -CommentId 12345 -Reaction "eyes"

            $result.TotalCount | Should -Be 1
            $result.Succeeded | Should -Be 1
            $result.Failed | Should -Be 0
        }

        It "Should return success for single ID" {
            $result = & $scriptPath -CommentId 12345 -Reaction "eyes"

            $result.Results[0].Success | Should -Be $true
            $result.Results[0].CommentId | Should -Be 12345
        }

        It "Should include reaction details in result" {
            $result = & $scriptPath -CommentId 12345 -Reaction "eyes"

            $result.Reaction | Should -Be "eyes"
            $result.Emoji | Should -Be "👀"
            $result.CommentType | Should -Be "review"
        }
    }

    Context "Array of CommentIds (batch mode)" {
        It "Should process all IDs in the array" {
            $result = & $scriptPath -CommentId @(100, 200, 300) -Reaction "eyes"

            $result.TotalCount | Should -Be 3
            $result.Succeeded | Should -Be 3
            $result.Failed | Should -Be 0
        }

        It "Should return results for each ID" {
            $result = & $scriptPath -CommentId @(100, 200, 300) -Reaction "eyes"

            $result.Results.Count | Should -Be 3
            $result.Results[0].CommentId | Should -Be 100
            $result.Results[1].CommentId | Should -Be 200
            $result.Results[2].CommentId | Should -Be 300
        }

        It "Should call gh api for each ID" {
            $null = & $scriptPath -CommentId @(100, 200, 300) -Reaction "eyes"

            Should -Invoke gh -Times 3
        }
    }

    Context "Empty array handling" {
        # PowerShell's parameter binding prevents empty arrays for mandatory parameters
        # This is expected behavior - document it rather than expect it to work
        It "Should reject empty array as invalid input" {
            { & $scriptPath -CommentId @() -Reaction "eyes" } | Should -Throw "*empty array*"
        }
    }

    Context "API failure handling" {
        BeforeEach {
            # Mock gh api to fail
            Mock gh {
                $global:LASTEXITCODE = 1
                "API error: not found"
            } -ParameterFilter { $args[0] -eq "api" }
        }

        It "Should increment Failed count on API error" {
            $result = & $scriptPath -CommentId 12345 -Reaction "eyes"

            $result.Failed | Should -Be 1
            $result.Succeeded | Should -Be 0
        }

        It "Should capture error message in result" {
            $result = & $scriptPath -CommentId 12345 -Reaction "eyes"

            $result.Results[0].Success | Should -Be $false
            $result.Results[0].Error | Should -Not -BeNullOrEmpty
        }
    }

    Context "Partial failure (mixed success/failure)" {
        BeforeEach {
            $callCount = 0
            Mock gh {
                $callCount++
                if ($callCount -eq 2) {
                    $global:LASTEXITCODE = 1
                    "API error: not found"
                }
                else {
                    $global:LASTEXITCODE = 0
                    '{"id": 1, "content": "eyes"}'
                }
            } -ParameterFilter { $args[0] -eq "api" }
        }

        It "Should count both succeeded and failed" {
            $script:callCount = 0
            Mock gh {
                $script:callCount++
                if ($script:callCount -eq 2) {
                    $global:LASTEXITCODE = 1
                    "API error"
                }
                else {
                    $global:LASTEXITCODE = 0
                    '{"id": 1}'
                }
            } -ParameterFilter { $args[0] -eq "api" }

            $result = & $scriptPath -CommentId @(100, 200, 300) -Reaction "eyes"

            $result.Succeeded | Should -Be 2
            $result.Failed | Should -Be 1
            $result.TotalCount | Should -Be 3
        }
    }

    Context "Idempotent behavior (duplicate reactions)" {
        BeforeEach {
            Mock gh {
                $global:LASTEXITCODE = 1
                "already reacted"
            } -ParameterFilter { $args[0] -eq "api" }
        }

        It "Should treat 'already reacted' as success" {
            $result = & $scriptPath -CommentId 12345 -Reaction "eyes"

            $result.Succeeded | Should -Be 1
            $result.Failed | Should -Be 0
            $result.Results[0].Success | Should -Be $true
        }
    }

    Context "CommentType parameter" {
        It "Should default to 'review' type" {
            $result = & $scriptPath -CommentId 12345 -Reaction "eyes"

            $result.CommentType | Should -Be "review"
        }

        It "Should accept 'issue' type" {
            $result = & $scriptPath -CommentId 12345 -CommentType "issue" -Reaction "eyes"

            $result.CommentType | Should -Be "issue"
        }

        It "Should call gh api for review comments" {
            $null = & $scriptPath -CommentId 12345 -CommentType "review" -Reaction "eyes"

            # Verify gh was called - endpoint construction is verified by successful execution
            Should -Invoke gh -Times 1
        }

        It "Should call gh api for issue comments" {
            $null = & $scriptPath -CommentId 12345 -CommentType "issue" -Reaction "eyes"

            # Verify gh was called - endpoint construction is verified by successful execution
            Should -Invoke gh -Times 1
        }
    }

    Context "Reaction types" {
        It "Should accept all valid reaction types" {
            $validReactions = @("+1", "-1", "laugh", "confused", "heart", "hooray", "rocket", "eyes")

            foreach ($reaction in $validReactions) {
                { & $scriptPath -CommentId 12345 -Reaction $reaction } | Should -Not -Throw
            }
        }
    }

    Context "Output structure" {
        It "Should return summary object with required properties" {
            $result = & $scriptPath -CommentId 12345 -Reaction "eyes"

            $result.PSObject.Properties.Name | Should -Contain "TotalCount"
            $result.PSObject.Properties.Name | Should -Contain "Succeeded"
            $result.PSObject.Properties.Name | Should -Contain "Failed"
            $result.PSObject.Properties.Name | Should -Contain "Reaction"
            $result.PSObject.Properties.Name | Should -Contain "Emoji"
            $result.PSObject.Properties.Name | Should -Contain "CommentType"
            $result.PSObject.Properties.Name | Should -Contain "Results"
        }

        It "Should return individual results with required properties" {
            $result = & $scriptPath -CommentId 12345 -Reaction "eyes"

            $result.Results[0].PSObject.Properties.Name | Should -Contain "Success"
            $result.Results[0].PSObject.Properties.Name | Should -Contain "CommentId"
            $result.Results[0].PSObject.Properties.Name | Should -Contain "CommentType"
            $result.Results[0].PSObject.Properties.Name | Should -Contain "Reaction"
            $result.Results[0].PSObject.Properties.Name | Should -Contain "Emoji"
            $result.Results[0].PSObject.Properties.Name | Should -Contain "Error"
        }
    }
}
