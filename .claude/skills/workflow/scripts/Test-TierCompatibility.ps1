<#
.SYNOPSIS
    Validates agent sequence respects tier hierarchy rules.

.DESCRIPTION
    Checks that agent sequences follow valid delegation patterns:
    - Higher tiers can delegate to lower tiers
    - Same tier agents can execute in parallel
    - Lower tiers cannot delegate to higher tiers (must escalate)

    Tier hierarchy (1 = highest authority):
    - Tier 1: Expert (high-level-advisor, independent-thinker, architect, roadmap)
    - Tier 2: Manager (orchestrator, milestone-planner, critic, issue-feature-review, pr-comment-responder)
    - Tier 3: Builder (implementer, qa, devops, security, debug)
    - Tier 4: Integration (analyst, explainer, task-decomposer, retrospective, spec-generator, etc.)

.PARAMETER AgentSequence
    Array of agent names in execution order.

.PARAMETER Verbose
    Enable detailed validation output.

.EXAMPLE
    Test-TierCompatibility -AgentSequence @("planner", "implementer", "qa")
    # Returns: $true (Manager → Builder → Builder is valid)

.EXAMPLE
    Test-TierCompatibility -AgentSequence @("implementer", "architect")
    # Returns: $false (Builder cannot delegate to Expert)

.EXAMPLE
    Test-TierCompatibility -AgentSequence @("architect", "implementer", "qa", "security")
    # Returns: $true (Expert → Builder + Builder + Builder is valid)

.EXITS
    0: Validation passed
    1: Tier violation detected
    2: Configuration error (invalid agent name)
    3: Parameter validation error

.NOTES
    See .agents/AGENT-SYSTEM.md Section 2.5 for tier hierarchy documentation.
    Related: orchestrator-routing-algorithm.md Phase 2.5
    ADR Reference: ADR-009 (Parallel-Safe Multi-Agent Design)
#>

param(
    [Parameter(Mandatory=$true)]
    [string[]]$AgentSequence
)

$ErrorActionPreference = 'Stop'

# Tier hierarchy levels (lower number = higher authority)
$TierHierarchy = @{
    "expert"       = 1
    "manager"      = 2
    "builder"      = 3
    "integration"  = 4
}

# Agent to tier mapping
$AgentTiers = @{
    # Expert Tier (1)
    "high-level-advisor"   = "expert"
    "independent-thinker"  = "expert"
    "architect"            = "expert"
    "roadmap"              = "expert"
    
    # Manager Tier (2)
    "orchestrator"         = "manager"
    "milestone-planner"    = "manager"
    "critic"               = "manager"
    "issue-feature-review" = "manager"
    "pr-comment-responder" = "manager"
    
    # Builder Tier (3)
    "implementer"          = "builder"
    "qa"                   = "builder"
    "devops"               = "builder"
    "security"             = "builder"
    "debug"                = "builder"
    
    # Integration Tier (4)
    "analyst"              = "integration"
    "explainer"            = "integration"
    "task-decomposer"      = "integration"
    "retrospective"        = "integration"
    "spec-generator"       = "integration"
    "adr-generator"        = "integration"
    "backlog-generator"    = "integration"
    "janitor"              = "integration"
    "memory"               = "integration"
    "skillbook"            = "integration"
    "context-retrieval"    = "integration"
}

# Validate all agents are known
foreach ($agent in $AgentSequence) {
    if ($agent -notin $AgentTiers.Keys) {
        Write-Error "Unknown agent: '$agent'. Valid agents: $(($AgentTiers.Keys | Sort-Object) -join ', ')"
        exit 2
    }
}

# Check sequence for tier violations
$violations = @()

for ($i = 0; $i -lt $AgentSequence.Count; $i++) {
    $currentAgent = $AgentSequence[$i]
    $currentAgentTier = $AgentTiers[$currentAgent]
    $currentLevel = $TierHierarchy[$currentAgentTier]
    
    if ($i -eq 0) {
        continue
    }
    
    $previousAgent = $AgentSequence[$i - 1]
    $previousAgentTier = $AgentTiers[$previousAgent]
    $previousLevel = $TierHierarchy[$previousAgentTier]
    
    # Check: is this same tier or valid delegation?
    if ($currentLevel -eq $previousLevel) {
        # Same tier - valid for parallel execution
        continue
    }
    elseif ($currentLevel -gt $previousLevel) {
        # Valid: higher tier to lower tier (delegation)
        continue
    }
    else {
        # Invalid: lower tier trying to delegate to higher tier
        $violation = @{
            Position = $i
            Agent = $currentAgent
            Tier = $currentAgentTier
            Level = $currentLevel
            PreviousAgent = $previousAgent
            PreviousTier = $previousAgentTier
            PreviousLevel = $previousLevel
            Message = "Invalid delegation: $previousAgent ($previousAgentTier) cannot delegate to $currentAgent ($currentAgentTier). Use escalation instead."
        }
        $violations += $violation
    }
}

# Report results
if ($violations.Count -gt 0) {
    Write-Host "Tier Validation: FAILED"
    Write-Host "Found $($violations.Count) violation(s):`n"
    
    foreach ($v in $violations) {
        Write-Host "  ❌ Position $($v.Position): $($v.Message)"
    }
    
    exit 1
}

# Success
Write-Host "Tier Validation: PASSED"
Write-Host "Agent sequence: $($AgentSequence -join ' -> ')"

exit 0
