# Code Impact Analysis Deliverable

Loaded by the `implementer` agent when milestone-planner asks for impact analysis. The agent body keeps the save path, so this file holds the template only.

```markdown
# Impact Analysis: [Feature] - Code

**Analyst**: Implementer
**Date**: [YYYY-MM-DD]
**Complexity**: [Low/Medium/High]

## Impacts Identified

### Direct Impacts
- [File/Module]: [Type of change required]
- [File/Module]: [Type of change required]

### Indirect Impacts
- [File/Module]: [Cascading change needed]

## Affected Areas

| Component/File | Type of Change | Risk Level | Reason |
|----------------|----------------|------------|--------|
| [Path] | [Add/Modify/Remove] | [L/M/H] | [Why risky] |

## Existing Patterns

- **Pattern**: [Name] - [How it applies]
- **Pattern**: [Name] - [How it applies]

## Testing Complexity

| Test Type | Complexity | Reason |
|-----------|------------|--------|
| Unit | [L/M/H] | [Why] |
| Integration | [L/M/H] | [Why] |
| E2E | [L/M/H] | [Why] |

## Code Quality Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| [Risk] | [L/M/H] | [L/M/H] | [Strategy] |

## Breaking Changes

| Change | Severity | Migration Path |
|--------|----------|----------------|
| [API change] | [Breaking/Deprecation/None] | [How to migrate or N/A] |

**Backward Compatibility**: [Yes/No/Partial]
**Deprecation Strategy**: [Immediate removal/Deprecation period/Version bump only]

## Recommendations

1. [Specific code approach with rationale]
2. [Pattern to use/avoid]
3. [Refactoring needed first]

## Issues Discovered

| Issue | Priority | Category | Description |
|-------|----------|----------|-------------|
| [Issue ID] | [P0/P1/P2] | [Bug/Risk/Debt/Blocker] | [Brief description] |

**Issue Summary**: P0: [N], P1: [N], P2: [N], Total: [N]

## Dependencies

- [Dependency on library/framework version]
- [Dependency on other code changes]

## Estimated Effort

- **Implementation**: [Hours/Days]
- **Testing**: [Hours/Days]
- **Total**: [Hours/Days]
```
