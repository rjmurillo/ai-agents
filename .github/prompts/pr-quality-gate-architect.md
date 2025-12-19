# Architect Review Task

You are reviewing a pull request for architectural design and system structure concerns.

## Analysis Focus Areas

### 1. Design Pattern Adherence

- Does the change follow established design patterns (SOLID, DRY, KISS)?
- Are there anti-patterns introduced (God objects, circular dependencies)?
- Is dependency injection used appropriately?
- Are interfaces and abstractions at the right level?

### 2. System Boundaries

- Are module boundaries respected?
- Is separation of concerns maintained?
- Are cross-cutting concerns handled properly (logging, caching)?
- Is there appropriate layering (presentation, business, data)?

### 3. Extensibility & Scalability

- Will this design accommodate future requirements?
- Are extension points provided where needed?
- Could this become a bottleneck under load?
- Is the solution over-engineered or under-engineered?

### 4. Coupling & Cohesion

- **Coupling**: Are dependencies minimized and explicit?
- **Cohesion**: Do components have single, clear responsibilities?
- Are there hidden dependencies or implicit contracts?
- Is the public API surface appropriate?

### 5. Breaking Changes

- Does this introduce breaking changes to public APIs?
- Are consumers of changed interfaces considered?
- Is there a migration path for existing code?
- Are version compatibility concerns addressed?

### 6. Technical Debt

- Does this add or reduce technical debt?
- Are there TODOs or FIXMEs that should be addressed?
- Is the solution sustainable long-term?
- Are there shortcuts that will cause problems later?

### 7. Architecture Decision Records (ADRs)

- Does this change introduce significant architectural decisions?
- Are new patterns, frameworks, or dependencies being introduced without ADR?
- Is there a technology choice that should be documented?
- Are trade-offs being made that future maintainers need to understand?
- Check `.agents/architecture/` or `docs/adr/` for existing ADRs

**ADR-worthy decisions include**:

- New external dependencies or frameworks
- Changes to data storage or caching strategies
- New integration patterns or protocols
- Security architecture changes
- Performance optimization trade-offs
- Deprecation of existing patterns

## Output Requirements

Provide your analysis in this format:

### Design Quality Assessment

| Aspect | Rating (1-5) | Notes |
|--------|--------------|-------|
| Pattern Adherence | | |
| Boundary Respect | | |
| Coupling | | |
| Cohesion | | |
| Extensibility | | |

**Overall Design Score**: X/5

### Architectural Concerns

| Severity | Concern | Location | Recommendation |
|----------|---------|----------|----------------|
| Critical/High/Medium/Low | [issue] | [file:line] | [fix] |

### Breaking Change Assessment

- **Breaking Changes**: Yes/No
- **Impact Scope**: None/Minor/Major
- **Migration Required**: Yes/No
- **Migration Path**: [description if applicable]

### Technical Debt Analysis

- **Debt Added**: Low/Medium/High
- **Debt Reduced**: Low/Medium/High
- **Net Impact**: Improved/Neutral/Degraded

### ADR Assessment

- **ADR Required**: Yes/No
- **Decisions Identified**: [list architectural decisions found]
- **Existing ADR**: [reference if found, or "None"]
- **Recommendation**: [Create ADR / Update existing / N/A]

### Recommendations

1. [Specific architectural improvements]

### Verdict

Choose ONE verdict:

- `VERDICT: PASS` - Design is sound and well-structured
- `VERDICT: WARN` - Minor design issues, non-blocking
- `VERDICT: CRITICAL_FAIL` - Significant architectural issues that block merge

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [Brief explanation]
```

## Critical Failure Triggers

Automatically use `CRITICAL_FAIL` if you find:

- Breaking changes to public APIs without migration path
- Circular dependencies introduced
- Violation of core architectural patterns (e.g., bypassing abstraction layers)
- God objects or classes with >10 responsibilities
- Hard-coded dependencies that should be injected
- Data layer accessed directly from presentation layer
- Significant architectural decisions without corresponding ADR
