# Skill-Protocol-002: Verification-Based Gate Effectiveness

## Statement

Verification-based BLOCKING gates (tool output required) achieve 100% compliance where trust-based guidance fails

## Context

When adding new protocol requirements to SESSION-PROTOCOL.md

## Evidence

SESSION-PROTOCOL.md Phase 1 (Serena init) has BLOCKING gate → 100% compliance (never violated)
Sessions 19-21 (2025-12-18): All followed BLOCKING gates correctly

Session 15 retrospective: Trust-based guidance ("agent should remember") had 5+ violations

## Metrics

- Atomicity: 100%
- Impact: 10/10
- Category: process, governance, protocol
- Created: 2025-12-18
- Tag: helpful
- Validated: 1

## Related Skills

- Skill-Analysis-001 (Comprehensive Analysis Standard)
- Skill-Testing-002 (Test-First Development)

## Gate Types Comparison

### Verification-Based BLOCKING Gate (100% Compliance)

**Pattern**:

```markdown
## Phase 1: Serena Initialization (BLOCKING)

You MUST NOT proceed to any other action until both calls succeed:

1. mcp__serena__activate_project (with project path)
2. mcp__serena__initial_instructions

**Verification**: Tool output appears in session transcript.
```

**Why it works**:

- Clear requirement: "MUST NOT proceed"
- Verifiable: Tool output visible
- Blocking: Cannot continue without completing
- Testable: Check transcript for tool output

### Trust-Based Guidance (Low Compliance)

**Pattern**:

```markdown
## Session Context

Agents should read HANDOFF.md to understand prior work.
```

**Why it fails**:

- Vague requirement: "should" not "MUST"
- Not verifiable: No evidence in transcript
- Not blocking: Can skip without consequence
- Not testable: Cannot check compliance

## BLOCKING Gate Design

### Required Elements

1. **BLOCKING keyword**: Signals non-negotiable requirement
2. **MUST language**: RFC 2119 imperative ("MUST", "MUST NOT")
3. **Verification method**: How to check compliance
4. **Tool output**: Evidence appears in transcript
5. **Consequence**: Clear what happens if skipped

### Template

```markdown
## Phase X: [Name] (BLOCKING)

You MUST [action] before [next step]:

1. [Required action 1]
2. [Required action 2]

**Verification**: [How to verify - tool output, file exists, etc.]

**If skipped**: [Consequence - context lost, errors, etc.]
```

## Examples from SESSION-PROTOCOL.md

### Phase 1: Serena Initialization ✅

**BLOCKING**: Yes
**Verification**: Tool output in transcript
**Compliance**: 100% (never violated)

### Phase 2: Context Retrieval ✅

**BLOCKING**: Yes (MUST read HANDOFF.md)
**Verification**: File content appears in session
**Compliance**: 100% (Sessions 19-21 all complied)

### Phase 3: Session Log ✅

**BLOCKING**: Yes (MUST create session log)
**Verification**: File exists at .agents/sessions/
**Compliance**: 100% (All sessions have logs)

## Anti-Pattern: Trust-Based Requirements

**Before (Session 15 had 5+ violations)**:

```markdown
Agents should remember to:
- Read skill-usage-mandatory
- Check for existing skills
- Follow naming conventions
```

**After (Phase 1.5 added - BLOCKING)**:

```markdown
## Phase 1.5: Skill Validation (BLOCKING)

You MUST read skill-usage-mandatory memory before creating skills:

mcp__serena__read_memory(memory_file_name="skill-usage-mandatory")

**Verification**: Memory content appears in session transcript
```

**Result**: 0 violations after BLOCKING gate added

## Success Criteria

- BLOCKING keyword present
- MUST language (RFC 2119)
- Verification method documented
- Tool output visible in transcript
- Compliance rate: 100%
- Zero violations across sessions
