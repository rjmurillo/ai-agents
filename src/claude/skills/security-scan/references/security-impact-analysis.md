# Security Impact Analysis Deliverable

Loaded by the `security` agent when milestone-planner asks for impact analysis. The agent body keeps the save path, so this file holds the template only.

```markdown
# Impact Analysis: [Feature] - Security

**Analyst**: Security
**Date**: [YYYY-MM-DD]
**Complexity**: [Low/Medium/High]

## Impacts Identified

### Direct Impacts
- [Security boundary/control]: [Type of change]
- [Attack surface]: [How affected]

### Indirect Impacts
- [Cascading security concern]

## Affected Areas

| Security Domain | Type of Change | Risk Level | Reason |
|-----------------|----------------|------------|--------|
| Authentication | [Add/Modify/Remove] | [L/M/H] | [Why] |
| Authorization | [Add/Modify/Remove] | [L/M/H] | [Why] |
| Data Protection | [Add/Modify/Remove] | [L/M/H] | [Why] |
| Input Validation | [Add/Modify/Remove] | [L/M/H] | [Why] |

## Attack Surface Analysis

| New Surface | Threat Level | Mitigation Required |
|-------------|--------------|---------------------|
| [Surface] | [L/M/H/Critical] | [Control] |

## Threat Vectors

| Threat | STRIDE Category | Likelihood | Impact | Mitigation |
|--------|-----------------|------------|--------|------------|
| [Threat] | [S/T/R/I/D/E] | [L/M/H] | [L/M/H] | [Strategy] |

## Required Security Controls

| Control | Priority | Type | Implementation Effort |
|---------|----------|------|----------------------|
| [Control] | [P0/P1/P2] | [Preventive/Detective/Corrective] | [L/M/H] |

## Compliance Implications

- [Regulation/Standard]: [Impact]
- [Regulation/Standard]: [Impact]

## Security Testing Requirements

| Test Type | Scope | Effort |
|-----------|-------|--------|
| Penetration Testing | [Areas] | [L/M/H] |
| Security Code Review | [Areas] | [L/M/H] |
| Vulnerability Scanning | [Areas] | [L/M/H] |

## Blast Radius Assessment

| If Control Fails | Systems Affected | Data at Risk | Containment Strategy |
|------------------|-----------------|--------------|---------------------|
| [Control] | [Systems] | [Data types] | [Strategy] |

**Worst Case Impact**: [Description of maximum damage if breach occurs]
**Isolation Boundaries**: [What limits the spread of a compromise]

## Dependency Security

| Dependency | Version | Known Vulnerabilities | Risk Level | Action Required |
|------------|---------|----------------------|------------|-----------------|
| [Package/Library] | [Ver] | [CVE list or None] | [L/M/H/Critical] | [Update/Monitor/Accept] |

**Transitive Dependencies**: [List critical transitive deps]
**License Compliance**: [Any license concerns]

## Recommendations

1. [Security architecture approach]
2. [Specific control to implement]
3. [Testing strategy]

## Issues Discovered

| Issue | Priority | Category | Description |
|-------|----------|----------|-------------|
| [Issue ID] | [P0/P1/P2] | [Vulnerability/Risk/Compliance/Blocker] | [Brief description] |

**Issue Summary**: P0: [N], P1: [N], P2: [N], Total: [N]

## Dependencies

- [Dependency on security library/framework]
- [Dependency on infrastructure security]

## Estimated Effort

- **Security design**: [Hours/Days]
- **Control implementation**: [Hours/Days]
- **Security testing**: [Hours/Days]
- **Total**: [Hours/Days]
```
