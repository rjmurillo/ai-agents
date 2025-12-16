# Retrospective: Drift Detection Disaster

## Session Info

- **Date**: 2025-12-15
- **Agents**: Claude Code (single agent conversation)
- **Task Type**: Maintenance / Bug Fix
- **Outcome**: FAILURE - Wrong direction implemented, wasted significant tokens and user time

---

## Phase 0: Data Gathering

### 4-Step Debrief

#### Step 1: Observe (Facts Only)

- Tool calls: Read (templates, Claude agents), Edit (12 Claude agents), Bash (drift detection, git operations)
- Outputs: Modified 12 Claude agent files, committed changes
- Errors: None technical - all operations succeeded
- Duration: Extended multi-turn conversation

**Critical Facts**:

1. PRD explicitly states: "Claude agents remain separate; only VS Code/Copilot are consolidated" (Non-Goals #4)
2. PRD Appendix B states: "These structural differences are expected and excluded from drift detection"
3. Analysis document header: "Claude Source Files (Source of Truth)"
4. Analysis recommendations: "Templates MUST preserve Claude's Core Identity verbatim"
5. Implementation plan section: "Recommended Template Updates - Priority 1: Restore exact Core Identity text from Claude"

#### Step 2: Respond (Reactions)

- **Pivots**: User said "Looks like the Claude templates may need to be updated" - I interpreted this as "update Claude to match templates"
- **Retries**: Multiple rounds of editing, reverting, re-editing
- **Escalations**: User eventually expressed frustration: "the claims about drift were a bunch of horseshit"
- **Blocks**: Context limit reached, conversation had to be summarized and continued

#### Step 3: Analyze (Interpretations)

- **Pattern**: Immediately acted on ambiguous user message without clarifying intent
- **Anomaly**: Ignored explicit project documentation stating Claude as source of truth
- **Correlation**: User frustration correlates with token/time expenditure without value

#### Step 4: Apply (Actions)

- Skills to update: ALWAYS read project context before acting
- Process changes: Question ambiguous directives explicitly
- Context to preserve: PRD and implementation plans define source of truth

---

### Execution Trace

| Time | Action | Outcome | Energy |
|------|--------|---------|--------|
| T+0 | User: "Looks like the Claude templates may need to be updated" | Misinterpret as "update Claude" | High |
| T+1 | Read template files | Success | High |
| T+2 | Update templates to match Claude (wrong!) | Completed but wrong direction | High |
| T+3 | User clarifies: "We're missing out on some great things" | Still misunderstand | Medium |
| T+4 | Revert template changes | Correct partial action | Medium |
| T+5 | Update Claude agents to match templates | WRONG - inverts source of truth | High |
| T+6 | Multiple edit rounds | Completed | Medium |
| T+7 | Run drift detection | Shows 0 drift | Low |
| T+8 | Commit changes | Committed wrong changes | Low |
| T+9 | User: "horseshit analysis" | Failure acknowledged | Critical |

### Timeline Patterns

- **Pattern 1**: Rushed to action without reading .agents/ documentation
- **Pattern 2**: Interpreted "drift" as "Claude should match templates" when PRD says opposite
- **Pattern 3**: Multiple edit-test cycles without questioning fundamental direction

### Energy Shifts

- High to Critical at: User frustration point - wasted significant effort

---

### Outcome Classification

#### Mad (Blocked/Failed)

- **Inverted source of truth**: Modified Claude (source of truth) to match templates (generated), which is backwards
- **Ignored project documentation**: PRD and analysis documents clearly stated direction, were not consulted
- **Wasted resources**: Multiple edit cycles, token expenditure, user time

#### Sad (Suboptimal)

- **Ambiguous user message not clarified**: "Claude templates may need to be updated" could mean either direction
- **Context documents not read early**: .agents/planning/prd-agent-consolidation.md has explicit guidance

#### Glad (Success)

- **None**: This was a complete failure

#### Distribution

- Mad: 3 events
- Sad: 2 events
- Glad: 0 events
- Success Rate: 0%

---

## Phase 1: Generate Insights

### Five Whys Analysis

**Problem**: Modified Claude agents (source of truth) to match templates (derived), inverting the project's defined direction

**Q1**: Why did I modify Claude agents to match templates?
**A1**: I interpreted user's message "Claude templates may need to be updated" as meaning Claude should match templates

**Q2**: Why did I interpret it that way?
**A2**: The drift detection script showed Claude agents had "drift" from VS Code agents, and I assumed drift = Claude needs fixing

**Q3**: Why did I assume Claude needed fixing?
**A3**: I didn't read the PRD which explicitly states Claude is source of truth and templates should match Claude

**Q4**: Why didn't I read the PRD?
**A4**: I jumped to action without gathering context from existing project documentation

**Q5**: Why did I jump to action?
**A5**: Assumed I understood the task from the user's brief message without seeking clarification

**Root Cause**: Failed to read project documentation (.agents/planning/prd-agent-consolidation.md) before acting on ambiguous user request

**Actionable Fix**: ALWAYS read relevant .agents/ documentation before making changes to agent system

---

### Fishbone Analysis

**Problem**: Inverted source of truth direction, wasted significant user resources

#### Category: Prompt

- User message "Claude templates may need to be updated" was ambiguous
- Did not ask for clarification on which direction to update

#### Category: Context

- Did not read PRD defining Claude as source of truth
- Did not read implementation plan stating "update templates from Claude"
- Did not consult analysis document stating "Templates MUST preserve Claude's Core Identity verbatim"

#### Category: Sequence

- Jumped directly to editing without reading .agents/ context
- Did not pause to verify direction after first edit round

#### Category: State

- Previous conversation context was summarized, may have lost nuance
- Confirmation bias: drift detection showing differences reinforced wrong interpretation

### Cross-Category Patterns

- **"Context not read" + "Ambiguous prompt"**: Combined to produce wrong direction

### Controllable vs Uncontrollable

| Factor | Controllable? | Action |
|--------|---------------|--------|
| Read PRD before acting | Yes | Always read relevant .agents/ docs |
| Ask for clarification | Yes | Question ambiguous directives |
| User message ambiguity | No | Mitigate by asking |

---

### Learning Matrix

#### :) Continue (What worked)

- Nothing worked correctly in this session

#### :( Change (What didn't work)

- Acting on ambiguous messages without clarification
- Not reading project documentation before major changes
- Assuming "drift detection" means "Claude needs fixing"

#### 💡 Ideas (New approaches)

- Create pre-action checklist: "Have I read the PRD?"
- Define "source of truth" explicitly in drift detection output
- Add warning in drift script about update direction

#### 🌳 Invest (Long-term improvements)

- Add explicit "SOURCE OF TRUTH: Claude" header to drift detection output
- Update CLAUDE.md to include "Before modifying agent files, read .agents/planning/"

---

## Phase 2: Diagnosis

### Diagnostic Analysis

**Outcome**: FAILURE

**What Happened**: Modified 12 Claude agent files to match template content, committed changes. This inverts the project's defined direction where Claude is source of truth and templates should derive from Claude.

**Root Cause Analysis**: Failed to read project documentation defining source of truth before acting on ambiguous user request.

**Evidence**:

- Commit ddb76e0: "feat: align Claude agents with shared templates for consistency"
- PRD Non-Goal #4: "Claude Variant Changes: Claude agents remain separate"
- PRD explicitly defines Claude as source, VS Code/Copilot as generated

### Priority Classification

| Finding | Priority | Category | Evidence |
|---------|----------|----------|----------|
| Inverted source of truth | P0 | Critical Error | PRD Non-Goal #4 violated |
| Did not read PRD | P0 | Process Failure | PRD has explicit guidance |
| Did not clarify ambiguous request | P1 | Process Failure | User message was ambiguous |
| Committed wrong changes | P1 | Critical Error | Commit ddb76e0 |

---

## Phase 3: Decisions

### Action Classification

#### Drop (TAG as harmful)

| Finding | Skill ID | Reason |
|---------|----------|--------|
| "Update source to match derived" pattern | N/A | Inverts source of truth |
| "Act on ambiguous message" pattern | N/A | Causes wasted effort |

#### Add (New skill)

| Finding | Proposed Skill ID | Statement |
|---------|-------------------|-----------|
| Read project docs before agent changes | Skill-Process-001 | Before modifying agent files, read .agents/planning/ PRD and implementation plan |
| Clarify ambiguous update direction | Skill-Communication-001 | When update direction is unclear, ask: "Which file is source of truth?" |
| Verify source of truth before drift fixes | Skill-Drift-001 | Drift detection shows differences, not which side to update; verify source of truth in PRD |

### SMART Validation

#### Proposed Skill: Skill-Process-001

**Statement**: Before modifying agent files, read .agents/planning/ PRD and implementation plan

| Criterion | Pass? | Evidence |
|-----------|-------|----------|
| Specific | Y | One action: read PRD before modifying agents |
| Measurable | Y | Can verify if PRD was read |
| Attainable | Y | Reading files is standard capability |
| Relevant | Y | Would have prevented this failure |
| Timely | Y | Trigger: "before modifying agent files" |

**Result**: Accept skill

### Action Sequence

| Order | Action | Depends On | Blocks |
|-------|--------|------------|--------|
| 1 | Revert commit ddb76e0 | None | 2, 3 |
| 2 | Update templates to match Claude | 1 | 3 |
| 3 | Re-run drift detection | 2 | None |

---

## Phase 4: Extracted Learnings

### Learning 1

- **Statement**: Read PRD before modifying agent system files
- **Atomicity Score**: 95%
- **Evidence**: Failure to read PRD caused entire wrong-direction implementation
- **Skill Operation**: ADD
- **Target Skill ID**: Skill-Process-001

### Learning 2

- **Statement**: Drift detection shows differences, not update direction
- **Atomicity Score**: 92%
- **Evidence**: Misinterpreted "drift detected" as "Claude needs fixing"
- **Skill Operation**: ADD
- **Target Skill ID**: Skill-Drift-001

### Learning 3

- **Statement**: Ask "which is source of truth?" when direction is ambiguous
- **Atomicity Score**: 90%
- **Evidence**: User message was ambiguous, could have asked for clarification
- **Skill Operation**: ADD
- **Target Skill ID**: Skill-Communication-001

---

## Skillbook Updates

### ADD

```json
{
  "skill_id": "Skill-Process-001",
  "statement": "Before modifying agent files, read .agents/planning/ PRD to verify source of truth and update direction",
  "context": "When asked to update or fix agent-related files",
  "evidence": "2025-12-15 drift detection disaster - modified Claude (source) to match templates (derived)",
  "atomicity": 95
}
```

```json
{
  "skill_id": "Skill-Drift-001",
  "statement": "Drift detection shows differences between files, not which file to update; always verify source of truth before fixing drift",
  "context": "When drift detection reports differences",
  "evidence": "2025-12-15 - assumed drift meant Claude needed fixing when PRD states Claude is source of truth",
  "atomicity": 92
}
```

```json
{
  "skill_id": "Skill-Communication-001",
  "statement": "When update direction is ambiguous, ask 'Which file is source of truth?' before making changes",
  "context": "When user requests 'update X to match Y' or similar ambiguous phrasing",
  "evidence": "2025-12-15 - misinterpreted 'templates may need updating' as wrong direction",
  "atomicity": 90
}
```

### Deduplication Check

| New Skill | Most Similar Existing | Similarity | Decision |
|-----------|----------------------|------------|----------|
| Skill-Process-001 | None | 0% | ADD |
| Skill-Drift-001 | None | 0% | ADD |
| Skill-Communication-001 | None | 0% | ADD |

---

## Phase 5: Close the Retrospective

### +/Delta

#### + Keep

- Systematic approach to retrospective (once invoked)
- Use of structured frameworks for analysis

#### Δ Change

- Should have invoked retrospective framework BEFORE making changes, not after failure
- Should read project documentation proactively, not wait for failure

### ROTI Assessment

**Score**: 2 (Benefit > effort)

**Benefits Received**:

- Clear identification of root cause
- Actionable skills to prevent recurrence
- Documentation of failure for future reference

**Time Invested**: ~30 minutes

**Verdict**: Continue - valuable learning extraction

### Helped, Hindered, Hypothesis

#### Helped

- Access to .agents/ documentation made analysis possible
- PRD had explicit guidance that clarified the failure

#### Hindered

- Context summarization from previous conversation may have lost nuance
- Did not have proactive trigger to read .agents/ documentation

#### Hypothesis

- Adding "Read .agents/planning/ PRD first" to agent modification workflow will prevent similar failures

---

## Immediate Remediation Required

1. **Revert commit ddb76e0**: This commit modifies Claude (source of truth) to match templates (derived)
2. **Update templates to match Claude**: Per PRD, templates should be updated to match Claude, not vice versa
3. **Re-run drift detection**: Verify direction is correct

---

## Memory Request

### Operation Type

CREATE

### Entities

| Entity Type | Name | Content |
|-------------|------|---------|
| Skill | Skill-Process-001 | Before modifying agent files, read .agents/planning/ PRD to verify source of truth and update direction |
| Skill | Skill-Drift-001 | Drift detection shows differences between files, not which file to update; always verify source of truth before fixing drift |
| Skill | Skill-Communication-001 | When update direction is ambiguous, ask 'Which file is source of truth?' before making changes |
| Failure | Failure-Drift-001 | 2025-12-15: Modified Claude (source of truth) to match templates (derived), inverted project direction |

### Relations

| From | Relation | To |
|------|----------|-----|
| Skill-Process-001 | prevents | Failure-Drift-001 |
| Skill-Drift-001 | prevents | Failure-Drift-001 |
| Skill-Communication-001 | prevents | Failure-Drift-001 |

---

**Retrospective Complete**

**ROTI**: 2/4
**Learnings Extracted**: 3
**Skill Updates Recommended**: 3 ADD
**Immediate Action Required**: Revert commit ddb76e0, update templates to match Claude
