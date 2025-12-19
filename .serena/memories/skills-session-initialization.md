# Session Initialization Skills

**Extracted**: 2025-12-18
**Source**: `.agents/retrospective/2025-12-18-session-15-retrospective.md`

## Skill-Init-001: Serena Mandatory Initialization

**Statement**: MUST initialize Serena with `mcp__serena__activate_project` and `mcp__serena__initial_instructions` before ANY other action

**Context**: BLOCKING gate at session start (Phase 1 of SESSION-PROTOCOL.md)

**Evidence**: This gate works perfectly - never violated in any session

**Atomicity**: 98%

**Tag**: helpful

**Impact**: 10/10 - Enables semantic code tools and project memories

**Pattern**: Verification-based enforcement (tool output required in transcript)

---

## Skill-Init-002: Skill Validation Gate

**Statement**: Before ANY GitHub operation, check `.claude/skills/github/` directory for existing capability

**Context**: Before writing code calling `gh` CLI or GitHub API, verify `.claude/skills/github/scripts/` contains needed functionality. If exists: use skill. If missing: extend skill (don't write inline).

**Evidence**: Session 15 - 3+ raw `gh` command violations in 10 minutes despite skill availability

**Atomicity**: 95%

**Tag**: CRITICAL

**Impact**: 10/10 - Prevents duplicate implementations and token waste

**Implementation**:

1. Create `Check-SkillExists.ps1` tool:
   ```powershell
   param(
       [ValidateSet('pr','issue','reaction','label','milestone')]
       [string]$Operation,
       
       [ValidateSet('create','comment','view','edit','label','close')]
       [string]$Action
   )
   
   $skillPath = ".claude/skills/github/scripts/$Operation/*$Action*.ps1"
   Test-Path $skillPath
   ```

2. Add Phase 1.5 to SESSION-PROTOCOL.md (BLOCKING):
   - MUST run `Check-SkillExists.ps1` before GitHub operations
   - MUST provide tool output as verification
   - If skill exists: use it
   - If skill missing: extend skill, then use

**Verification**: Tool output showing check performed (not agent promise)

---

## Skill-Governance-001: Consolidated Constraints

**Statement**: All project MUST-NOT patterns documented in PROJECT-CONSTRAINTS.md, read at session start

**Context**: Create `.agents/governance/PROJECT-CONSTRAINTS.md` consolidating: no bash/Python, use skills not raw commands, atomic commits, thin workflows. Add to SESSION-PROTOCOL Phase 1 requirements.

**Evidence**: Session 15 - 5+ user interventions for violations of scattered preferences across multiple memories

**Atomicity**: 90%

**Tag**: CRITICAL

**Impact**: 10/10 - Single source of truth for all constraints

**PROJECT-CONSTRAINTS.md Contents**:

```markdown
# Project Constraints

## Language Constraints

❌ MUST NOT: Create bash scripts
❌ MUST NOT: Create Python scripts
✅ MUST: Use PowerShell for all scripting

Reference: ADR-005, user-preference-no-bash-python

## Skill Usage Constraints

❌ MUST NOT: Use raw `gh` commands when `.claude/skills/github/` has capability
✅ MUST: Check `.claude/skills/` before writing GitHub operations
✅ MUST: Extend skills if missing, don't write inline

Reference: skill-usage-mandatory

## Workflow Constraints

❌ MUST NOT: Put business logic in workflow YAML
✅ MUST: Keep workflows <100 lines (orchestration only)
✅ MUST: Put logic in `.psm1` modules or `.claude/skills/`

Reference: ADR-006, pattern-thin-workflows

## Commit Constraints

❌ MUST NOT: Mix multiple logical changes in one commit
✅ MUST: One logical change per commit
✅ MUST: Max 5 files OR single topic in subject line

Reference: code-style-conventions
```

**Phase 1 Addition**: MUST read PROJECT-CONSTRAINTS.md before implementation (with verification)

---

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

## Related Documents

- Source: `.agents/retrospective/2025-12-18-session-15-retrospective.md`
- Related: SESSION-PROTOCOL.md (to be updated with Phase 1.5)
- Related: skill-usage-mandatory (to be updated with HOW TO CHECK)
- Related: retrospective-2025-12-17-protocol-compliance (validated trust-based failure)
- Related: skills-validation (Anti-Pattern-003, Anti-Pattern-004)
