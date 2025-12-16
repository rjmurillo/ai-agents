# Security Skills

**Extracted**: 2025-12-16
**Source**: `.agents/retrospective/phase1-remediation-pr43.md`

## Skill-Security-001: Two-Phase Security Review

**Statement**: Security review requires TWO phases: pre-implementation (threat model, controls) and post-implementation (verification, actual code review)

**Context**: Any feature with security implications

**Evidence**: Issue #I7 - security script not re-reviewed after implementation; implementer is best positioned to flag security-relevant changes during coding

**Atomicity**: 94%

**Tag**: helpful

**Impact**: 10/10

**Pattern**:

```text
Phase 1 (Pre-Implementation):
  security agent → Threat model, required controls, security requirements
  
Phase 2 (Implementation):  
  implementer → Code + flag security-relevant changes for review
  
Phase 3 (Post-Implementation):
  security agent → Verify controls implemented, actual code review
```

**Anti-Pattern**:

- Single security review at planning time only
- Security not re-engaged after implementation
- No handoff from implementer back to security

---

## Related Documents

- Source: `.agents/retrospective/phase1-remediation-pr43.md`
- Issue: #I7 in retrospective
- Related: skills-process-workflow-gaps (workflow patterns)
