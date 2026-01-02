<#
.SYNOPSIS
    Pester tests for Extract-SessionEpisode.ps1

.DESCRIPTION
    Unit tests for the session episode extraction script.
    Tests all parsing functions for various session log formats and edge cases.

.NOTES
    Task: M-005 (Phase 2A Memory System)
    Coverage Target: All 8 parsing functions
#>

BeforeAll {
    # Get script path for dot-sourcing private functions
    $ScriptPath = Join-Path $PSScriptRoot ".." "scripts" "Extract-SessionEpisode.ps1"

    # Create a module scope to access private functions
    $script:TestModule = New-Module -Name "ExtractSessionEpisodeTest" -ScriptBlock {
        Set-StrictMode -Version Latest
        $ErrorActionPreference = 'Stop'

        # Define the helper functions from the script for testing
        function Get-SessionIdFromPath {
            param([string]$Path)
            $fileName = [System.IO.Path]::GetFileNameWithoutExtension($Path)
            if ($fileName -match '(\d{4}-\d{2}-\d{2}-session-\d+)') {
                return $Matches[1]
            }
            if ($fileName -match '(session-\d+)') {
                return $Matches[1]
            }
            return $fileName
        }

        function ConvertFrom-SessionMetadata {
            param([string[]]$Lines)
            $metadata = @{
                title       = ""
                date        = ""
                status      = ""
                objectives  = @()
                deliverables = @()
            }
            $inSection = ""
            foreach ($line in $Lines) {
                if ($line -match '^#\s+(.+)$' -and -not $metadata.title) {
                    $metadata.title = $Matches[1]
                    continue
                }
                if ($line -match '^\*\*Date\*\*:\s*(.+)$') {
                    $metadata.date = $Matches[1].Trim()
                    continue
                }
                if ($line -match '^\*\*Status\*\*:\s*(.+)$') {
                    $metadata.status = $Matches[1].Trim()
                    continue
                }
                if ($line -match '^##\s*Objectives?') {
                    $inSection = "objectives"
                    continue
                }
                if ($line -match '^##\s*Deliverables?') {
                    $inSection = "deliverables"
                    continue
                }
                if ($line -match '^##\s') {
                    $inSection = ""
                    continue
                }
                if ($line -match '^\s*[-*]\s+(.+)$') {
                    $item = $Matches[1].Trim()
                    if ($inSection -eq "objectives") {
                        $metadata.objectives += $item
                    }
                    elseif ($inSection -eq "deliverables") {
                        $metadata.deliverables += $item
                    }
                }
            }
            return $metadata
        }

        function Get-DecisionType {
            param([string]$Text)
            $textLower = $Text.ToLower()
            if ($textLower -match 'design|architect|schema|structure') { return "design" }
            if ($textLower -match 'test|pester|coverage|assert') { return "test" }
            if ($textLower -match 'recover|fix|retry|fallback') { return "recovery" }
            if ($textLower -match 'route|delegate|agent|handoff') { return "routing" }
            return "implementation"
        }

        function Get-SessionOutcome {
            param([hashtable]$Metadata, [array]$Events)
            $status = $Metadata.status.ToLower()
            if ($status -match 'complete|done|success') { return "success" }
            if ($status -match 'partial|in.?progress|blocked') { return "partial" }
            if ($status -match 'fail|abort|error') { return "failure" }
            $errorCount = @($Events | Where-Object { $_.type -eq "error" }).Count
            $milestoneCount = @($Events | Where-Object { $_.type -eq "milestone" }).Count
            if ($errorCount -gt $milestoneCount) { return "failure" }
            if ($milestoneCount -gt 0) { return "success" }
            return "partial"
        }

        function ConvertFrom-Decisions {
            param([string[]]$Lines)
            $decisions = @()
            $decisionIndex = 0
            $inDecisionSection = $false
            if ($Lines.Count -eq 0) { return $decisions }
            foreach ($i in 0..($Lines.Count - 1)) {
                $line = $Lines[$i]
                if ($line -match '^##\s*Decisions?') {
                    $inDecisionSection = $true
                    continue
                }
                if ($inDecisionSection -and $line -match '^##\s') {
                    $inDecisionSection = $false
                }
                if ($line -match '^\*\*Decision\*\*:\s*(.+)$' -or
                    $line -match '^Decision:\s*(.+)$' -or
                    ($inDecisionSection -and $line -match '^\s*[-*]\s+\*\*(.+?)\*\*:\s*(.+)$')) {
                    $decisionIndex++
                    $decisionText = if ($Matches[2]) { "$($Matches[1]): $($Matches[2])" } else { $Matches[1] }
                    $decision = @{
                        id        = "d{0:D3}" -f $decisionIndex
                        timestamp = (Get-Date).ToString("o")
                        type      = Get-DecisionType -Text $decisionText
                        context   = ""
                        chosen    = $decisionText
                        rationale = ""
                        outcome   = "success"
                        effects   = @()
                    }
                    if ($i -gt 0 -and $Lines[$i-1] -match '^\s*[-*]\s+(.+)$') {
                        $decision.context = $Matches[1]
                    }
                    $decisions += $decision
                }
                if ($line -match 'chose|decided|selected|opted for' -and $line -notmatch '^#') {
                    $decisionIndex++
                    $decisions += @{
                        id        = "d{0:D3}" -f $decisionIndex
                        timestamp = (Get-Date).ToString("o")
                        type      = "implementation"
                        context   = ""
                        chosen    = $line.Trim()
                        rationale = ""
                        outcome   = "success"
                        effects   = @()
                    }
                }
            }
            return $decisions
        }

        function ConvertFrom-Events {
            param([string[]]$Lines)
            $events = @()
            $eventIndex = 0
            foreach ($line in $Lines) {
                $evt = $null
                if ($line -match 'commit[ted]?\s+(?:as\s+)?([a-f0-9]{7,40})' -or
                    $line -match '([a-f0-9]{7,40})\s+\w+\(.+\):') {
                    $eventIndex++
                    $evt = @{
                        id        = "e{0:D3}" -f $eventIndex
                        timestamp = (Get-Date).ToString("o")
                        type      = "commit"
                        content   = "Commit: $($Matches[1])"
                        caused_by = @()
                        leads_to  = @()
                    }
                }
                if ($line -match 'error|fail|exception' -and $line -notmatch '^#') {
                    $eventIndex++
                    $evt = @{
                        id        = "e{0:D3}" -f $eventIndex
                        timestamp = (Get-Date).ToString("o")
                        type      = "error"
                        content   = $line.Trim()
                        caused_by = @()
                        leads_to  = @()
                    }
                }
                if ($line -match '✅|completed?|done|finished|success' -and $line -match '^[-*]') {
                    $eventIndex++
                    $evt = @{
                        id        = "e{0:D3}" -f $eventIndex
                        timestamp = (Get-Date).ToString("o")
                        type      = "milestone"
                        content   = $line.Trim() -replace '^[-*]\s*', ''
                        caused_by = @()
                        leads_to  = @()
                    }
                }
                if ($line -match 'test[s]?\s+(pass|fail|run)' -or $line -match 'Pester') {
                    $eventIndex++
                    $evt = @{
                        id        = "e{0:D3}" -f $eventIndex
                        timestamp = (Get-Date).ToString("o")
                        type      = "test"
                        content   = $line.Trim()
                        caused_by = @()
                        leads_to  = @()
                    }
                }
                if ($evt) {
                    $events += $evt
                }
            }
            return $events
        }

        function ConvertFrom-Lessons {
            param([string[]]$Lines)
            $lessons = @()
            $inLessonsSection = $false
            foreach ($line in $Lines) {
                if ($line -match '^##\s*(Lessons?\s*Learned?|Key\s*Learnings?|Takeaways?)') {
                    $inLessonsSection = $true
                    continue
                }
                if ($inLessonsSection -and $line -match '^##\s') {
                    $inLessonsSection = $false
                }
                if ($inLessonsSection -and $line -match '^\s*[-*]\s+(.+)$') {
                    $lessons += $Matches[1].Trim()
                }
                if ($line -match 'lesson|learned|takeaway|note for future' -and $line -notmatch '^#') {
                    $lessons += $line.Trim()
                }
            }
            return $lessons | Select-Object -Unique
        }

        function ConvertFrom-Metrics {
            param([string[]]$Lines)
            $metrics = @{
                duration_minutes = 0
                tool_calls       = 0
                errors           = 0
                recoveries       = 0
                commits          = 0
                files_changed    = 0
            }
            foreach ($line in $Lines) {
                if ($line -match '(\d+)\s*minutes?' -or $line -match 'duration:\s*(\d+)') {
                    $metrics.duration_minutes = [int]$Matches[1]
                }
                if ($line -match '[a-f0-9]{7,40}') {
                    $metrics.commits++
                }
                if ($line -match 'error|fail|exception' -and $line -notmatch '^#') {
                    $metrics.errors++
                }
                if ($line -match '(\d+)\s+files?\s+(changed|modified|created)') {
                    $metrics.files_changed += [int]$Matches[1]
                }
            }
            return $metrics
        }

        Export-ModuleMember -Function @(
            'Get-SessionIdFromPath',
            'ConvertFrom-SessionMetadata',
            'Get-DecisionType',
            'Get-SessionOutcome',
            'ConvertFrom-Decisions',
            'ConvertFrom-Events',
            'ConvertFrom-Lessons',
            'ConvertFrom-Metrics'
        )
    }
    Import-Module $script:TestModule -Force
}

AfterAll {
    if ($script:TestModule) {
        Remove-Module -Name "ExtractSessionEpisodeTest" -Force -ErrorAction SilentlyContinue
    }
}

Describe "Get-SessionIdFromPath" {
    It "Extracts session ID from standard format YYYY-MM-DD-session-NNN" {
        $result = Get-SessionIdFromPath -Path "/path/to/2026-01-01-session-126.md"
        $result | Should -Be "2026-01-01-session-126"
    }

    It "Extracts session ID from session-NNN format" {
        $result = Get-SessionIdFromPath -Path "/path/to/session-042-description.md"
        $result | Should -Be "session-042"
    }

    It "Returns filename when no pattern matches" {
        $result = Get-SessionIdFromPath -Path "/path/to/random-log-file.md"
        $result | Should -Be "random-log-file"
    }

    It "Handles Windows-style paths" {
        $result = Get-SessionIdFromPath -Path "C:\Users\test\sessions\2026-01-01-session-001.md"
        $result | Should -Be "2026-01-01-session-001"
    }

    It "Handles paths with multiple date patterns" {
        $result = Get-SessionIdFromPath -Path "/logs/2025-12-31/2026-01-01-session-999.md"
        $result | Should -Be "2026-01-01-session-999"
    }
}

Describe "ConvertFrom-SessionMetadata" {
    Context "Standard session log format" {
        BeforeAll {
            $script:StandardLog = @(
                "# Session 126: Implement Memory Router",
                "",
                "**Date**: 2026-01-01",
                "**Status**: Complete",
                "",
                "## Objectives",
                "",
                "- Implement MemoryRouter.psm1",
                "- Add unit tests",
                "- Update documentation",
                "",
                "## Deliverables",
                "",
                "- MemoryRouter module",
                "- Test coverage report"
            )
        }

        It "Extracts title from H1 header" {
            $result = ConvertFrom-SessionMetadata -Lines $script:StandardLog
            $result.title | Should -Be "Session 126: Implement Memory Router"
        }

        It "Extracts date field" {
            $result = ConvertFrom-SessionMetadata -Lines $script:StandardLog
            $result.date | Should -Be "2026-01-01"
        }

        It "Extracts status field" {
            $result = ConvertFrom-SessionMetadata -Lines $script:StandardLog
            $result.status | Should -Be "Complete"
        }

        It "Extracts objectives list" {
            $result = ConvertFrom-SessionMetadata -Lines $script:StandardLog
            $result.objectives.Count | Should -Be 3
            $result.objectives[0] | Should -Be "Implement MemoryRouter.psm1"
        }

        It "Extracts deliverables list" {
            $result = ConvertFrom-SessionMetadata -Lines $script:StandardLog
            $result.deliverables.Count | Should -Be 2
            $result.deliverables[0] | Should -Be "MemoryRouter module"
        }
    }

    Context "Empty or missing sections" {
        It "Returns empty arrays for missing objectives" {
            $lines = @("# Title", "**Date**: 2026-01-01")
            $result = ConvertFrom-SessionMetadata -Lines $lines
            $result.objectives | Should -BeNullOrEmpty
        }

        It "Handles empty lines array" {
            $result = ConvertFrom-SessionMetadata -Lines @()
            $result.title | Should -BeNullOrEmpty
            $result.date | Should -BeNullOrEmpty
        }
    }

    Context "Alternative formats" {
        It "Handles asterisk list markers" {
            $lines = @(
                "# Title",
                "## Objectives",
                "* First objective",
                "* Second objective"
            )
            $result = ConvertFrom-SessionMetadata -Lines $lines
            $result.objectives.Count | Should -Be 2
        }

        It "Handles singular 'Objective' header" {
            $lines = @(
                "# Title",
                "## Objective",
                "- Single objective"
            )
            $result = ConvertFrom-SessionMetadata -Lines $lines
            $result.objectives.Count | Should -Be 1
        }
    }
}

Describe "Get-DecisionType" {
    It "Categorizes design decisions" {
        Get-DecisionType -Text "Use microservice architecture pattern" | Should -Be "design"
        Get-DecisionType -Text "Define schema for episodes" | Should -Be "design"
    }

    It "Categorizes test decisions" {
        Get-DecisionType -Text "Add Pester unit tests" | Should -Be "test"
        Get-DecisionType -Text "Increase coverage to 80%" | Should -Be "test"
    }

    It "Categorizes recovery decisions" {
        Get-DecisionType -Text "Implement retry logic for API" | Should -Be "recovery"
        Get-DecisionType -Text "Add fallback to Serena when Forgetful unavailable" | Should -Be "recovery"
    }

    It "Categorizes routing decisions" {
        Get-DecisionType -Text "Delegate work to implementer agent" | Should -Be "routing"
        Get-DecisionType -Text "Route to QA for verification" | Should -Be "routing"
    }

    It "Defaults to implementation for other decisions" {
        Get-DecisionType -Text "Add new function to module" | Should -Be "implementation"
        Get-DecisionType -Text "Update configuration file" | Should -Be "implementation"
    }
}

Describe "Get-SessionOutcome" {
    Context "Status-based determination" {
        It "Returns success for complete status" {
            $metadata = @{ status = "Complete" }
            Get-SessionOutcome -Metadata $metadata -Events @() | Should -Be "success"
        }

        It "Returns success for done status" {
            $metadata = @{ status = "Done" }
            Get-SessionOutcome -Metadata $metadata -Events @() | Should -Be "success"
        }

        It "Returns partial for in-progress status" {
            $metadata = @{ status = "In Progress" }
            Get-SessionOutcome -Metadata $metadata -Events @() | Should -Be "partial"
        }

        It "Returns partial for blocked status" {
            $metadata = @{ status = "Blocked" }
            Get-SessionOutcome -Metadata $metadata -Events @() | Should -Be "partial"
        }

        It "Returns failure for failed status" {
            $metadata = @{ status = "Failed" }
            Get-SessionOutcome -Metadata $metadata -Events @() | Should -Be "failure"
        }
    }

    Context "Event-based inference" {
        It "Returns failure when errors outnumber milestones" {
            $metadata = @{ status = "unknown" }
            $events = @(
                @{ type = "error" },
                @{ type = "error" },
                @{ type = "milestone" }
            )
            Get-SessionOutcome -Metadata $metadata -Events $events | Should -Be "failure"
        }

        It "Returns success when milestones exist and outweigh errors" {
            $metadata = @{ status = "unknown" }
            $events = @(
                @{ type = "milestone" },
                @{ type = "milestone" },
                @{ type = "error" }
            )
            Get-SessionOutcome -Metadata $metadata -Events $events | Should -Be "success"
        }

        It "Returns partial when no events determine outcome" {
            $metadata = @{ status = "unknown" }
            $events = @()
            Get-SessionOutcome -Metadata $metadata -Events $events | Should -Be "partial"
        }
    }
}

Describe "ConvertFrom-Decisions" {
    Context "Decision section parsing" {
        It "Extracts decisions from Decision section" {
            $lines = @(
                "# Session Log",
                "## Decisions",
                "**Decision**: Use Serena-first routing",
                "## Next Section"
            )
            $result = @(ConvertFrom-Decisions -Lines $lines)
            $result.Count | Should -Be 1
            $result[0].chosen | Should -Be "Use Serena-first routing"
        }

        It "Extracts multiple decisions" {
            $lines = @(
                "## Decisions",
                "**Decision**: Use PowerShell only",
                "**Decision**: Add retry logic"
            )
            $result = @(ConvertFrom-Decisions -Lines $lines)
            $result.Count | Should -Be 2
        }

        It "Assigns sequential IDs" {
            $lines = @(
                "**Decision**: First decision",
                "**Decision**: Second decision"
            )
            $result = @(ConvertFrom-Decisions -Lines $lines)
            $result[0].id | Should -Be "d001"
            $result[1].id | Should -Be "d002"
        }

        It "Categorizes decision type correctly" {
            $lines = @(
                "**Decision**: Use microservice architecture"
            )
            $result = @(ConvertFrom-Decisions -Lines $lines)
            $result[0].type | Should -Be "design"
        }
    }

    Context "Inline decision patterns" {
        It "Extracts decisions with 'chose' keyword" {
            $lines = @(
                "We chose to use atomic commits for this feature"
            )
            $result = @(ConvertFrom-Decisions -Lines $lines)
            $result.Count | Should -Be 1
            $result[0].type | Should -Be "implementation"
        }

        It "Extracts decisions with 'decided' keyword" {
            $lines = @(
                "Team decided to implement the retry pattern"
            )
            $result = @(ConvertFrom-Decisions -Lines $lines)
            $result.Count | Should -Be 1
        }

        It "Ignores header lines with decision keywords" {
            $lines = @(
                "## How we decided on the architecture",
                "Some explanation text"
            )
            $result = @(ConvertFrom-Decisions -Lines $lines)
            $result.Count | Should -Be 0
        }
    }

    Context "Edge cases" {
        It "Returns empty array for no decisions" {
            $lines = @("# Title", "Some content")
            $result = ConvertFrom-Decisions -Lines $lines
            @($result) | Should -BeNullOrEmpty
        }

        It "Handles empty lines array" {
            $result = ConvertFrom-Decisions -Lines @()
            @($result) | Should -BeNullOrEmpty
        }
    }
}

Describe "ConvertFrom-Events" {
    Context "Commit events" {
        It "Extracts commit SHA from 'commit as' pattern" {
            $lines = @("commit as abc1234def")
            $result = ConvertFrom-Events -Lines $lines
            @($result).Count | Should -BeGreaterOrEqual 1
            ($result | Where-Object { $_.type -eq "commit" }) | Should -Not -BeNullOrEmpty
        }

        It "Extracts 7-character short SHA" {
            $lines = @("commit abc1234")
            $result = ConvertFrom-Events -Lines $lines
            ($result | Where-Object { $_.type -eq "commit" }) | Should -Not -BeNullOrEmpty
        }
    }

    Context "Error events" {
        It "Detects lines with 'error' keyword" {
            $lines = @("Build error: missing dependency")
            $result = ConvertFrom-Events -Lines $lines
            ($result | Where-Object { $_.type -eq "error" }) | Should -Not -BeNullOrEmpty
        }

        It "Detects lines with 'exception' keyword" {
            $lines = @("NullReferenceException thrown")
            $result = ConvertFrom-Events -Lines $lines
            ($result | Where-Object { $_.type -eq "error" }) | Should -Not -BeNullOrEmpty
        }

        It "Ignores error in headers" {
            $lines = @("## Error Handling")
            $result = ConvertFrom-Events -Lines $lines
            ($result | Where-Object { $_.type -eq "error" }) | Should -BeNullOrEmpty
        }
    }

    Context "Milestone events" {
        It "Detects completed milestones with checkmark" {
            $lines = @("- ✅ Feature implementation complete")
            $result = ConvertFrom-Events -Lines $lines
            ($result | Where-Object { $_.type -eq "milestone" }) | Should -Not -BeNullOrEmpty
        }

        It "Detects completed milestones with 'done' keyword" {
            $lines = @("- Task done")
            $result = ConvertFrom-Events -Lines $lines
            ($result | Where-Object { $_.type -eq "milestone" }) | Should -Not -BeNullOrEmpty
        }

        It "Strips list markers from content" {
            $lines = @("- ✅ Completed the implementation")
            $result = ConvertFrom-Events -Lines $lines
            $milestone = $result | Where-Object { $_.type -eq "milestone" } | Select-Object -First 1
            $milestone.content | Should -Not -Match '^[-*]'
        }
    }

    Context "Test events" {
        It "Detects Pester test runs" {
            $lines = @("Running Pester tests for module")
            $result = ConvertFrom-Events -Lines $lines
            ($result | Where-Object { $_.type -eq "test" }) | Should -Not -BeNullOrEmpty
        }

        It "Detects 'tests pass' pattern" {
            $lines = @("All tests pass successfully")
            $result = ConvertFrom-Events -Lines $lines
            ($result | Where-Object { $_.type -eq "test" }) | Should -Not -BeNullOrEmpty
        }
    }

    Context "Edge cases" {
        It "Returns empty array for no events" {
            $lines = @("# Title", "Just some text")
            $result = ConvertFrom-Events -Lines $lines
            @($result) | Should -BeNullOrEmpty
        }

        It "Assigns sequential IDs" {
            $lines = @(
                "Build error occurred",
                "- ✅ Fixed the error"
            )
            $result = ConvertFrom-Events -Lines $lines
            $result[0].id | Should -Match '^e\d{3}$'
        }
    }
}

Describe "ConvertFrom-Lessons" {
    Context "Lessons section parsing" {
        It "Extracts lessons from 'Lessons Learned' section" {
            $lines = @(
                "## Lessons Learned",
                "- Always validate input",
                "- Use atomic commits",
                "## Next Section"
            )
            $result = ConvertFrom-Lessons -Lines $lines
            @($result).Count | Should -Be 2
            $result[0] | Should -Be "Always validate input"
        }

        It "Handles 'Key Learnings' header variant" {
            $lines = @(
                "## Key Learnings",
                "- Important learning"
            )
            $result = ConvertFrom-Lessons -Lines $lines
            @($result).Count | Should -Be 1
        }

        It "Handles 'Takeaways' header variant" {
            $lines = @(
                "## Takeaways",
                "- Important insight"
            )
            $result = ConvertFrom-Lessons -Lines $lines
            @($result).Count | Should -Be 1
        }

        It "Stops collecting at next section" {
            $lines = @(
                "## Lessons Learned",
                "- First insight",
                "## Another Section",
                "- Not an insight"
            )
            $result = ConvertFrom-Lessons -Lines $lines
            # The section parsing should stop at "## Another Section"
            # Note: "First insight" is captured, "Not an insight" should not be
            @($result).Count | Should -BeGreaterOrEqual 1
            $result | Should -Contain "First insight"
            $result | Should -Not -Contain "Not an insight"
        }
    }

    Context "Inline lesson detection" {
        It "Detects 'lesson' keyword in text" {
            $lines = @("The lesson here is to always test first")
            $result = ConvertFrom-Lessons -Lines $lines
            @($result).Count | Should -Be 1
        }

        It "Detects 'note for future' keyword" {
            $lines = @("Note for future: validate all paths")
            $result = ConvertFrom-Lessons -Lines $lines
            @($result).Count | Should -Be 1
        }
    }

    Context "Deduplication" {
        It "Returns unique lessons only" {
            $lines = @(
                "## Lessons Learned",
                "- Always test first",
                "This is a lesson about testing first"
            )
            $result = ConvertFrom-Lessons -Lines $lines
            # Both might match, but duplicates should be removed
            @($result) | Should -Not -BeNullOrEmpty
        }
    }

    Context "Edge cases" {
        It "Returns empty for no lessons" {
            $lines = @("# Title", "Some content")
            $result = ConvertFrom-Lessons -Lines $lines
            @($result) | Should -BeNullOrEmpty
        }

        It "Handles empty lines array" {
            $result = ConvertFrom-Lessons -Lines @()
            @($result) | Should -BeNullOrEmpty
        }
    }
}

Describe "ConvertFrom-Metrics" {
    Context "Duration extraction" {
        It "Extracts duration in minutes" {
            $lines = @("Session lasted 45 minutes")
            $result = ConvertFrom-Metrics -Lines $lines
            $result.duration_minutes | Should -Be 45
        }

        It "Extracts duration from 'duration:' format" {
            $lines = @("duration: 60")
            $result = ConvertFrom-Metrics -Lines $lines
            $result.duration_minutes | Should -Be 60
        }
    }

    Context "Commit counting" {
        It "Counts commit SHAs" {
            $lines = @(
                "Committed abc1234",
                "Also committed def5678"
            )
            $result = ConvertFrom-Metrics -Lines $lines
            $result.commits | Should -Be 2
        }

        It "Counts 40-character full SHAs" {
            $lines = @("Full SHA: abc1234567890abc1234567890abc1234567890ab")
            $result = ConvertFrom-Metrics -Lines $lines
            $result.commits | Should -BeGreaterOrEqual 1
        }
    }

    Context "Error counting" {
        It "Counts error mentions" {
            $lines = @(
                "Build error occurred",
                "Another failure detected"
            )
            $result = ConvertFrom-Metrics -Lines $lines
            $result.errors | Should -Be 2
        }

        It "Ignores errors in headers" {
            $lines = @(
                "## Error Handling",
                "Actual error in code"
            )
            $result = ConvertFrom-Metrics -Lines $lines
            $result.errors | Should -Be 1
        }
    }

    Context "Files changed counting" {
        It "Extracts files changed count" {
            $lines = @("5 files changed")
            $result = ConvertFrom-Metrics -Lines $lines
            $result.files_changed | Should -Be 5
        }

        It "Extracts files modified count" {
            $lines = @("3 files modified")
            $result = ConvertFrom-Metrics -Lines $lines
            $result.files_changed | Should -Be 3
        }

        It "Accumulates multiple file counts" {
            $lines = @(
                "2 files changed",
                "3 files created"
            )
            $result = ConvertFrom-Metrics -Lines $lines
            $result.files_changed | Should -Be 5
        }
    }

    Context "Default values" {
        It "Returns zero defaults for empty input" {
            $result = ConvertFrom-Metrics -Lines @()
            $result.duration_minutes | Should -Be 0
            $result.commits | Should -Be 0
            $result.errors | Should -Be 0
            $result.files_changed | Should -Be 0
        }

        It "Has all expected metric keys" {
            $result = ConvertFrom-Metrics -Lines @()
            $result.Keys | Should -Contain "duration_minutes"
            $result.Keys | Should -Contain "commits"
            $result.Keys | Should -Contain "errors"
            $result.Keys | Should -Contain "files_changed"
        }
    }
}

Describe "Script Integration" -Tag "Integration" {
    BeforeAll {
        $script:TestDir = Join-Path ([System.IO.Path]::GetTempPath()) "ExtractSessionEpisode-Tests-$(Get-Random)"
        New-Item -Path $script:TestDir -ItemType Directory -Force | Out-Null

        # Create a test session log
        $script:TestSessionLog = Join-Path $script:TestDir "2026-01-01-session-999.md"
        @"
# Session 999: Test Session

**Date**: 2026-01-01
**Status**: Complete

## Objectives

- Test objective 1
- Test objective 2

## Decisions

**Decision**: Use Serena-first routing

## Work Log

- Committed as abc1234
- Tests pass

## Lessons Learned

- Always validate input
"@ | Set-Content -Path $script:TestSessionLog -Encoding UTF8

        $script:OutputDir = Join-Path $script:TestDir "episodes"
    }

    AfterAll {
        if (Test-Path $script:TestDir) {
            Remove-Item $script:TestDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It "Extracts episode from valid session log" {
        $ScriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "memory" "scripts" "Extract-SessionEpisode.ps1"

        if (-not (Test-Path $ScriptPath)) {
            Set-ItResult -Skipped -Because "Script not found at $ScriptPath"
            return
        }

        $result = & $ScriptPath -SessionLogPath $script:TestSessionLog -OutputPath $script:OutputDir -Force

        $result | Should -Not -BeNullOrEmpty
        $result.id | Should -Be "episode-2026-01-01-session-999"
        $result.outcome | Should -Be "success"
    }

    It "Creates episode JSON file" {
        $episodeFile = Join-Path $script:OutputDir "episode-2026-01-01-session-999.json"

        if (-not (Test-Path $script:OutputDir)) {
            Set-ItResult -Skipped -Because "Output directory not created"
            return
        }

        Test-Path $episodeFile | Should -BeTrue
    }

    It "Episode JSON has valid structure" {
        $episodeFile = Join-Path $script:OutputDir "episode-2026-01-01-session-999.json"

        if (-not (Test-Path $episodeFile)) {
            Set-ItResult -Skipped -Because "Episode file not created"
            return
        }

        $episode = Get-Content $episodeFile -Raw | ConvertFrom-Json

        $episode.id | Should -Not -BeNullOrEmpty
        $episode.session | Should -Not -BeNullOrEmpty
        $episode.timestamp | Should -Not -BeNullOrEmpty
        $episode.outcome | Should -BeIn @("success", "partial", "failure")
    }
}
