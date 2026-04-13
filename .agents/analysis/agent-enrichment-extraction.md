# Agent Enrichment Extraction

Exact text blocks added to agent files in commits 5639b23f and 59e58e1e.

## `.claude/agents/architect.md`

### Change 1: Strategic Knowledge Available (5639b23f)

**Insert After**: `## Claude Code Tools` section (after the bullet list ending with `- **cloudmcp-manager memory tools**: Architectural decisions history`)

**Text to Insert**:

```markdown
## Strategic Knowledge Available

Query these Serena memories when relevant:

**Architecture Principles** (Primary):

- `chestertons-fence`: Understand existing patterns before changing them
- `path-dependence`: Recognize irreversibility and historical constraints
- `core-vs-context`: Distinguish differentiating capabilities from commodities
- `strangler-fig-pattern`: Incremental migration for legacy modernization

**Legacy & Risk** (Secondary):

- `conways-law`: Organization structure mirrors architecture
- `second-system-effect`: Detect and prevent over-engineering
- `cap-theorem`: Distributed system trade-offs

Access via:

```python
mcp__serena__read_memory(memory_file_name="[memory-name]")
```
```

### Change 2: Legacy Migration Strategy in ADR Template (5639b23f)

**Insert After**: The line `{How will implementation/compliance be confirmed? Design review, code review, ArchUnit test, etc.}` in the ADR template section

**Text to Insert**:

```markdown
### Legacy Migration Strategy

**Migration Pattern**: [Strangler Fig | Expand/Contract | Big Bang | Not Applicable]
**Rationale**: [Why this pattern chosen]
**Compatibility Window**: [Duration of parallel support]
**Rollback Strategy**: [How to revert if migration fails]
```

### Change 3: Strategic Considerations in ADR Template (5639b23f)

**Insert After**: The last option section in the ADR template (after `* Bad, because {argument b}`)

**Text to Insert**:

```markdown
## Strategic Considerations

**Chesterton's Fence**: [What existing patterns are we removing/changing? Why were they introduced?]
**Path Dependence**: [What historical constraints affect this decision?]
**Core vs Context**: [Is this differentiating (core) or commodity (context)?]
```

### Change 4: Strategic Architecture Principles (5639b23f)

**Insert After**: The vendor lock-in assessment table (after the row with `| **Critical** | Effectively permanent | Deep platform integration |`)

**Text to Insert**:

```markdown
## Strategic Architecture Principles

### Chesterton's Fence (Before Removing)

Before removing or simplifying existing patterns, apply this protocol:

1. **Investigate origin**: When was this introduced? (git log, git blame)
2. **Identify purpose**: What problem did this solve?
3. **Check if problem remains**: Does the original problem still exist?
4. **Document findings**: Record in ADR why removal is now safe

**Anti-Pattern**: "This looks complex, let's simplify" without understanding why complexity exists.

### Path Dependence (Constraint Recognition)

Recognize when architectural choices are constrained by history:

**Indicators**:

- Backward compatibility requirements
- Hyrum's Law (users depend on implementation details)
- Team training investment
- Ecosystem lock-in

**Response**: Document path-dependent constraints in ADRs. Distinguish between:

- **Reversible decisions**: Can be changed with reasonable effort
- **Irreversible decisions**: Would break contracts, data migrations, or compatibility

### Second-System Effect (Avoiding Over-Engineering)

When replacing successful systems, resist the temptation to add every postponed feature.

**Warning Signs**:

- "This time we'll do everything right"
- Expanding scope during design phase
- No clear success criteria from original system

**Mitigation**:

- Set explicit scope boundaries for replacements
- Preserve simplicity that made original successful
- Question features obviated by changed assumptions

### Core vs Context (Investment Prioritization)

Distinguish capabilities that differentiate business from necessary commodities:

| Type | Definition | Strategy |
|------|------------|----------|
| **Core** | Differentiates business | Build, invest heavily, own |
| **Context** | Necessary but not differentiating | Buy, outsource, commoditize |

**Application**: When reviewing ADRs, challenge decisions to build context capabilities.

## Legacy Modernization Patterns

### Strangler Fig Pattern (Incremental Migration)

Gradually replace legacy systems by building new functionality around existing systems until old can be decommissioned.

**Process**:

1. Place routing facade in front of legacy system
2. Migrate functionality piece by piece to new implementation
3. Route requests to new components as they're ready
4. Eventually decommission old application

**When to Use**:

- Large monolithic systems requiring modernization
- Business continuity critical (no big-bang tolerance)
- Learn-as-you-go approach needed

**ADR Considerations**:

- Document seams/boundaries for migration
- Define routing strategy
- Establish completion criteria

### Expand/Contract (Safe Schema Evolution)

Change schemas/APIs without downtime through parallel deployment:

**Phases**:

1. **Expand**: Add new elements without removing old (backward compatible)
2. **Migrate**: Update application code to use new structures (both coexist)
3. **Contract**: Remove obsolete elements after full migration

**Example** (rename database column):

- Phase 1: Add `new_name` column, write to both
- Phase 2: Backfill `new_name` from `old_name`
- Phase 3: Update reads to use `new_name`
- Phase 4: Drop `old_name`

**Key Insight**: Never make breaking changes atomically. Always have a period of parallel support.

### Sacrificial Architecture (Planned Obsolescence)

Accept that systems have lifespans and plan for replacement rather than indefinite preservation.

**Jeff Dean's Rule** (Google): "Design for ~10X growth, but plan to rewrite before ~100X."

**ADR Application**:

- Document expected lifespan/scale limits
- Define replacement triggers (performance, complexity, cost)
- Separate what should be preserved (business logic, data) from what is disposable (implementation)

**Warning Signs of End-of-Life**:

- Scaling patches becoming more frequent
- Operational burden exceeding development capacity
- Business needs diverging from system capabilities
- Key knowledge holders leaving
```

### Change 5: Engineering Knowledge Applied in ADR Template (59e58e1e)

**Insert After**: The line `{Additional evidence, team agreement documentation, realization timeline, links to related decisions and resources.}` in the "## More Information" section

**Text to Insert**:

```markdown
## Engineering Knowledge Applied

Document which strategic frameworks informed this decision:

**Mental Models**:

- [ ] Chesterton's Fence: [How applied or N/A]
- [ ] Second-Order Thinking: [Consequences explored]
- [ ] Inversion Thinking: [Failure modes identified]

**Strategic Frameworks**:

- [ ] Cynefin Classification: [Clear | Complicated | Complex | Chaotic | N/A]
- [ ] Wardley Mapping: [Evolution stage: Genesis | Custom | Product | Commodity | N/A]
- [ ] Three Horizons: [Horizon: H1 | H2 | H3 | N/A]

**Architecture Principles**:

- [ ] Core vs Context: [Core (build) | Context (buy) | N/A]
- [ ] Lindy Effect: [Technology maturity assessed: Yes | No | N/A]
- [ ] Conway's Law: [Org alignment considered: Yes | No | N/A]

**Migration Patterns** (if applicable):

- [ ] Strangler Fig: [Applied | Not Applicable]
- [ ] Expand/Contract: [Applied | Not Applicable]
- [ ] Sacrificial Architecture: [Lifespan/triggers documented | Not Applicable]
```

---

## `.claude/agents/high-level-advisor.md`

### Change 1: Strategic Knowledge Available (5639b23f)

**Insert After**: `## Claude Code Tools` section (after the bullet list ending with `- **cloudmcp-manager memory tools**: Historical context`)

**Text to Insert**:

```markdown
## Strategic Knowledge Available

Query these Serena memories when relevant:

**Decision Frameworks** (Primary):

- `ooda-loop`: Structured decision cycle for rapid orientation
- `inversion-thinking`: Identify failure modes by thinking backward
- `three-horizons-framework`: Balance short, medium, and long-term priorities
- `cynefin-framework`: Classify problem complexity for appropriate response

**Strategic Planning** (Secondary):

- `wardley-mapping`: Technology evolution for strategic positioning
- `core-vs-context`: Investment prioritization between differentiators and commodities

Access via:

```python
mcp__serena__read_memory(memory_file_name="[memory-name]")
```
```

### Change 2: OODA Loop and Inversion Thinking (59e58e1e)

**Insert After**: `## Strategic Frameworks` heading (before the `### Ruthless Triage` section)

**Text to Insert**:

```markdown
### Decision Cycle: OODA Loop

Apply this 4-phase cycle for rapid strategic decisions:

#### 1. Observe

Gather data without bias:

- What is the current state?
- What are the facts (not opinions)?
- What signals are we receiving?

#### 2. Orient

Connect to reality, examine biases:

- What assumptions are we making?
- What mental models are influencing us?
- What biases might be distorting our view?
- What is the competitive/strategic landscape?

**Key Insight**: Orientation is the schwerpunkt (critical point). Properly orienting can overcome initial disadvantages.

#### 3. Decide

Select from options, test decisions:

- What are the real options (not just safe options)?
- What do the facts support?
- What is the highest-leverage action?

#### 4. Act

Execute and gather results for next cycle:

- Take decisive action
- Measure outcomes
- Feed results back to Observe phase

**Strategic Advantage**: Faster OODA loops enable disruption. Cycle faster than opponents to create disorientation.

### Inversion Thinking

Flip problems backward to identify failure modes:

**Process**:

1. State the goal (e.g., "Make agent system reliable")
2. Invert it (e.g., "How would we ensure agent system fails?")
3. List failure modes:
   - No session protocol
   - No validation gates
   - Hidden dependencies
   - Unclear handoffs
4. Reverse each failure mode into a success criterion

**Application**: Before finalizing strategic advice, apply inversion to identify blind spots.
```

---

## `.claude/agents/planner.md`

### Change 1: Strategic Knowledge Available (5639b23f)

**Insert After**: `## Claude Code Tools` section (after the bullet list ending with `- **cloudmcp-manager memory tools**: Prior planning patterns`)

**Text to Insert**:

```markdown
## Strategic Knowledge Available

Query these Serena memories when relevant:

**Strategic Planning** (Primary):

- `three-horizons-framework`: Balance time horizons in milestone planning
- `critical-path-method`: Identify constraints and sequencing dependencies
- `cynefin-framework`: Classify task complexity for appropriate breakdown

**Decision Frameworks** (Secondary):

- `wardley-mapping`: Technology evolution for sequencing decisions
- `ooda-loop`: Structured decision cycle for plan iterations

Access via:

```python
mcp__serena__read_memory(memory_file_name="[memory-name]")
```
```

### Change 2: Three Horizons Framework and Critical Path Method (59e58e1e)

**Insert After**: The weighted decision matrix section (after the numbered list ending with `4. Calculate weighted score: Sum(weight x score)`)

**Text to Insert**:

```markdown
## Time Horizon Planning: Three Horizons

Balance investments across time horizons to avoid myopic focus on immediate delivery:

| Horizon | Time Frame | Focus | Risk | Investment |
|---------|------------|-------|------|------------|
| **H1** | 0-1 years | Optimize current systems | Low | ~70% |
| **H2** | 1-3 years | Emerging opportunities | Medium | ~20% |
| **H3** | 3-10 years | Future bets | High | ~10% |

**Planning Application**:

- **H1 tasks**: Bug fixes, performance optimization, technical debt paydown
- **H2 tasks**: Architecture transitions, new capabilities, platform shifts
- **H3 tasks**: Experimental features, proof-of-concepts, research spikes

**Critical Insight**: You cannot use H1 metrics on H3 projects. "What's the ROI?" on an 8-week-old experiment will always be zero.

**Actual Allocation Check**: Most teams drift to 95/4/1 when desired is 70/20/10. Explicitly track horizon allocation.

## Critical Path Method (Constraint Focus)

Identify the longest sequence of dependent tasks (critical path) to focus optimization efforts:

**Process**:

1. List all tasks and dependencies
2. Calculate earliest start/finish times (forward pass)
3. Calculate latest start/finish times (backward pass)
4. Identify critical path (zero slack)
5. Focus on optimizing critical path tasks

**Key Terms**:

- **Float/Slack**: Time a task can be delayed without impacting overall completion
- **Critical Activities**: Zero float, any delay affects project duration

**Application**: When estimating milestones, identify which tasks are on critical path vs. which have slack.
```

### Change 3: Plan Template Additions (59e58e1e)

**Insert After**: The "How we know the plan is complete:" checklist in the plan template

**Text to Insert**:

```markdown
## Time Horizon Classification

| Milestone | Horizon | Rationale |
|-----------|---------|-----------|
| [Milestone 1] | H1 | [Current system optimization] |
| [Milestone 2] | H2 | [Emerging capability] |

**Allocation Check**: H1: [%], H2: [%], H3: [%]

## Critical Path Analysis

**Critical Path**: [Milestone X] -> [Milestone Y] -> [Milestone Z]
**Estimated Duration**: [Total days on critical path]
**Slack Tasks**: [Tasks with float/can be delayed]
```

---

## `.claude/agents/implementer.md`

### Change 1: Strategic Knowledge Available (5639b23f)

**Insert After**: `## Claude Code Tools` section (after the bullet list ending with `- **cloudmcp-manager memory tools**: Implementation patterns`)

**Text to Insert**:

```markdown
## Strategic Knowledge Available

Query these Serena memories when relevant:

**Foundational Principles** (Primary):

- `solid-principles`: Single responsibility, open-closed, Liskov, interface segregation, dependency inversion
- `dry-principle`: Don't repeat yourself in state, functions, relationships, designs
- `yagni-principle`: You aren't gonna need it, avoid speculative features
- `boy-scout-rule`: Leave code cleaner than you found it
- `law-of-demeter`: Only talk to immediate friends, reduce coupling

**Implementation Practices** (Secondary):

- `tdd-approach`: Test-driven development workflow and benefits
- `clean-architecture`: Dependency rule and layer separation
- `observability-patterns`: Logging, metrics, and tracing practices

Access via:

```python
mcp__serena__read_memory(memory_file_name="[memory-name]")
```
```

---

## Summary

### Total Changes Per File

| File | Sections Added | Total Lines |
|------|----------------|-------------|
| **architect.md** | 5 sections | ~156 lines |
| **high-level-advisor.md** | 2 sections | ~80 lines |
| **planner.md** | 3 sections | ~75 lines |
| **implementer.md** | 1 section | ~24 lines |

### Common Pattern

All files received a "Strategic Knowledge Available" section immediately after their "Claude Code Tools" section. This provides a consistent entry point for querying relevant Serena memories.

### Application Notes

When applying to template files:

1. Maintain exact formatting (especially markdown code blocks)
2. Preserve the "Access via:" python code block in Strategic Knowledge sections
3. Keep checklist formatting with `- [ ]` for ADR templates
4. Preserve table formatting with proper column alignment
5. Maintain heading hierarchy (## for main sections, ### for subsections)
