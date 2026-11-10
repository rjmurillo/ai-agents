# Strategic Principles and Legacy Modernization Patterns

Loaded by the Copilot CLI `architect` body when an ADR or review touches one of these patterns. The VS Code body carries the same sections but has no skill tree, so it uses its inline summaries. The Claude body carries neither section and does not load this file.

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
