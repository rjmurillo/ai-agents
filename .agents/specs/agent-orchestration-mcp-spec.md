# Agent Orchestration MCP Technical Specification

> **Status**: Draft
> **Version**: 0.1.0
> **ADR**: [ADR-013](../architecture/ADR-013-agent-orchestration-mcp.md)
> **Date**: 2025-12-21

## Overview

The Agent Orchestration MCP provides structured agent invocation, handoff tracking, and parallel execution management for the 18-agent system.

---

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                          Claude Code CLI                            │
│                                                                      │
│  invoke_agent() ──────>  Agent Orchestration MCP                    │
│  track_handoff()                   │                                │
│  start_parallel_execution()        │                                │
│                                    v                                │
│                         ┌──────────────────┐                        │
│                         │  Agent Registry  │                        │
│                         │  (18 agents)     │                        │
│                         └────────┬─────────┘                        │
│                                  │                                  │
│    ┌─────────────────────────────┼─────────────────────────────┐   │
│    │                             │                             │   │
│    v                             v                             v   │
│ ┌──────────┐              ┌──────────┐              ┌──────────┐  │
│ │ Session  │ <──────────> │ Serena   │ <──────────> │ Skill    │  │
│ │ State    │   integrate  │ MCP      │   integrate  │ Catalog  │  │
│ │ MCP      │              │          │              │ MCP      │  │
│ └──────────┘              └──────────┘              └──────────┘  │
└────────────────────────────────────────────────────────────────────┘
                                  │
                                  v
                    ┌─────────────────────────┐
                    │   src/claude/*.md       │
                    │   (Agent Definitions)   │
                    │                         │
                    │   orchestrator.md       │
                    │   analyst.md            │
                    │   architect.md          │
                    │   ... (18 total)        │
                    └─────────────────────────┘
```

---

## Agent Registry

### Agent Definitions

```typescript
type AgentName =
  | "orchestrator" | "analyst" | "architect" | "planner"
  | "implementer" | "critic" | "qa" | "devops" | "security"
  | "explainer" | "task-generator" | "high-level-advisor"
  | "roadmap" | "retrospective" | "memory" | "skillbook"
  | "independent-thinker" | "pr-comment-responder";

interface AgentDefinition {
  name: AgentName;
  file: string;
  role: string;
  default_model: "sonnet" | "opus" | "haiku";
  delegates_to: AgentName[];
  called_by: AgentName[];
  artifact_directory?: string;
}

const AGENT_REGISTRY: AgentDefinition[] = [
  {
    name: "orchestrator",
    file: "src/claude/orchestrator.md",
    role: "Central coordinator routing tasks to specialists",
    default_model: "sonnet",
    delegates_to: ["analyst", "architect", "planner", "implementer", "qa", "..."],
    called_by: ["user", "pr-comment-responder"]
  },
  {
    name: "implementer",
    file: "src/claude/implementer.md",
    role: "Writes production-quality code",
    default_model: "sonnet",
    delegates_to: [],
    called_by: ["orchestrator", "planner"]
  },
  {
    name: "high-level-advisor",
    file: "src/claude/high-level-advisor.md",
    role: "Brutally honest strategic advisor",
    default_model: "opus",  // Strategic depth requires opus
    delegates_to: [],
    called_by: ["orchestrator", "roadmap"]
  },
  {
    name: "security",
    file: "src/claude/security.md",
    role: "Vulnerability assessment and threat modeling",
    default_model: "opus",  // Thorough review requires opus
    delegates_to: [],
    called_by: ["orchestrator", "architect", "devops"]
  }
  // ... remaining agents
];
```

### Model Assignment

| Model | Agents | Rationale |
|-------|--------|-----------|
| opus | high-level-advisor, independent-thinker, security, roadmap | Deep analysis, strategic decisions |
| sonnet | All others | Balanced speed/quality |
| haiku | (none default) | Available for cost optimization |

---

## Tool Implementations

### invoke_agent

```typescript
interface InvokeAgentParams {
  agent: AgentName;
  prompt: string;
  context?: {
    prior_agent?: AgentName;
    prior_output?: string;
    artifacts?: string[];
    steering?: string[];
  };
  model_override?: "sonnet" | "opus" | "haiku";
  parallel_id?: string;
}

interface InvokeAgentResult {
  invocation_id: string;
  agent: AgentName;
  model: string;
  status: "started" | "completed" | "failed";
  output?: string;
  artifacts_created?: string[];
  handoff_context?: string;
}

async function invokeAgent(params: InvokeAgentParams): Promise<InvokeAgentResult> {
  // 1. Validate agent exists
  const agentDef = AGENT_REGISTRY.find(a => a.name === params.agent);
  if (!agentDef) {
    throw new Error(`Unknown agent: ${params.agent}`);
  }

  // 2. Determine model
  const model = params.model_override || agentDef.default_model;

  // 3. Generate invocation ID
  const invocationId = `inv-${Date.now()}-${params.agent}`;

  // 4. Build context-enriched prompt
  let enrichedPrompt = params.prompt;
  if (params.context?.prior_output) {
    enrichedPrompt = `## Prior Agent Output\n${params.context.prior_output}\n\n## Current Task\n${params.prompt}`;
  }

  // 5. Inject steering if provided
  if (params.context?.steering?.length) {
    const steeringContent = await loadSteeringFiles(params.context.steering);
    enrichedPrompt = `## Steering Guidance\n${steeringContent}\n\n${enrichedPrompt}`;
  }

  // 6. Record invocation start
  await recordInvocation({
    invocation_id: invocationId,
    agent: params.agent,
    model,
    started_at: new Date().toISOString(),
    parallel_id: params.parallel_id
  });

  // 7. Link to Session State MCP if available
  try {
    await callMCP("session_state", "record_evidence", {
      phase: "AGENT_INVOCATION",
      evidence_type: "tool_output",
      evidence: `Invoked ${params.agent} (${model})`
    });
  } catch {
    // Session State MCP not available
  }

  // 8. Perform actual invocation via Task tool
  // Note: This is a design representation - actual execution
  // happens through Claude Code's Task mechanism
  return {
    invocation_id: invocationId,
    agent: params.agent,
    model,
    status: "started"
    // Output populated when agent completes
  };
}
```

### track_handoff

```typescript
interface TrackHandoffParams {
  from_agent: AgentName;
  to_agent: AgentName;
  context: {
    summary: string;
    artifacts: string[];
    decisions: { decision: string; rationale: string }[];
    open_questions: string[];
  };
  parallel_id?: string;
}

interface TrackHandoffResult {
  handoff_id: string;
  timestamp: string;
  context_preserved: boolean;
}

async function trackHandoff(params: TrackHandoffParams): Promise<TrackHandoffResult> {
  const handoffId = `hnd-${Date.now()}`;
  const timestamp = new Date().toISOString();

  // 1. Persist handoff to Serena
  const handoffChain = await loadHandoffChain();
  handoffChain.push({
    handoff_id: handoffId,
    from: params.from_agent,
    to: params.to_agent,
    timestamp,
    context: params.context,
    parallel_id: params.parallel_id
  });

  await serena.write_memory("agent-handoff-chain", formatHandoffChain(handoffChain));

  // 2. Update HANDOFF.md atomically (if orchestrator consolidating)
  if (params.to_agent === "orchestrator" && !params.parallel_id) {
    await updateHandoffMd(params.context);
  }

  return {
    handoff_id: handoffId,
    timestamp,
    context_preserved: true
  };
}
```

### start_parallel_execution

```typescript
interface StartParallelExecutionParams {
  agents: {
    agent: AgentName;
    prompt: string;
    context?: object;
  }[];
  aggregation_strategy: "merge" | "vote" | "escalate";
  conflict_handler?: AgentName;  // default: high-level-advisor
}

interface StartParallelExecutionResult {
  parallel_id: string;
  agents_started: AgentName[];
  status: "running";
}

async function startParallelExecution(params: StartParallelExecutionParams): Promise<StartParallelExecutionResult> {
  const parallelId = `par-${Date.now()}`;

  // 1. Record parallel execution state
  const parallelState: ParallelExecution = {
    parallel_id: parallelId,
    agents: params.agents.map(a => a.agent),
    status: "running",
    aggregation_strategy: params.aggregation_strategy,
    conflict_handler: params.conflict_handler || "high-level-advisor",
    started_at: new Date().toISOString(),
    results: {}
  };

  await serena.write_memory("agent-parallel-state", formatParallelState(parallelState));

  // 2. Invoke each agent with parallel_id
  for (const agentSpec of params.agents) {
    await invokeAgent({
      agent: agentSpec.agent,
      prompt: agentSpec.prompt,
      context: agentSpec.context,
      parallel_id: parallelId
    });
  }

  return {
    parallel_id: parallelId,
    agents_started: params.agents.map(a => a.agent),
    status: "running"
  };
}
```

### aggregate_parallel_results

```typescript
interface AggregateParallelResultsParams {
  parallel_id: string;
  wait_for_all?: boolean;
}

interface AggregateParallelResultsResult {
  parallel_id: string;
  status: "complete" | "partial" | "conflict";
  results: {
    agent: AgentName;
    status: "completed" | "failed" | "pending";
    output?: string;
  }[];
  aggregated_output?: string;
  conflicts?: {
    agents: AgentName[];
    issue: string;
  }[];
}

async function aggregateParallelResults(params: AggregateParallelResultsParams): Promise<AggregateParallelResultsResult> {
  const parallelState = await loadParallelState(params.parallel_id);

  // 1. Collect results from all agents
  const results = [];
  let allComplete = true;
  for (const agent of parallelState.agents) {
    const result = parallelState.results[agent];
    if (!result) {
      allComplete = false;
      results.push({ agent, status: "pending" as const });
    } else {
      results.push({ agent, status: result.status, output: result.output });
    }
  }

  if (!allComplete && params.wait_for_all) {
    // In real implementation, would block or poll
    return { parallel_id: params.parallel_id, status: "partial", results };
  }

  // 2. Check for conflicts
  const conflicts = detectConflicts(results);
  if (conflicts.length > 0) {
    return {
      parallel_id: params.parallel_id,
      status: "conflict",
      results,
      conflicts
    };
  }

  // 3. Aggregate based on strategy
  let aggregated: string;
  switch (parallelState.aggregation_strategy) {
    case "merge":
      aggregated = mergeOutputs(results);
      break;
    case "vote":
      aggregated = voteOnOutputs(results);
      break;
    case "escalate":
      // Always escalate to conflict_handler
      aggregated = await escalateToHandler(parallelState.conflict_handler, results);
      break;
  }

  return {
    parallel_id: params.parallel_id,
    status: "complete",
    results,
    aggregated_output: aggregated
  };
}
```

### get_routing_recommendation

```typescript
interface GetRoutingRecommendationParams {
  task: string;
  current_state?: string;
}

interface GetRoutingRecommendationResult {
  recommended_workflow: string;
  recommended_agents: AgentName[];
  confidence: number;
  reasoning: string;
}

const ROUTING_HEURISTICS: { pattern: RegExp; workflow: string; agents: AgentName[]; confidence: number }[] = [
  {
    pattern: /fix|bug|typo|null check/i,
    workflow: "quick-fix",
    agents: ["implementer", "qa"],
    confidence: 0.9
  },
  {
    pattern: /implement|add feature|create/i,
    workflow: "standard",
    agents: ["analyst", "planner", "implementer", "qa"],
    confidence: 0.8
  },
  {
    pattern: /should we|decision|choose between/i,
    workflow: "strategic",
    agents: ["independent-thinker", "high-level-advisor", "task-generator"],
    confidence: 0.85
  },
  {
    pattern: /security|vulnerability|threat|auth/i,
    workflow: "security-review",
    agents: ["analyst", "security", "architect", "implementer", "qa"],
    confidence: 0.9
  },
  {
    pattern: /deploy|ci|pipeline|workflow/i,
    workflow: "devops",
    agents: ["devops", "security", "qa"],
    confidence: 0.85
  }
];

async function getRoutingRecommendation(params: GetRoutingRecommendationParams): Promise<GetRoutingRecommendationResult> {
  // 1. Match against heuristics
  for (const rule of ROUTING_HEURISTICS) {
    if (rule.pattern.test(params.task)) {
      return {
        recommended_workflow: rule.workflow,
        recommended_agents: rule.agents,
        confidence: rule.confidence * 100,
        reasoning: `Task matches "${rule.pattern.source}" pattern`
      };
    }
  }

  // 2. Default to standard workflow
  return {
    recommended_workflow: "standard",
    recommended_agents: ["analyst", "planner", "implementer", "qa"],
    confidence: 50,
    reasoning: "No specific pattern matched, using standard workflow"
  };
}
```

---

## Resource URIs

### agents://catalog

```json
{
  "agents": [
    {
      "name": "orchestrator",
      "role": "Central coordinator",
      "default_model": "sonnet",
      "delegates_to": ["analyst", "architect", "..."]
    }
  ],
  "total_agents": 18
}
```

### agents://workflows

```json
{
  "workflows": [
    {
      "name": "quick-fix",
      "agents": ["implementer", "qa"],
      "trigger": "Single file fixes"
    },
    {
      "name": "standard",
      "agents": ["analyst", "planner", "implementer", "qa"],
      "trigger": "New features, 2-5 files"
    }
  ]
}
```

### agents://active

```json
{
  "active_invocations": [
    { "id": "inv-001", "agent": "implementer", "status": "running" }
  ],
  "parallel_executions": [
    { "id": "par-001", "agents": ["architect", "security"], "status": "running" }
  ]
}
```

### agents://history

```json
{
  "invocations": [
    { "id": "inv-001", "agent": "analyst", "duration_ms": 45000 }
  ],
  "handoffs": [
    { "from": "analyst", "to": "architect", "context_size": 2048 }
  ]
}
```

---

## Serena Integration

| Memory | Purpose |
|--------|---------|
| `agent-invocation-history` | Recent 50 invocations |
| `agent-handoff-chain` | Current session handoffs |
| `agent-parallel-state` | Active parallel executions |
| `agent-conflict-log` | Conflict resolutions |

---

## Integration with Other MCPs

### Session State MCP

```typescript
// Record agent invocations as session evidence
sessionStateMCP.record_evidence("AGENT_INVOCATION", {
  agent: "implementer",
  invocation_id: "inv-001"
});
```

### Skill Catalog MCP

```typescript
// Before invoking agent, check for skill suggestions
const suggestions = await skillCatalogMCP.suggest_skills({
  task: prompt,
  operations_planned: detectOperations(prompt)
});

if (suggestions.warnings.length > 0) {
  // Warn about raw command usage
}
```

---

## Parallel Execution Patterns

### Merge Strategy

All outputs combined into single document:

```markdown
## Aggregated Analysis

### From: architect
[Architecture analysis...]

### From: security
[Security analysis...]

### From: devops
[DevOps analysis...]
```

### Vote Strategy

Count recommendations, majority wins:

```typescript
function voteOnOutputs(results: Result[]): string {
  const recommendations = results.map(r => extractRecommendation(r.output));
  const counts = countBy(recommendations);
  const winner = maxBy(Object.entries(counts), ([_, count]) => count);
  return `Recommendation: ${winner[0]} (${winner[1]}/${results.length} votes)`;
}
```

### Escalate Strategy

Always route to conflict handler (high-level-advisor):

```typescript
async function escalateToHandler(handler: AgentName, results: Result[]): Promise<string> {
  const summary = results.map(r => `${r.agent}: ${r.output?.slice(0, 200)}`).join('\n\n');
  const resolution = await invokeAgent({
    agent: handler,
    prompt: `Resolve these parallel analyses:\n\n${summary}`
  });
  return resolution.output;
}
```

---

## Conflict Detection

```typescript
function detectConflicts(results: Result[]): Conflict[] {
  const conflicts: Conflict[] = [];

  // Check for contradictory recommendations
  const recommendations = results
    .filter(r => r.output)
    .map(r => ({ agent: r.agent, rec: extractRecommendation(r.output!) }));

  // Group by recommendation
  const groups = groupBy(recommendations, r => r.rec);

  // If multiple groups, there's a conflict
  if (Object.keys(groups).length > 1) {
    conflicts.push({
      agents: recommendations.map(r => r.agent),
      issue: "Conflicting recommendations: " + Object.keys(groups).join(" vs ")
    });
  }

  return conflicts;
}
```

---

## References

- [ADR-013](../architecture/ADR-013-agent-orchestration-mcp.md)
- [AGENT-SYSTEM.md](../AGENT-SYSTEM.md)
- [skill-orchestration-001](../../.serena/memories/skill-orchestration-001-parallel-execution-time-savings.md)
- [skill-orchestration-002](../../.serena/memories/skill-orchestration-002-parallel-handoff-coordination.md)
