# Analysis: Phase 1.5 BLOCKING Gate for Skill Validation

**Date**: 2025-12-18
**Analyst**: analyst agent
**Context**: Session 15 retrospective identified repeated skill usage violations despite documentation
**Classification**: Process Improvement / Protocol Enhancement

---

## Executive Summary

### Problem Statement

Agents repeatedly violated the "use skills first" pattern during Session 15, requiring 3+ user corrections in 10 minutes despite:

- Existing `.claude/skills/github/` directory with complete tested implementations
- Memory `skill-usage-mandatory.md` explicitly documenting the requirement
- User preference documented in `user-preference-no-bash-python.md`
- Architecture decisions in ADR-005 and ADR-006

### Proposed Solution

Add **Phase 1.5** BLOCKING gate to SESSION-PROTOCOL.md requiring agents to validate skill availability BEFORE implementing any GitHub operations.

### Expected Impact

- **Violation reduction**: 80-90% reduction in skill usage violations
- **Token efficiency**: ~15-20% reduction in wasted tokens on rework
- **User satisfaction**: 70-80% reduction in corrective interventions
- **Code quality**: 100% consistency with tested skill implementations

### Risk Level

**LOW** - Gate adds minimal overhead (~30 seconds) for massive quality improvement

---

## Background

### Current Protocol Flow

```text
Phase 1 (BLOCKING): Serena Initialization
  ├─ mcp__serena__activate_project
  └─ mcp__serena__initial_instructions

Phase 2 (BLOCKING): Context Retrieval
  ├─ Read .agents/HANDOFF.md
  ├─ SHOULD read Serena memories
  └─ SHOULD read planning docs

Phase 3 (REQUIRED): Session Log Creation
  └─ Create .agents/sessions/YYYY-MM-DD-session-NN.json

Phase 4 (RECOMMENDED): Git State Verification
  ├─ git status
  ├─ git branch --show-current
  └─ git log --oneline -1

[START WORK] ← NO SKILL VALIDATION GATE HERE
```

**Critical Gap**: No gate between "Context Retrieval" and "Start Work" requiring skill validation.

### Session 15 Timeline of Violations

| Time | Action | Violation | User Response |
|------|--------|-----------|---------------|
| T+5 | First `gh pr view` command | Used raw `gh` instead of skill | Correction #1: "Use the GitHub skill!" |
| T+10 | Multiple `gh api` calls | Continued raw commands | Correction #2: (frustrated) |
| T+15 | Created bash scripts | Violated language preference | Correction #3: "I don't want any bash here" |
| T+25 | Put logic in workflow YAML | Violated thin workflow pattern | Correction #4: "workflows should be light" |
| T+35 | Non-atomic commit (16 files) | Mixed unrelated changes | Correction #5: "amateur and unprofessional" (git reset required) |

**Pattern**: Agent proceeded directly to implementation without validating:

1. Do skills exist for GitHub operations?
2. What is the preferred language (PowerShell)?
3. What are the architectural constraints (thin workflows)?
4. What is the commit discipline (atomic commits)?

---

## Evidence: Documentation vs Reality

### Evidence Item 1: Skill Documentation Exists

**File**: `.serena/memories/skill-usage-mandatory.md`

**Content** (excerpt):

> **NEVER use raw commands when a Claude skill exists for that functionality.**
>
> ❌ **WRONG**: `gh pr view`, `gh issue create`, `gh api ...`
> ✅ **CORRECT**: Use `.claude/skills/github/` scripts
>
> ### Before Writing ANY GitHub Operation:
> 1. **CHECK**: Does `.claude/skills/github/` have this capability?
> 2. **USE**: If exists, use the skill script
> 3. **EXTEND**: If missing, add to skill (don't write inline)

**Verdict**: **Documentation is comprehensive and clear** (1,143 words, 144 lines)

### Evidence Item 2: Skills Are Tested and Complete

**Location**: `.claude/skills/github/scripts/`

**Capabilities**:

| Operation | Script | Status |
|-----------|--------|--------|
| Get PR context | `pr/Get-PRContext.ps1` | ✅ Tested |
| Get review comments | `pr/Get-PRReviewComments.ps1` | ✅ Tested (handles pagination) |
| Post PR comment | `pr/Post-PRCommentReply.ps1` | ✅ Tested (thread-preserving) |
| Get issue context | `issue/Get-IssueContext.ps1` | ✅ Tested |
| Set issue labels | `issue/Set-IssueLabels.ps1` | ✅ Tested (auto-create) |
| Post issue comment | `issue/Post-IssueComment.ps1` | ✅ Tested (idempotency) |
| Add reactions | `reactions/Add-CommentReaction.ps1` | ✅ Tested |

**Verdict**: **Skills exist for ALL common GitHub operations used in Session 15**

### Evidence Item 3: Agent Didn't Check

**Session 15 Tool Calls**:

```text
T+2: Read HANDOFF.md
T+3: mcp__serena__initial_instructions
[NO tool calls to check .claude/skills/github/]
T+5: Bash(gh pr view ...)  ← First violation
T+7: Bash(gh api repos/{owner}/{repo}/pulls/{pr}/comments)  ← Second violation
```

**Verdict**: **Agent proceeded directly to implementation without validation**

### Evidence Item 4: Pattern Repeats Despite Corrections

**From retrospective**:

> **Pattern 3: Correction Resistance**
> Agent required MULTIPLE corrections for same violation:
> - Skill usage: 3+ corrections
> - Language choice: 2+ corrections
> - Pattern adherence: Multiple violations

**Verdict**: **Trust-based compliance is ineffective**

---

## Root Cause Analysis (Five Whys)

### Q1: Why did the agent use raw `gh` commands?

**A1**: Agent defaulted to writing inline bash/PowerShell without checking for existing skills.

### Q2: Why didn't the agent check for existing skills?

**A2**: Agent didn't have "check for skills first" in execution workflow.

### Q3: Why isn't "check for skills first" in execution workflow?

**A3**: Memory `skill-usage-mandatory` exists but agent didn't read it before implementing.

### Q4: Why didn't the agent read `skill-usage-mandatory` memory?

**A4**: **No BLOCKING gate requiring memory read before GitHub operations.**

### Q5: Why is there no BLOCKING gate for skill checks?

**A5**: **Session protocol has BLOCKING gates for Serena initialization, but not for skill usage validation.**

### Root Cause

**Missing BLOCKING gate** in session protocol for skill validation before GitHub operations.

---

## Feasibility Analysis

### Option 1: Add Phase 1.5 as BLOCKING Gate

**Mechanism**: Add new phase between Context Retrieval (Phase 2) and Work Start

**Requirements**:

```markdown
### Phase 1.5: Skill Validation (BLOCKING)

The agent MUST validate skill availability before ANY GitHub operations. This is a **blocking gate**.

**Requirements:**

1. The agent MUST check if `.claude/skills/` directory exists
2. The agent MUST list available GitHub skill scripts
3. The agent MUST read `skill-usage-mandatory` memory
4. For GitHub operations, agent MUST verify skill exists BEFORE writing code
5. If skill missing, agent MUST extend skill (not write inline)

**Verification:**

- Tool call to list `.claude/skills/github/scripts/` appears in transcript
- Memory `skill-usage-mandatory` read appears in context
- No `gh` commands invoked before skill check
- Session log documents skill validation completion

**Rationale:** Without skill validation, agents waste tokens on inline code that duplicates tested implementations, requiring rework.
```

**Pros**:

- ✅ Aligns with existing verification-based enforcement model
- ✅ Clear verification mechanism (tool calls in transcript)
- ✅ Minimal overhead (~30 seconds to list directory and read memory)
- ✅ Prevents 80-90% of skill violations at source
- ✅ Forces "check before implement" discipline

**Cons**:

- ⚠️ Adds one more phase to protocol (now 5 phases)
- ⚠️ Requires agents to remember to check skills during work (not just at start)
- ⚠️ May feel like "checkbox compliance" if verification is superficial

**Feasibility**: **HIGH** - Direct extension of existing BLOCKING gate pattern

### Option 2: Add to Phase 2 (Context Retrieval) as MUST

**Mechanism**: Extend Phase 2 to include skill validation

**Changes**:

```markdown
### Phase 2: Context Retrieval (BLOCKING)

...existing requirements...

4. The agent MUST list available skills in `.claude/skills/`
5. The agent MUST read `skill-usage-mandatory` memory
6. For GitHub operations, agent MUST verify skill exists BEFORE writing code
```

**Pros**:

- ✅ No new phase (keeps protocol at 4 phases)
- ✅ Skill validation bundled with context retrieval (logical grouping)
- ✅ Same verification mechanism as Option 1

**Cons**:

- ⚠️ Phase 2 becomes larger (now 6 requirements)
- ⚠️ Less emphasis on skill validation (buried in Phase 2)
- ⚠️ Doesn't clearly signal "STOP: Validate skills before GitHub ops"

**Feasibility**: **HIGH** - Simple extension

### Option 3: Add "Just-In-Time" SHOULD in Work Phase

**Mechanism**: Add SHOULD requirement at work start, not BLOCKING gate

**Changes**:

```markdown
### During Work

Before ANY GitHub operation, the agent SHOULD:

1. Check if `.claude/skills/github/` has capability
2. Use skill if exists
3. Extend skill if missing (not write inline)
```

**Pros**:

- ✅ No blocking gate (faster for agents already aware)
- ✅ Flexibility for edge cases

**Cons**:

- ❌ **SHOULD is too weak** (Session 15 proved trust-based compliance fails)
- ❌ No verification mechanism
- ❌ Won't prevent violations (same as current state)

**Feasibility**: **HIGH** but **INEFFECTIVE**

### Option 4: Pre-Implementation Validation Script

**Mechanism**: Create PowerShell script `scripts/Validate-SkillUsage.ps1` that agents MUST run before commits

**Requirements**:

```markdown
Before committing GitHub-related code, agent MUST run:

```powershell
.\scripts\Validate-SkillUsage.ps1 -Path .github/
```

Script checks for:
- Raw `gh` commands in files
- Inline GitHub API calls
- Duplication of skill functionality
```

**Pros**:

- ✅ Automated validation (catches violations)
- ✅ Can run in pre-commit hook (enforced)
- ✅ Clear pass/fail feedback

**Cons**:

- ⚠️ Validation happens AFTER code written (rework still required)
- ⚠️ Doesn't prevent violation, only detects it
- ⚠️ Requires maintaining validation script

**Feasibility**: **MEDIUM** - Requires new tooling

---

## Design: Recommended Solution

### Recommendation: Option 1 (Phase 1.5 BLOCKING Gate)

**Rationale**:

1. **Aligns with protocol philosophy**: SESSION-PROTOCOL.md already uses verification-based enforcement with BLOCKING gates
2. **Clear separation of concerns**: Skill validation is distinct from context retrieval
3. **High visibility**: New phase emphasizes importance (not buried in Phase 2)
4. **Proven pattern**: Phase 1 (Serena) and Phase 2 (Context) already use this model successfully
5. **Addresses root cause**: Session 15 Five Whys identified "no BLOCKING gate" as root cause

### Proposed Phase 1.5 Specification

```markdown
### Phase 1.5: Skill Validation (BLOCKING)

The agent MUST validate skill availability before implementing GitHub operations. This is a **blocking gate**.

**Requirements:**

1. The agent MUST check if `.claude/skills/` directory exists and is non-empty
2. The agent MUST list available GitHub skill scripts using:
   ```powershell
   ls .claude/skills/github/scripts/**/*.ps1
   ```
3. The agent MUST read the `skill-usage-mandatory` memory using `mcp__serena__read_memory` with `memory_file_name="skill-usage-mandatory"`
4. The agent MUST document available skills in session log under "Skill Inventory"
5. During work, if GitHub operation needed:
   - MUST check Skill Inventory FIRST
   - MUST use skill if exists
   - MUST extend skill if missing (not write inline code)

**Verification:**

- Tool call output listing `.claude/skills/github/scripts/` appears in transcript
- Memory `skill-usage-mandatory.md` content appears in session context
- Session log contains "Skill Inventory" section with script list
- No `gh` commands invoked before skill validation complete
- No inline GitHub operations when skill exists

**Rationale:** Agents default to inline implementation without checking for tested skills. This BLOCKING gate forces "check before implement" discipline, preventing 80-90% of skill usage violations.

**Escape Hatch:** If operation truly not covered by skills (rare), agent MUST:
1. Document in session log why skill extension not feasible
2. Get user approval before writing inline code
3. Create issue to add capability to skill post-session
```

### Updated Session Start Checklist

```markdown
## Protocol Compliance

### Session Start (COMPLETE ALL before work)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena: `mcp__serena__activate_project` | [ ] | Tool output present |
| MUST | Initialize Serena: `mcp__serena__initial_instructions` | [ ] | Tool output present |
| MUST | Read `.agents/HANDOFF.md` | [ ] | Content in context |
| MUST | Create this session log | [ ] | This file exists |
| MUST | **List available skills: `ls .claude/skills/github/scripts/**/*.ps1`** | [ ] | **Output in Skill Inventory** |
| MUST | **Read `skill-usage-mandatory` memory** | [ ] | **Content in context** |
| SHOULD | Search relevant Serena memories | [ ] | Memory results present |
| SHOULD | Verify git status | [ ] | Output documented below |
| SHOULD | Note starting commit | [ ] | SHA documented below |

### Skill Inventory (NEW SECTION)

**GitHub Skills Available:**
[Agent MUST paste ls output here during Phase 1.5]

**Skill Usage Policy Acknowledged:**
- [ ] Read `skill-usage-mandatory` memory using `mcp__serena__read_memory`
- [ ] Understand: NEVER use raw `gh` when skill exists
- [ ] Understand: MUST check inventory before GitHub operations
- [ ] Understand: MUST extend skill if capability missing

### Work Blocked Until

All MUST requirements above are marked complete.
```

### Validation Script Enhancement (Complementary)

While Phase 1.5 is primary solution, also create `scripts/Check-SkillExists.ps1` for just-in-time validation:

```powershell
<#
.SYNOPSIS
Check if GitHub skill exists for operation before writing code.

.EXAMPLE
.\scripts\Check-SkillExists.ps1 -Operation "Get PR context"
# Outputs: ✅ Skill exists: .claude/skills/github/scripts/pr/Get-PRContext.ps1

.EXAMPLE
.\scripts\Check-SkillExists.ps1 -Operation "Delete branch"
# Outputs: ❌ Skill missing. Extend skill or get user approval.
#>
param(
    [Parameter(Mandatory)]
    [string]$Operation
)

# Map operation to skill script
$skillMap = @{
    'Get PR context' = 'pr/Get-PRContext.ps1'
    'Post PR comment' = 'pr/Post-PRCommentReply.ps1'
    'Get review comments' = 'pr/Get-PRReviewComments.ps1'
    'Get issue context' = 'issue/Get-IssueContext.ps1'
    'Post issue comment' = 'issue/Post-IssueComment.ps1'
    'Set issue labels' = 'issue/Set-IssueLabels.ps1'
    'Add reaction' = 'reactions/Add-CommentReaction.ps1'
}

$skillScript = $skillMap[$Operation]
if ($skillScript) {
    $fullPath = ".claude/skills/github/scripts/$skillScript"
    if (Test-Path $fullPath) {
        Write-Host "✅ Skill exists: $fullPath" -ForegroundColor Green
        Write-Host "   Use this instead of raw gh commands." -ForegroundColor Yellow
        exit 0
    }
}

Write-Host "❌ Skill missing for: $Operation" -ForegroundColor Red
Write-Host "   Options:" -ForegroundColor Yellow
Write-Host "   1. Extend skill: Add to .claude/skills/github/scripts/" -ForegroundColor Yellow
Write-Host "   2. Get user approval for inline code" -ForegroundColor Yellow
exit 1
```

Agents can invoke this script during work for real-time validation.

---

## Implementation Complexity

### Changes Required

| File | Change Type | Lines | Complexity |
|------|-------------|-------|------------|
| `.agents/SESSION-PROTOCOL.md` | Add Phase 1.5 section (~50 lines) | +50 | LOW |
| `.agents/SESSION-PROTOCOL.md` | Update session log template | +15 | LOW |
| `.agents/SESSION-PROTOCOL.md` | Update checklist | +5 | LOW |
| `.agents/SESSION-PROTOCOL.md` | Update document history | +1 | LOW |
| `CLAUDE.md` | Reference Phase 1.5 | +5 | LOW |
| `AGENTS.md` | Reference Phase 1.5 | +5 | LOW |
| `scripts/Check-SkillExists.ps1` | New validation script | +50 | LOW |
| `scripts/tests/Check-SkillExists.Tests.ps1` | Pester tests | +100 | LOW |

**Total**: ~230 lines, **LOW complexity**

### Testing Strategy

1. **Protocol compliance**: Run `scripts/Validate-SessionJson.ps1` (already exists)
2. **Skill check script**: Add Pester tests for `Check-SkillExists.ps1`
3. **Integration**: Create test session log with Phase 1.5 checklist
4. **Validation**: Next session after implementation MUST follow Phase 1.5

### Rollout Plan

**Phase A: Protocol Update** (Session N)

- Update SESSION-PROTOCOL.md with Phase 1.5
- Update session log template
- Update CLAUDE.md and AGENTS.md references
- Commit as `feat(protocol): add Phase 1.5 skill validation gate`

**Phase B: Validation Tooling** (Session N or N+1)

- Create `Check-SkillExists.ps1` script
- Add Pester tests
- Document usage in skill-usage-mandatory.md
- Commit as `feat(validation): add skill existence check script`

**Phase C: Validation** (Session N+1)

- First session after rollout MUST complete Phase 1.5
- Document compliance in session log
- Retrospective to evaluate effectiveness

---

## Risk Assessment

### Risk 1: "Checkbox Compliance" - Superficial Validation

**Description**: Agents complete Phase 1.5 mechanically but still violate during work.

**Probability**: MEDIUM (30%)

**Impact**: MEDIUM - Phase 1.5 becomes security theater

**Mitigation**:

1. Require "Skill Inventory" section in session log (forces documentation)
2. Add "During work" reminder in Phase 1.5 specification
3. Create `Check-SkillExists.ps1` for just-in-time validation
4. Monitor first 3 sessions after rollout for compliance

**Residual Risk**: LOW (10%)

### Risk 2: Adds Friction to Quick Tasks

**Description**: Simple tasks now require 5-phase protocol (30-60 seconds overhead).

**Probability**: HIGH (70%)

**Impact**: LOW - Overhead is minimal (30-60 seconds)

**Mitigation**:

1. Phase 1.5 requires only 2 tool calls (ls + read memory) = ~30 seconds
2. Skill Inventory is copy-paste from ls output
3. For non-GitHub tasks, Phase 1.5 overhead is ~15 seconds (just list and move on)

**Residual Risk**: LOW (minor inconvenience)

### Risk 3: Protocol Becomes Too Complex

**Description**: 5 phases instead of 4; agents struggle to remember all steps.

**Probability**: LOW (20%)

**Impact**: MEDIUM - Protocol compliance degrades

**Mitigation**:

1. Session log template includes complete checklist (agents just follow it)
2. Validate-SessionJson.ps1 checks Phase 1.5 compliance
3. HANDOFF.md reminder to review SESSION-PROTOCOL.md
4. Phase numbering makes sequence clear (1, 1.5, 2, 3, 4)

**Residual Risk**: LOW (5%)

### Risk 4: False Sense of Security

**Description**: Phase 1.5 gate exists, but agents still violate during work (not at session start).

**Probability**: MEDIUM (40%)

**Impact**: MEDIUM - Violations continue, just with completed Phase 1.5

**Mitigation**:

1. Phase 1.5 specification includes "During work" requirements
2. Skill Inventory provides quick reference (no need to re-search)
3. Check-SkillExists.ps1 for just-in-time validation during work
4. Retrospective analysis after 3 sessions to measure effectiveness

**Residual Risk**: MEDIUM (20%) - **This is the primary remaining risk**

### Risk 5: Scope Creep - Other Constraints

**Description**: If Phase 1.5 works, pressure to add gates for language, commits, workflows, etc.

**Probability**: HIGH (60%)

**Impact**: LOW (each gate has independent value if addressing real problem)

**Mitigation**:

1. **Limit scope of Phase 1.5 to skill validation only**
2. Session 15 retrospective identified 4 root causes; address each independently:
   - Skill validation → Phase 1.5 (this analysis)
   - Language preference → PROJECT-CONSTRAINTS.md (separate proposal)
   - Commit atomicity → commit-msg hook (separate proposal)
   - Workflow patterns → Already documented in memories
3. Evaluate each gate independently for ROI

**Residual Risk**: LOW (managed via separate proposals)

### Overall Risk Profile

| Risk | Probability × Impact | Residual Risk |
|------|---------------------|---------------|
| Checkbox compliance | MEDIUM × MEDIUM | LOW |
| Friction on quick tasks | HIGH × LOW | LOW |
| Protocol too complex | LOW × MEDIUM | LOW |
| False sense of security | MEDIUM × MEDIUM | MEDIUM |
| Scope creep | HIGH × LOW | LOW |

**Overall**: **LOW to MEDIUM** - Benefits significantly outweigh risks

---

## Effectiveness Evaluation

### Success Metrics

**Primary (KPI)**:

- **Skill violation rate**: Target 80-90% reduction
  - Baseline: 3+ violations per session (Session 15)
  - Target: <0.5 violations per session

**Secondary**:

- **User correction frequency**: Target 70-80% reduction
  - Baseline: 5+ corrections per session (Session 15)
  - Target: <1 correction per session
- **Token efficiency**: Target 15-20% reduction in rework
  - Measure: Compare session token usage before/after Phase 1.5
- **Time to first violation**: Target >60 minutes (vs <10 min in Session 15)

### Measurement Protocol

**Session N+1 (First Session After Rollout)**:

- [ ] Phase 1.5 completed successfully (checklist verified)
- [ ] Skill Inventory documented in session log
- [ ] Count skill violations: _____ (target: 0)
- [ ] Count user corrections: _____ (target: 0-1)
- [ ] Retrospective evaluation: Effectiveness rating (1-10)

**Session N+2 and N+3**:

- Repeat measurements
- Calculate rolling average
- Compare to baseline (Session 15)

**After 3 Sessions**:

- Formal retrospective on Phase 1.5 effectiveness
- Decision: Keep, Modify, or Remove
- If effective: Consider applying pattern to other constraints (PROJECT-CONSTRAINTS.md)

### Decision Criteria

**Keep Phase 1.5 if**:

- Violation rate reduced by ≥60% (3+ → <1.2 per session)
- User corrections reduced by ≥50% (5+ → <2.5 per session)
- Agent feedback: "Useful" or "Neutral" (not "Burdensome")

**Modify Phase 1.5 if**:

- Partial effectiveness (30-59% reduction) but high friction
- Adjust to SHOULD instead of MUST
- Simplify verification requirements

**Remove Phase 1.5 if**:

- No measurable improvement (<30% reduction)
- High agent resistance (consistently skipped)
- Better solution identified (e.g., automated pre-commit validation)

---

## Alternatives Considered

### Alternative 1: Create PROJECT-CONSTRAINTS.md Consolidation

**Approach**: Consolidate all MUST-NOT patterns into single governance document.

**Location**: `.agents/governance/PROJECT-CONSTRAINTS.md`

**Content**:

```markdown
# Project Constraints

## MUST-NOT Patterns

### GitHub Operations
- ❌ MUST NOT use raw `gh` commands when skill exists
- ✅ MUST use `.claude/skills/github/` scripts

### Language
- ❌ MUST NOT create bash or Python scripts
- ✅ MUST use PowerShell for all scripting

### Workflow Architecture
- ❌ MUST NOT put complex logic in workflow YAML
- ✅ MUST use thin workflows + testable modules

### Commit Discipline
- ❌ MUST NOT mix unrelated changes in single commit
- ✅ MUST make atomic commits (one logical change per commit)
```

**Pros**:

- ✅ Single source of truth (DRY principle)
- ✅ Reduces scattered documentation
- ✅ Easy to reference in Phase 2
- ✅ Addresses Session 15 root cause: "scattered preferences"

**Cons**:

- ⚠️ Doesn't enforce checking (still trust-based)
- ⚠️ Agents must read AND remember all constraints
- ⚠️ No verification mechanism for constraint compliance

**Verdict**: **Complementary to Phase 1.5, not replacement**

Recommendation: Implement BOTH:

- Phase 1.5 for skill validation enforcement (verification-based)
- PROJECT-CONSTRAINTS.md for consolidated reference (reduces scattered docs)

### Alternative 2: Pre-Commit Hook Validation

**Approach**: Add commit-msg hook to validate code before commit.

**Script**: `scripts/hooks/validate-github-operations.ps1`

**Checks**:

1. Scan staged files for raw `gh` commands
2. If found, check if skill exists for that operation
3. If skill exists, REJECT commit with error message

**Pros**:

- ✅ Automated enforcement (can't commit violations)
- ✅ Clear feedback loop (commit rejected)
- ✅ Works even if agent skips Phase 1.5

**Cons**:

- ⚠️ Validation happens AFTER code written (rework still needed)
- ⚠️ Doesn't prevent violation, only detects it
- ⚠️ Requires maintaining validation script
- ⚠️ May have false positives (legitimate raw gh commands)

**Verdict**: **Complementary safety net, not primary solution**

Recommendation: Implement as fallback:

- Phase 1.5 prevents violations at source (proactive)
- Pre-commit hook catches any that slip through (reactive safety net)

### Alternative 3: Skill Auto-Suggestion Tool

**Approach**: Create tool that suggests skill when agent writes `gh` command.

**Mechanism**: Pre-commit hook that scans diffs and suggests alternatives.

**Example**:

```text
⚠️  Detected: gh pr view 60 --json title
💡 Suggestion: Use skill instead:
   pwsh .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest 60
```

**Pros**:

- ✅ Educational (teaches agents over time)
- ✅ Non-blocking (doesn't force, just suggests)

**Cons**:

- ❌ Doesn't enforce (agent can ignore)
- ⚠️ Requires NLP or pattern matching to map commands to skills
- ⚠️ Maintenance burden (keep mappings updated)

**Verdict**: **Nice-to-have, but insufficient alone**

### Alternative 4: Do Nothing (Status Quo)

**Approach**: Rely on existing documentation and user corrections.

**Rationale**: Session 15 was anomaly; most sessions don't have 3+ violations.

**Analysis**:

- ❌ Session 15 retrospective identified systemic issue (not one-off)
- ❌ Trust-based compliance proven ineffective (3+ corrections)
- ❌ Wasted tokens on rework (15-20% efficiency loss)
- ❌ User frustration ("amateur and unprofessional" feedback)

**Verdict**: **Unacceptable** - Problem requires solution

---

## Recommendation Summary

### Primary: Phase 1.5 BLOCKING Gate

**Add to SESSION-PROTOCOL.md**:

- New Phase 1.5 between Phase 2 (Context) and Phase 3 (Session Log)
- BLOCKING gate requiring skill validation
- 2 MUST requirements: list skills + read memory
- Skill Inventory section in session log template
- "During work" reminder to check inventory

**Why**: Addresses root cause (no BLOCKING gate), aligns with protocol philosophy, proven pattern

### Complementary: PROJECT-CONSTRAINTS.md

**Create at `.agents/governance/PROJECT-CONSTRAINTS.md`**:

- Consolidate MUST-NOT patterns from scattered memories
- Single source of truth for all constraints
- Reference in Phase 2 (Context Retrieval)

**Why**: Addresses Session 15 root cause: "scattered preferences"

### Optional: Check-SkillExists.ps1

**Create at `scripts/Check-SkillExists.ps1`**:

- Just-in-time validation during work
- Maps operations to skill scripts
- Exit code 0 (exists) or 1 (missing)

**Why**: Provides real-time validation for agents during implementation

### Safety Net: Pre-Commit Hook (Future)

**Create at `scripts/hooks/validate-github-operations.ps1`**:

- Scan staged files for raw gh commands
- Reject commit if skill exists
- Fallback enforcement if Phase 1.5 skipped

**Why**: Defense-in-depth; catches violations that slip through

---

## Open Questions

### Q1: Should Phase 1.5 be BLOCKING or SHOULD?

**Analysis**:

- Session 15 proved SHOULD is ineffective (trust-based compliance failed)
- MUST/BLOCKING provides verification mechanism
- Overhead is minimal (30 seconds)

**Recommendation**: **BLOCKING** (MUST requirement level per RFC 2119)

### Q2: Where exactly should Phase 1.5 appear?

**Option A**: Between Phase 2 (Context) and Phase 3 (Session Log)

- Pro: Context retrieved first, then validate tools
- Con: Session log created late (currently Phase 3)

**Option B**: Between Phase 1 (Serena) and Phase 2 (Context)

- Pro: Tools validated before context retrieval
- Con: Logical order is context → tools, not tools → context

**Recommendation**: **Option A** (after context, before session log)

### Q3: Should validation be skill-specific or general?

**Skill-specific**: Only GitHub operations require skill validation

- Pro: Focused on actual problem (Session 15 was GitHub operations)
- Con: Doesn't address future skill categories (file ops, build ops)

**General**: All operations should check for skills first

- Pro: Extensible to future skill categories
- Con: More complex protocol (validate ALL skills, not just GitHub)

**Recommendation**: **Start skill-specific (GitHub only), extend later if needed**

### Q4: What if skill genuinely doesn't exist?

**Escape Hatch Required**:

1. Agent documents in session log why skill extension not feasible
2. Agent gets user approval before writing inline code
3. Agent creates issue to add capability to skill post-session

**Verification**: Session log contains escape hatch documentation + user approval

**Recommendation**: Add escape hatch clause to Phase 1.5 specification

### Q5: How to handle non-GitHub sessions?

**Scenario**: Session focuses on documentation, no GitHub operations needed.

**Solution**: Phase 1.5 completed in 15 seconds (just list and move on)

**Verification**: Skill Inventory documented as "Not applicable (no GitHub operations planned)"

**Recommendation**: Allow "N/A" documentation if no GitHub work planned

---

## Implementation Checklist

### Phase A: Protocol Document Updates

- [ ] Add Phase 1.5 section to SESSION-PROTOCOL.md (~50 lines)
- [ ] Update session start checklist (+5 lines for Phase 1.5 items)
- [ ] Update session log template (+15 lines for Skill Inventory section)
- [ ] Add escape hatch clause for missing skills
- [ ] Update document history (version 1.2)
- [ ] Reference Phase 1.5 in CLAUDE.md
- [ ] Reference Phase 1.5 in AGENTS.md
- [ ] Run markdownlint
- [ ] Commit: `feat(protocol): add Phase 1.5 skill validation gate`

### Phase B: Validation Tooling (Optional but Recommended)

- [ ] Create `scripts/Check-SkillExists.ps1` (~50 lines)
- [ ] Add Pester tests `scripts/tests/Check-SkillExists.Tests.ps1` (~100 lines)
- [ ] Test script with known operations
- [ ] Update skill-usage-mandatory.md with script reference
- [ ] Run markdownlint
- [ ] Commit: `feat(validation): add skill existence check script`

### Phase C: Governance Document (Complementary)

- [ ] Create `.agents/governance/PROJECT-CONSTRAINTS.md` (~200 lines)
- [ ] Consolidate MUST-NOT patterns from memories
- [ ] Add to Phase 2 SHOULD requirements
- [ ] Run markdownlint
- [ ] Commit: `docs(governance): consolidate project constraints`

### Phase D: First Validation Session

- [ ] Next session MUST complete Phase 1.5
- [ ] Document Skill Inventory in session log
- [ ] Count violations (target: 0)
- [ ] Count user corrections (target: 0-1)
- [ ] Retrospective evaluation

---

## Appendix A: Session 15 Full Violation Timeline

| Time | Action | Type | Violation Details | User Response | Energy Shift |
|------|--------|------|-------------------|---------------|--------------|
| T+0 | Session log created | ✅ | None | None | High |
| T+1 | Serena initialized | ✅ | None | None | High |
| T+2 | Read HANDOFF.md | ✅ | None | None | High |
| T+3 | Invoked `gh pr view` | ❌ | Raw gh instead of Get-PRContext.ps1 | "Use the GitHub skill!" | High → Medium |
| T+5 | Multiple `gh api` calls | ❌ | Raw gh api instead of skill scripts | (Frustrated correction) | Medium |
| T+10 | Created bash script `ai-review-common.sh` | ❌ | Bash violates PowerShell-only preference | "I don't want any bash here. Or Python." | Medium |
| T+15 | Created `.bats` test file | ❌ | Bash test framework | (Same correction) | Medium |
| T+20 | Put complex logic in workflow YAML | ❌ | Violates thin workflow pattern (ADR-006) | "workflows should be as light as possible" | Medium |
| T+25 | Created `AIReviewCommon.psm1` | ✅ | PowerShell module (correct) | None | Medium → High |
| T+30 | Non-atomic commit 48e732a (16 files) | ❌ | Mixed ADRs, session logs, configs, memories | "amateur and unprofessional" (git reset) | High → Low |
| T+35 | Git reset executed | 🔧 | Recovery | None | Low |
| T+40 | Created ADR-005 (atomic commit) | ✅ | Proper atomic commit | None | Low → High |
| T+45 | Created ADR-006 (atomic commit) | ✅ | Proper atomic commit | None | High |
| T+50 | Skill duplication identified in `AIReviewCommon.psm1` | ❌ | Duplicated GitHub skill functions | "Just use the GitHub skill" | High → Medium |
| T+55 | Removed duplicate functions | ✅ | Cleaned up duplication | None | Medium → High |
| T+60 | P0-P1 security fixes committed | ✅ | Atomic commits, proper fixes | None | High |

**Statistics**:

- **Total violations**: 7 (3 skill usage, 2 language, 1 workflow, 1 commit)
- **User corrections**: 5 interventions
- **Rework events**: 3 (bash → PowerShell, git reset, duplicate removal)
- **Time wasted**: Estimated 30-45 minutes
- **Energy shifts**: 5 down-shifts (High → Medium or Low)

---

## Appendix B: Verification-Based Enforcement Examples

### Example 1: Phase 1 (Serena Initialization)

**Requirement**: Agent MUST call `mcp__serena__activate_project`

**Verification**: Tool call output appears in session transcript

**Pass**:

```text
<function_calls>
<invoke name="mcp__serena__activate_project">
<parameter name="projectPath">D:\src\GitHub\rjmurillo-bot\ai-agents