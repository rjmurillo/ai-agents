---
name: session
description: Skills for session management and protocol compliance including session initialization, log fixing, and QA validation eligibility checking.
license: MIT
metadata:
  version: 2.0.0
  model: claude-sonnet-4-5
---

# Session Management Skills

Unified collection of skills for session protocol compliance and management.

---

## Available Skills

| Skill | Purpose | When to Use | Path |
|-------|---------|-------------|------|
| **init** | Create protocol-compliant session logs | Starting any new session | [init/](init/) |
| **log-fixer** | Fix session validation failures | After CI validation fails | [log-fixer/](log-fixer/) |
| **qa-eligibility** | Check QA skip eligibility | Before committing investigation work | [qa-eligibility/](qa-eligibility/) |

---

## Quick Reference

### Session Init

**Prevents** malformed session logs at creation time.

```text
/session-init
```

Creates session log from canonical template with immediate validation.

[Full Documentation →](init/SKILL.md)

### Session Log Fixer

**Fixes** session logs after CI validation failure.

```text
session-log-fixer: fix run 20548622722
```

Reads Job Summary, identifies issues, applies fixes.

[Full Documentation →](log-fixer/SKILL.md)

### QA Eligibility

**Validates** if investigation-only QA skip is allowed.

```powershell
pwsh .claude/skills/session/qa-eligibility/scripts/Test-InvestigationEligibility.ps1
```

Returns JSON with eligibility verdict.

[Full Documentation →](qa-eligibility/SKILL.md)

---

## Workflow Integration

### Session Start

1. **Initialize**: Use `/session-init` to create session log
2. Validates immediately with Validate-SessionProtocol.ps1
3. Proceed with Session Start checklist

### Session End

1. **Validate QA eligibility**: Run Test-InvestigationEligibility.ps1 (if investigation-only)
2. Complete Session End checklist
3. If CI fails validation: Use `/session-log-fixer`

---

## Pattern: Verification-Based Enforcement

All session skills follow this pattern:

| Aspect | Implementation |
|--------|----------------|
| **Verification** | File output or script exit code |
| **Feedback** | Immediate (seconds, not minutes) |
| **Enforcement** | Cannot proceed without passing |
| **Compliance** | Measured and tracked |

**Why it works**: Technical controls prevent violations at source rather than relying on trust.

---

## Related

| Reference | Description |
|-----------|-------------|
| [SESSION-PROTOCOL.md](../../../.agents/SESSION-PROTOCOL.md) | Canonical protocol requirements |
| [Validate-SessionProtocol.ps1](../../../scripts/Validate-SessionProtocol.ps1) | CI validation script |
| [ADR-034](../../../.agents/architecture/ADR-034-investigation-session-qa-exemption.md) | QA exemption architecture |
