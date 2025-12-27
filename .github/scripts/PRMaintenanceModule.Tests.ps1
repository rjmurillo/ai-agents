<#
.SYNOPSIS
    Pester tests for PRMaintenanceModule.psm1.

.DESCRIPTION
    Tests the PR maintenance workflow module functions per ADR-006.
    Covers rate limit checking, log parsing, summary generation,
    and alert body generation.

.NOTES
    Requires Pester 5.x or later.
#>

BeforeAll {
    $Script:ModulePath = Join-Path $PSScriptRoot "PRMaintenanceModule.psm1"
    Import-Module $Script:ModulePath -Force
}

AfterAll {
    Remove-Module PRMaintenanceModule -Force -ErrorAction SilentlyContinue
}

Describe "PRMaintenanceModule" {

    Context "Module Import" {
        It "Should import without errors" {
            { Import-Module $Script:ModulePath -Force } | Should -Not -Throw
        }

        It "Should export expected functions" {
            $module = Get-Module PRMaintenanceModule
            $expectedFunctions = @(
                'Test-WorkflowRateLimit',
                'Get-MaintenanceResults',
                'New-MaintenanceSummary',
                'New-BlockedPRsAlertBody',
                'New-WorkflowFailureAlertBody',
                'Test-WorkflowEnvironment'
            )
            foreach ($fn in $expectedFunctions) {
                $module.ExportedFunctions.Keys | Should -Contain $fn
            }
        }
    }

    Context "Test-WorkflowRateLimit" {

        It "Should return success when all resources above threshold" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return @'
{
    "resources": {
        "core": { "remaining": 5000, "limit": 5000, "reset": 1234567890 },
        "search": { "remaining": 30, "limit": 30, "reset": 1234567890 },
        "code_search": { "remaining": 10, "limit": 10, "reset": 1234567890 },
        "graphql": { "remaining": 5000, "limit": 5000, "reset": 1234567890 }
    }
}
'@
            } -ModuleName PRMaintenanceModule

            $result = Test-WorkflowRateLimit
            $result.Success | Should -Be $true
            $result.CoreRemaining | Should -Be 5000
        }

        It "Should return failure when core below threshold" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return @'
{
    "resources": {
        "core": { "remaining": 50, "limit": 5000, "reset": 1234567890 },
        "search": { "remaining": 30, "limit": 30, "reset": 1234567890 },
        "code_search": { "remaining": 10, "limit": 10, "reset": 1234567890 },
        "graphql": { "remaining": 5000, "limit": 5000, "reset": 1234567890 }
    }
}
'@
            } -ModuleName PRMaintenanceModule

            $result = Test-WorkflowRateLimit
            $result.Success | Should -Be $false
            $result.Resources['core'].Passed | Should -Be $false
        }

        It "Should return failure when search below threshold" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return @'
{
    "resources": {
        "core": { "remaining": 5000, "limit": 5000, "reset": 1234567890 },
        "search": { "remaining": 5, "limit": 30, "reset": 1234567890 },
        "code_search": { "remaining": 10, "limit": 10, "reset": 1234567890 },
        "graphql": { "remaining": 5000, "limit": 5000, "reset": 1234567890 }
    }
}
'@
            } -ModuleName PRMaintenanceModule

            $result = Test-WorkflowRateLimit
            $result.Success | Should -Be $false
            $result.Resources['search'].Passed | Should -Be $false
        }

        It "Should accept custom thresholds" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return @'
{
    "resources": {
        "core": { "remaining": 150, "limit": 5000, "reset": 1234567890 },
        "search": { "remaining": 30, "limit": 30, "reset": 1234567890 },
        "code_search": { "remaining": 10, "limit": 10, "reset": 1234567890 },
        "graphql": { "remaining": 5000, "limit": 5000, "reset": 1234567890 }
    }
}
'@
            } -ModuleName PRMaintenanceModule

            # With default threshold (100), this should pass
            $result = Test-WorkflowRateLimit -ResourceThresholds @{ 'core' = 100 }
            $result.Success | Should -Be $true

            # With higher threshold (200), this should fail
            $result = Test-WorkflowRateLimit -ResourceThresholds @{ 'core' = 200 }
            $result.Success | Should -Be $false
        }

        It "Should generate markdown summary" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return @'
{
    "resources": {
        "core": { "remaining": 5000, "limit": 5000, "reset": 1234567890 },
        "search": { "remaining": 30, "limit": 30, "reset": 1234567890 },
        "code_search": { "remaining": 10, "limit": 10, "reset": 1234567890 },
        "graphql": { "remaining": 5000, "limit": 5000, "reset": 1234567890 }
    }
}
'@
            } -ModuleName PRMaintenanceModule

            $result = Test-WorkflowRateLimit
            $result.SummaryMarkdown | Should -Match 'API Rate Limit Status'
            $result.SummaryMarkdown | Should -Match '\| Resource \|'
            $result.SummaryMarkdown | Should -Match 'OK'
        }

        It "Should throw when gh command fails" {
            Mock gh {
                $global:LASTEXITCODE = 1
                return "Error: API error"
            } -ModuleName PRMaintenanceModule

            { Test-WorkflowRateLimit } | Should -Throw
        }
    }

    Context "Get-MaintenanceResults" {

        BeforeEach {
            $Script:TestLogPath = Join-Path $TestDrive "test-maintenance.log"
        }

        It "Should parse metrics from log file" {
            $logContent = @"
[2025-01-01 00:00:00] Starting PR Maintenance
PRs Processed: 5
Comments Acknowledged: 12
Conflicts Resolved: 2
"@
            $logContent | Out-File $Script:TestLogPath -Encoding utf8

            $result = Get-MaintenanceResults -LogPath $Script:TestLogPath
            $result.Processed | Should -Be 5
            $result.Acknowledged | Should -Be 12
            $result.Resolved | Should -Be 2
            $result.HasBlocked | Should -Be $false
        }

        It "Should extract blocked PRs list" {
            $logContent = @"
[2025-01-01 00:00:00] Starting PR Maintenance
PRs Processed: 3
Comments Acknowledged: 5
Conflicts Resolved: 0
Blocked PRs (require human action):
  PR #123 - Merge conflicts cannot be auto-resolved
  PR #456 - Changes requested by reviewer
"@
            $logContent | Out-File $Script:TestLogPath -Encoding utf8

            $result = Get-MaintenanceResults -LogPath $Script:TestLogPath
            $result.HasBlocked | Should -Be $true
            $result.BlockedPRs.Count | Should -Be 2
            $result.BlockedPRs[0] | Should -Match 'PR #123'
            $result.BlockedPRs[1] | Should -Match 'PR #456'
        }

        It "Should return zeros when log file missing" {
            $result = Get-MaintenanceResults -LogPath "nonexistent.log"
            $result.Processed | Should -Be 0
            $result.Acknowledged | Should -Be 0
            $result.Resolved | Should -Be 0
            $result.HasBlocked | Should -Be $false
        }

        It "Should handle log with no metrics" {
            $logContent = @"
[2025-01-01 00:00:00] Starting PR Maintenance
[2025-01-01 00:00:01] No PRs found to process
"@
            $logContent | Out-File $Script:TestLogPath -Encoding utf8

            $result = Get-MaintenanceResults -LogPath $Script:TestLogPath
            $result.Processed | Should -Be 0
            $result.Acknowledged | Should -Be 0
            $result.Resolved | Should -Be 0
        }

        It "Should handle large metric values" {
            $logContent = @"
PRs Processed: 999
Comments Acknowledged: 12345
Conflicts Resolved: 100
"@
            $logContent | Out-File $Script:TestLogPath -Encoding utf8

            $result = Get-MaintenanceResults -LogPath $Script:TestLogPath
            $result.Processed | Should -Be 999
            $result.Acknowledged | Should -Be 12345
            $result.Resolved | Should -Be 100
        }
    }

    Context "New-MaintenanceSummary" {

        It "Should generate basic summary" {
            $results = [PSCustomObject]@{
                Processed    = 5
                Acknowledged = 12
                Resolved     = 2
                BlockedPRs   = @()
                HasBlocked   = $false
            }

            $summary = New-MaintenanceSummary -Results $results -CoreRemaining 4500

            $summary | Should -Match 'PR Maintenance Summary'
            $summary | Should -Match 'PRs Processed.*5'
            $summary | Should -Match 'Comments Acknowledged.*12'
            $summary | Should -Match 'Conflicts Resolved.*2'
            $summary | Should -Match 'Core API.*4500'
        }

        It "Should include blocked PRs section when present" {
            $results = [PSCustomObject]@{
                Processed    = 3
                Acknowledged = 5
                Resolved     = 0
                BlockedPRs   = @('PR #123 - conflicts', 'PR #456 - changes requested')
                HasBlocked   = $true
            }

            $summary = New-MaintenanceSummary -Results $results -CoreRemaining 4000

            $summary | Should -Match 'Blocked PRs \(Require Human Action\)'
            $summary | Should -Match 'PR #123'
            $summary | Should -Match 'PR #456'
        }

        It "Should include run URL when provided" {
            $results = [PSCustomObject]@{
                Processed    = 1
                Acknowledged = 1
                Resolved     = 0
                BlockedPRs   = @()
                HasBlocked   = $false
            }

            $runUrl = 'https://github.com/owner/repo/actions/runs/12345'
            $summary = New-MaintenanceSummary -Results $results -RunUrl $runUrl

            $summary | Should -Match 'View Logs'
            $summary | Should -Match $runUrl
        }
    }

    Context "New-BlockedPRsAlertBody" {

        It "Should generate alert body with blocked PRs list" {
            $blockedPRs = @(
                'PR #123 - Merge conflicts',
                'PR #456 - Changes requested'
            )

            $body = New-BlockedPRsAlertBody -BlockedPRs $blockedPRs

            $body | Should -Match 'Blocked PRs'
            $body | Should -Match 'PR #123'
            $body | Should -Match 'PR #456'
            $body | Should -Match 'Action Required'
        }

        It "Should include run URL when provided" {
            $blockedPRs = @('PR #789 - Issue')
            $runUrl = 'https://github.com/owner/repo/actions/runs/99999'

            $body = New-BlockedPRsAlertBody -BlockedPRs $blockedPRs -RunUrl $runUrl

            $body | Should -Match 'Workflow Run'
            $body | Should -Match $runUrl
        }

        It "Should include footer" {
            $body = New-BlockedPRsAlertBody -BlockedPRs @('PR #1')

            $body | Should -Match 'Powered by'
            $body | Should -Match 'PR Maintenance'
        }
    }

    Context "New-WorkflowFailureAlertBody" {

        It "Should generate failure alert body" {
            $body = New-WorkflowFailureAlertBody -TriggerEvent 'schedule'

            $body | Should -Match 'Workflow Failure'
            $body | Should -Match 'schedule'
            $body | Should -Match 'Action Required'
            $body | Should -Match 'Investigate workflow logs'
        }

        It "Should include run URL when provided" {
            $runUrl = 'https://github.com/owner/repo/actions/runs/55555'

            $body = New-WorkflowFailureAlertBody -RunUrl $runUrl -TriggerEvent 'workflow_dispatch'

            $body | Should -Match $runUrl
            $body | Should -Match 'workflow_dispatch'
        }

        It "Should include timestamp" {
            $body = New-WorkflowFailureAlertBody

            # Should contain date format pattern
            $body | Should -Match '\d{4}-\d{2}-\d{2}'
        }
    }

    Context "Test-WorkflowEnvironment" {

        It "Should return valid when all tools available" {
            $result = Test-WorkflowEnvironment

            # PowerShell is definitely available since we're running in it
            $result.Versions['PowerShell'] | Should -Not -BeNullOrEmpty

            # Result should have expected structure
            $result.Valid | Should -BeOfType [bool]
            $result.SummaryMarkdown | Should -Match 'Environment Validation'
        }

        It "Should include version information in summary" {
            $result = Test-WorkflowEnvironment

            $result.SummaryMarkdown | Should -Match 'PowerShell'
            $result.SummaryMarkdown | Should -Match '\| Tool \|'
        }

        It "Should have correct PowerShell version" {
            $result = Test-WorkflowEnvironment

            $expectedVersion = $PSVersionTable.PSVersion.ToString()
            $result.Versions['PowerShell'] | Should -Be $expectedVersion
        }
    }
}

Describe "Integration Scenarios" -Tag 'Integration' {

    Context "Full workflow simulation" {

        It "Should handle complete happy path" {
            # Create test log
            $logPath = Join-Path $TestDrive "integration-test.log"
            @"
PRs Processed: 10
Comments Acknowledged: 25
Conflicts Resolved: 3
"@ | Out-File $logPath -Encoding utf8

            # Parse results
            $results = Get-MaintenanceResults -LogPath $logPath

            # Generate summary
            $summary = New-MaintenanceSummary -Results $results -CoreRemaining 4000

            # Verify end-to-end
            $results.Processed | Should -Be 10
            $summary | Should -Match 'PRs Processed.*10'
            $summary | Should -Match 'Comments Acknowledged.*25'
        }

        It "Should handle blocked PRs workflow" {
            # Create test log with blocked PRs
            $logPath = Join-Path $TestDrive "blocked-test.log"
            @"
PRs Processed: 5
Comments Acknowledged: 8
Conflicts Resolved: 0
Blocked PRs (require human action):
  PR #100 - Cannot auto-merge
  PR #200 - Review required
"@ | Out-File $logPath -Encoding utf8

            # Parse results
            $results = Get-MaintenanceResults -LogPath $logPath

            # Generate summary
            $summary = New-MaintenanceSummary -Results $results

            # Generate alert body
            $alertBody = New-BlockedPRsAlertBody -BlockedPRs $results.BlockedPRs

            # Verify
            $results.HasBlocked | Should -Be $true
            $summary | Should -Match 'Blocked PRs'
            $alertBody | Should -Match 'PR #100'
            $alertBody | Should -Match 'PR #200'
        }
    }
}
