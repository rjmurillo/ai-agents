/**
 * Agent Registry Schema
 *
 * TypeScript interfaces for agent registry per ADR-013.
 * This defines the structure for agent definitions, invocation parameters,
 * and orchestration primitives.
 */

/**
 * Valid agent names in the system.
 * Derived from agent definition files in src/claude/*.md
 */
export type AgentName =
  | "analyst"
  | "architect"
  | "critic"
  | "debug"
  | "devops"
  | "explainer"
  | "high-level-advisor"
  | "implementer"
  | "independent-thinker"
  | "janitor"
  | "memory"
  | "merge-resolver"
  | "milestone-planner"
  | "orchestrator"
  | "pr-comment-responder"
  | "qa"
  | "retrospective"
  | "roadmap"
  | "security"
  | "skillbook"
  | "spec-generator"
  | "task-decomposer";

/**
 * Available Claude model types for agent execution.
 */
export type ModelName = "sonnet" | "opus" | "haiku";

/**
 * Input specification for an agent.
 */
export interface InputSpec {
  name: string;
  type: string;
  description: string;
  required: boolean;
}

/**
 * Output specification for an agent.
 */
export interface OutputSpec {
  name: string;
  type: string;
  description: string;
}

/**
 * Complete agent definition including capabilities and relationships.
 */
export interface AgentDefinition {
  /** Agent name (must match AgentName type) */
  name: AgentName;

  /** Path to agent definition file */
  file: string;

  /** One-line role description */
  role: string;

  /** Domain expertise and specialization */
  specialization: string;

  /** Default Claude model for this agent */
  default_model: ModelName;

  /** Input specifications */
  inputs: InputSpec[];

  /** Output specifications */
  outputs: OutputSpec[];

  /** Agents this agent can delegate work to */
  delegates_to: AgentName[];

  /** Agents that can invoke this agent */
  called_by: AgentName[];

  /** Optional artifact output directory */
  artifact_directory?: string;
}

/**
 * Context passed between agents during handoffs.
 */
export interface AgentContext {
  /** Agent that performed the handoff */
  prior_agent?: AgentName;

  /** Summary of prior agent's output */
  prior_output?: string;

  /** Paths to relevant artifacts */
  artifacts?: string[];

  /** Injected steering files */
  steering?: string[];

  /** Link to Session State MCP session ID */
  session_id?: string;
}

/**
 * Parameters for invoking an agent.
 */
export interface InvokeAgentParams {
  /** Agent to invoke */
  agent: AgentName;

  /** Task prompt for the agent */
  prompt: string;

  /** Additional context for the agent */
  context?: AgentContext;

  /** Override default model */
  model_override?: ModelName;

  /** Parallel execution tracking ID */
  parallel_id?: string;
}

/**
 * Result from agent invocation.
 */
export interface InvokeAgentResult {
  /** Unique invocation reference */
  invocation_id: string;

  /** Agent that was invoked */
  agent: AgentName;

  /** Model used for execution */
  model: ModelName;

  /** Invocation status */
  status: "started" | "completed" | "failed";

  /** Agent output (if completed) */
  output?: string;

  /** Artifacts created by agent */
  artifacts_created?: string[];

  /** Recommended next agents */
  suggested_next?: AgentName[];

  /** Context for next agent handoff */
  handoff_context?: string;
}

/**
 * Decision record with rationale.
 */
export interface Decision {
  /** Decision made */
  decision: string;

  /** Rationale for the decision */
  rationale: string;

  /** Alternatives that were considered */
  alternatives_considered?: string[];
}

/**
 * Context for agent-to-agent handoff.
 */
export interface HandoffContext {
  /** Summary of what was accomplished */
  summary: string;

  /** Artifacts created */
  artifacts: string[];

  /** Key decisions made */
  decisions: Decision[];

  /** Unresolved questions */
  open_questions: string[];

  /** Recommendations for next agent */
  recommendations: string[];
}

/**
 * Parameters for tracking agent handoff.
 */
export interface TrackHandoffParams {
  /** Agent performing handoff */
  from_agent: AgentName;

  /** Agent receiving handoff */
  to_agent: AgentName;

  /** Handoff context */
  context: HandoffContext;

  /** Parallel execution tracking ID */
  parallel_id?: string;
}

/**
 * Result from tracking handoff.
 */
export interface TrackHandoffResult {
  /** Unique handoff reference */
  handoff_id: string;

  /** Handoff timestamp */
  timestamp: string;

  /** Source agent */
  from: AgentName;

  /** Destination agent */
  to: AgentName;

  /** Whether context was preserved */
  context_preserved: boolean;

  /** Session ID (if applicable) */
  session_id?: string;
}

/**
 * Workflow definition.
 */
export interface WorkflowDefinition {
  /** Workflow name */
  name: string;

  /** When to use this workflow */
  trigger: string;

  /** Ordered agent sequence */
  agents: AgentName[];

  /** Quality gates in workflow */
  gates: string[];
}

/**
 * Routing rule for agent selection.
 */
export interface RoutingRule {
  /** Pattern to match in task description */
  pattern: RegExp;

  /** Primary agent for this pattern */
  primary: AgentName;

  /** Fallback agent if primary unavailable */
  fallback: AgentName;

  /** Confidence level (0-1) */
  confidence: number;
}

/**
 * Agent catalog result.
 */
export interface GetAgentCatalogResult {
  /** All agent definitions */
  agents: AgentDefinition[];

  /** Available workflows */
  workflows: WorkflowDefinition[];

  /** Routing heuristics */
  routing_heuristics: RoutingRule[];
}

/**
 * Alternative workflow option.
 */
export interface Alternative {
  /** Workflow name */
  workflow: string;

  /** Agent sequence */
  agents: AgentName[];

  /** Confidence level (0-100) */
  confidence: number;

  /** Reason not chosen */
  why_not_chosen: string;
}

/**
 * Parameters for routing recommendation.
 */
export interface GetRoutingRecommendationParams {
  /** Task description */
  task: string;

  /** Current session state */
  current_state?: string;

  /** Task constraints */
  constraints?: string[];
}

/**
 * Routing recommendation result.
 */
export interface GetRoutingRecommendationResult {
  /** Recommended workflow name */
  recommended_workflow: string;

  /** Recommended agent sequence */
  recommended_agents: AgentName[];

  /** Confidence level (0-100) */
  confidence: number;

  /** Reasoning for recommendation */
  reasoning: string;

  /** Alternative options */
  alternatives: Alternative[];
}

/**
 * Agent for parallel execution.
 */
export interface ParallelAgent {
  /** Agent to invoke */
  agent: AgentName;

  /** Task prompt */
  prompt: string;

  /** Additional context */
  context?: AgentContext;
}

/**
 * Parameters for parallel execution.
 */
export interface StartParallelExecutionParams {
  /** Agents to execute in parallel */
  agents: ParallelAgent[];

  /** Result aggregation strategy */
  aggregation_strategy: "merge" | "vote" | "escalate";

  /** Agent that resolves conflicts */
  conflict_handler?: AgentName;
}

/**
 * Parallel execution result.
 */
export interface StartParallelExecutionResult {
  /** Parallel execution ID */
  parallel_id: string;

  /** Agents that were started */
  agents_started: AgentName[];

  /** Execution status */
  status: "running" | "completed" | "conflict";

  /** Estimated completion timestamp */
  estimated_completion?: string;
}

/**
 * Result from individual parallel agent.
 */
export interface ParallelResult {
  /** Agent that executed */
  agent: AgentName;

  /** Execution status */
  status: "completed" | "failed" | "pending";

  /** Agent output */
  output?: string;

  /** Artifacts created */
  artifacts?: string[];
}

/**
 * Position in a conflict.
 */
export interface Position {
  /** Agent holding this position */
  agent: AgentName;

  /** Position statement */
  position: string;

  /** Supporting evidence */
  evidence?: string[];
}

/**
 * Conflict between agents.
 */
export interface Conflict {
  /** Agents in conflict */
  agents: AgentName[];

  /** Issue description */
  issue: string;

  /** Positions held by agents */
  positions: Position[];
}

/**
 * Parameters for aggregating parallel results.
 */
export interface AggregateParallelResultsParams {
  /** Parallel execution ID */
  parallel_id: string;

  /** Wait for all agents to complete */
  wait_for_all?: boolean;
}

/**
 * Aggregated parallel results.
 */
export interface AggregateParallelResultsResult {
  /** Parallel execution ID */
  parallel_id: string;

  /** Aggregation status */
  status: "complete" | "partial" | "conflict";

  /** Individual agent results */
  results: ParallelResult[];

  /** Merged output */
  aggregated_output?: string;

  /** Conflicts detected */
  conflicts?: Conflict[];

  /** Whether resolution is needed */
  resolution_needed?: boolean;
}

/**
 * Parameters for conflict resolution.
 */
export interface ResolveConflictParams {
  /** Parallel execution ID */
  parallel_id: string;

  /** Conflict ID to resolve */
  conflict_id: string;

  /** Resolution strategy */
  resolution_strategy: "vote" | "escalate" | "manual";

  /** Manual resolution (if strategy is manual) */
  manual_resolution?: string;
}

/**
 * Conflict resolution result.
 */
export interface ResolveConflictResult {
  /** Conflict ID */
  conflict_id: string;

  /** Whether resolved */
  resolved: boolean;

  /** Resolution details */
  resolution: string;

  /** Who/what resolved it */
  resolved_by: AgentName | "manual";

  /** Rationale for resolution */
  rationale: string;
}
