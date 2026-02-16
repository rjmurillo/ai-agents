# Protocol: Verificationbased Gates

## Skill-Protocol-001: Verification-Based Gates

**Statement**: BLOCKING gates requiring tool output verification achieve 100% compliance where trust-based gates achieve 0% compliance

**Context**: When designing protocol enforcement mechanisms in SESSION-PROTOCOL.md or agent workflows

**Evidence**: 
- Phase 1 (Serena init) has BLOCKING gate with tool output requirement → 100% compliance (never violated)
- Session 15: Trust-based skill checks had 0% compliance → 5+ violations
- Sessions 19-21: All agents followed BLOCKING gates correctly (Phase 1, Phase 2, Phase 3)

**Atomicity**: 100%

- Single concept (verification vs trust) ✓
- Specific metric (100% vs 0% compliance) ✓
- Actionable (use verification-based gates) ✓
- Length: 14 words ✓

**Tag**: CRITICAL

**Impact**: 10/10 - Shifts from ineffective trust to effective verification

**Trust vs Verification**:

| Approach | Example | Effectiveness |
|----------|---------|---------------|
| **Trust-based** | "I will check for skills" | ❌ 0% (fails every time) |
| **Verification-based** | `Check-SkillExists.ps1` output in transcript | ✅ 100% (like Serena init) |

**Protocol Enhancement**:

Add Phase 1.5 (BLOCKING) to SESSION-PROTOCOL.md:

```markdown
### Phase 1.5: Constraint Validation (BLOCKING)

| Req | Step | Verification |
|-----|------|--------------|
| MUST | Read PROJECT-CONSTRAINTS.md | File content appears in context |
| MUST | Run Check-SkillExists.ps1 for planned operations | Tool output in transcript |
| MUST | List .claude/skills/github/scripts/ | Directory structure visible |
```

**Force Field Analysis**:

Before verification gates:
- Restraining forces: 21/25 (trust-based ineffective, no gates, scattered docs)
- Driving forces: 16/20 (documentation exists, user frustration)
- Net: -5 (favors violations)

After verification gates:
- Restraining forces: 4/25 (gates added, docs consolidated, verification enforced)
- Driving forces: 20/20 (all documentation accessible, gates prevent violations)
- Net: +16 (prevents violations)

---

## Implementation Roadmap

### P0 (Immediate - Next Session)

1. **Create PROJECT-CONSTRAINTS.md** (30 min)
   - Consolidate all MUST-NOT patterns
   - Add to `.agents/governance/`
   - Version control

2. **Create Check-SkillExists.ps1** (20 min)
   - Implement in `scripts/`
   - Add Pester tests
   - Document usage

3. **Add Phase 1.5 to SESSION-PROTOCOL.md** (15 min)
   - Add BLOCKING gate section
   - Require verification (not trust)
   - Update session log template

### P1 (Next 1-2 Sessions)

4. **Create commit-msg hook for atomicity** (45 min)
   - Parse subject line for topics
   - Count staged files
   - Reject if >5 files AND >1 topic

5. **Update skill-usage-mandatory** (10 min)
   - Add "HOW TO CHECK" section
   - Reference Check-SkillExists.ps1
   - Provide usage examples

### P2 (Enhancement)

6. **Automated timeline generation** (60 min)
   - Extract agent actions from session logs
   - Generate timeline tables
   - Reduce retrospective time

7. **Pre-retrospective validation checklist** (30 min)
   - Validate session log exists
   - Check commits clean
   - Verify user feedback captured

---

## Success Metrics

| Metric | Before (Session 15) | Target (After Gates) |
|--------|---------------------|----------------------|
| User interventions per session | 5+ | 0-1 |
| Violations requiring rework | 4 | 0 |
| Time lost to rework | 30-45 min | 0-5 min |
| Success rate (clean outcomes) | 42% | 95%+ |
| BLOCKING gate compliance | 100% (Serena) | 100% (all gates) |

---

## Related

- [protocol-002-verification-based-gate-effectiveness](protocol-002-verification-based-gate-effectiveness.md)
- [protocol-004-rfc-2119-must-evidence](protocol-004-rfc-2119-must-evidence.md)
- [protocol-005-template-enforcement](protocol-005-template-enforcement.md)
- [protocol-006-legacy-session-grandfathering](protocol-006-legacy-session-grandfathering.md)
- [protocol-012-branch-handoffs](protocol-012-branch-handoffs.md)
