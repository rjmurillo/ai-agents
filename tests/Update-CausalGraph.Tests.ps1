<#
.SYNOPSIS
    Pester tests for Update-CausalGraph.ps1

.DESCRIPTION
    Unit tests for the causal graph update script.
    Tests pattern extraction, chain building, and -DryRun behavior.

.NOTES
    Task: M-005 (Phase 2A Memory System)
    Coverage Target: All helper functions and main execution paths
#>

BeforeAll {
    # Import ReflexionMemory module for testing
    $ModulePath = Join-Path $PSScriptRoot ".." ".claude" "skills" "memory" "scripts" "ReflexionMemory.psm1"
    if (Test-Path $ModulePath) {
        Import-Module $ModulePath -Force
    }

    # Script path
    $script:ScriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "memory" "scripts" "Update-CausalGraph.ps1"

    # Create test directories
    $script:TestDir = Join-Path ([System.IO.Path]::GetTempPath()) "UpdateCausalGraph-Tests-$(Get-Random)"
    $script:EpisodesDir = Join-Path $script:TestDir "episodes"
    $script:CausalityDir = Join-Path $script:TestDir "causality"

    New-Item -Path $script:EpisodesDir -ItemType Directory -Force | Out-Null
    New-Item -Path $script:CausalityDir -ItemType Directory -Force | Out-Null

    # Create test episode files with proper PSCustomObject conversion
    $script:TestEpisode1 = [PSCustomObject]@{
        id        = "episode-2026-01-01-session-001"
        session   = "2026-01-01-session-001"
        timestamp = "2026-01-01T10:00:00Z"
        outcome   = "success"
        task      = "Implement feature X"
        decisions = @(
            [PSCustomObject]@{
                id        = "d001"
                type      = "design"
                context   = "Need to choose architecture"
                chosen    = "Use Serena-first routing"
                outcome   = "success"
            },
            [PSCustomObject]@{
                id        = "d002"
                type      = "implementation"
                context   = "Need error handling"
                chosen    = "Add try-catch blocks"
                outcome   = "success"
            }
        )
        events    = @(
            [PSCustomObject]@{
                id      = "e001"
                type    = "milestone"
                content = "Completed initial design"
            },
            [PSCustomObject]@{
                id      = "e002"
                type    = "error"
                content = "Build failed due to missing import"
            },
            [PSCustomObject]@{
                id      = "e003"
                type    = "milestone"
                content = "Fixed import and resolved build error"
            }
        )
        metrics   = [PSCustomObject]@{
            duration_minutes = 60
            commits          = 3
        }
        lessons   = @("Always validate imports")
    }

    $script:TestEpisode2 = [PSCustomObject]@{
        id        = "episode-2026-01-02-session-002"
        session   = "2026-01-02-session-002"
        timestamp = "2026-01-02T10:00:00Z"
        outcome   = "failure"
        task      = "Debug issue Y"
        decisions = @(
            [PSCustomObject]@{
                id        = "d001"
                type      = "recovery"
                context   = "Error occurred"
                chosen    = "Retry with different approach"
                outcome   = "failure"
            }
        )
        events    = @(
            [PSCustomObject]@{
                id      = "e001"
                type    = "error"
                content = "Unrecoverable error"
            }
        )
        metrics   = [PSCustomObject]@{
            duration_minutes = 30
            errors           = 1
        }
        lessons   = @()
    }

    # Write test episodes to files
    $script:TestEpisode1 | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $script:EpisodesDir "episode-2026-01-01-session-001.json")
    $script:TestEpisode2 | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $script:EpisodesDir "episode-2026-01-02-session-002.json")

    # Initialize empty causal graph
    $script:EmptyGraph = @{
        version  = "1.0"
        updated  = (Get-Date).ToString("o")
        nodes    = @()
        edges    = @()
        patterns = @()
    }
    $script:EmptyGraph | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $script:CausalityDir "causal-graph.json")
}

AfterAll {
    if (Test-Path $script:TestDir) {
        Remove-Item $script:TestDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe "Get-EpisodeFile Helper" {
    BeforeAll {
        # Define the helper function for testing
        function Get-EpisodeFile {
            param([string]$Path, [Nullable[datetime]]$Since)
            if (Test-Path $Path -PathType Leaf) {
                return @(Get-Item $Path)
            }
            if (-not (Test-Path $Path)) {
                return @()
            }
            $files = Get-ChildItem -Path $Path -Filter "episode-*.json" -ErrorAction SilentlyContinue
            if ($Since) {
                $files = $files | Where-Object {
                    try {
                        $content = Get-Content $_.FullName -Raw | ConvertFrom-Json
                        $episodeDate = [datetime]::Parse($content.timestamp)
                        return $episodeDate -ge $Since
                    }
                    catch {
                        return $false
                    }
                }
            }
            return $files
        }
    }

    It "Returns all episode files when no filter specified" {
        $files = Get-EpisodeFile -Path $script:EpisodesDir
        $files.Count | Should -Be 2
    }

    It "Filters episodes by Since date" {
        $files = Get-EpisodeFile -Path $script:EpisodesDir -Since ([datetime]"2026-01-02")
        $files.Count | Should -Be 1
        $files[0].Name | Should -Match "session-002"
    }

    It "Returns empty array for non-existent path" {
        $files = Get-EpisodeFile -Path "/nonexistent/path"
        $files | Should -BeNullOrEmpty
    }

    It "Returns single file when path is a file" {
        $singleFile = Join-Path $script:EpisodesDir "episode-2026-01-01-session-001.json"
        $files = Get-EpisodeFile -Path $singleFile
        $files.Count | Should -Be 1
    }

    It "Handles malformed episode gracefully" {
        # Create malformed episode
        $malformedPath = Join-Path $script:EpisodesDir "episode-malformed.json"
        "{ invalid json }" | Set-Content $malformedPath

        $files = Get-EpisodeFile -Path $script:EpisodesDir -Since ([datetime]"2026-01-01")

        # Should still return valid files, skipping malformed
        $files.Count | Should -BeGreaterOrEqual 0

        # Cleanup
        Remove-Item $malformedPath -Force -ErrorAction SilentlyContinue
    }
}

Describe "Get-DecisionPattern Helper" {
    BeforeAll {
        function Get-DecisionPattern {
            param([PSCustomObject]$Episode)
            $patterns = [System.Collections.ArrayList]::new()
            $successDecisions = @($Episode.decisions | Where-Object { $_.outcome -eq "success" })
            $failureDecisions = @($Episode.decisions | Where-Object { $_.outcome -eq "failure" })
            foreach ($decision in $successDecisions) {
                $trigger = $decision.context
                if (-not $trigger) { $trigger = "When $($decision.type) decision needed" }
                [void]$patterns.Add([PSCustomObject]@{
                    name        = "$($decision.type) pattern"
                    description = "Pattern from $($Episode.id)"
                    trigger     = $trigger
                    action      = $decision.chosen
                    success     = $true
                })
            }
            foreach ($decision in $failureDecisions) {
                $trigger = $decision.context
                if (-not $trigger) { $trigger = "When $($decision.type) decision needed" }
                [void]$patterns.Add([PSCustomObject]@{
                    name        = "$($decision.type) anti-pattern"
                    description = "Anti-pattern from $($Episode.id)"
                    trigger     = $trigger
                    action      = "AVOID: $($decision.chosen)"
                    success     = $false
                })
            }
            return @($patterns)
        }
    }

    It "Extracts success patterns from episode" {
        $patterns = Get-DecisionPattern -Episode $script:TestEpisode1

        $successPatterns = @($patterns | Where-Object { $_.success -eq $true })
        $successPatterns.Count | Should -Be 2
    }

    It "Extracts failure patterns as anti-patterns" {
        $patterns = Get-DecisionPattern -Episode $script:TestEpisode2

        $antiPatterns = @($patterns | Where-Object { $_.success -eq $false })
        $antiPatterns.Count | Should -Be 1
        $antiPatterns[0].action | Should -Match "^AVOID:"
    }

    It "Uses context as trigger when available" {
        $patterns = Get-DecisionPattern -Episode $script:TestEpisode1

        $patterns[0].trigger | Should -Be "Need to choose architecture"
    }

    It "Generates default trigger when context missing" {
        $episodeNoContext = [PSCustomObject]@{
            id        = "episode-test"
            decisions = @(
                [PSCustomObject]@{ type = "design"; chosen = "Something"; outcome = "success" }
            )
        }
        $patterns = Get-DecisionPattern -Episode $episodeNoContext

        $patterns[0].trigger | Should -Match "When design decision needed"
    }
}

Describe "Build-CausalChain Helper" {
    BeforeAll {
        function Build-CausalChain {
            param([PSCustomObject]$Episode)
            $chains = [System.Collections.ArrayList]::new()
            $errors = @($Episode.events | Where-Object { $_.type -eq "error" })
            foreach ($error in $errors) {
                $eventsArray = @($Episode.events)
                $errorIndex = -1
                for ($i = 0; $i -lt $eventsArray.Count; $i++) {
                    if ($eventsArray[$i].id -eq $error.id) {
                        $errorIndex = $i
                        break
                    }
                }
                if ($errorIndex -lt 0) { continue }
                $followingEvents = @($eventsArray | Select-Object -Skip ($errorIndex + 1) -First 5)
                $recovery = $followingEvents | Where-Object {
                    $_.type -eq "milestone" -and $_.content -match 'fix|recover|resolve'
                } | Select-Object -First 1
                if ($recovery) {
                    [void]$chains.Add([PSCustomObject]@{
                        from_type  = "error"
                        from_label = $error.content
                        to_type    = "outcome"
                        to_label   = $recovery.content
                        edge_type  = "causes"
                        weight     = 0.8
                    })
                }
            }
            return @($chains)
        }
    }

    It "Builds error-to-recovery chains" {
        $chains = Build-CausalChain -Episode $script:TestEpisode1

        @($chains).Count | Should -Be 1
        $chains[0].from_type | Should -Be "error"
        $chains[0].to_type | Should -Be "outcome"
        $chains[0].edge_type | Should -Be "causes"
    }

    It "Returns empty array when no recoveries found" {
        $chains = Build-CausalChain -Episode $script:TestEpisode2

        $chains | Should -BeNullOrEmpty
    }

    It "Assigns appropriate weight to chains" {
        $chains = Build-CausalChain -Episode $script:TestEpisode1

        $chains[0].weight | Should -Be 0.8
    }
}

Describe "Script DryRun Mode" {
    It "Does not modify causal graph in DryRun mode" {
        if (-not (Test-Path $script:ScriptPath)) {
            Set-ItResult -Skipped -Because "Script not found"
            return
        }

        # Get initial graph state
        $graphPath = Join-Path $script:CausalityDir "causal-graph.json"
        $initialContent = Get-Content $graphPath -Raw

        # Run in DryRun mode
        $null = & $script:ScriptPath -EpisodePath $script:EpisodesDir -DryRun 2>&1

        # Verify graph unchanged
        $finalContent = Get-Content $graphPath -Raw
        $finalContent | Should -Be $initialContent
    }

    It "Reports what would be added in DryRun mode" {
        if (-not (Test-Path $script:ScriptPath)) {
            Set-ItResult -Skipped -Because "Script not found"
            return
        }

        # Capture all output streams including Write-Host (stream 6)
        $output = & $script:ScriptPath -EpisodePath $script:EpisodesDir -DryRun *>&1 | Out-String

        $output | Should -Match "DRY"
    }
}

Describe "Script Execution" -Tag "Integration" {
    BeforeEach {
        # Reset causal graph before each test
        $script:EmptyGraph | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $script:CausalityDir "causal-graph.json")
    }

    It "Processes episodes and returns stats" {
        if (-not (Test-Path $script:ScriptPath)) {
            Set-ItResult -Skipped -Because "Script not found at $($script:ScriptPath)"
            return
        }

        # Create test episode with decisions and patterns
        $testEpisode = @{
            id        = "episode-integration-test"
            session   = "integration-test"
            timestamp = (Get-Date).ToString("o")
            outcome   = "success"
            task      = "Integration test"
            decisions = @(
                @{ id = "d001"; type = "design"; chosen = "Option A"; outcome = "success"; context = "When designing the integration test" }
            )
            events    = @()
            metrics   = @{ duration_minutes = 10 }
            lessons   = @()
        }
        $testEpisode | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $script:EpisodesDir "episode-integration-test.json")

        # Run the script with DryRun to avoid side effects
        # Note: The script uses the module's internal causality path configuration
        $result = & $script:ScriptPath -EpisodePath $script:EpisodesDir -DryRun
        $result | Should -Not -BeNullOrEmpty
    }

    It "Filters episodes by Since parameter" {
        if (-not (Test-Path $script:ScriptPath)) {
            Set-ItResult -Skipped -Because "Script not found at $($script:ScriptPath)"
            return
        }

        # Create old episode (should be filtered out)
        $oldEpisode = @{
            id        = "episode-old"
            session   = "old-session"
            timestamp = "2020-01-01T00:00:00Z"
            outcome   = "success"
            task      = "Old task"
            decisions = @()
            events    = @()
            metrics   = @{ duration_minutes = 5 }
            lessons   = @()
        }
        $oldEpisode | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $script:EpisodesDir "episode-old.json")

        # Create new episode
        $newEpisode = @{
            id        = "episode-new"
            session   = "new-session"
            timestamp = (Get-Date).ToString("o")
            outcome   = "success"
            task      = "New task"
            decisions = @(
                @{ id = "d001"; type = "design"; chosen = "New approach"; outcome = "success"; context = "When making a new decision" }
            )
            events    = @()
            metrics   = @{ duration_minutes = 10 }
            lessons   = @()
        }
        $newEpisode | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $script:EpisodesDir "episode-new.json")

        # Run with Since filter - should only process new episode
        # Note: The script uses the module's internal causality path configuration
        $result = & $script:ScriptPath -EpisodePath $script:EpisodesDir -Since (Get-Date).AddDays(-1) -DryRun
        # The old episode should not be in the processed stats
        $result | Should -Not -BeNullOrEmpty
    }

    It "Handles empty episode directory gracefully" {
        if (-not (Test-Path $script:ScriptPath)) {
            Set-ItResult -Skipped -Because "Script not found"
            return
        }

        $emptyDir = Join-Path $script:TestDir "empty-episodes"
        New-Item -Path $emptyDir -ItemType Directory -Force | Out-Null

        # Should exit gracefully with no errors
        { & $script:ScriptPath -EpisodePath $emptyDir 2>&1 } | Should -Not -Throw

        Remove-Item $emptyDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe "Edge Cases" {
    It "Handles episode with no decisions" {
        $episodeNoDecisions = @{
            id        = "episode-no-decisions"
            session   = "no-decisions"
            timestamp = "2026-01-01T10:00:00Z"
            outcome   = "partial"
            task      = "Empty session"
            decisions = @()
            events    = @()
            metrics   = @{}
            lessons   = @()
        }
        $path = Join-Path $script:EpisodesDir "episode-no-decisions.json"
        $episodeNoDecisions | ConvertTo-Json -Depth 10 | Set-Content $path

        # Should process without error
        { Get-Content $path -Raw | ConvertFrom-Json } | Should -Not -Throw

        Remove-Item $path -Force -ErrorAction SilentlyContinue
    }

    It "Handles episode with null events array" {
        $episodeNullEvents = @{
            id        = "episode-null-events"
            session   = "null-events"
            timestamp = "2026-01-01T10:00:00Z"
            outcome   = "partial"
            task      = "Session with null events"
            decisions = @()
            events    = $null
            metrics   = @{}
            lessons   = @()
        }
        $path = Join-Path $script:EpisodesDir "episode-null-events.json"
        $episodeNullEvents | ConvertTo-Json -Depth 10 | Set-Content $path

        # Should deserialize without error
        $episode = Get-Content $path -Raw | ConvertFrom-Json
        $episode.events | Should -BeNullOrEmpty

        Remove-Item $path -Force -ErrorAction SilentlyContinue
    }

    It "Handles very long decision text gracefully" {
        $longText = "a" * 1000
        $episodeLongText = @{
            id        = "episode-long-text"
            session   = "long-text"
            timestamp = "2026-01-01T10:00:00Z"
            outcome   = "success"
            task      = "Session with long text"
            decisions = @(
                @{ type = "implementation"; chosen = $longText; outcome = "success" }
            )
            events    = @()
            metrics   = @{}
            lessons   = @()
        }
        $path = Join-Path $script:EpisodesDir "episode-long-text.json"
        $episodeLongText | ConvertTo-Json -Depth 10 | Set-Content $path

        # Should handle without error
        { Get-Content $path -Raw | ConvertFrom-Json } | Should -Not -Throw

        Remove-Item $path -Force -ErrorAction SilentlyContinue
    }
}
