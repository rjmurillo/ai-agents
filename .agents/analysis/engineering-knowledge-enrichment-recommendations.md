# Engineering Knowledge Enrichment Recommendations

**Analysis Date**: 2026-01-10
**Scope**: Integration of 5-tier engineering knowledge framework into ai-agents system
**Research Base**: 67 Serena memories covering foundational through distinguished engineer knowledge

---

## Executive Summary

The engineering knowledge additions (commits 8b8fae4e, cb65b561) provide 5 experience tiers of engineering wisdom spanning mental models, strategic frameworks, architectural patterns, and leadership principles. This analysis identifies 18 high-impact opportunities to integrate this knowledge into agents, skills, and commands to improve decision-making, strategic thinking, and architectural coherence.

**Priority Distribution**: 6 P0 (critical), 8 P1 (high), 4 P2 (enhancement)

---

## Part 1: Agent Enrichment Opportunities

### 1. Analyst Agent: Strategic Research Frameworks (P0)

**Current State**: Analysis templates focus on technical research without strategic decision frameworks.

**Knowledge Integration**: Add Cynefin Framework, Wardley Mapping, and Rumsfeld Matrix.

**Specific Changes**:

Add new section after "Research Tools" in `.claude/agents/analyst.md`:

```markdown
## Strategic Analysis Frameworks

### Cynefin Framework (Problem Classification)

Classify analysis problems to choose appropriate research approach:

| Domain | Characteristics | Research Approach |
|--------|----------------|-------------------|
| **Clear** | Obvious cause-effect | Best practices research (documentation, standards) |
| **Complicated** | Expert analysis needed | Deep technical research, consult specialists |
| **Complex** | Patterns emerge over time | Survey community signal, case studies, experiments |
| **Chaotic** | No discernible pattern | Act-sense-respond (rapid prototyping to learn) |

**Application**: Before deep research, classify the problem domain to select optimal research strategy.

### Wardley Mapping (Technology Evolution)

Map technology maturity to inform build-vs-buy recommendations:

| Stage | Characteristics | Research Focus |
|-------|----------------|----------------|
| **Genesis** | Novel, uncertain | Bleeding-edge research, academic papers |
| **Custom** | Known problem, bespoke solutions | Industry implementations, case studies |
| **Product** | Standardized, competitive market | Product comparisons, vendor evaluations |
| **Commodity** | Utility, cost-based | Standard implementations, SaaS options |

**Application**: Position technologies on evolution axis to guide strategic recommendations.

### Rumsfeld Matrix (Knowledge Gaps)

Structure research to surface hidden knowledge:

| | Known | Unknown |
|--|-------|---------|
| **Known** | Known Knowns (document facts) | Known Unknowns (research questions) |
| **Unknown** | Unknown Knowns (surface via interviews, git archaeology) | Unknown Unknowns (design for resilience) |

**Application**: Use matrix to identify what research can discover vs. what requires risk mitigation.
```

**Expected Benefit**: Analyst provides strategic context beyond technical facts. Research recommendations aligned with technology maturity and problem complexity.

**Effort**: 2 hours (documentation update)

---

### 2. Architect Agent: Principal-Level Decision Frameworks (P0)

**Current State**: ADR template focuses on options but lacks strategic decision-making frameworks.

**Knowledge Integration**: Add Chesterton's Fence, Path Dependence, Second-System Effect, Core/Context Mapping.

**Specific Changes**:

Add new section after "Reversibility Assessment" in `.claude/agents/architect.md`:

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
```

Add to ADR template after "Decision Outcome" section:

```markdown
### Strategic Considerations

**Chesterton's Fence**: [What existing patterns are we removing/changing? Why were they introduced?]
**Path Dependence**: [What historical constraints affect this decision?]
**Core vs Context**: [Is this differentiating (core) or commodity (context)?]
```

**Expected Benefit**: Architecture decisions informed by strategic principles. Reduced second-system over-engineering. Explicit recognition of irreversible decisions.

**Effort**: 4 hours (documentation + template updates)

---

### 3. High-Level Advisor: OODA Loop Decision Cycle (P1)

**Current State**: Strategic frameworks exist but lack explicit decision cycle methodology.

**Knowledge Integration**: Add OODA Loop and Inversion Thinking.

**Specific Changes**:

Add new section after "Strategic Frameworks" in `.claude/agents/high-level-advisor.md`:

```markdown
## Decision Cycle: OODA Loop

Apply this 4-phase cycle for rapid strategic decisions:

### 1. Observe
Gather data without bias:
- What is the current state?
- What are the facts (not opinions)?
- What signals are we receiving?

### 2. Orient
Connect to reality, examine biases:
- What assumptions are we making?
- What mental models are influencing us?
- What biases might be distorting our view?
- What is the competitive/strategic landscape?

**Key Insight**: Orientation is the schwerpunkt (critical point). Properly orienting can overcome initial disadvantages.

### 3. Decide
Select from options, test decisions:
- What are the real options (not just safe options)?
- What do the facts support?
- What is the highest-leverage action?

### 4. Act
Execute and gather results for next cycle:
- Take decisive action
- Measure outcomes
- Feed results back to Observe phase

**Strategic Advantage**: Faster OODA loops enable disruption. Cycle faster than opponents to create disorientation.

## Inversion Thinking

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

**Expected Benefit**: High-level advisor provides structured decision methodology. Faster strategic cycles. Proactive identification of failure modes.

**Effort**: 2 hours (documentation update)

---

### 4. Planner Agent: Three Horizons Framework (P1)

**Current State**: Plans focus on immediate execution without time horizon thinking.

**Knowledge Integration**: Add Three Horizons Framework, Critical Path Method.

**Specific Changes**:

Add new section after "Prioritization Frameworks" in `.claude/agents/planner.md`:

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

Add to plan template after "Milestones" section:

```markdown
## Time Horizon Classification

| Milestone | Horizon | Rationale |
|-----------|---------|-----------|
| [Milestone 1] | H1 | [Current system optimization] |
| [Milestone 2] | H2 | [Emerging capability] |

**Allocation Check**: H1: [%], H2: [%], H3: [%]

## Critical Path Analysis

**Critical Path**: [Milestone X] → [Milestone Y] → [Milestone Z]
**Estimated Duration**: [Total days on critical path]
**Slack Tasks**: [Tasks with float/can be delayed]
```

**Expected Benefit**: Plans balance immediate needs with long-term investment. Critical path focus prevents late delivery. Explicit time horizon tracking prevents H1 dominance.

**Effort**: 3 hours (documentation + template updates)

---

### 5. Analyst Agent: Lindy Effect Technology Assessment (P1)

**Current State**: Technology evaluations lack maturity/stability assessment frameworks.

**Knowledge Integration**: Add Lindy Effect for technology evaluation.

**Specific Changes**:

Add to "Ideation Research" template in `.claude/agents/analyst.md`:

```markdown
### Technology Maturity Assessment (Lindy Effect)

The Lindy Effect suggests technologies that have survived longer are likely to survive longer. Older, proven technologies often represent lower risk than novel alternatives.

**Maturity Indicators**:

| Age | Lindy Assessment | Risk Level | Consideration |
|-----|-----------------|------------|---------------|
| **25+ years** | High survival probability | Very Low | Battle-tested, stable, extensive ecosystem |
| **10-25 years** | Established | Low | Proven at scale, mature tooling |
| **5-10 years** | Maturing | Medium | Emerging standards, growing adoption |
| **2-5 years** | Early adoption | Medium-High | Unstable APIs, evolving patterns |
| **<2 years** | Novel/experimental | Very High | Uncertain longevity, minimal training data |

**Application**:
- For critical systems: Favor technologies with 10+ years survival
- For experimental features: Novel technologies acceptable with isolation boundaries
- For core infrastructure: Prefer "boring technology" (Lindy survivors)

**AI Tooling Consideration**: AI coding tools (Copilot, Claude, Cursor) perform better on established stacks due to vastly higher training data volume. Choosing Lindy technologies improves AI assistance quality.

### Community Signal vs. Lindy Tension

When community signal (GitHub stars, downloads) conflicts with Lindy assessment:

- **High signal, Low Lindy**: Trendy but unproven (proceed with caution, expect churn)
- **Low signal, High Lindy**: Mature but declining (stable but limited future investment)
- **High signal, High Lindy**: Established and growing (ideal state)
- **Low signal, Low Lindy**: Avoid unless strategic differentiation
```

**Expected Benefit**: Technology recommendations balanced between novelty and stability. Explicit risk assessment based on maturity. Better AI tooling support through Lindy-aware choices.

**Effort**: 2 hours (documentation update)

---

### 6. Architect Agent: Strangler Fig Migration Pattern (P0)

**Current State**: No explicit guidance for legacy modernization patterns.

**Knowledge Integration**: Add Strangler Fig Pattern, Expand/Contract, Sacrificial Architecture.

**Specific Changes**:

Add new section after "Architectural Principles" in `.claude/agents/architect.md`:

```markdown
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

Add to ADR template after "Consequences" section:

```markdown
### Legacy Migration Strategy

**Migration Pattern**: [Strangler Fig | Expand/Contract | Big Bang | Not Applicable]
**Rationale**: [Why this pattern chosen]
**Compatibility Window**: [Duration of parallel support]
**Rollback Strategy**: [How to revert if migration fails]
```

**Expected Benefit**: Architectural decisions include explicit migration patterns. Reduced big-bang rewrite risk. Clear strategies for schema evolution without downtime.

**Effort**: 4 hours (documentation + template updates)

---

## Part 2: Skill Enrichment Opportunities

### 7. decision-critic Skill: Inversion Thinking Integration (P0)

**Current State**: `.claude/skills/decision-critic/SKILL.md` stresses decision testing but lacks inversion methodology.

**Knowledge Integration**: Add Inversion Thinking as structured decision testing technique.

**Specific Changes**:

Add new section after existing "Structured Thinking" in decision-critic SKILL.md:

```markdown
## Inversion Thinking Protocol

Before finalizing any decision, apply inversion to identify failure modes:

### Step 1: State the Goal
Clearly articulate what success looks like.

Example: "Make the agent system reliable and maintainable"

### Step 2: Invert the Goal
Flip it to identify failure modes: "How would we ensure the agent system fails?"

### Step 3: List Failure Scenarios
Brainstorm specific ways to achieve failure:
- Remove all validation gates
- Allow circular agent delegation
- Make handoffs implicit
- Hide dependencies
- Skip documentation
- No testing strategy

### Step 4: Reverse to Success Criteria
Convert each failure mode into a success criterion:
- Failure: "No validation gates" → Success: "Automated validation at every phase"
- Failure: "Circular delegation" → Success: "Clear hierarchy preventing loops"
- Failure: "Implicit handoffs" → Success: "Explicit handoff protocol"

### Step 5: Validate Decision Against Inverted Criteria
Check if the decision being reviewed addresses each failure mode.

**Output Template**:

```markdown
## Inversion Analysis

### Goal
[What success looks like]

### Inverted Goal (Failure)
[How to ensure failure]

### Failure Modes
1. [Failure mode 1]
2. [Failure mode 2]
3. [Failure mode 3]

### Success Criteria (Reversed)
1. [Success criterion 1 - addresses failure mode 1]
2. [Success criterion 2 - addresses failure mode 2]
3. [Success criterion 3 - addresses failure mode 3]

### Decision Validation
- [ ] Addresses failure mode 1: [Evidence]
- [ ] Addresses failure mode 2: [Evidence]
- [ ] Addresses failure mode 3: [Evidence]
```

**Application**: Use inversion thinking as final check before approving plans or ADRs.
```

**Expected Benefit**: Decisions proactively address failure modes. Blind spots surfaced through systematic inversion. Higher-quality validation through "how to fail" thinking.

**Effort**: 2 hours (skill documentation update)

---

### 8. programming-advisor Skill: Buy vs Build Framework Enhancement (P1)

**Current State**: `.claude/skills/programming-advisor/SKILL.md` evaluates solutions but lacks structured buy-vs-build framework.

**Knowledge Integration**: Add structured evaluation framework from principal engineer knowledge.

**Specific Changes**:

Replace existing evaluation section with enhanced framework:

```markdown
## Buy vs Build Evaluation Framework

### When to Build

- [ ] Software is core to business differentiation
- [ ] Competitive advantage requires 100% control
- [ ] Vendor solutions insufficient for requirements
- [ ] Team has capacity without additional investment
- [ ] Long-term total cost of ownership favors build

### When to Buy

- [ ] Time to value critical (weeks not months)
- [ ] Standard capability, not differentiating
- [ ] Vendor efficiencies reduce total cost
- [ ] Team should focus on higher-impact projects
- [ ] Acceptable vendor lock-in trade-off

### Evaluation Matrix

| Factor | Build | Buy | Weight | Score |
|--------|-------|-----|--------|-------|
| Core competency | [Evidence] | [Evidence] | 30% | [Weighted score] |
| Time to value | [Evidence] | [Evidence] | 25% | [Weighted score] |
| Total cost (5 years) | [Evidence] | [Evidence] | 20% | [Weighted score] |
| Customization needs | [Evidence] | [Evidence] | 15% | [Weighted score] |
| Team expertise | [Evidence] | [Evidence] | 10% | [Weighted score] |
| **Total Score** | | | **100%** | [Sum] |

### Hidden Costs Analysis

**Build Hidden Costs**:
- Maintenance burden (20-40% of build cost annually)
- Opportunity cost (what else could team build?)
- Expertise acquisition/retention
- Testing and security validation
- Documentation and knowledge transfer

**Buy Hidden Costs**:
- Integration complexity (API changes, data mapping)
- Vendor lock-in (switching cost estimation)
- Customization limitations (workarounds needed?)
- Ongoing licensing (per-user, per-transaction costs)
- Vendor stability risk (acquisition, discontinuation)

### Core vs Context Assessment

Use Geoffrey Moore's framework to prioritize investment:

| Capability | Type | Rationale | Strategy |
|------------|------|-----------|----------|
| [Capability 1] | Core | [Differentiates business] | Build, own, invest |
| [Capability 2] | Context | [Necessary but commodity] | Buy, outsource |

**Key Insight**: Building context is a distraction from core. Buy context, build core.

### Lindy Effect Consideration

Evaluate technology maturity:
- **Build**: Are you creating novel solution in unstable space? (High risk)
- **Buy**: Is vendor solution based on Lindy survivor tech? (Lower risk)

### Recommendation Template

```markdown
## Buy vs Build Recommendation: [Capability]

**Verdict**: [BUILD | BUY | HYBRID]

### Core Rationale
[Primary reason in 2-3 sentences]

### Evaluation Scores
- Build score: [X/100]
- Buy score: [Y/100]

### Core vs Context
[Core/Context classification with justification]

### Hidden Costs Accepted
**If Build**: [Maintenance burden, opportunity cost, expertise]
**If Buy**: [Lock-in level, integration complexity, licensing]

### Decision Confidence
[High | Medium | Low] - [Why]

### Review Trigger
Revisit if: [Conditions that would change this decision]
```
```

**Expected Benefit**: Structured, evidence-based build-vs-buy recommendations. Explicit core-vs-context classification. Hidden cost transparency prevents underestimation.

**Effort**: 3 hours (skill documentation update)

---

### 9. adr-review Skill: Add Strategic Review Checklist (P1)

**Current State**: ADR review focuses on structural completeness without strategic validation.

**Knowledge Integration**: Add Chesterton's Fence, Path Dependence, Core/Context validation.

**Specific Changes**:

Add new review phase to `.claude/skills/adr-review/SKILL.md` after existing review structure:

```markdown
## Phase 4: Strategic Review (Principal-Level Validation)

After structural and technical review, apply strategic lenses:

### Strategic Validation Checklist

#### Chesterton's Fence (Change Justification)
- [ ] If removing/changing existing patterns: Original purpose documented
- [ ] Investigation evidence provided (git archaeology, interviews, documentation)
- [ ] Confirmation original problem no longer exists
- [ ] Assessment: [PASS | FAIL | N/A]

#### Path Dependence (Irreversibility Recognition)
- [ ] Historical constraints identified and documented
- [ ] Reversibility assessment complete (rollback capability, vendor lock-in)
- [ ] Migration/exit strategy defined if adding dependencies
- [ ] Irreversible decisions explicitly flagged and justified
- [ ] Assessment: [PASS | FAIL | N/A]

#### Core vs Context (Investment Prioritization)
- [ ] Capability classified as Core (differentiating) or Context (commodity)
- [ ] If building Context: Justification for not buying/outsourcing
- [ ] If Core: Competitive differentiation explained
- [ ] Assessment: [PASS | FAIL | N/A]

#### Second-System Effect (Over-Engineering Detection)
- [ ] If replacing existing system: Scope boundaries explicit
- [ ] Feature list justified (not "everything we didn't do last time")
- [ ] Simplicity preservation strategy documented
- [ ] Assessment: [PASS | FAIL | N/A]

### Strategic Review Verdict

**Overall Strategic Assessment**: [APPROVED | CONCERNS | REJECTED]

**Blocking Issues**:
- [Strategic issue 1 with required mitigation]
- [Strategic issue 2 with required mitigation]

**Recommendations**:
- [Strategic improvement 1]
- [Strategic improvement 2]
```

**Expected Benefit**: ADRs validated against strategic principles, not just structural completeness. Reduced over-engineering through second-system detection. Explicit core-vs-context classification.

**Effort**: 2 hours (skill documentation update)

---

### 10. session Skill: Add Knowledge Continuity Protocol (P2)

**Current State**: Session protocol focuses on task execution without long-term knowledge preservation.

**Knowledge Integration**: Add knowledge continuity practices from distinguished engineer knowledge.

**Specific Changes**:

Add new section to `.claude/skills/session/SKILL.md` after session lifecycle:

```markdown
## Knowledge Continuity Protocol

Sessions generate context that must persist beyond individual conversations. Apply these practices to prevent knowledge rot:

### Architectural Decisions
When making design choices:
- [ ] Create ADR if architecturally significant
- [ ] Link to related ADRs for traceability
- [ ] Document why alternatives were rejected

### System Intent
When modifying existing systems:
- [ ] Apply Chesterton's Fence (investigate before changing)
- [ ] Document original purpose in commit/ADR
- [ ] Record assumptions and constraints

### Incident Knowledge
When resolving issues:
- [ ] Document root cause, not just symptoms
- [ ] Link to related incidents (patterns)
- [ ] Record failure scenarios for future reference

### Tribal Knowledge Capture
When discovering undocumented knowledge:
- [ ] Write to Serena memory with provenance
- [ ] Tag with relevant keywords for discovery
- [ ] Link to related memories/documents

### Knowledge Decay Prevention

**Signs of knowledge rot**:
- Multiple engineers asking same questions
- Repeated rediscovery of past decisions
- Lost context for "why" behind design choices

**Mitigation**:
- Treat documentation as code (version controlled, reviewed)
- Create succession plans for critical systems
- Rotate team members to spread knowledge
- Record video walkthroughs for complex systems
```

**Expected Benefit**: Long-term knowledge preservation. Reduced knowledge rot. Succession planning for systems and decisions.

**Effort**: 2 hours (skill documentation update)

---

## Part 3: Command Enrichment Opportunities

### 11. /context_gather Command: Add Strategic Context Sources (P2)

**Current State**: Command gathers technical context without strategic decision frameworks.

**Knowledge Integration**: Add references to strategic frameworks (Cynefin, Wardley, OODA).

**Specific Changes**:

Add to `.claude/commands/context_gather.md` after existing context sources:

```markdown
## Strategic Context Sources

When gathering context for strategic decisions, consult:

### Mental Models
- Chesterton's Fence: Understand before changing
- Second-Order Thinking: Ask "And then what?"
- Inversion Thinking: How would this fail?

### Strategic Frameworks
- Cynefin: Classify problem complexity
- Wardley Mapping: Assess technology maturity
- OODA Loop: Structure decision cycle
- Three Horizons: Balance time horizons

### Architecture Principles
- CAP Theorem: Understand distributed system trade-offs
- Strangler Fig: Incremental migration patterns
- Core vs Context: Investment prioritization

### Access Frameworks

Query Serena memories:
```python
mcp__serena__read_memory(memory_file_name="cynefin-framework")
mcp__serena__read_memory(memory_file_name="wardley-mapping")
mcp__serena__read_memory(memory_file_name="chestertons-fence")
```

Query Forgetful knowledge:
```text
mcp__cloudmcp-manager__memory-search_nodes
Query: "strategic frameworks decision-making"
```
```

**Expected Benefit**: Context gathering includes strategic frameworks. Decision-makers access mental models proactively.

**Effort**: 1 hour (documentation update)

---

### 12. /push-pr Command: Add Pre-Flight Strategic Checks (P1)

**Current State**: Command focuses on technical validation without strategic review.

**Knowledge Integration**: Add strategic pre-flight checks from principal engineer knowledge.

**Specific Changes**:

Add to `.claude/commands/push-pr.md` before PR creation:

```markdown
## Pre-Flight Strategic Checks

Before opening PR, validate strategic alignment:

### Architectural Coherence
- [ ] Aligns with existing ADRs
- [ ] No introduction of unapproved patterns
- [ ] Reversibility assessed if adding dependencies
- [ ] Core vs Context classification appropriate

### Migration Pattern Validation (if applicable)
- [ ] If replacing existing code: Strangler Fig or Big Bang?
- [ ] If schema change: Expand/Contract pattern used?
- [ ] If API change: Backward compatibility maintained?

### Knowledge Continuity
- [ ] Significant decisions captured in ADRs
- [ ] Complex logic documented with rationale
- [ ] Links to related decisions/incidents
- [ ] Tribal knowledge surfaced and recorded

### Strategic Risk Assessment
- [ ] Path-dependent constraints documented
- [ ] Second-system effect avoided (if replacement)
- [ ] Vendor lock-in level acceptable
- [ ] Lindy effect considered for technology choices
```

**Expected Benefit**: PRs undergo strategic validation before submission. Architectural drift detected early. Knowledge preservation integrated into workflow.

**Effort**: 1 hour (documentation update)

---

## Part 4: Cross-Cutting Improvements

### 13. Memory System: Add Engineering Knowledge Index (P0)

**Current State**: 67 Serena memories exist but lack unified index/navigation.

**Knowledge Integration**: Create memory index with tier-based access.

**Specific Changes**:

Create new file: `.serena/memories/engineering-knowledge-index.md`

```markdown
# Engineering Knowledge Index

Comprehensive index of engineering knowledge across 5 experience tiers.

## How to Use This Index

1. **By Experience Level**: Find knowledge appropriate to your experience tier
2. **By Concept**: Look up specific mental models, frameworks, or patterns
3. **By Problem Domain**: Find relevant knowledge for specific challenges

## Knowledge by Experience Tier

### Tier 1: Foundational (<5 Years)

**Mental Models**:
- `chestertons-fence`: Understand before removing
- `conways-law`: Org structure mirrors architecture
- `hyrums-law`: Observable behaviors become dependencies
- `second-order-thinking`: Ask "And then what?"
- `law-of-demeter`: Only talk to immediate friends
- `galls-law`: Complex systems evolve from simple ones
- `yagni`: You aren't gonna need it
- `technical-debt-quadrant`: Deliberate vs inadvertent, prudent vs reckless
- `boy-scout-rule`: Leave code better than you found it

**Principles**:
- `solid-principles`: Single responsibility, open-closed, Liskov, interface segregation, dependency inversion
- `dry-principle`: Don't repeat yourself
- `kiss-principle`: Keep it simple
- `separation-of-concerns`: Decompose into non-overlapping parts
- `tell-dont-ask`: Bundle data with behavior
- `programming-by-intention`: Express intent over implementation

**Practices**:
- `tdd-red-green-refactor`: Test-driven development cycle
- `clean-architecture`: Domain at center, dependencies point inward
- `twelve-factor-app`: Cloud-ready application methodology
- `trunk-based-development`: Frequent commits to shared trunk
- `observability-three-pillars`: Logs, metrics, traces

### Tier 2: Advanced (5-10 Years)

**Architectural Models**:
- `c4-model`: Context, container, component, code
- `cap-theorem`: Consistency, availability, partition tolerance
- `resilience-patterns`: Circuit breaker, bulkheads, retries, timeouts
- `idempotency`: Operations safe to retry
- `poka-yoke`: Design to prevent errors

**Patterns**:
- `strategy-pattern`: Vary behavior at runtime
- `decorator-pattern`: Add behavior dynamically
- `null-object-pattern`: Avoid null checks
- `specification-pattern`: Encapsulate business rules

**Security**:
- `owasp-top-10`: Web vulnerabilities
- `principle-of-least-privilege`: Minimal permissions needed

### Tier 3: Senior (10-15 Years)

**Trade-Off Thinking**:
- `coupling-vs-duplication`: When to copy vs share
- `speed-vs-safety`: Fast vs validated
- `complexity-vs-flexibility`: General vs specific

**Design Practices**:
- `design-for-replaceability`: Favor replaceability over reuse
- `design-by-contract`: Preconditions, postconditions, invariants
- `policy-vs-mechanism`: Separate rules from execution
- `fallacies-of-distributed-computing`: Network assumptions that fail

**Evolution Patterns**:
- `feature-toggles`: Decouple deployment from release
- `branch-by-abstraction`: Large refactorings safely
- `strangler-fig-pattern`: Incremental legacy migration
- `expand-contract-migration`: Schema changes without downtime

**Thinking Models**:
- `wardley-mapping`: Capability evolution and strategy
- `cynefin-framework`: Problem classification (clear, complicated, complex, chaotic)
- `antifragility`: Systems that improve from stress
- `rumsfeld-matrix`: Known/unknown knowns/unknowns

**Operability**:
- `slo-sli-sla`: Service level objectives, indicators, agreements
- `error-budgets`: Acceptable unreliability enabling innovation
- `mttr-optimization`: Mean time to recovery
- `blameless-postmortems`: Learning from failures

### Tier 4: Principal (15-25 Years)

**Wisdom**:
- `chestertons-fence`: [Advanced application]
- `conways-law`: [Strategic application with inverse Conway maneuver]
- `paved-roads-guardrails`: Defaults without constraints

**Strategic Models**:
- `wardley-mapping`: [Strategic positioning]
- `cynefin-framework`: [Response strategy selection]
- `ooda-loop`: Observe, orient, decide, act
- `inversion-thinking`: How would this fail?
- `critical-path-method`: Focus on longest dependency chain
- `systems-archetypes`: Fixes that fail, shifting burden, limits to growth

**Architecture**:
- `adrs-architecture-decision-records`: Capture decisions with context
- `sociotechnical-design`: Align org and architecture (Team Topologies)
- `fitness-functions`: Automated architectural intent verification
- `products-over-projects`: Durable teams over temporary funding

**Risk & Resilience**:
- `slos-error-budgets`: Balance reliability and velocity
- `chaos-engineering`: Confidence through controlled failure
- `threat-modeling`: Structured security risk identification
- `pre-mortems`: Identify failure modes before starting

**Organizational Leadership**:
- `engineering-strategy`: Vision, strategy, specifications
- `platform-engineering`: Self-service developer capabilities
- `buy-vs-build-framework`: Core vs context evaluation
- `migrations-at-scale`: Incremental transformation

### Tier 5: Distinguished (25+ Years)

**Legacy Thinking**:
- `lindy-effect`: Older technology has longer expected life
- `second-system-effect`: Resist over-engineering replacements
- `path-dependence`: Historical constraints on current choices
- `architectural-paleontology`: Understanding design layers
- `golden-path-vs-golden-cage`: Enable without constraining

**Governance**:
- `sociotechnical-coherence`: Align technology with org dynamics
- `run-vs-change-business`: Separate operations from innovation
- `systemic-risk-portfolios`: Classify dependencies and failure risk
- `compliance-as-code`: Policy enforcement via automation
- `data-lineage-sovereignty`: Track data across jurisdictions

**Migration**:
- `strangler-fig-pattern`: [Strategic application]
- `expand-contract`: [Schema evolution]
- `capability-based-migration`: User-facing capabilities over technical components
- `sacrificial-architecture`: Plan for replacement
- `core-context-mapping`: Invest in differentiation, buy commodities

**Time Horizons**:
- `three-horizons-framework`: Balance current (H1), emerging (H2), future (H3)
- `long-term-constraint-thinking`: What will successors wish we documented?

**Leadership**:
- `principle-based-governance`: Guide via values, not rules
- `enterprise-architecture`: Cross-cutting business-technology integration
- `technical-ethics`: Privacy, fairness, bias, safety
- `knowledge-continuity`: Prevent knowledge rot in long-lived systems

**Classics**:
- `mythical-man-month`: Brooks's Law, conceptual integrity
- `designing-data-intensive-applications`: Distributed systems foundation
- `thinking-in-systems`: Stocks, flows, feedback loops, leverage points
- `fifth-discipline`: Learning organization disciplines
- `how-buildings-learn`: Pace layers, shearing layers
- `wardley-mapping`: [Strategic application]

## Knowledge by Problem Domain

### Decision-Making
- Tier 1: `second-order-thinking`, `technical-debt-quadrant`
- Tier 3: `cynefin-framework`, `rumsfeld-matrix`
- Tier 4: `ooda-loop`, `inversion-thinking`, `pre-mortems`

### Architecture
- Tier 1: `clean-architecture`, `separation-of-concerns`
- Tier 2: `c4-model`, `cap-theorem`, `poka-yoke`
- Tier 3: `wardley-mapping`, `strangler-fig-pattern`
- Tier 4: `adrs-architecture-decision-records`, `sociotechnical-design`, `fitness-functions`
- Tier 5: `second-system-effect`, `architectural-paleontology`, `sacrificial-architecture`

### Change Management
- Tier 1: `chestertons-fence`, `boy-scout-rule`
- Tier 3: `feature-toggles`, `branch-by-abstraction`, `expand-contract-migration`
- Tier 4: `migrations-at-scale`
- Tier 5: `strangler-fig-pattern`, `capability-based-migration`

### Legacy Systems
- Tier 1: `chestertons-fence`, `galls-law`
- Tier 3: `strangler-fig-pattern`, `expand-contract-migration`
- Tier 5: `lindy-effect`, `second-system-effect`, `path-dependence`, `architectural-paleontology`

### Strategic Planning
- Tier 3: `wardley-mapping`, `cynefin-framework`, `antifragility`
- Tier 4: `ooda-loop`, `critical-path-method`, `products-over-projects`
- Tier 5: `three-horizons-framework`, `core-context-mapping`

### Operability & Reliability
- Tier 1: `observability-three-pillars`
- Tier 2: `resilience-patterns`, `idempotency`
- Tier 3: `slo-sli-sla`, `error-budgets`, `mttr-optimization`, `blameless-postmortems`
- Tier 4: `chaos-engineering`, `threat-modeling`

### Organization Design
- Tier 1: `conways-law`
- Tier 4: `sociotechnical-design`, `platform-engineering`
- Tier 5: `sociotechnical-coherence`, `run-vs-change-business`, `knowledge-continuity`

## Query Examples

**By Memory Name**:
```python
mcp__serena__read_memory(memory_file_name="cynefin-framework")
```

**By Experience Tier**:
```python
# Search for foundational knowledge
mcp__serena__list_memories()
# Filter by "tier-1-foundational" tag
```

**By Problem Domain**:
```python
# Search for decision-making frameworks
mcp__serena__read_memory(memory_file_name="ooda-loop")
mcp__serena__read_memory(memory_file_name="inversion-thinking")
```

## Integration with Agents

**Analyst**: Use Tier 3-4 strategic frameworks for research classification
**Architect**: Use Tier 1-5 architecture and legacy system knowledge
**High-Level Advisor**: Use Tier 4-5 strategic and decision-making frameworks
**Planner**: Use Tier 3-4 time horizon and critical path knowledge
**Implementer**: Use Tier 1-2 foundational principles and practices
**QA**: Use Tier 1-2 testing and quality frameworks

## Maintenance

This index should be updated when:
- New engineering knowledge added to Serena memories
- Knowledge reclassified across experience tiers
- New problem domains identified
- Agent knowledge requirements change
```

**Expected Benefit**: Unified navigation across 67 memories. Experience-appropriate knowledge discovery. Problem-domain-based access. Agent-specific knowledge recommendations.

**Effort**: 4 hours (index creation + integration testing)

---

### 14. Agent Prompts: Add Strategic Context References (P1)

**Current State**: Agent prompts reference tools and constraints but not strategic frameworks.

**Knowledge Integration**: Add "Strategic Knowledge Available" section to each agent.

**Specific Changes**:

For each agent in `.claude/agents/`, add after "Claude Code Tools" section:

```markdown
## Strategic Knowledge Available

Query these Serena memories when relevant:

**Decision Frameworks**:
- `cynefin-framework`: Classify problem complexity
- `ooda-loop`: Structured decision cycle
- `inversion-thinking`: Identify failure modes
- `rumsfeld-matrix`: Known/unknown knowledge gaps

**Architecture Principles**:
- `chestertons-fence`: Understand before changing
- `conways-law`: Org structure mirrors architecture
- `cap-theorem`: Distributed system trade-offs
- `strangler-fig-pattern`: Incremental migration

**Strategic Planning**:
- `wardley-mapping`: Technology evolution assessment
- `three-horizons-framework`: Time horizon balance
- `critical-path-method`: Constraint identification
- `buy-vs-build-framework`: Investment prioritization

**Legacy & Risk**:
- `lindy-effect`: Technology maturity assessment
- `second-system-effect`: Over-engineering detection
- `path-dependence`: Irreversibility recognition
- `antifragility`: Design for stress resilience

Access via:
```python
mcp__serena__read_memory(memory_file_name="[memory-name]")
```
```

**Per-Agent Customization**:

- **Analyst**: Focus on Cynefin, Wardley Mapping, Lindy Effect
- **Architect**: Focus on Chesterton's Fence, Path Dependence, Strangler Fig, Core vs Context
- **High-Level Advisor**: Focus on OODA Loop, Inversion, Three Horizons
- **Planner**: Focus on Critical Path, Three Horizons, Wardley Mapping
- **Implementer**: Focus on foundational principles (SOLID, DRY, YAGNI)

**Expected Benefit**: Agents proactively access strategic knowledge. Context-appropriate framework application. Reduced ad-hoc decision-making.

**Effort**: 6 hours (8 agent files × 45 minutes each)

---

### 15. Orchestrator Logic: Add Strategic Routing Triggers (P1)

**Current State**: Orchestrator routes based on task type without strategic complexity assessment.

**Knowledge Integration**: Add Cynefin classification to routing decisions.

**Specific Changes**:

Add to `.claude/agents/orchestrator.md` routing logic:

```markdown
## Strategic Complexity Routing

Before routing, classify task complexity using Cynefin Framework:

### Classification Questions

1. **Is cause-effect relationship obvious?**
   - Yes → Clear domain
   - No → Continue assessment

2. **Can experts analyze to find cause-effect?**
   - Yes → Complicated domain
   - No → Continue assessment

3. **Do patterns only emerge after observation?**
   - Yes → Complex domain
   - No → Chaotic domain

### Routing by Domain

| Domain | Characteristics | Route To | Rationale |
|--------|----------------|----------|-----------|
| **Clear** | Best practices apply | implementer | Standard implementation |
| **Complicated** | Expert analysis needed | architect → analyst | Deep technical research |
| **Complex** | Emergent patterns | analyst → planner → implementer | Probe-sense-respond approach |
| **Chaotic** | No clear pattern | high-level-advisor | Act-sense-respond (stabilize first) |

### Example Routing

**Task**: "Add new authentication method"
- **Classification**: Complicated (security expert analysis needed)
- **Route**: architect (design review) → security (threat model) → implementer

**Task**: "Investigate why users abandon checkout"
- **Classification**: Complex (patterns emerge from data)
- **Route**: analyst (user research) → high-level-advisor (strategic direction) → planner

**Task**: "Production outage, payments down"
- **Classification**: Chaotic (immediate action needed)
- **Route**: high-level-advisor (triage) → implementer (hotfix) → retrospective (learn)
```

**Expected Benefit**: Task routing aligned with complexity. Appropriate agent expertise matched to problem domain. Reduced misrouting and rework.

**Effort**: 3 hours (documentation + routing logic update)

---

## Part 5: Documentation & Training

### 16. Create Engineering Knowledge Quick Reference (P2)

**Current State**: No quick reference for applying engineering knowledge to agent tasks.

**Knowledge Integration**: Create quick reference guide with decision trees.

**Specific Changes**:

Create new file: `.agents/ENGINEERING-KNOWLEDGE-QUICK-REFERENCE.md`

```markdown
# Engineering Knowledge Quick Reference

Fast lookup for applying strategic frameworks to agent tasks.

## Decision Tree: Which Framework to Use?

```
START
│
├─ Making architecture decision?
│  ├─ YES → Chesterton's Fence + Path Dependence + Core vs Context
│  └─ NO → Continue
│
├─ Removing existing code?
│  ├─ YES → Chesterton's Fence (MANDATORY)
│  └─ NO → Continue
│
├─ Evaluating technology?
│  ├─ YES → Lindy Effect + Wardley Mapping
│  └─ NO → Continue
│
├─ Planning feature?
│  ├─ YES → Three Horizons + Critical Path
│  └─ NO → Continue
│
├─ Unclear problem complexity?
│  ├─ YES → Cynefin Framework
│  └─ NO → Continue
│
├─ Need strategic direction?
│  ├─ YES → OODA Loop + Inversion Thinking
│  └─ NO → Continue
│
└─ Migrating legacy system?
   ├─ YES → Strangler Fig + Expand/Contract
   └─ NO → Default to foundational principles
```

## One-Sentence Summaries

| Framework | Use When | One-Sentence Summary |
|-----------|----------|---------------------|
| **Chesterton's Fence** | Removing existing code/patterns | Understand why it exists before removing it |
| **Conway's Law** | Org/architecture alignment | Systems mirror org communication structures |
| **Cynefin** | Classifying problem complexity | Match response strategy to problem domain |
| **OODA Loop** | Strategic decisions | Observe-Orient-Decide-Act cycle for rapid decisions |
| **Wardley Mapping** | Technology maturity assessment | Map capabilities on evolution axis |
| **Three Horizons** | Planning time allocation | Balance H1 (current), H2 (emerging), H3 (future) |
| **Lindy Effect** | Technology selection | Older tech has longer expected life |
| **Strangler Fig** | Legacy migration | Incrementally replace rather than big-bang rewrite |
| **CAP Theorem** | Distributed systems | Choose 2 of 3: Consistency, Availability, Partition Tolerance |
| **Core vs Context** | Build vs buy | Build core differentiation, buy commodity context |

## Agent-Specific Recommendations

**I am analyst agent, what knowledge do I need?**
- Primary: Cynefin, Wardley Mapping, Lindy Effect, Rumsfeld Matrix
- Secondary: CAP Theorem, Strangler Fig (for migration analysis)

**I am architect agent, what knowledge do I need?**
- Primary: Chesterton's Fence, Path Dependence, Core vs Context, Strangler Fig
- Secondary: Conway's Law, Second-System Effect, CAP Theorem

**I am high-level-advisor agent, what knowledge do I need?**
- Primary: OODA Loop, Inversion Thinking, Three Horizons, Cynefin
- Secondary: Wardley Mapping, Core vs Context

**I am planner agent, what knowledge do I need?**
- Primary: Three Horizons, Critical Path Method, Cynefin
- Secondary: Wardley Mapping, OODA Loop

**I am implementer agent, what knowledge do I need?**
- Primary: SOLID, DRY, YAGNI, Boy Scout Rule, Law of Demeter
- Secondary: TDD, Clean Architecture, Observability

## Common Scenarios

### Scenario: "Should we build this or buy it?"

**Apply**: Core vs Context + Lindy Effect + Buy vs Build Framework

**Questions**:
1. Is this core differentiation or commodity capability?
2. What is the technology maturity (Lindy)?
3. What are hidden costs (both build and buy)?
4. What is the 5-year TCO?

**Output**: BUILD | BUY | HYBRID verdict with rationale

### Scenario: "Can we remove this complex code?"

**Apply**: Chesterton's Fence (MANDATORY) + Path Dependence

**Questions**:
1. When was this introduced? (git blame/log)
2. What problem did it solve? (commit messages, issues)
3. Does the problem still exist?
4. What dependencies exist on this behavior? (Hyrum's Law)

**Output**: REMOVE | REFACTOR | KEEP verdict with evidence

### Scenario: "How do we migrate this monolith?"

**Apply**: Strangler Fig + Expand/Contract + Core vs Context

**Questions**:
1. What bounded contexts exist?
2. What can we extract incrementally?
3. What is core vs context in current system?
4. What is the routing strategy?

**Output**: Migration plan with incremental phases

### Scenario: "This problem feels overwhelming"

**Apply**: Cynefin Framework + OODA Loop

**Questions**:
1. Is cause-effect obvious, discoverable, emergent, or absent?
2. What response strategy matches the domain?
3. What should we observe first?

**Output**: Problem classification + appropriate response strategy
```

**Expected Benefit**: Fast decision tree for framework selection. Agent-specific recommendations. Scenario-based application guidance. Reduced cognitive load through quick reference.

**Effort**: 3 hours (guide creation)

---

### 17. ADR Template: Add Engineering Knowledge References (P1)

**Current State**: ADR template lacks references to strategic frameworks.

**Knowledge Integration**: Add framework reference section to ADR template.

**Specific Changes**:

Add to `.claude/agents/architect.md` ADR template after "More Information":

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

**Expected Benefit**: ADRs document strategic thinking, not just technical choices. Reviewers understand framework application. Future engineers see reasoning behind decisions.

**Effort**: 1 hour (template update)

---

### 18. Create Experience Tier Self-Assessment (P2)

**Current State**: No guidance for users on which knowledge tier applies to their experience level.

**Knowledge Integration**: Create self-assessment tool mapping experience to knowledge tiers.

**Specific Changes**:

Create new file: `.agents/ENGINEERING-KNOWLEDGE-TIER-ASSESSMENT.md`

```markdown
# Engineering Knowledge Tier Self-Assessment

Determine which knowledge tier best matches your experience and responsibilities.

## Quick Assessment

Answer these 5 questions:

1. **Experience**: How many years of professional software engineering?
   - A: 0-5 years → Score 1
   - B: 5-10 years → Score 2
   - C: 10-15 years → Score 3
   - D: 15-25 years → Score 4
   - E: 25+ years → Score 5

2. **Scope**: What is your typical scope of impact?
   - A: Individual features → Score 1
   - B: Multiple features, single team → Score 2
   - C: Multi-team projects → Score 3
   - D: Organization-wide systems → Score 4
   - E: Industry-wide influence → Score 5

3. **Decision Authority**: What level of decisions do you make?
   - A: Implementation details → Score 1
   - B: Component design → Score 2
   - C: Architecture patterns → Score 3
   - D: Strategic technology choices → Score 4
   - E: Enterprise-wide standards → Score 5

4. **Leadership**: How do you contribute to others' growth?
   - A: Learning from peers → Score 1
   - B: Peer mentoring → Score 2
   - C: Team technical leadership → Score 3
   - D: Cross-team influence → Score 4
   - E: Industry thought leadership → Score 5

5. **Complexity**: What problem complexity do you typically handle?
   - A: Well-defined problems → Score 1
   - B: Technical trade-offs → Score 2
   - C: Multi-dimensional trade-offs → Score 3
   - D: Strategic ambiguity → Score 4
   - E: Existential risk management → Score 5

**Your Score**: Sum the scores above

**Tier Mapping**:
- 5-8 points: **Tier 1 (Foundational)** - Focus on principles, practices, clean code
- 9-12 points: **Tier 2 (Advanced)** - Add architectural patterns, security, domain-driven design
- 13-16 points: **Tier 3 (Senior)** - Add strategic thinking, leadership, operability
- 17-20 points: **Tier 4 (Principal)** - Add organizational leadership, strategic frameworks
- 21-25 points: **Tier 5 (Distinguished)** - Add legacy-scale thinking, governance, long-term constraints

## Detailed Tier Descriptions

### Tier 1: Foundational (<5 years)

**You are here if**:
- Learning how to write clean, maintainable code
- Understanding design patterns and principles
- Building features within established systems
- Seeking code review and mentorship

**Focus on**:
- SOLID principles, DRY, YAGNI
- Test-driven development
- Refactoring techniques
- Basic architectural patterns

### Tier 2: Advanced (5-10 years)

**You are here if**:
- Designing components and modules
- Making local architecture decisions
- Evaluating technical trade-offs
- Mentoring junior engineers

**Focus on**:
- Architectural patterns (C4, CAP theorem)
- Security fundamentals (OWASP Top 10)
- Domain-driven design
- Resilience patterns

### Tier 3: Senior (10-15 years)

**You are here if**:
- Leading technical direction for teams
- Balancing competing priorities
- Influencing multi-team decisions
- Building engineering culture

**Focus on**:
- Strategic thinking (Wardley, Cynefin)
- Operability (SLOs, error budgets)
- Evolution patterns (Strangler Fig)
- Leadership without authority

### Tier 4: Principal (15-25 years)

**You are here if**:
- Setting organization-wide technical direction
- Making strategic technology bets
- Designing sociotechnical systems
- Building engineering capacity

**Focus on**:
- OODA Loop, Inversion Thinking
- ADRs, engineering strategy
- Platform engineering
- Buy vs build frameworks

### Tier 5: Distinguished (25+ years)

**You are here if**:
- Influencing industry standards
- Managing legacy-scale transformations
- Balancing technical ethics and business survival
- Building succession for long-lived systems

**Focus on**:
- Lindy Effect, path dependence
- Governance at scale
- Knowledge continuity
- Three Horizons time management

## Recommended Learning Path

**If Tier 1**: Master foundational principles before advanced patterns
**If Tier 2**: Add strategic frameworks to complement technical depth
**If Tier 3**: Focus on leadership and operability
**If Tier 4**: Add organizational design and strategic thinking
**If Tier 5**: Focus on governance, ethics, and long-term constraints

## Integration with Agents

Use your tier to guide which strategic frameworks to prioritize:

- **Tier 1-2**: Implementer agent knowledge (foundational principles)
- **Tier 2-3**: Analyst, QA agent knowledge (patterns, testing strategies)
- **Tier 3-4**: Architect, Planner agent knowledge (strategic frameworks)
- **Tier 4-5**: High-Level Advisor agent knowledge (organizational, governance)
```

**Expected Benefit**: Users identify appropriate knowledge tier. Learning paths customized by experience level. Agent knowledge recommendations aligned with user capability.

**Effort**: 2 hours (assessment creation)

---

## Priority Summary

### P0 (Critical) - Immediate Impact

1. Analyst: Strategic research frameworks (2h)
2. Architect: Principal-level decision frameworks (4h)
3. Architect: Strangler Fig migration patterns (4h)
4. decision-critic: Inversion thinking (2h)
5. Memory System: Engineering knowledge index (4h)
6. Cross-agent: Strategic context references (6h)

**Total P0 Effort**: 22 hours

### P1 (High) - Near-Term Value

1. High-Level Advisor: OODA Loop (2h)
2. Planner: Three Horizons framework (3h)
3. Analyst: Lindy Effect technology assessment (2h)
4. programming-advisor: Buy vs build framework (3h)
5. adr-review: Strategic review checklist (2h)
6. /push-pr: Pre-flight strategic checks (1h)
7. Orchestrator: Strategic routing triggers (3h)
8. ADR Template: Framework references (1h)

**Total P1 Effort**: 17 hours

### P2 (Enhancement) - Long-Term Quality

1. session: Knowledge continuity protocol (2h)
2. /context_gather: Strategic context sources (1h)
3. Engineering Knowledge Quick Reference (3h)
4. Experience Tier Self-Assessment (2h)

**Total P2 Effort**: 8 hours

**Overall Effort**: 47 hours (approximately 6 working days)

---

## Implementation Sequence

Recommended rollout order to maximize early value:

### Phase 1: Foundation (Week 1)
1. Memory System: Engineering knowledge index (enables discovery)
2. Analyst: Strategic frameworks (high agent usage)
3. Architect: Principal-level frameworks (critical for ADRs)

### Phase 2: Strategic Integration (Week 2)
4. decision-critic: Inversion thinking (quality gate)
5. High-Level Advisor: OODA Loop (unblock decisions)
6. Planner: Three Horizons (balance time horizons)

### Phase 3: Agent Enrichment (Week 3)
7. Cross-agent strategic references (all agents improved)
8. programming-advisor: Buy vs build (common need)
9. adr-review: Strategic checklist (quality improvement)

### Phase 4: Workflow Integration (Week 4)
10. Orchestrator: Strategic routing (smarter delegation)
11. Architect: Strangler Fig patterns (legacy modernization)
12. ADR Template: Framework references (documentation)

### Phase 5: Polish & Training (Week 5)
13. Engineering Knowledge Quick Reference (usability)
14. Experience Tier Self-Assessment (onboarding)
15. Remaining P2 items (completeness)

---

## Success Metrics

### Qualitative Indicators
- ADRs reference strategic frameworks explicitly
- Agents cite relevant mental models in decisions
- Analysts classify problems using Cynefin before research
- Architects apply Chesterton's Fence before removals
- Plans balance Three Horizons explicitly

### Quantitative Indicators
- Memory index queries: Baseline → +50% (discovery improvement)
- ADRs with strategic framework references: 0% → 80%
- Agent handoff decisions citing frameworks: 0% → 60%
- Build-vs-buy analyses using structured framework: 0% → 100%

### Risk Indicators (What Could Go Wrong)
- Overuse of frameworks (form over substance)
- Paralysis by analysis (too much upfront thinking)
- Framework mismatch (using wrong model for problem)

**Mitigation**: Quick reference guide prevents misapplication. Orchestrator routing ensures appropriate framework selection.

---

## Appendix: Framework Cross-Reference

| Framework | Analysis | Architect | Advisor | Planner | Implementer |
|-----------|----------|-----------|---------|---------|-------------|
| Chesterton's Fence | Research | Primary | - | - | - |
| Cynefin | Primary | - | Primary | Secondary | - |
| Wardley Mapping | Primary | - | - | Secondary | - |
| OODA Loop | - | - | Primary | - | - |
| Three Horizons | - | - | Secondary | Primary | - |
| Lindy Effect | Primary | Secondary | - | - | - |
| Strangler Fig | Secondary | Primary | - | Secondary | - |
| Core vs Context | - | Primary | Primary | - | - |
| Inversion Thinking | - | - | Primary | - | - |
| Path Dependence | - | Primary | - | - | - |
| CAP Theorem | Secondary | Secondary | - | - | - |
| Conway's Law | - | Primary | Secondary | - | - |

**Legend**: Primary (central to role), Secondary (supporting knowledge), - (not applicable)

---

## Conclusion

The engineering knowledge additions provide foundational mental models and strategic frameworks spanning 5 experience tiers. This analysis identified 18 high-impact opportunities to integrate this wisdom into agents (6 opportunities), skills (4), commands (2), and cross-cutting improvements (6).

**Priority Focus**: P0 items (22 hours) deliver immediate value through strategic research frameworks (analyst), principal-level decision-making (architect), migration patterns (architect), inversion thinking (decision-critic), unified knowledge index (memory system), and cross-agent strategic references.

**Implementation Strategy**: Phased rollout over 5 weeks maximizes early value through foundational improvements (week 1), strategic integration (week 2), agent enrichment (week 3), workflow integration (week 4), and polish/training (week 5).

**Expected Outcome**: AI agents make strategically informed decisions grounded in proven engineering wisdom. Mental models become first-class citizens in planning, design, and analysis workflows. Knowledge propagates through explicit references rather than implicit assumptions.
