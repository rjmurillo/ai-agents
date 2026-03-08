#Requires -Modules Pester
#Requires -Version 5.1

BeforeAll {
    $script:ScriptRoot = Split-Path -Parent $PSScriptRoot
    $script:TestScript = Join-Path $script:ScriptRoot ".claude/skills/workflow/scripts/Test-TierCompatibility.ps1"
}

Describe "Test-TierCompatibility" {
    Context "Valid tier sequences" {
        It "accepts Expert -> Manager delegation" {
            $result = & $script:TestScript -AgentSequence @("architect", "orchestrator")
            $LASTEXITCODE | Should -Be 0
        }

        It "accepts Expert -> Builder delegation" {
            $result = & $script:TestScript -AgentSequence @("architect", "implementer")
            $LASTEXITCODE | Should -Be 0
        }

        It "accepts Expert -> Integration delegation" {
            $result = & $script:TestScript -AgentSequence @("architect", "analyst")
            $LASTEXITCODE | Should -Be 0
        }

        It "accepts Manager -> Builder delegation" {
            $result = & $script:TestScript -AgentSequence @("orchestrator", "implementer")
            $LASTEXITCODE | Should -Be 0
        }

        It "accepts Manager -> Integration delegation" {
            $result = & $script:TestScript -AgentSequence @("orchestrator", "analyst")
            $LASTEXITCODE | Should -Be 0
        }

        It "accepts Builder -> Integration delegation" {
            $result = & $script:TestScript -AgentSequence @("implementer", "analyst")
            $LASTEXITCODE | Should -Be 0
        }

        It "accepts same-tier parallel agents (Expert)" {
            $result = & $script:TestScript -AgentSequence @("architect", "roadmap")
            $LASTEXITCODE | Should -Be 0
        }

        It "accepts same-tier parallel agents (Manager)" {
            $result = & $script:TestScript -AgentSequence @("orchestrator", "critic")
            $LASTEXITCODE | Should -Be 0
        }

        It "accepts same-tier parallel agents (Builder)" {
            $result = & $script:TestScript -AgentSequence @("implementer", "qa", "security")
            $LASTEXITCODE | Should -Be 0
        }

        It "accepts same-tier parallel agents (Integration)" {
            $result = & $script:TestScript -AgentSequence @("analyst", "explainer")
            $LASTEXITCODE | Should -Be 0
        }

        It "accepts multi-tier hierarchy: Expert -> Manager -> Builder" {
            $result = & $script:TestScript -AgentSequence @("architect", "orchestrator", "implementer", "qa")
            $LASTEXITCODE | Should -Be 0
        }

        It "accepts multi-tier hierarchy: Expert -> Manager -> Builder + Builder (parallel)" {
            $result = & $script:TestScript -AgentSequence @("architect", "orchestrator", "implementer", "qa", "security")
            $LASTEXITCODE | Should -Be 0
        }

        It "accepts full hierarchy: Expert -> Manager -> Builder -> Integration" {
            $result = & $script:TestScript -AgentSequence @("roadmap", "critic", "implementer", "analyst")
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "Invalid tier sequences" {
        It "rejects Builder -> Manager delegation (escalate instead)" {
            $result = & $script:TestScript -AgentSequence @("implementer", "orchestrator") 2>&1
            $LASTEXITCODE | Should -Be 1
            $result -join "`n" | Should -Match "cannot delegate"
        }

        It "rejects Builder -> Expert delegation (escalate instead)" {
            $result = & $script:TestScript -AgentSequence @("qa", "architect") 2>&1
            $LASTEXITCODE | Should -Be 1
            $result -join "`n" | Should -Match "cannot delegate"
        }

        It "rejects Integration -> Builder delegation" {
            $result = & $script:TestScript -AgentSequence @("analyst", "implementer") 2>&1
            $LASTEXITCODE | Should -Be 1
            $result -join "`n" | Should -Match "cannot delegate"
        }

        It "rejects Integration -> Manager delegation" {
            $result = & $script:TestScript -AgentSequence @("explainer", "orchestrator") 2>&1
            $LASTEXITCODE | Should -Be 1
            $result -join "`n" | Should -Match "cannot delegate"
        }

        It "rejects Integration -> Expert delegation" {
            $result = & $script:TestScript -AgentSequence @("retrospective", "architect") 2>&1
            $LASTEXITCODE | Should -Be 1
            $result -join "`n" | Should -Match "cannot delegate"
        }

        It "rejects Manager -> Expert delegation (escalate instead)" {
            $result = & $script:TestScript -AgentSequence @("orchestrator", "architect") 2>&1
            $LASTEXITCODE | Should -Be 1
            $result -join "`n" | Should -Match "cannot delegate"
        }

        It "rejects mixed invalid pattern: Builder -> Manager -> Builder" {
            $result = & $script:TestScript -AgentSequence @("implementer", "orchestrator", "qa") 2>&1
            $LASTEXITCODE | Should -Be 1
        }
    }

    Context "Unknown agents" {
        It "rejects unknown agent name" {
            $result = & $script:TestScript -AgentSequence @("unknown-agent") 2>&1
            $LASTEXITCODE | Should -Be 2
            $result -join "`n" | Should -Match "Unknown agent"
        }

        It "rejects sequence with unknown agent in middle" {
            $result = & $script:TestScript -AgentSequence @("architect", "unknown-agent", "implementer") 2>&1
            $LASTEXITCODE | Should -Be 2
        }
    }

    Context "Tier group validation" {
        It "reports first violation when multiple exist" {
            $result = & $script:TestScript -AgentSequence @("architect", "implementer", "orchestrator") 2>&1
            # Second element (orchestrator) is Builder -> Manager which is invalid
            $LASTEXITCODE | Should -Be 1
            $result -join "`n" | Should -Match "Position 2"
        }
    }

    Context "All recognized agents" {
        $AllAgents = @(
            # Expert
            "high-level-advisor", "independent-thinker", "architect", "roadmap",
            # Manager
            "orchestrator", "milestone-planner", "critic", "issue-feature-review", "pr-comment-responder",
            # Builder
            "implementer", "qa", "devops", "security", "debug",
            # Integration
            "analyst", "explainer", "task-decomposer", "retrospective", "spec-generator",
            "adr-generator", "backlog-generator", "janitor", "memory", "skillbook",
            "context-retrieval"
        )

        It "recognizes <_> as valid agent" -TestCases $AllAgents.ForEach({ @{ Agent = $_ } }) {
            param($Agent)
            $result = & $script:TestScript -AgentSequence @($Agent)
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "Real-world workflows" {
        It "routes security incident: analyst -> security -> devops -> critic -> implementer -> qa" {
            $result = & $script:TestScript -AgentSequence @("analyst", "security", "devops", "critic", "implementer", "qa")
            $LASTEXITCODE | Should -Be 0
        }

        It "routes feature: analyst -> architect -> milestone-planner -> critic -> implementer + qa + security (parallel)" {
            $result = & $script:TestScript -AgentSequence @("analyst", "architect", "milestone-planner", "critic", "implementer", "qa", "security")
            $LASTEXITCODE | Should -Be 0
        }

        It "routes strategic decision: roadmap -> high-level-advisor -> architect -> orchestrator -> implementer" {
            $result = & $script:TestScript -AgentSequence @("roadmap", "high-level-advisor", "architect", "orchestrator", "implementer")
            $LASTEXITCODE | Should -Be 0
        }

        It "routes documentation: explainer -> critic" {
            $result = & $script:TestScript -AgentSequence @("explainer", "critic")
            $LASTEXITCODE | Should -Be 0
        }

        It "routes research: analyst -> explainer (Integration peers)" {
            $result = & $script:TestScript -AgentSequence @("analyst", "explainer")
            $LASTEXITCODE | Should -Be 0
        }
    }
}
