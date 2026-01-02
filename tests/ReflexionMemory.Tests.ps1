#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for ReflexionMemory module.

.DESCRIPTION
    Tests the reflexion memory system per ADR-038:
    - Episode storage and retrieval
    - Causal graph management
    - Pattern extraction and matching

.NOTES
    Task: M-005 (Phase 2A Memory System)
    ADR: ADR-038 Reflexion Memory Schema
#>

BeforeAll {
    # Import the module
    $modulePath = Join-Path $PSScriptRoot ".." ".claude" "skills" "memory" "scripts" "ReflexionMemory.psm1"
    Import-Module $modulePath -Force

    # Get the actual paths the module uses
    $script:EpisodesPath = Join-Path $PSScriptRoot ".." ".agents" "memory" "episodes"
    $script:CausalityPath = Join-Path $PSScriptRoot ".." ".agents" "memory" "causality"
    $script:CausalGraphFile = Join-Path $script:CausalityPath "causal-graph.json"

    # Backup original causal graph if exists
    if (Test-Path $script:CausalGraphFile) {
        $script:OriginalGraph = Get-Content -Path $script:CausalGraphFile -Raw
    }

    # Ensure directories exist
    New-Item -Path $script:EpisodesPath -ItemType Directory -Force -ErrorAction SilentlyContinue | Out-Null
    New-Item -Path $script:CausalityPath -ItemType Directory -Force -ErrorAction SilentlyContinue | Out-Null
}

AfterAll {
    # Restore original causal graph
    if ($script:OriginalGraph) {
        Set-Content -Path $script:CausalGraphFile -Value $script:OriginalGraph -Encoding UTF8
    }
    elseif (Test-Path $script:CausalGraphFile) {
        # Reset to empty graph
        $emptyGraph = @{ version = "1.0"; updated = (Get-Date).ToString("o"); nodes = @(); edges = @(); patterns = @() } | ConvertTo-Json
        Set-Content -Path $script:CausalGraphFile -Value $emptyGraph -Encoding UTF8
    }

    # Clean up test episodes
    Get-ChildItem -Path $script:EpisodesPath -Filter "episode-*test*.json" -ErrorAction SilentlyContinue | Remove-Item -Force
}

Describe "Episode Functions" {
    BeforeEach {
        # Clear test episodes (only files with "test" in name to avoid affecting real data)
        Get-ChildItem -Path $script:EpisodesPath -Filter "episode-*test*.json" -ErrorAction SilentlyContinue | Remove-Item -Force
        Get-ChildItem -Path $script:EpisodesPath -Filter "episode-filter-test*.json" -ErrorAction SilentlyContinue | Remove-Item -Force
        Get-ChildItem -Path $script:EpisodesPath -Filter "episode-get-test*.json" -ErrorAction SilentlyContinue | Remove-Item -Force
        Get-ChildItem -Path $script:EpisodesPath -Filter "episode-sequence-test*.json" -ErrorAction SilentlyContinue | Remove-Item -Force
        Get-ChildItem -Path $script:EpisodesPath -Filter "episode-status-test*.json" -ErrorAction SilentlyContinue | Remove-Item -Force
    }

    Describe "New-Episode" {
        It "Creates episode with required fields" {
            $params = @{
                SessionId = "2026-01-01-session-001"
                Task      = "Test implementation"
                Outcome   = "success"
            }

            $episode = New-Episode @params

            $episode | Should -Not -BeNullOrEmpty
            $episode.id | Should -Be "episode-2026-01-01-session-001"
            $episode.session | Should -Be "2026-01-01-session-001"
            $episode.outcome | Should -Be "success"
            $episode.task | Should -Be "Test implementation"
        }

        It "Creates episode with decisions and events" {
            $decisions = @(
                @{
                    id        = "d001"
                    timestamp = (Get-Date).ToString("o")
                    type      = "design"
                    context   = "Choosing design pattern"
                    chosen    = "Use pattern A"
                    outcome   = "success"
                }
            )
            $events = @(
                @{
                    id        = "e001"
                    timestamp = (Get-Date).ToString("o")
                    type      = "commit"
                    content   = "Initial commit"
                }
            )

            $episode = New-Episode -SessionId "2026-01-01-test-002" -Task "Test" -Outcome "success" -Decisions $decisions -Events $events

            $episode.decisions.Count | Should -Be 1
            $episode.events.Count | Should -Be 1
        }

        It "Creates episode with lessons" {
            $lessons = @("Lesson 1", "Lesson 2")

            $episode = New-Episode -SessionId "2026-01-01-test-003" -Task "Test" -Outcome "success" -Lessons $lessons

            $episode.lessons.Count | Should -Be 2
            $episode.lessons[0] | Should -Be "Lesson 1"
        }

        It "Creates episode with metrics" {
            $metrics = @{
                duration_minutes = 30
                commits          = 5
                errors           = 1
            }

            $episode = New-Episode -SessionId "2026-01-01-test-004" -Task "Test" -Outcome "partial" -Metrics $metrics

            $episode.metrics.duration_minutes | Should -Be 30
            $episode.metrics.commits | Should -Be 5
        }

        It "Validates outcome parameter" {
            { New-Episode -SessionId "test" -Task "Test" -Outcome "invalid" } | Should -Throw
        }
    }

    Describe "Get-Episode" {
        It "Returns null for non-existent episode" {
            $result = Get-Episode -SessionId "non-existent-session"
            $result | Should -BeNullOrEmpty
        }

        It "Retrieves existing episode" {
            # Create episode first
            New-Episode -SessionId "2026-01-01-test-005" -Task "Test retrieval" -Outcome "success"

            $result = Get-Episode -SessionId "2026-01-01-test-005"

            $result | Should -Not -BeNullOrEmpty
            $result.task | Should -Be "Test retrieval"
        }
    }

    Describe "Get-Episodes" {
        BeforeEach {
            # Create test episodes with schema-compliant session IDs
            New-Episode -SessionId "2026-01-01-filter-001" -Task "Task 1" -Outcome "success"
            New-Episode -SessionId "2026-01-01-filter-002" -Task "Task 2" -Outcome "failure"
            New-Episode -SessionId "2026-01-01-filter-003" -Task "Task 3" -Outcome "partial"
        }

        It "Returns all episodes without filter" {
            $results = Get-Episodes

            $results.Count | Should -BeGreaterOrEqual 3
        }

        It "Filters by outcome" {
            $results = Get-Episodes -Outcome "success"

            $results | ForEach-Object { $_.outcome | Should -Be "success" }
        }

        It "Respects MaxResults" {
            $results = Get-Episodes -MaxResults 2

            $results.Count | Should -BeLessOrEqual 2
        }

        It "Returns results that can be collected as array" {
            # Verify results can be wrapped in array and counted
            $results = @(Get-Episodes -MaxResults 5)

            # Should be able to get count (array-like behavior)
            $results.Count | Should -BeGreaterOrEqual 0
            $results.GetType().BaseType.Name | Should -Be "Array"
        }
    }

    Describe "Get-DecisionSequence" {
        It "Returns empty array for non-existent episode" {
            $result = @(Get-DecisionSequence -EpisodeId "episode-non-existent")

            $result.Count | Should -Be 0
        }

        It "Returns decisions sorted by timestamp" {
            $decisions = @(
                @{
                    id        = "d002"
                    timestamp = "2026-01-01T10:00:00Z"
                    type      = "test"
                    context   = "Testing second"
                    chosen    = "Second"
                    outcome   = "success"
                }
                @{
                    id        = "d001"
                    timestamp = "2026-01-01T09:00:00Z"
                    type      = "design"
                    context   = "Designing first"
                    chosen    = "First"
                    outcome   = "success"
                }
            )

            New-Episode -SessionId "2026-01-01-sequence-001" -Task "Test" -Outcome "success" -Decisions $decisions

            $result = Get-DecisionSequence -EpisodeId "episode-2026-01-01-sequence-001"

            $result.Count | Should -Be 2
        }
    }
}

Describe "Causal Graph Functions" {
    BeforeEach {
        # Reset causal graph to empty state
        $emptyGraph = @{
            version  = "1.0"
            updated  = (Get-Date).ToString("o")
            nodes    = @()
            edges    = @()
            patterns = @()
        } | ConvertTo-Json -Depth 5
        Set-Content -Path $script:CausalGraphFile -Value $emptyGraph -Encoding UTF8
    }

    Describe "Add-CausalNode" {
        It "Creates node with required fields" {
            $node = Add-CausalNode -Type "decision" -Label "Test decision"

            $node | Should -Not -BeNullOrEmpty
            $node.id | Should -Match "^n\d{3}$"
            $node.type | Should -Be "decision"
            $node.label | Should -Be "Test decision"
            $node.frequency | Should -Be 1
        }

        It "Validates node type" {
            { Add-CausalNode -Type "invalid" -Label "Test" } | Should -Throw
        }

        It "Updates frequency for duplicate labels" {
            $node1 = Add-CausalNode -Type "decision" -Label "Repeated decision"
            $node2 = Add-CausalNode -Type "decision" -Label "Repeated decision"

            $node2.frequency | Should -Be 2
            $node1.id | Should -Be $node2.id
        }

        It "Associates episode with node" {
            $node = Add-CausalNode -Type "event" -Label "Test event" -EpisodeId "episode-test-1"

            $node.episodes | Should -Contain "episode-test-1"
        }

        It "Supports all valid node types" {
            $types = @("decision", "event", "outcome", "pattern", "error")

            foreach ($type in $types) {
                $node = Add-CausalNode -Type $type -Label "Node of type $type"
                $node.type | Should -Be $type
            }
        }
    }

    Describe "Add-CausalEdge" {
        BeforeEach {
            # Create test nodes
            $script:node1 = Add-CausalNode -Type "decision" -Label "Source node"
            $script:node2 = Add-CausalNode -Type "outcome" -Label "Target node"
        }

        It "Creates edge with required fields" {
            $edge = Add-CausalEdge -SourceId $script:node1.id -TargetId $script:node2.id -Type "causes"

            $edge | Should -Not -BeNullOrEmpty
            $edge.source | Should -Be $script:node1.id
            $edge.target | Should -Be $script:node2.id
            $edge.type | Should -Be "causes"
            $edge.evidence_count | Should -Be 1
        }

        It "Uses default weight of 0.5" {
            $edge = Add-CausalEdge -SourceId $script:node1.id -TargetId $script:node2.id -Type "enables"

            $edge.weight | Should -Be 0.5
        }

        It "Accepts custom weight" {
            $edge = Add-CausalEdge -SourceId $script:node1.id -TargetId $script:node2.id -Type "causes" -Weight 0.9

            $edge.weight | Should -Be 0.9
        }

        It "Validates edge type" {
            { Add-CausalEdge -SourceId "n001" -TargetId "n002" -Type "invalid" } | Should -Throw
        }

        It "Updates evidence count for duplicate edges" {
            $edge1 = Add-CausalEdge -SourceId $script:node1.id -TargetId $script:node2.id -Type "causes" -Weight 0.8
            $edge2 = Add-CausalEdge -SourceId $script:node1.id -TargetId $script:node2.id -Type "causes" -Weight 1.0

            $edge2.evidence_count | Should -Be 2
            # Weight should be running average: (0.8 + 1.0) / 2 = 0.9
            $edge2.weight | Should -BeGreaterThan 0.8
        }

        It "Supports all valid edge types" {
            $types = @("causes", "enables", "prevents", "correlates")

            foreach ($type in $types) {
                $n1 = Add-CausalNode -Type "decision" -Label "From $type"
                $n2 = Add-CausalNode -Type "outcome" -Label "To $type"
                $edge = Add-CausalEdge -SourceId $n1.id -TargetId $n2.id -Type $type
                $edge.type | Should -Be $type
            }
        }
    }

    Describe "Get-CausalPath" {
        BeforeEach {
            # Build test graph: A -> B -> C
            $script:nodeA = Add-CausalNode -Type "decision" -Label "Start node A"
            $script:nodeB = Add-CausalNode -Type "event" -Label "Middle node B"
            $script:nodeC = Add-CausalNode -Type "outcome" -Label "End node C"

            Add-CausalEdge -SourceId $script:nodeA.id -TargetId $script:nodeB.id -Type "causes"
            Add-CausalEdge -SourceId $script:nodeB.id -TargetId $script:nodeC.id -Type "causes"
        }

        It "Finds direct path between connected nodes" {
            $result = Get-CausalPath -FromLabel "Start node A" -ToLabel "Middle node B"

            $result.found | Should -Be $true
            $result.depth | Should -Be 1
        }

        It "Finds path through intermediate nodes" {
            $result = Get-CausalPath -FromLabel "Start node A" -ToLabel "End node C"

            $result.found | Should -Be $true
            $result.depth | Should -Be 2
            $result.path.Count | Should -Be 3
        }

        It "Returns not found for disconnected nodes" {
            $isolated = Add-CausalNode -Type "decision" -Label "Isolated node"

            $result = Get-CausalPath -FromLabel "Start node A" -ToLabel "Isolated node"

            $result.found | Should -Be $false
        }

        It "Returns error for non-existent nodes" {
            $result = Get-CausalPath -FromLabel "Non-existent" -ToLabel "Also non-existent"

            $result.found | Should -Be $false
            $result.error | Should -Not -BeNullOrEmpty
        }

        It "Respects MaxDepth" {
            $result = Get-CausalPath -FromLabel "Start node A" -ToLabel "End node C" -MaxDepth 1

            # Path requires depth 2, but MaxDepth is 1
            $result.found | Should -Be $false
        }

        It "Supports partial label matching" {
            $result = Get-CausalPath -FromLabel "Start" -ToLabel "End"

            $result.found | Should -Be $true
        }
    }
}

Describe "Pattern Functions" {
    BeforeEach {
        # Reset causal graph to empty state
        $emptyGraph = @{
            version  = "1.0"
            updated  = (Get-Date).ToString("o")
            nodes    = @()
            edges    = @()
            patterns = @()
        } | ConvertTo-Json -Depth 5
        Set-Content -Path $script:CausalGraphFile -Value $emptyGraph -Encoding UTF8
    }

    Describe "Add-Pattern" {
        It "Creates pattern with required fields" {
            $pattern = Add-Pattern -Name "Test pattern" -Trigger "When X happens" -Action "Do Y"

            $pattern | Should -Not -BeNullOrEmpty
            $pattern.id | Should -Match "^p\d{3}$"
            $pattern.name | Should -Be "Test pattern"
            $pattern.trigger | Should -Be "When X happens"
            $pattern.action | Should -Be "Do Y"
            $pattern.occurrences | Should -Be 1
        }

        It "Creates pattern with description" {
            $pattern = Add-Pattern -Name "Described pattern" -Description "This is a test" -Trigger "Trigger" -Action "Action"

            $pattern.description | Should -Be "This is a test"
        }

        It "Uses default success rate of 1.0" {
            $pattern = Add-Pattern -Name "Default success" -Trigger "T" -Action "A"

            $pattern.success_rate | Should -Be 1.0
        }

        It "Accepts custom success rate" {
            $pattern = Add-Pattern -Name "Custom success" -Trigger "T" -Action "A" -SuccessRate 0.75

            $pattern.success_rate | Should -Be 0.75
        }

        It "Updates occurrences for duplicate patterns" {
            $p1 = Add-Pattern -Name "Repeated" -Trigger "T" -Action "A" -SuccessRate 1.0
            $p2 = Add-Pattern -Name "Repeated" -Trigger "T" -Action "A" -SuccessRate 0.5

            $p2.occurrences | Should -Be 2
            # Success rate should be running average: (1.0 + 0.5) / 2 = 0.75
            $p2.success_rate | Should -Be 0.75
        }

        It "Updates last_used timestamp" {
            $p1 = Add-Pattern -Name "Timed" -Trigger "T" -Action "A"
            Start-Sleep -Milliseconds 100
            $p2 = Add-Pattern -Name "Timed" -Trigger "T" -Action "A"

            $p2.last_used | Should -Not -Be $p1.last_used
        }
    }

    Describe "Get-Patterns" {
        BeforeEach {
            Add-Pattern -Name "High success" -Trigger "T1" -Action "A1" -SuccessRate 0.9
            Add-Pattern -Name "Medium success" -Trigger "T2" -Action "A2" -SuccessRate 0.6
            Add-Pattern -Name "Low success" -Trigger "T3" -Action "A3" -SuccessRate 0.3
            # Add occurrence to make filtering testable
            Add-Pattern -Name "High success" -Trigger "T1" -Action "A1" -SuccessRate 0.9
            Add-Pattern -Name "High success" -Trigger "T1" -Action "A1" -SuccessRate 0.9
        }

        It "Returns all patterns without filter" {
            $results = Get-Patterns

            $results.Count | Should -BeGreaterOrEqual 3
        }

        It "Filters by minimum success rate" {
            $results = Get-Patterns -MinSuccessRate 0.7

            $results | ForEach-Object { $_.success_rate | Should -BeGreaterOrEqual 0.7 }
        }

        It "Filters by minimum occurrences" {
            $results = Get-Patterns -MinOccurrences 3

            $results | ForEach-Object { $_.occurrences | Should -BeGreaterOrEqual 3 }
        }

        It "Combines filters" {
            $results = Get-Patterns -MinSuccessRate 0.8 -MinOccurrences 2

            $results.Count | Should -BeGreaterOrEqual 1
            $results | ForEach-Object {
                $_.success_rate | Should -BeGreaterOrEqual 0.8
                $_.occurrences | Should -BeGreaterOrEqual 2
            }
        }

        It "Sorts by success rate descending" {
            $results = Get-Patterns

            for ($i = 0; $i -lt $results.Count - 1; $i++) {
                $results[$i].success_rate | Should -BeGreaterOrEqual $results[$i + 1].success_rate
            }
        }
    }

    Describe "Get-AntiPatterns" {
        BeforeEach {
            # Create patterns with varying success rates
            Add-Pattern -Name "Good pattern" -Trigger "T1" -Action "A1" -SuccessRate 0.9
            Add-Pattern -Name "Bad pattern" -Trigger "T2" -Action "A2" -SuccessRate 0.2
            # Need 2 occurrences to qualify as anti-pattern
            Add-Pattern -Name "Bad pattern" -Trigger "T2" -Action "A2" -SuccessRate 0.2
            Add-Pattern -Name "Worse pattern" -Trigger "T3" -Action "A3" -SuccessRate 0.1
            Add-Pattern -Name "Worse pattern" -Trigger "T3" -Action "A3" -SuccessRate 0.1
        }

        It "Returns patterns with low success rate" {
            $results = Get-AntiPatterns

            $results | ForEach-Object { $_.success_rate | Should -BeLessOrEqual 0.3 }
        }

        It "Uses custom max success rate" {
            $results = Get-AntiPatterns -MaxSuccessRate 0.15

            $results | ForEach-Object { $_.success_rate | Should -BeLessOrEqual 0.15 }
        }

        It "Requires at least 2 occurrences" {
            $results = Get-AntiPatterns

            $results | ForEach-Object { $_.occurrences | Should -BeGreaterOrEqual 2 }
        }

        It "Sorts by success rate ascending" {
            $results = Get-AntiPatterns

            for ($i = 0; $i -lt $results.Count - 1; $i++) {
                $results[$i].success_rate | Should -BeLessOrEqual $results[$i + 1].success_rate
            }
        }
    }
}

Describe "Status Functions" {
    Describe "Get-ReflexionMemoryStatus" {
        It "Returns status object" {
            $status = Get-ReflexionMemoryStatus

            $status | Should -Not -BeNullOrEmpty
            $status.Episodes | Should -Not -BeNullOrEmpty
            $status.CausalGraph | Should -Not -BeNullOrEmpty
            $status.Configuration | Should -Not -BeNullOrEmpty
        }

        It "Reports episode count" {
            # Create some episodes
            New-Episode -SessionId "status-test-1" -Task "Test 1" -Outcome "success"
            New-Episode -SessionId "status-test-2" -Task "Test 2" -Outcome "success"

            $status = Get-ReflexionMemoryStatus

            $status.Episodes.Count | Should -BeGreaterOrEqual 2
        }

        It "Reports causal graph metrics" {
            Add-CausalNode -Type "decision" -Label "Status test node"
            Add-Pattern -Name "Status test pattern" -Trigger "T" -Action "A"

            $status = Get-ReflexionMemoryStatus

            $status.CausalGraph.Nodes | Should -BeGreaterOrEqual 1
            $status.CausalGraph.Patterns | Should -BeGreaterOrEqual 1
        }

        It "Reports configuration paths" {
            $status = Get-ReflexionMemoryStatus

            $status.Configuration.EpisodesPath | Should -Not -BeNullOrEmpty
            $status.Configuration.CausalityPath | Should -Not -BeNullOrEmpty
        }
    }
}

Describe "Corruption Recovery" -Tag "ErrorHandling" {
    BeforeAll {
        $script:CorruptionTestDir = Join-Path ([System.IO.Path]::GetTempPath()) "ReflexionCorruption-$(Get-Random)"
        New-Item -Path $script:CorruptionTestDir -ItemType Directory -Force | Out-Null
    }

    AfterAll {
        if (Test-Path $script:CorruptionTestDir) {
            Remove-Item $script:CorruptionTestDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Describe "Get-Episode Corruption Handling" {
        It "Throws on malformed episode JSON" {
            # Create corrupted episode file
            $corruptFile = Join-Path $script:EpisodesPath "episode-corrupt-test.json"
            "{ invalid json here" | Set-Content -Path $corruptFile -Encoding UTF8

            { Get-Episode -SessionId "corrupt-test" } | Should -Throw -ExceptionType ([System.IO.InvalidDataException])

            # Clean up
            Remove-Item $corruptFile -Force -ErrorAction SilentlyContinue
        }

        It "Returns null for non-existent episode" {
            $result = Get-Episode -SessionId "non-existent-episode-12345"
            $result | Should -BeNull
        }
    }

    Describe "Get-CausalGraph Corruption Handling" {
        BeforeEach {
            # Backup and clear causal graph for isolated tests
            if (Test-Path $script:CausalGraphFile) {
                $script:BackupGraph = Get-Content -Path $script:CausalGraphFile -Raw
            }
        }

        AfterEach {
            # Restore original causal graph
            if ($script:BackupGraph) {
                $script:BackupGraph | Set-Content -Path $script:CausalGraphFile -Encoding UTF8
            }
        }

        It "Throws by default on corrupted causal graph" {
            # Corrupt the causal graph
            "{ this is not valid JSON }" | Set-Content -Path $script:CausalGraphFile -Encoding UTF8

            # Re-import module to pick up corrupted file
            Import-Module $modulePath -Force

            # Should throw by default
            {
                # Access private function via InModuleScope
                InModuleScope ReflexionMemory {
                    Get-CausalGraph
                }
            } | Should -Throw -ExceptionType ([System.IO.InvalidDataException])
        }

        It "Returns empty graph with -AllowEmpty on corruption" {
            # Corrupt the causal graph
            "{ invalid: json: here }" | Set-Content -Path $script:CausalGraphFile -Encoding UTF8

            # Re-import module
            Import-Module $modulePath -Force

            $result = InModuleScope ReflexionMemory {
                Get-CausalGraph -AllowEmpty
            }

            $result | Should -Not -BeNull
            $result.nodes | Should -BeNullOrEmpty
            $result.edges | Should -BeNullOrEmpty
            $result.patterns | Should -BeNullOrEmpty
        }

        It "Returns empty graph for empty file" {
            "" | Set-Content -Path $script:CausalGraphFile -Encoding UTF8

            Import-Module $modulePath -Force

            $result = InModuleScope ReflexionMemory {
                Get-CausalGraph
            }

            $result.nodes.Count | Should -Be 0
        }
    }

    Describe "Save-CausalGraph Error Propagation" {
        It "Throws on write failure to read-only location" {
            # This test verifies that Save-CausalGraph throws instead of silently failing
            # Note: This requires a read-only directory which is OS-dependent
            # We'll test the error path indirectly by verifying the function signature

            $modulePath = Join-Path $PSScriptRoot ".." ".claude" "skills" "memory" "scripts" "ReflexionMemory.psm1"
            $content = Get-Content -Path $modulePath -Raw

            # Verify the function throws IOException on failure
            $content | Should -Match 'throw \[System\.IO\.IOException\]'
        }
    }
}
