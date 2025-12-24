# Security Validation Chain

## Skill-Security-001: Multi-Agent Security Validation Chain (88%)

**Statement**: Security findings require three-agent validation: security analysis → qa verification → devops compatibility check.

**Context**: When remediating security vulnerabilities

**Evidence**: Session 44 used Security → QA → DevOps chain, all passed, remediation successful

**Pattern**:

```text
Security Agent:
  - Threat analysis
  - Remediation plan (SR-XXX report)
  ↓
QA Agent:
  - Syntax validation
  - Acceptance criteria verification
  - QA report
  ↓
DevOps Agent:
  - CI compatibility check
  - Build time impact assessment
  - Platform availability verification
  ↓
Implementer:
  - Apply remediation
  - Commit with all three reports
```

**Two-Phase Pattern** (for planning):

```text
Phase 1 (Pre-Implementation):
  security agent → Threat model, required controls

Phase 2 (Implementation):
  implementer → Code + flag security-relevant changes

Phase 3 (Post-Implementation):
  security agent → Verify controls, actual code review
```

**Anti-Pattern**:

- Single security review at planning time only
- Security not re-engaged after implementation
- No handoff from implementer back to security
- Single-agent security review without downstream validation

**Source**: `.agents/retrospective/phase1-remediation-pr43.md`
