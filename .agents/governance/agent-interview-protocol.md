# Agent Interview Protocol

## Purpose

This protocol provides a standardized process for discovering and documenting agent capabilities. It ensures all agents have consistent, complete documentation that enables accurate orchestrator routing and informed agent selection.

## When to Use This Protocol

| Scenario | Required? | Timing |
|----------|-----------|--------|
| New agent creation | Yes | Before release |
| Significant capability change | Yes | Before deployment |
| Annual capability review | Recommended | Quarterly or annually |
| Routing issues discovered | Yes | Immediately |
| Orchestrator update | Recommended | Validate affected agents |

## The 8 Standardized Questions

### Question 1: Core Specialty

> What is your core specialty? (One sentence)

**Purpose**: Enables quick agent identification and routing decisions.

**Example Response**: "I am a security specialist focused on vulnerability assessment, threat modeling, and secure coding practices."

### Question 2: Specific Tasks

> What specific tasks can you handle? (5-10 examples with descriptions)

**Purpose**: Defines the agent's capability scope for routing decisions.

**Response Format**:

| Task | Description | Typical Output |
|------|-------------|----------------|
| [Task name] | [What it involves] | [Deliverable type] |

### Question 3: Limitations

> What are your limitations? What you CANNOT do? (Critical!)

**Purpose**: Prevents misrouting and identifies gaps requiring other agents.

**Required Categories**:

- Technical limitations (languages, frameworks not supported)
- Scope limitations (what's out of scope)
- Dependency limitations (what requires other agents first)
- Output limitations (what deliverables cannot be produced)

### Question 4: Agent Pairings

> Which agents work well with you? (Pairing preferences)

**Purpose**: Enables multi-agent workflow design.

**Response Format**:

| Agent | Relationship | When to Pair |
|-------|--------------|--------------|
| [Agent name] | Before/After/Parallel | [Scenario] |

### Question 5: Input Expectations

> What input format do you expect? (Task description format, detail level)

**Purpose**: Ensures tasks are properly formatted for the agent.

**Required Information**:

- Minimum required context
- Preferred format (prose, structured, checklist)
- Required vs. optional information
- Example good task description
- Example insufficient task description

### Question 6: Output Format

> What should I expect in your output? (Report, code, recommendations, etc.)

**Purpose**: Sets expectations for consumers of agent output.

**Required Information**:

- Primary deliverable type
- Output location (`.agents/[category]/`)
- Format and structure
- Dependencies on other agent outputs
- Handoff artifacts

### Question 7: When to Use

> When should I use you? (Invocation rules, ideal scenarios)

**Purpose**: Provides clear entry criteria for orchestrator routing.

**Response Format**:

| Scenario | Priority | Confidence |
|----------|----------|------------|
| [Scenario description] | P0/P1/P2 | High/Medium/Low |

### Question 8: When NOT to Use

> When should I NOT use you? (Anti-patterns, inappropriate use)

**Purpose**: Prevents misuse and identifies routing to other agents.

**Required Categories**:

- Tasks better suited to other agents (with agent name)
- Scenarios where agent adds no value
- Prerequisite tasks that must happen first
- Common misuse patterns

## Interview Process

### Step 1: Prepare

1. Review agent's current documentation
2. Gather usage history (if available)
3. Identify known issues or gaps
4. Schedule 30-60 minutes for interview

### Step 2: Conduct Interview

1. Open the agent in isolation
2. Ask each question in sequence
3. Record responses in the [Response Template](./interview-response-template.md)
4. Probe for specificity on vague answers
5. Cross-reference with known capabilities

### Step 3: Validate

1. Compare responses to actual behavior
2. Test edge cases mentioned in limitations
3. Verify agent pairings are reciprocal
4. Check for consistency with capabilities matrix

### Step 4: Document

1. Complete the response template
2. Update capabilities matrix if needed
3. Store in `.agents/governance/interviews/[agent]-interview.md`
4. Notify orchestrator of changes

## Quality Assurance Checklist

Before finalizing an interview:

- [ ] All 8 questions answered completely
- [ ] Limitations are specific and testable
- [ ] Agent pairings verified with paired agents
- [ ] Input/output expectations are concrete
- [ ] Entry criteria are objective (not subjective)
- [ ] Anti-patterns reference alternative agents
- [ ] Response follows standardized template
- [ ] Cross-referenced with capabilities matrix

## Interview Cadence

| Agent Type | Interview Frequency | Trigger Events |
|------------|---------------------|----------------|
| New agents | Before first release | Creation complete |
| Core agents | Quarterly | Major version changes |
| Specialized agents | Semi-annually | Capability additions |
| All agents | On-demand | Routing failures |

## Maintenance

### Updating Interviews

1. Re-interview using full protocol
2. Note changes from previous version
3. Update capabilities matrix
4. Notify dependent agents/workflows

### Archiving

- Keep previous versions for 1 year
- Archive location: `.agents/governance/interviews/archive/`
- Naming: `[agent]-interview-[YYYY-MM-DD].md`

## Related Documents

- [Interview Response Template](./interview-response-template.md)
- [Capabilities Matrix](../../docs/agent-capabilities-matrix.md) (if exists)
- [Agent Design Principles](./agent-design-principles.md)

---

*Protocol Version: 1.0*
*Created: 2025-12-13*
*GitHub Issue: #6*
