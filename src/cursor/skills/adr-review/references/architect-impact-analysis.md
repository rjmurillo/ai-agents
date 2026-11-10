# Architecture Impact Analysis Deliverable

Loaded by the `architect` agent when milestone-planner asks for impact analysis. The agent body keeps the analysis checklist and the save path, so this file holds the template only.

```markdown
# Impact Analysis: [Feature] - Architecture

**Analyst**: Architect
**Date**: [YYYY-MM-DD]
**Complexity**: [Low/Medium/High]

## Impacts Identified

### Direct Impacts
- [Architectural layer/component]: [Type of change]
- [Pattern/principle]: [How affected]

### Indirect Impacts
- [System-wide implication]

## Affected Areas

| Architectural Concern | Type of Change | Risk Level | Reason |
|----------------------|----------------|------------|--------|
| [Concern] | [Modify/Extend/Violate] | [L/M/H] | [Why] |

## ADR Alignment

| ADR | Status | Notes |
|-----|--------|-------|
| ADR-NNNN | Aligns / Conflicts / Not Applicable | [Details] |

## Required Patterns

- **Pattern**: [Name] - [Why needed, how applied]
- **Pattern**: [Name] - [Why needed, how applied]

## Design Conflicts

| Conflict | Impact | Resolution |
|----------|--------|------------|
| [Conflict] | [Impact] | [Recommendation] |

## Long-Term Implications

- [Implication 1]: [Description]
- [Implication 2]: [Description]

## Domain Model Alignment

| Domain Concept | Current Representation | Proposed Change | Alignment Status |
|----------------|----------------------|-----------------|------------------|
| [Concept] | [Current] | [New] | [Aligned/Drift/Breaking] |

**Ubiquitous Language Impact**: [How domain language is affected]
**Bounded Context Changes**: [Any context boundary changes]

## Abstraction Consistency

| Layer | Current Abstraction | Change Impact | Consistency Status |
|-------|--------------------|--------------|--------------------|
| [Layer] | [Current] | [Impact] | [Maintained/Broken/Improved] |

**Abstraction Level Changes**: [Is the abstraction level appropriate]
**Interface Stability**: [Impact on public interfaces]

## Recommendations

1. [Architectural approach with rationale]
2. [Pattern to enforce]
3. [New ADR needed]

## Issues Discovered

| Issue | Priority | Category | Description |
|-------|----------|----------|-------------|
| [Issue ID] | [P0/P1/P2] | [Design Flaw/Risk/Debt/Blocker] | [Brief description] |

**Issue Summary**: P0: [N], P1: [N], P2: [N], Total: [N]

## Dependencies

- [Dependency on architectural decision]
- [Dependency on refactoring]

## Estimated Effort

- **Design work**: [Hours/Days]
- **ADR creation**: [Hours/Days]
- **Total**: [Hours/Days]
```
