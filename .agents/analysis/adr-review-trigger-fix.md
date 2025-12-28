# Analysis: ADR Review Automatic Triggering Fix

## 1. Objective and Scope

**Objective**: Ensure adr-review skill is ALWAYS triggered automatically when an ADR is created or updated, regardless of which agent performs the operation.

**Scope**: Changes to architect agent, orchestrator agent, AGENTS.md, and adr-review skill documentation.

## 2. Context

**Problem**: ADR-021 was created without triggering the adr-review skill. User had to manually request review.

**Current State**: The adr-review skill documentation claims it triggers "when architect agent creates/updates an ADR" but this is aspirational, not implemented.

## 3. Approach

**Methodology**: Read all relevant agent files and skill documentation to identify missing trigger points.

**Tools Used**: Read, Grep, file analysis

**Limitations**: Cannot verify runtime behavior without testing.

## 4. Data and Analysis

### Evidence Gathered

| Finding | Source | Confidence |
|---------|--------|------------|
| No adr-review trigger in architect.md | `src/claude/architect.md` line 441-450 | High |
| No adr-review routing in orchestrator.md | `src/claude/orchestrator.md` | High |
| Skill claims automatic trigger but no enforcement | `.claude/skills/adr-review/SKILL.md` line 15 | High |
| No cross-reference in AGENTS.md | `AGENTS.md` | High |

### Facts (Verified)

1. Architect agent handoff protocol (lines 441-450) does NOT mention adr-review
2. Orchestrator routing table does NOT include ADR creation as trigger for adr-review
3. adr-review skill documentation states activation occurs "when architect agent creates/updates an ADR" (line 15) but provides no enforcement mechanism
4. AGENTS.md does not require adr-review after ADR operations

### Hypotheses (Unverified)

1. Implementer agent might also create ADRs (needs verification)
2. Other agents might modify ADRs without triggering review (needs verification)

## 5. Results

The automatic trigger is missing in 4 critical locations where enforcement must occur:

1. **Architect agent handoff protocol**: No requirement to trigger adr-review
2. **Orchestrator routing logic**: No routing rule for ADR operations
3. **AGENTS.md global instructions**: No cross-reference to adr-review requirement
4. **adr-review skill**: Claims automatic trigger but provides no enforcement

## 6. Discussion

The skill documentation uses aspirational language ("triggers on") rather than imperative enforcement ("MUST trigger"). This creates a documentation-implementation gap where the desired behavior is described but not enforced.

The architect agent is the primary creator of ADRs, but the handoff protocol allows architects to skip adr-review and route directly to other agents. This violates the principle that all ADRs require multi-agent validation.

## 7. Recommendations

| Priority | Recommendation | Rationale | Effort |
|----------|----------------|-----------|--------|
| P0 | Add BLOCKING gate to architect handoff protocol | Prevents ADRs from bypassing review | 30 min |
| P0 | Add adr-review routing to orchestrator | Ensures orchestrator enforces trigger | 30 min |
| P1 | Update AGENTS.md with mandatory rule | Global visibility of requirement | 15 min |
| P1 | Update adr-review skill with enforcement language | Clear expectations | 15 min |

## 8. Conclusion

**Verdict**: Proceed with 4 documentation changes
**Confidence**: High
**Rationale**: All changes are documentation-only with no code modifications required. Changes enforce existing intent through blocking gates.

### User Impact

**What changes for you**: After these fixes, you will never need to manually request ADR review. The system will automatically trigger adr-review after any ADR creation or update.

**Effort required**: None - changes are transparent to user workflow.

**Risk if ignored**: ADRs will continue bypassing multi-agent review, resulting in lower-quality architectural decisions.

## 9. Appendices

### Sources Consulted

- `.claude/skills/adr-review/SKILL.md`
- `src/claude/architect.md`
- `src/claude/orchestrator.md`
- `AGENTS.md`

### Data Transparency

**Found**:
- All agent handoff protocols
- Skill documentation and activation triggers
- Orchestrator routing tables
- Global agent instructions

**Not Found**:
- Evidence of implementer or other agents creating ADRs (would require grep search)
- Historical data on how often adr-review is manually triggered

---

## Required Changes

### Change 1: Architect Agent (`src/claude/architect.md`)

**Location**: Lines 441-450 (Handoff Protocol section)

**Current**:

```markdown
## Handoff Protocol

**As a subagent, you CANNOT delegate**. Return results to orchestrator.

When review is complete:

1. Save findings to `.agents/architecture/`
2. Update architecture changelog if decisions made
3. Store decision in memory
4. Return to orchestrator: "Architecture review complete. Recommend orchestrator routes to [agent] for [next step]"
```

**Replace with**:

```markdown
## Handoff Protocol

**As a subagent, you CANNOT delegate**. Return results to orchestrator.

### ADR Creation/Update Protocol (BLOCKING)

When you create or update an ADR file matching `.agents/architecture/ADR-*.md`:

1. Save ADR to `.agents/architecture/ADR-NNNN-[title].md`
2. Update architecture changelog if needed
3. Store decision in memory
4. Return to orchestrator with **MANDATORY routing**:

```text
ADR created/updated: [path to ADR file]

MANDATORY: Orchestrator MUST invoke adr-review skill before proceeding.

Command:
  Skill(skill="adr-review", args="[path to ADR file]")

Rationale: All ADRs require multi-agent validation per adr-review protocol.
```

**BLOCKING REQUIREMENT**: You MUST NOT recommend routing to any other agent (planner, implementer, etc.) until adr-review completes. Orchestrator is responsible for enforcing this gate.

### Non-ADR Review Handoff

When review is complete and NO ADR was created/updated:

1. Save findings to `.agents/architecture/`
2. Update architecture changelog if decisions made
3. Store decision in memory
4. Return to orchestrator: "Architecture review complete. Recommend orchestrator routes to [agent] for [next step]"
```

**Rationale**: This creates a BLOCKING gate where architect explicitly signals adr-review is required. Orchestrator becomes responsible for enforcement.

---

### Change 2: Orchestrator Agent (`src/claude/orchestrator.md`)

**Location**: After the Agent Sequences by Task Type table (around line 500)

**Add new section**:

```markdown
### ADR Review Enforcement (BLOCKING)

When ANY agent returns output indicating ADR creation/update:

**Detection Pattern**:
- Agent output contains: "ADR created/updated: .agents/architecture/ADR-*.md"
- Agent output contains: "MANDATORY: Orchestrator MUST invoke adr-review"

**Enforcement**:

```text
BLOCKING GATE: ADR Review Required

1. Verify ADR file exists at specified path
2. Invoke adr-review skill:

   Skill(skill="adr-review", args="[ADR file path]")

3. Wait for adr-review completion
4. Only after adr-review completes, route to next agent per original plan

DO NOT route to next agent until adr-review completes.
```

**Failure Handling**:

| Condition | Action |
|-----------|--------|
| ADR file not found | Report error to user, halt workflow |
| adr-review skill unavailable | Report error to user, document gap, proceed with warning |
| adr-review fails | Review failure output, decide to retry or escalate to user |
```

**Rationale**: Orchestrator enforces the blocking gate by detecting the mandatory routing signal and refusing to proceed without adr-review.

---

### Change 3: AGENTS.md Global Instructions

**Location**: After the "Agent-by-Agent Guide" section, around line 850

**Add new subsection**:

```markdown
### ADR Review Requirement (MANDATORY)

**Rule**: ALL ADRs created or updated MUST trigger the adr-review skill before workflow continues.

**Scope**: Applies to ADR files matching `.agents/architecture/ADR-*.md` and `docs/architecture/ADR-*.md`

**Enforcement**:

| Agent | Responsibility |
|-------|----------------|
| **architect** | Signal MANDATORY routing to orchestrator when ADR created/updated |
| **orchestrator** | Detect signal and invoke adr-review skill before routing to next agent |
| **implementer** | If creating ADR, signal MANDATORY routing to orchestrator |
| **All agents** | Do NOT bypass adr-review by directly routing to next agent |

**Blocking Gate**:

```text
IF ADR created/updated:
  1. Agent returns to orchestrator with MANDATORY routing signal
  2. Orchestrator invokes adr-review skill
  3. adr-review completes (may take multiple rounds)
  4. Orchestrator routes to next agent only after adr-review PASS

VIOLATION: Routing to next agent without adr-review is a protocol violation.
```

**Skill Invocation**:

```bash
# Orchestrator invokes adr-review skill
Skill(skill="adr-review", args="[path to ADR file]")
```

**Rationale**: All ADRs benefit from multi-agent validation (architect, critic, independent-thinker, security, analyst, high-level-advisor) coordinated by adr-review skill.

**Related**: See `.claude/skills/adr-review/SKILL.md` for debate protocol details.
```

**Rationale**: Global visibility ensures all agents are aware of the requirement and understand their role in enforcement.

---

### Change 4: ADR Review Skill (`.claude/skills/adr-review/SKILL.md`)

**Location**: Lines 12-17 (When to Use section)

**Current**:

```markdown
## When to Use

- User requests ADR review ("review this ADR", "validate this decision")
- Architect creates or updates an ADR
- Orchestrator detects ADR file changes
- Strategic decisions require multi-perspective validation
```

**Replace with**:

```markdown
## When to Use

**MANDATORY Triggers** (automatic, non-negotiable):

- Architect creates or updates an ADR and signals orchestrator
- ANY agent creates or updates a file matching `.agents/architecture/ADR-*.md`
- Orchestrator detects ADR creation/update signal from agent output

**User-Initiated Triggers** (manual):

- User explicitly requests ADR review ("review this ADR", "validate this decision")
- User requests multi-perspective validation for strategic decisions

**Enforcement**:

The architect agent is configured to ALWAYS signal orchestrator with MANDATORY routing when ADR files are created/updated. Orchestrator is configured to BLOCK workflow continuation until adr-review completes.

**Scope**:

- Primary location: `.agents/architecture/ADR-*.md`
- Secondary location: `docs/architecture/ADR-*.md` (if project uses this structure)

**Anti-Pattern**:

❌ Architect routes to planner without adr-review
❌ Orchestrator proceeds to next agent without invoking adr-review
❌ User must manually request adr-review after ADR creation

**Correct Pattern**:

✅ Architect signals orchestrator: "MANDATORY: invoke adr-review"
✅ Orchestrator invokes adr-review skill
✅ Workflow continues only after adr-review completes
```

**Rationale**: Clear enforcement language with anti-patterns helps agents understand the blocking requirement.

---

## Implementation Plan

1. **Edit architect.md** (Change 1): Update Handoff Protocol section
2. **Edit orchestrator.md** (Change 2): Add ADR Review Enforcement section
3. **Edit AGENTS.md** (Change 3): Add ADR Review Requirement subsection
4. **Edit adr-review SKILL.md** (Change 4): Update When to Use section with enforcement

**Validation**:

After changes, search for "MANDATORY" in all 4 files to verify blocking gates are in place.

**Testing**:

1. Create test ADR using architect agent
2. Verify architect returns MANDATORY routing signal
3. Verify orchestrator invokes adr-review before continuing
4. Verify adr-review completes multi-agent debate
5. Verify workflow continues only after adr-review

**Rollback**:

All changes are documentation-only. Rollback is simply reverting the file edits.

---

## Design Decisions

### Decision 1: Blocking Gate vs Advisory

**Chosen**: Blocking gate (MANDATORY routing)

**Rationale**: Advisory approach failed (current state). Only blocking enforcement ensures 100% compliance.

### Decision 2: Enforcement Location

**Chosen**: Split responsibility (architect signals, orchestrator enforces)

**Rationale**: Architect cannot delegate (architecture constraint). Orchestrator is ROOT agent responsible for all routing decisions.

### Decision 3: Failure Handling

**Chosen**: Halt workflow if adr-review unavailable

**Rationale**: Proceeding without review defeats the purpose. Better to fail-closed than fail-open.

### Decision 4: Scope

**Chosen**: All ADR-*.md files in `.agents/architecture/` and `docs/architecture/`

**Rationale**: Covers all ADR locations used by project.

---

## Success Criteria

**Definition of Done**:

- [x] All 4 files updated with blocking gate language
- [x] MANDATORY routing signal defined in architect handoff protocol
- [x] Orchestrator enforcement logic documented
- [x] Global instructions include ADR review requirement
- [x] adr-review skill updated with enforcement details
- [ ] Validation: grep "MANDATORY" returns 4+ matches across files
- [ ] Testing: Create test ADR, verify automatic adr-review trigger

**Acceptance Test**:

```bash
# After implementing changes, verify enforcement
grep -r "MANDATORY.*adr-review" src/claude/architect.md src/claude/orchestrator.md AGENTS.md .claude/skills/adr-review/SKILL.md

# Expected: 4+ matches showing blocking gates
```

---

## Appendix: File Paths

| File | Path |
|------|------|
| Architect agent | `src/claude/architect.md` |
| Orchestrator agent | `src/claude/orchestrator.md` |
| Global instructions | `AGENTS.md` |
| ADR review skill | `.claude/skills/adr-review/SKILL.md` |

## Appendix: Related Issues

- Original issue: ADR-021 created without automatic adr-review trigger
- Related pattern: Blocking gates enforce protocol compliance (used in session-end validation)
- Similar fix needed: Check if implementer agent can create ADRs (hypothesis to verify)
