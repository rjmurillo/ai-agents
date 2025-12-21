# ADR-013: Agent Orchestration MCP

## Status

Proposed

## Date

2025-12-21

## Context

The ai-agents project has **18 specialized agents** coordinated by an orchestrator. Current orchestration relies on:

1. **Prompt-based routing**: Orchestrator reads AGENT-SYSTEM.md and makes routing decisions
2. **Manual handoffs**: Agents return to orchestrator via text output
3. **HANDOFF.md**: Cross-session context passed via markdown file

### Current Agent Catalog

| Category | Agents |
|----------|--------|
| Coordination | orchestrator, planner, task-generator |
| Implementation | implementer, devops, security |
| Quality | critic, qa, independent-thinker |
| Design | architect, analyst, explainer |
| Strategy | high-level-advisor, roadmap, retrospective |
| Support | memory, skillbook, pr-comment-responder |

### Problems

1. **No structured invocation**: `Task()` calls are untyped, error-prone
2. **Lost context**: Handoffs lose information between agent transitions
3. **No workflow tracking**: Can't trace agent-to-agent flow
4. **Parallel conflicts**: Multiple agents updating shared state (HANDOFF.md)
5. **Model selection opacity**: Agent-model mapping not enforced

### Evidence from Retrospectives

- **Sessions 19-21**: Parallel agents caused HANDOFF.md staging conflicts
- **skill-orchestration-002**: Orchestrator MUST consolidate HANDOFF updates
- **skill-orchestration-001**: Parallel execution saves 40% time but needs coordination

## Decision

Create an **Agent Orchestration MCP** that:

1. Provides structured agent invocation with typed parameters
2. Tracks handoffs with context preservation
3. Manages parallel execution with conflict resolution
4. Enforces model selection per agent
5. Integrates with Session State MCP for session-level tracking

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   Agent Orchestration MCP                        │
├─────────────────────────────────────────────────────────────────┤
│  TOOLS                           │  RESOURCES                    │
│  ─────                           │  ─────────                    │
│  invoke_agent(name, prompt)      │  agents://catalog             │
│  get_agent_catalog()             │  agents://workflows           │
│  track_handoff(from, to, ctx)    │  agents://active              │
│  get_routing_recommendation()    │  agents://history             │
│  start_parallel_execution()      │                               │
│  aggregate_parallel_results()    │                               │
│  resolve_conflict()              │                               │
├─────────────────────────────────────────────────────────────────┤
│                    AGENT SOURCES                                 │
│  ─────────────────────────────────────────────────────────────  │
│  src/claude/*.md (18 agent definitions)                         │
│  .agents/AGENT-SYSTEM.md (workflows, routing)                   │
│  .agents/HANDOFF.md (cross-session context)                     │
└─────────────────────────────────────────────────────────────────┘
```

## Tool Interface Design

### invoke_agent

Structured agent invocation with typed parameters and automatic context injection.

```typescript
interface InvokeAgentParams {
  agent: AgentName;                // Validated agent name
  prompt: string;                  // Task for agent
  context?: AgentContext;          // Additional context
  model_override?: ModelName;      // Override default model
  parallel_id?: string;            // For parallel execution tracking
}

type AgentName =
  | "orchestrator" | "analyst" | "architect" | "planner" | "implementer"
  | "critic" | "qa" | "devops" | "security" | "explainer"
  | "task-generator" | "high-level-advisor" | "roadmap" | "retrospective"
  | "memory" | "skillbook" | "independent-thinker" | "pr-comment-responder";

type ModelName = "sonnet" | "opus" | "haiku";

interface AgentContext {
  prior_agent?: AgentName;         // Who handed off
  prior_output?: string;           // Summary of prior work
  artifacts?: string[];            // Paths to relevant artifacts
  steering?: string[];             // Injected steering files
  session_id?: string;             // Link to Session State MCP
}

interface InvokeAgentResult {
  invocation_id: string;           // Unique invocation reference
  agent: AgentName;
  model: ModelName;
  status: "started" | "completed" | "failed";
  output?: string;                 // Agent output (if completed)
  artifacts_created?: string[];    // New artifacts
  suggested_next?: AgentName[];    // Recommended next agents
  handoff_context?: string;        // Context for next agent
}
```

**Model Assignment (from AGENT-SYSTEM.md):**

| Agent | Default Model | Rationale |
|-------|---------------|-----------|
| orchestrator | sonnet | Fast routing |
| implementer | sonnet | Balanced generation |
| analyst | sonnet | Research efficiency |
| architect | sonnet | Design analysis |
| high-level-advisor | opus | Strategic depth |
| independent-thinker | opus | Deep analysis |
| security | opus | Thorough review |
| roadmap | opus | Strategic vision |
| (others) | sonnet | Default |

### get_agent_catalog

Retrieve full agent catalog with capabilities, inputs, outputs.

```typescript
interface GetAgentCatalogResult {
  agents: AgentDefinition[];
  workflows: WorkflowDefinition[];
  routing_heuristics: RoutingRule[];
}

interface AgentDefinition {
  name: AgentName;
  file: string;                    // src/claude/*.md
  role: string;                    // One-line role
  specialization: string;          // Domain expertise
  default_model: ModelName;
  inputs: InputSpec[];
  outputs: OutputSpec[];
  delegates_to: AgentName[];       // Can hand off to
  called_by: AgentName[];          // Receives from
  artifact_directory?: string;     // e.g., ".agents/analysis/"
}

interface WorkflowDefinition {
  name: string;                    // e.g., "quick-fix", "standard", "strategic"
  trigger: string;                 // When to use
  agents: AgentName[];             // Ordered agent sequence
  gates: string[];                 // Quality gates in workflow
}
```

### track_handoff

Record handoff between agents with full context preservation.

```typescript
interface TrackHandoffParams {
  from_agent: AgentName;
  to_agent: AgentName;
  context: HandoffContext;
  parallel_id?: string;            // If part of parallel execution
}

interface HandoffContext {
  summary: string;                 // What was accomplished
  artifacts: string[];             // Created artifacts
  decisions: Decision[];           // Key decisions made
  open_questions: string[];        // Unresolved items
  recommendations: string[];       // Suggestions for next agent
}

interface Decision {
  decision: string;
  rationale: string;
  alternatives_considered?: string[];
}

interface TrackHandoffResult {
  handoff_id: string;
  timestamp: string;
  from: AgentName;
  to: AgentName;
  context_preserved: boolean;
  session_id?: string;
}
```

### get_routing_recommendation

Get AI-assisted routing recommendation based on task analysis.

```typescript
interface GetRoutingRecommendationParams {
  task: string;                    // User's task description
  current_state?: string;          // Current session state
  constraints?: string[];          // e.g., "no security review needed"
}

interface GetRoutingRecommendationResult {
  recommended_workflow: string;    // Workflow name
  recommended_agents: AgentName[]; // Ordered sequence
  confidence: number;              // 0-100
  reasoning: string;               // Why this workflow
  alternatives: Alternative[];     // Other options considered
}

interface Alternative {
  workflow: string;
  agents: AgentName[];
  confidence: number;
  why_not_chosen: string;
}
```

### start_parallel_execution

Initialize parallel agent execution with conflict management.

```typescript
interface StartParallelExecutionParams {
  agents: ParallelAgent[];
  aggregation_strategy: "merge" | "vote" | "escalate";
  conflict_handler?: AgentName;    // Who resolves conflicts (default: high-level-advisor)
}

interface ParallelAgent {
  agent: AgentName;
  prompt: string;
  context?: AgentContext;
}

interface StartParallelExecutionResult {
  parallel_id: string;
  agents_started: AgentName[];
  status: "running" | "completed" | "conflict";
  estimated_completion?: string;   // ISO timestamp
}
```

### aggregate_parallel_results

Aggregate results from parallel execution.

```typescript
interface AggregateParallelResultsParams {
  parallel_id: string;
  wait_for_all?: boolean;          // Block until all complete
}

interface AggregateParallelResultsResult {
  parallel_id: string;
  status: "complete" | "partial" | "conflict";
  results: ParallelResult[];
  aggregated_output?: string;      // Merged result
  conflicts?: Conflict[];          // If status is "conflict"
  resolution_needed?: boolean;
}

interface ParallelResult {
  agent: AgentName;
  status: "completed" | "failed" | "pending";
  output?: string;
  artifacts?: string[];
}

interface Conflict {
  agents: AgentName[];
  issue: string;                   // What they disagree on
  positions: Position[];
}
```

### resolve_conflict

Resolve conflicts between agent outputs.

```typescript
interface ResolveConflictParams {
  parallel_id: string;
  conflict_id: string;
  resolution_strategy: "vote" | "escalate" | "manual";
  manual_resolution?: string;      // If strategy is "manual"
}

interface ResolveConflictResult {
  conflict_id: string;
  resolved: boolean;
  resolution: string;
  resolved_by: AgentName | "manual";
  rationale: string;
}
```

## Resource URIs

### agents://catalog

Full agent catalog with definitions.

```json
{
  "agents": [
    {
      "name": "orchestrator",
      "file": "src/claude/orchestrator.md",
      "role": "Central coordinator routing tasks to appropriate specialists",
      "specialization": "Task analysis, agent selection, workflow management",
      "default_model": "sonnet",
      "delegates_to": ["analyst", "architect", "planner", "implementer", "qa", "..."],
      "called_by": ["user", "pr-comment-responder"]
    },
    {
      "name": "implementer",
      "file": "src/claude/implementer.md",
      "role": "Writes production-quality code following established patterns",
      "specialization": "C#, .NET, test-driven development, SOLID principles",
      "default_model": "sonnet",
      "delegates_to": [],
      "called_by": ["orchestrator", "planner"],
      "artifact_directory": null
    }
  ],
  "total_agents": 18
}
```

### agents://workflows

Available workflow patterns.

```json
{
  "workflows": [
    {
      "name": "quick-fix",
      "trigger": "Single file changes, obvious bug fixes, typos",
      "agents": ["implementer", "qa"],
      "gates": ["qa_validation"]
    },
    {
      "name": "standard",
      "trigger": "2-5 files affected, some complexity, new functionality",
      "agents": ["analyst", "planner", "implementer", "qa"],
      "gates": ["critic_review", "qa_validation"]
    },
    {
      "name": "strategic",
      "trigger": "Should we do this? questions, scope/priority conflicts",
      "agents": ["independent-thinker", "high-level-advisor", "task-generator"],
      "gates": []
    },
    {
      "name": "ideation",
      "trigger": "Vague ideas, package requests, exploratory",
      "agents": ["analyst", "high-level-advisor", "independent-thinker", "critic", "roadmap", "explainer", "task-generator", "architect", "devops", "security", "qa"],
      "gates": ["validation_consensus", "plan_review"]
    }
  ]
}
```

### agents://active

Currently active agents and parallel executions.

```json
{
  "active_invocations": [
    {
      "invocation_id": "inv-001",
      "agent": "implementer",
      "started_at": "2025-12-21T15:30:00Z",
      "parallel_id": "par-001",
      "status": "running"
    }
  ],
  "parallel_executions": [
    {
      "parallel_id": "par-001",
      "agents": ["implementer", "architect", "security"],
      "status": "running",
      "aggregation_strategy": "merge"
    }
  ]
}
```

### agents://history

Recent agent invocations and handoffs.

```json
{
  "invocations": [
    {
      "invocation_id": "inv-001",
      "agent": "analyst",
      "timestamp": "2025-12-21T14:00:00Z",
      "session_id": "2025-12-21-session-01",
      "duration_ms": 45000,
      "artifacts_created": [".agents/analysis/api-latency.md"]
    }
  ],
  "handoffs": [
    {
      "handoff_id": "hnd-001",
      "from": "analyst",
      "to": "architect",
      "timestamp": "2025-12-21T14:01:00Z",
      "context_size_bytes": 2048
    }
  ]
}
```

## Serena Integration

### Memory Schema

| Memory Name | Purpose | Lifecycle |
|-------------|---------|-----------|
| `agent-invocation-history` | Recent invocations | Rolling 50 |
| `agent-handoff-chain` | Current session handoffs | Session-scoped |
| `agent-parallel-state` | Active parallel executions | Ephemeral |
| `agent-conflict-log` | Conflict resolutions | Persistent |

### Integration with Session State MCP

```typescript
// When invoke_agent is called, link to session
async function invokeAgent(params: InvokeAgentParams): Promise<InvokeAgentResult> {
  // 1. Get current session from Session State MCP
  const session = await sessionStateMCP.getCurrentSession();

  // 2. Record invocation in session context
  await sessionStateMCP.record_evidence("AGENT_INVOCATION", {
    agent: params.agent,
    timestamp: new Date().toISOString()
  });

  // 3. Perform invocation
  const result = await performInvocation(params);

  // 4. Track handoff if returning to orchestrator
  if (result.status === "completed") {
    await trackHandoff({
      from_agent: params.agent,
      to_agent: "orchestrator",
      context: { summary: result.output }
    });
  }

  return result;
}
```

## Workflow Enforcement

### Routing Heuristics (from AGENT-SYSTEM.md)

```typescript
const ROUTING_HEURISTICS: RoutingRule[] = [
  {
    pattern: /implement|code|fix|add/i,
    primary: "implementer",
    fallback: "architect",
    confidence: 0.8
  },
  {
    pattern: /test|coverage|qa|verify/i,
    primary: "qa",
    fallback: "implementer",
    confidence: 0.9
  },
  {
    pattern: /design|architecture|ADR/i,
    primary: "architect",
    fallback: "planner",
    confidence: 0.85
  },
  {
    pattern: /investigate|research|why/i,
    primary: "analyst",
    fallback: "explainer",
    confidence: 0.8
  },
  {
    pattern: /security|vulnerability|threat/i,
    primary: "security",
    fallback: "analyst",
    confidence: 0.95
  },
  {
    pattern: /deploy|ci|pipeline|build/i,
    primary: "devops",
    fallback: "implementer",
    confidence: 0.9
  }
];
```

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Prompt-only orchestration | Simple, no tooling | Lost context, conflicts | Current approach fails |
| Workflow YAML | Declarative | Rigid, can't adapt | AI routing more flexible |
| Single orchestrator agent | Centralized | Bottleneck, complex prompt | Already exists, needs enhancement |
| External queue (Redis) | Robust parallelism | Infrastructure overhead | Overkill for single-user CLI |

### Trade-offs

**Structured invocation vs flexibility**: Typed agents may reject novel use cases. Solution: Allow `context` field for arbitrary data.

**History retention vs storage**: Full history grows unbounded. Solution: Rolling window (50 invocations).

## Consequences

### Positive

- Type-safe agent invocations prevent typos
- Full handoff context preserved
- Parallel execution with conflict resolution
- Model assignment enforced
- Integration with Session State and Skill Catalog MCPs

### Negative

- Learning curve for new invocation pattern
- Additional token overhead for context passing
- Three-MCP coordination complexity

### Neutral

- Existing `Task()` calls can be wrapped
- Agent prompt files unchanged
- HANDOFF.md persists as backup

## Implementation Notes

### Phase 1: Core Invocation (P0)

1. Implement invoke_agent with type validation
2. Add get_agent_catalog from AGENT-SYSTEM.md
3. Create agents://catalog resource

### Phase 2: Handoff Tracking (P1)

1. Implement track_handoff with Serena persistence
2. Add agents://history resource
3. Integrate with Session State MCP

### Phase 3: Parallel Execution (P2)

1. Implement start_parallel_execution
2. Add aggregate_parallel_results
3. Implement resolve_conflict with high-level-advisor

### Phase 4: Smart Routing (P3)

1. Implement get_routing_recommendation
2. Add agents://workflows resource
3. Create routing analytics

## Related Decisions

- [ADR-009: Parallel-Safe Multi-Agent Design](./ADR-009-parallel-safe-multi-agent-design.md)
- [ADR-011: Session State MCP](./ADR-011-session-state-mcp.md)
- [ADR-012: Skill Catalog MCP](./ADR-012-skill-catalog-mcp.md)

## References

- [AGENT-SYSTEM.md](../AGENT-SYSTEM.md) - Agent catalog and workflows
- [skill-orchestration-001](../.serena/memories/skill-orchestration-001-parallel-execution-time-savings.md) - Parallel execution patterns
- [skill-orchestration-002](../.serena/memories/skill-orchestration-002-parallel-handoff-coordination.md) - Handoff coordination

---

*Template Version: 1.0*
*Created: 2025-12-21*
