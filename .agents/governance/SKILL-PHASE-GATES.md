# Skill Phase Gates

## Purpose

Phase gates are explicit checkpoints within skills that **force structured re-evaluation** at critical points. They prevent protocol bypasses by blocking progression until conditions are verified.

**Key insight**: The value is not determinism but **forcing iteration**. Phase gates structure when re-evaluation happens while preserving LLM judgment for what to do at each gate.

---

## Gate Types

### 1. Evidence Gate

**Purpose**: Require sufficient evidence before conclusions.

**Use when**: Skill makes conclusions, recommendations, or decisions.

**Implementation**:

```markdown
### GATE: Evidence Sufficiency

**BLOCKING**: Do NOT proceed until:
- [ ] Minimum [N] independent sources consulted
- [ ] Sources documented with file paths or URLs
- [ ] Conflicting evidence noted if present

**Pass criteria**: Include in --thoughts: "Evidence gate: [N] sources from [locations]"
```

**Example skills**: analyze, security-detection, adr-review

---

### 2. Verification Gate

**Purpose**: Require confirmation of state before proceeding.

**Use when**: Skill modifies state or makes irreversible changes.

**Implementation**:

```markdown
### GATE: State Verification

**BLOCKING**: Do NOT proceed until:
- [ ] Current state documented
- [ ] Expected end state documented
- [ ] Rollback path identified (if applicable)

**Pass criteria**: Include in --thoughts: "Verification gate: [current] -> [expected]"
```

**Example skills**: merge-resolver, session-log-fixer

---

### 3. Review Gate

**Purpose**: Require handoff to reviewer before finalization.

**Use when**: Skill produces artifacts that require validation.

**Implementation**:

```markdown
### GATE: Review Required

**BLOCKING**: Do NOT finalize until:
- [ ] Artifact written to designated location
- [ ] Review agent/step invoked
- [ ] Review verdict: PASS or PASS_WITH_CONCERNS

**Pass criteria**: Review verdict documented in output
```

**Example skills**: planner (review phase), prompt-engineer

---

### 4. Documentation Gate

**Purpose**: Require artifact creation before proceeding.

**Use when**: Skill has intermediate artifacts that must be persisted.

**Implementation**:

```markdown
### GATE: Documentation Required

**BLOCKING**: Do NOT proceed until:
- [ ] Artifact written to [path]
- [ ] File existence verified
- [ ] Content summary included in --thoughts

**Pass criteria**: File path in output
```

**Example skills**: planner (plan file), analyze (findings file)

---

## Gate Placement Guidelines

### When to Add Gates

| Condition | Gate Type | Rationale |
|-----------|-----------|-----------|
| Skill makes conclusions | Evidence | Prevent unfounded conclusions |
| Skill modifies files | Verification | Prevent unintended changes |
| Skill produces final output | Review | Catch quality issues |
| Skill has multi-step workflow | Documentation | Preserve intermediate state |

### When NOT to Add Gates

| Condition | Rationale |
|-----------|-----------|
| Single-step skill | Overhead exceeds benefit |
| Read-only skill | No risk of incorrect modification |
| Time-critical path | Gate latency unacceptable |
| Skill has external enforcement | Redundant (e.g., PR checks) |

---

## Implementation Patterns

### Pattern A: Script-Enforced Gates

For skills with Python/PowerShell scripts:

```python
# In skill script
def check_evidence_gate(thoughts: str) -> bool:
    """Verify evidence gate was passed."""
    return "Evidence gate:" in thoughts and "sources" in thoughts

if step_number == 2 and not check_evidence_gate(thoughts):
    print("BLOCKED: Evidence gate not satisfied")
    print("Required: Document sources before proceeding")
    sys.exit(1)
```

**Pros**: Hard enforcement, cannot bypass
**Cons**: Requires script modification

### Pattern B: Documentation-Enforced Gates

For skills without scripts (SKILL.md only):

```markdown
## Phase 2: Analysis

**PREREQUISITE**: Phase 1 evidence gate must be passed.

[Phase 2 instructions]

### GATE: Analysis Verification

[Gate definition]
```

**Pros**: Zero code changes, immediate deployment
**Cons**: Soft enforcement, relies on LLM compliance

### Pattern C: Hybrid Enforcement

Combine documentation gates with output validation:

```markdown
## Phase 2 Output Format

When completing Phase 2, you MUST include:

```text
GATE_STATUS:
  evidence_gate: PASSED | sources: [count]
  verification_gate: PASSED | state: [description]
```

This format is validated by downstream consumers.
```

**Pros**: Balance of flexibility and enforcement
**Cons**: Validation logic must exist downstream

---

## Reference Implementation: Planner Skill

The planner skill demonstrates all gate types:

| Phase | Gate | Type | Enforcement |
|-------|------|------|-------------|
| Planning → Review | Documentation | Plan file must exist | Script checks path |
| Review Step 1 | Review | TW review required | Script blocks step 2 |
| Review Step 2 | Review | QR review required | Script emits verdict |
| Review → Execution | Verification | PASS verdict required | Script checks status |

See: `.claude/skills/planner/SKILL.md`

---

## Compliance Checklist

When adding phase gates to a skill:

- [ ] Identify high-risk transition points
- [ ] Select appropriate gate type for each
- [ ] Write gate definition with explicit pass criteria
- [ ] Choose enforcement pattern (script/documentation/hybrid)
- [ ] Add gate status to skill output format
- [ ] Document in SKILL.md
- [ ] Test bypass attempts

---

## Skill Gate Matrix

| Skill | Evidence | Verification | Review | Documentation | Status |
|-------|----------|--------------|--------|---------------|--------|
| planner | - | - | Yes | Yes | Compliant |
| merge-resolver | Required | Required | - | - | Pending |
| analyze | Required | - | - | Required | Pending |
| session-log-fixer | - | Required | - | - | Pending |
| adr-review | Required | - | Required | - | Pending |
| prompt-engineer | - | - | Required | - | Pending |

---

## Metrics

Track gate effectiveness:

| Metric | Target | Measurement |
|--------|--------|-------------|
| Gate bypass rate | <5% | Audit skill outputs for gate status |
| Protocol violations | <10% (from 60%) | Session log analysis |
| Rework cycles | -50% | Count iterations before acceptance |

---

## Related Documents

- [ADR-033](../architecture/ADR-033-routing-level-enforcement-gates.md): Routing-level enforcement gates
- [SKILL-CREATION-CRITERIA.md](./SKILL-CREATION-CRITERIA.md): When to create skills
- [Agent Design Principles](./agent-design-principles.md): Composability requirement

---

*Governance Version: 1.2*
*Established: 2025-12-30*
*Updated: 2025-12-30 - Removed ADR-032 reference (number reserved for exit code standardization per PR #557)*
*ADR Reference: ADR-033 (routing-level)*
