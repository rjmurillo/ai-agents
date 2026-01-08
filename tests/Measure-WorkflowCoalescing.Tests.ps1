BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot '../.github/scripts/Measure-WorkflowCoalescing.ps1'
    $scriptPath = Resolve-Path $scriptPath
    . $scriptPath
}

Describe "Measure-WorkflowCoalescing" {
    Context "Overlap Detection" {
        It "Detects overlapping runs" {
            $run1 = @{
                id = 1
                created_at = '2026-01-01T10:00:00Z'
                updated_at = '2026-01-01T10:05:00Z'
                conclusion = 'success'
            }
            
            $run2 = @{
                id = 2
                created_at = '2026-01-01T10:03:00Z'
                updated_at = '2026-01-01T10:08:00Z'
                conclusion = 'success'
            }
            
            $result = Test-RunsOverlap -Run1 $run1 -Run2 $run2
            $result | Should -Be $true
        }
        
        It "Treats equal start time as overlap" {
            $run1 = @{ id = 1; created_at = '2026-01-01T10:00:00Z'; updated_at = '2026-01-01T10:05:00Z'; conclusion = 'success' }
            $run2 = @{ id = 2; created_at = '2026-01-01T10:00:00Z'; updated_at = '2026-01-01T10:06:00Z'; conclusion = 'success' }
            $result = Test-RunsOverlap -Run1 $run1 -Run2 $run2
            $result | Should -Be $true
        }
        
        It "Does not detect non-overlapping runs" {
            $run1 = @{
                id = 1
                created_at = '2026-01-01T10:00:00Z'
                updated_at = '2026-01-01T10:05:00Z'
                conclusion = 'success'
            }
            
            $run2 = @{
                id = 2
                created_at = '2026-01-01T10:06:00Z'
                updated_at = '2026-01-01T10:10:00Z'
                conclusion = 'success'
            }
            
            $result = Test-RunsOverlap -Run1 $run1 -Run2 $run2
            $result | Should -Be $false
        }
        
        It "Handles runs where Run2 starts before Run1 finishes" {
            $run1 = @{
                id = 1
                created_at = '2026-01-01T10:00:00Z'
                updated_at = '2026-01-01T10:10:00Z'
                conclusion = 'cancelled'
            }
            
            $run2 = @{
                id = 2
                created_at = '2026-01-01T10:02:00Z'
                updated_at = '2026-01-01T10:12:00Z'
                conclusion = 'success'
            }
            
            $result = Test-RunsOverlap -Run1 $run1 -Run2 $run2
            $result | Should -Be $true
        }
    }
    
    Context "Cancellation Detection" {
        It "Identifies cancelled runs in overlap" {
            $run1 = @{
                id = 1
                name = 'ai-pr-quality-gate'
                created_at = '2026-01-01T10:00:00Z'
                updated_at = '2026-01-01T10:05:00Z'
                conclusion = 'cancelled'
                event = 'pull_request'
                pull_requests = @(@{ number = 123 })
                head_branch = 'feature-branch'
            }
            
            $run2 = @{
                id = 2
                name = 'ai-pr-quality-gate'
                created_at = '2026-01-01T10:03:00Z'
                updated_at = '2026-01-01T10:08:00Z'
                conclusion = 'success'
                event = 'pull_request'
                pull_requests = @(@{ number = 123 })
                head_branch = 'feature-branch'
            }
            
            $overlaps = Get-OverlappingRuns -Runs @($run1, $run2)
            
            $overlaps.Count | Should -Be 1
            $overlaps[0].Run1Cancelled | Should -Be $true
            $overlaps[0].IsRaceCondition | Should -Be $false
        }
        
        It "Identifies parallel runs (race condition)" {
            $run1 = @{
                id = 1
                name = 'ai-pr-quality-gate'
                created_at = '2026-01-01T10:00:00Z'
                updated_at = '2026-01-01T10:05:00Z'
                conclusion = 'success'
                event = 'pull_request'
                pull_requests = @(@{ number = 123 })
                head_branch = 'feature-branch'
            }
            
            $run2 = @{
                id = 2
                name = 'ai-pr-quality-gate'
                created_at = '2026-01-01T10:03:00Z'
                updated_at = '2026-01-01T10:08:00Z'
                conclusion = 'success'
                event = 'pull_request'
                pull_requests = @(@{ number = 123 })
                head_branch = 'feature-branch'
            }
            
            $overlaps = Get-OverlappingRuns -Runs @($run1, $run2)
            
            $overlaps.Count | Should -Be 1
            $overlaps[0].Run1Cancelled | Should -Be $false
            $overlaps[0].Run2Cancelled | Should -Be $false
            $overlaps[0].IsRaceCondition | Should -Be $true
        }
    }
    
    Context "Metrics Calculation" {
        It "Calculates coalescing effectiveness correctly with 90% success" {
            $runs = @(
                @{ id = 1; conclusion = 'cancelled'; created_at = '2026-01-01T10:00:00Z'; updated_at = '2026-01-01T10:05:00Z' }
                @{ id = 2; conclusion = 'cancelled'; created_at = '2026-01-01T10:00:00Z'; updated_at = '2026-01-01T10:05:00Z' }
                @{ id = 3; conclusion = 'cancelled'; created_at = '2026-01-01T10:00:00Z'; updated_at = '2026-01-01T10:05:00Z' }
                @{ id = 4; conclusion = 'cancelled'; created_at = '2026-01-01T10:00:00Z'; updated_at = '2026-01-01T10:05:00Z' }
                @{ id = 5; conclusion = 'cancelled'; created_at = '2026-01-01T10:00:00Z'; updated_at = '2026-01-01T10:05:00Z' }
                @{ id = 6; conclusion = 'cancelled'; created_at = '2026-01-01T10:00:00Z'; updated_at = '2026-01-01T10:05:00Z' }
                @{ id = 7; conclusion = 'cancelled'; created_at = '2026-01-01T10:00:00Z'; updated_at = '2026-01-01T10:05:00Z' }
                @{ id = 8; conclusion = 'cancelled'; created_at = '2026-01-01T10:00:00Z'; updated_at = '2026-01-01T10:05:00Z' }
                @{ id = 9; conclusion = 'cancelled'; created_at = '2026-01-01T10:00:00Z'; updated_at = '2026-01-01T10:05:00Z' }
                @{ id = 10; conclusion = 'success'; created_at = '2026-01-01T10:00:00Z'; updated_at = '2026-01-01T10:05:00Z' }
            )
            
            $overlaps = @(
                @{ Run1 = @{ id = 1 }; Run2 = @{ id = 2 }; Run1Cancelled = $true; IsRaceCondition = $false }
                @{ Run1 = @{ id = 2 }; Run2 = @{ id = 3 }; Run1Cancelled = $true; IsRaceCondition = $false }
                @{ Run1 = @{ id = 3 }; Run2 = @{ id = 4 }; Run1Cancelled = $true; IsRaceCondition = $false }
                @{ Run1 = @{ id = 4 }; Run2 = @{ id = 5 }; Run1Cancelled = $true; IsRaceCondition = $false }
                @{ Run1 = @{ id = 5 }; Run2 = @{ id = 6 }; Run1Cancelled = $true; IsRaceCondition = $false }
                @{ Run1 = @{ id = 6 }; Run2 = @{ id = 7 }; Run1Cancelled = $true; IsRaceCondition = $false }
                @{ Run1 = @{ id = 7 }; Run2 = @{ id = 8 }; Run1Cancelled = $true; IsRaceCondition = $false }
                @{ Run1 = @{ id = 8 }; Run2 = @{ id = 9 }; Run1Cancelled = $true; IsRaceCondition = $false }
                @{ Run1 = @{ id = 9 }; Run2 = @{ id = 10 }; Run1Cancelled = $true; IsRaceCondition = $false }
                @{ Run1 = @{ id = 10 }; Run2 = @{ id = 11 }; Run1Cancelled = $false; IsRaceCondition = $true }
            )
            
            $metrics = Get-CoalescingMetrics -Runs $runs -Overlaps $overlaps
            
            $metrics.CoalescingEffectiveness | Should -Be 90
            $metrics.SuccessfulCoalescing | Should -Be 9
            $metrics.RaceConditions | Should -Be 1
        }
        
        It "Handles zero runs gracefully" {
            $runs = @()
            $overlaps = @()
            
            $metrics = Get-CoalescingMetrics -Runs $runs -Overlaps $overlaps
            
            $metrics.TotalRuns | Should -Be 0
            $metrics.CoalescingEffectiveness | Should -Be 0
            $metrics.RaceConditionRate | Should -Be 0
        }
        
        It "Handles 100% effectiveness" {
            $runs = @(
                @{ id = 1; conclusion = 'cancelled'; created_at = '2026-01-01T10:00:00Z'; updated_at = '2026-01-01T10:05:00Z' }
                @{ id = 2; conclusion = 'success'; created_at = '2026-01-01T10:00:00Z'; updated_at = '2026-01-01T10:05:00Z' }
            )
            
            $overlaps = @(
                @{ Run1Cancelled = $true; IsRaceCondition = $false }
            )
            
            $metrics = Get-CoalescingMetrics -Runs $runs -Overlaps $overlaps
            
            $metrics.CoalescingEffectiveness | Should -Be 100
            $metrics.RaceConditions | Should -Be 0
        }
    }
    
    Context "Concurrency Group Extraction" {
        It "Extracts PR-based concurrency group for quality workflow" {
            $run = @{
                name = 'ai-pr-quality-gate'
                event = 'pull_request'
                pull_requests = @(@{ number = 123 })
                head_branch = 'feature-branch'
            }
            
            $group = Get-ConcurrencyGroup -Run $run
            $group | Should -Be 'ai-quality-123'
        }
        
        It "Extracts PR-based concurrency group for spec validation" {
            $run = @{
                name = 'ai-spec-validation'
                event = 'pull_request'
                pull_requests = @(@{ number = 456 })
                head_branch = 'feature-branch'
            }
            
            $group = Get-ConcurrencyGroup -Run $run
            $group | Should -Be 'spec-validation-456'
        }
        
        It "Falls back to workflow name and branch for non-PR events" {
            $run = @{
                name = 'ai-pr-quality-gate'
                event = 'push'
                pull_requests = @()
                head_branch = 'main'
            }
            
            $group = Get-ConcurrencyGroup -Run $run
            $group | Should -Be 'ai-pr-quality-gate-main'
        }
    }
    
    Context "Report Generation" {
        It "Generates valid markdown structure" {
            $metrics = @{
                TotalRuns = 100
                CancelledRuns = 45
                RaceConditions = 5
                SuccessfulCoalescing = 40
                CoalescingEffectiveness = 88.89
                RaceConditionRate = 5.0
                AvgCancellationTime = 3.5
            }
            
            $runs = @(
                @{ name = 'ai-pr-quality-gate'; conclusion = 'success'; created_at = '2026-01-01T10:00:00Z'; updated_at = '2026-01-01T10:05:00Z' }
            )
            
            $overlaps = @()
            
            $workflows = @('ai-pr-quality-gate', 'ai-spec-validation')
            
            $startDate = [DateTime]::Parse('2026-01-01')
            $endDate = [DateTime]::Parse('2026-01-31')
            
            $report = Format-MarkdownReport -Metrics $metrics -Runs $runs -Overlaps $overlaps -StartDate $startDate -EndDate $endDate -Workflows $workflows -Workflows $workflows
            
            $report | Should -Match '# Workflow Run Coalescing Metrics'
            $report | Should -Match '## Report Period'
            $report | Should -Match '## Executive Summary'
            $report | Should -Match 'Coalescing Effectiveness'
            $report | Should -Match '88.89%'
        }
    }
}
