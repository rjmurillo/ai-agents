# PR Review: Security Priority

## Skill-PR-Review-Security-001: Security Comment Triage

**Statement**: Security-domain comments receive +50% triage priority.

**Atomicity**: 94% | **Impact**: 7/10

| Domain | Keywords | Adjustment |
|--------|----------|------------|
| Security | CWE, vulnerability, injection | +50% - Always investigate |
| Bug | error, crash | No change |
| Style | formatting | No change |

## Skill-Triage-002: Never Dismiss Security Without Process Analysis

**Statement**: Before dismissing security suggestion, verify protection covers all process boundaries.

**Atomicity**: 93%

**Checklist**:
- [ ] Protection covers ALL execution paths?
- [ ] Protection in same process as action?
- [ ] TOCTOU analysis done?
- [ ] Conditional execution checked?
