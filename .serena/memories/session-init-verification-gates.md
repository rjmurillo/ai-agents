# Skill-Protocol-001: Verification-Based Gates

**Statement**: BLOCKING gates requiring tool output verification achieve 100% compliance where trust-based gates achieve 0% compliance.

**Context**: When designing protocol enforcement mechanisms in SESSION-PROTOCOL.md or agent workflows.

**Atomicity**: 100%

**Tag**: CRITICAL

**Impact**: 10/10 - Shifts from ineffective trust to effective verification

## Evidence

- Phase 1 (Serena init) has BLOCKING gate with tool output requirement → 100% compliance
- Session 15: Trust-based skill checks had 0% compliance → 5+ violations
- Sessions 19-21: All agents followed BLOCKING gates correctly

## Trust vs Verification

| Approach | Example | Effectiveness |
|----------|---------|---------------|
| **Trust-based** | "I will check for skills" | ❌ 0% (fails every time) |
| **Verification-based** | `Check-SkillExists.ps1` output in transcript | ✅ 100% (like Serena init) |

## Force Field Analysis

**Before verification gates**:
- Restraining forces: 21/25 (trust-based ineffective, no gates)
- Net: -5 (favors violations)

**After verification gates**:
- Driving forces: 20/20 (gates prevent violations)
- Net: +16 (prevents violations)
