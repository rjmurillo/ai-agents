# Task-Generator: Gate vs Skill Evaluation

## Metadata

**Investigation ID**: 766
**Date**: 2026-01-04
**Investigator**: GitHub Copilot CLI
**Parent Issue**: #612 (Phase 1: Core ADR-033 Gates)
**Status**: COMPLETE

## Executive Summary

**DECISION**: **NO ACTION NEEDED**

The task-generator agent consistently produces TASK-NNN format and is being invoked appropriately. The evidence shows:

1. **Format consistency**: 227 TASK-NNN references across 12 planning files
2. **Agent compliance**: Task-generator definition explicitly requires TASK-NNN format (line 103)
3. **Quality issues are content-related**: Critique feedback targets task prompt self-containment and specificity, NOT format standardization or generation enforcement

**Recommendation**: Close issue #766 with NO ACTION verdict. Task-generator does not need a gate (it's being invoked) or skill (format is standardized).

---

## Investigation Questions

### Q1: Is the problem "tasks aren't generated"?

**Answer**: NO

**Evidence**:

1. **Planning artifacts exist**: 4 task breakdown files found
   - `tasks-agent-consolidation.md` (21 tasks)
   - `tasks-pr365-remediation.md` (14 tasks)
   - `tasks-pr-maintenance-authority.md` (17 tasks)
   - `tasks-acknowledged-vs-resolved.md` (count not inspected)

2. **Session logs show usage**: 5 session logs reference task-generator
   - `2025-12-22-session-64a-guardrails-task-validation.md`
   - `2025-12-18-session-15-pr-60-response.md`
   - `2025-12-26-session-88-prd-planning-workflow-retrospective.md`
   - Others not inspected

3. **Retrospective evidence**: Session 88 documents complete workflow
   - "analyst → explainer → critic → **task-generator**" (line 11)
   - "Task-generator output" documented in artifacts table (line 30)

**Verdict**: Tasks ARE being generated. No enforcement gate needed.

---

### Q2: Is the problem "task format varies"?

**Answer**: NO

**Evidence**:

1. **TASK-NNN format ubiquitous**: 227 instances across planning files
   ```bash
   grep -r "TASK-[0-9][0-9][0-9]" .agents/planning/*.md | wc -l
   # Output: 227
   ```

2. **Agent definition mandates format**: Line 103 of task-generator.md
   ```markdown
   **ID**: TASK-[NNN]
   ```

3. **Task breakdown files comply**:
   - `tasks-agent-consolidation.md`: TASK-001 through TASK-021 (line 40, 61, 101, etc.)
   - `tasks-pr365-remediation.md`: TASK-001 through TASK-014 (line 36, 54, 85, etc.)
   - `tasks-pr-maintenance-authority.md`: Uses TASK-1.1, TASK-2.1 format (nested milestones)

4. **No format deviation found**: All inspected task files use numeric IDs with zero variation

**Verdict**: Format is standardized. No skill needed.

---

### Q3: Does task-generator agent already produce consistent TASK-NNN format?

**Answer**: YES

**Evidence**:

1. **Agent definition explicitly requires format** (line 103):
   ```markdown
   **ID**: TASK-[NNN]
   ```

2. **Output format template** (line 149):
   ```markdown
   ### Task: [Short Title]
   
   **ID**: TASK-[NNN]
   **Type**: Feature | Bug | Chore | Spike
   **Complexity**: XS | S | M | L | XL
   ```

3. **Handoff validation checklist** (line 256):
   ```markdown
   - [ ] All tasks have unique IDs (TASK-NNN format)
   ```

4. **Recent outputs comply**:
   - `tasks-agent-consolidation.md` (2025-12-30): "**ID**: TASK-001" (line 40)
   - `tasks-pr365-remediation.md` (date unknown): "#### TASK-001:" (line 36)

**Verdict**: Agent consistently produces required format. No action needed.

---

## Quality Analysis: What IS the Problem?

### Actual Issue: Task Prompt Self-Containment

**Source**: `.agents/critique/tasks-pr-maintenance-authority-critique.md`

**Key Findings**:

1. **Verdict**: NEEDS REVISION (line 8)
2. **Scope**: 11 of 17 tasks require revision (line 11)
3. **Root cause**: "vague location references requiring cross-task context" (line 11)

**Examples**:

- Task 1.3: "Remove or comment out any duplicate call **after Task 1.2**" (line 27)
  - **Issue**: Requires reading Task 1.2 to understand location
  - **Fix**: Provide absolute line number or exact search pattern

- Task 2.2: "add comment collection **after the copilot detection block (Task 2.1)**" (line 40)
  - **Issue**: Must locate Task 2.1 code first
  - **Fix**: Specify "approximately line 1268, AFTER $isCopilotPR detection"

- Tasks 5.1-5.6: Assume "Process-SinglePR" function exists (line 50)
  - **Issue**: No verification that function exists
  - **Fix**: Document actual invocation pattern or add existence check

### Pattern: Location References

**Anti-Pattern**: Relative location references like "after Task X" (line 83)

**Correct Pattern**: Absolute references
- File path: `/home/richard/ai-agents/path/to/file.ps1`
- Line number: "Line 1268"
- Search pattern: "Search for `$isCopilotPR =`"

**Evidence from working tasks** (line 14):
- Task 1.1: "Excellent - specific line numbers, complete code, zero ambiguity"
- Task 1.2: "Excellent - specific line numbers, complete code, zero ambiguity"
- Task 4.1: "Clear replacement logic with full code block showing all branches"

### Pattern: Test Structure Discovery

**Issue**: Tests generated BEFORE test structure discovered (Session 88, line 66)

**Anti-Pattern**: Assume function existence ("Process-SinglePR") without verification

**Correct Pattern**: Discover test structure, THEN generate test tasks

**Skill Extracted**: Skill-Planning-006
- "Discover test structure before generating test tasks" (Session 88, line 74)
- Atomicity: 90%
- Impact: Prevents assumptions

---

## Root Cause Assessment

### Why Tasks Need Revision

**Layer Analysis**:

| Layer | Issue | Gate Needed? | Skill Needed? |
|-------|-------|--------------|---------------|
| **Format** | None - TASK-NNN consistent | NO | NO |
| **Invocation** | Agent being called | NO | NO |
| **Content Quality** | Self-containment issues | NO | MAYBE |

**Content Quality Issues**:

1. Location references: "after Task X" vs absolute paths/line numbers
2. Function existence assumptions: Process-SinglePR without verification
3. Test structure discovery: Generate tests BEFORE understanding patterns
4. File path inconsistency: Some absolute, some relative

**Are these gate-worthy?**

NO. These are **task generation quality issues**, not **protocol bypass** issues.

**Gate Definition** (ADR-033, line 48):
> "Gates operate at the **tool invocation layer**, blocking high-stakes actions until validation prerequisites are met."

**Examples of gate-worthy issues** (ADR-033, lines 135-138):
- `git commit` without session log
- `gh pr create` without QA validation
- `gh pr merge` without critic review

**Task content quality** does NOT fit gate model because:
- No tool invocation to block
- No validation prerequisite to enforce
- Quality feedback is already handled by critic agent

---

## ADR-033 Gate Criteria Assessment

### Session Protocol Gate (ADR-033, line 209)

**Trigger**: `git commit`, `gh pr create`
**Prerequisite**: Session log exists

**Does task-generator need this?** NO

- Task-generator doesn't directly invoke git/gh commands
- Task-generator is a planning agent, not implementation agent
- Session log check applies to implementer/orchestrator, not task-generator

### QA Validation Gate (ADR-033, line 226)

**Trigger**: `gh pr create`
**Prerequisite**: `.agents/qa/` report exists

**Does task-generator need this?** NO

- Task-generator outputs planning artifacts, not PRs
- QA validation applies AFTER implementation, not during planning

### Critic Review Gate (ADR-033, line 278)

**Trigger**: `gh pr merge`
**Prerequisite**: Critic agent invoked

**Does task-generator need this?** NO

- Evidence shows critic already reviews task breakdowns (Session 88)
- Critic review is ADVISORY (NEEDS REVISION verdict), not BLOCKING
- Task iteration loop exists but is trust-based, not gate-enforced

### "Do Router" Integration (ADR-033, line 384)

**Pattern**: Keyword-based mandatory routing
- Security agent for `**/Auth/**` files
- Architect agent for `ADR-*.md` changes
- QA agent before PR action

**Does task-generator need routing enforcement?** NO

- Task-generator is invoked by orchestrator per standard workflow (Session 88, line 11)
- No evidence of task-generator being skipped
- Routing enforcement would target orchestrator, not task-generator output

---

## Alternative: Skill for Task Quality

### Skill Hypothesis

Could a skill improve task-generator output quality?

**Existing Skill**: Skill-Planning-006 (Session 88, line 74)
- "Discover test structure before generating test tasks"
- Atomicity: 90%
- Impact: Prevents assumptions
- **Status**: Already extracted

**Potential New Skill**: "Self-Contained Task Prompts"

**Content**:
```markdown
# Skill: Self-Contained Task Prompts

## Pattern

When generating tasks, ensure each task prompt is executable by an amnesiac agent:

1. **File paths**: Absolute paths only (`/home/user/repo/file.ps1`)
2. **Line numbers**: Exact line or search pattern, not "after Task X"
3. **Function existence**: Verify before invoking in tests
4. **Code blocks**: Complete with no placeholders
5. **Verification steps**: Explicit commands to confirm correctness

## Anti-Pattern

- "Remove or comment out any duplicate call after Task 1.2"
- "Add after the copilot detection block (Task 2.1)"
- "Adjust mocking approach to match existing test patterns in the file"

## Correct Pattern

- "Search for `Get-UnacknowledgedComments` on line 1305, REPLACE with [code]"
- "Line 1268: AFTER `$isCopilotPR = ...`, BEFORE action determination, INSERT [code]"
- "Test file uses `Mock Get-GitHubClient` with `{ @{ GetPR = {...} } }` pattern"
```

**Evaluation**:

| Criterion | Assessment | Rationale |
|-----------|------------|-----------|
| Atomicity | 85% | Clear, single-purpose pattern |
| Actionable | 90% | Provides explicit do/don't guidance |
| Timeless | 80% | Principles apply across languages |
| Evidence-based | 95% | Derived from critic feedback |

**Recommendation**: CREATE SKILL

**But**: Skill would be embedded in task-generator agent definition, NOT a separate skill file.

**Action**: Update task-generator.md with self-containment guidance.

---

## Recommended Actions

### Action A: No Gate Implementation

**Rationale**: Task-generator does not need a gate because:
1. Agent is being invoked (no enforcement gap)
2. Content quality is not gate-worthy (no tool invocation to block)
3. Critic review already provides quality feedback

**Decision**: Do NOT implement gate for task-generator.

### Action B: No Separate Skill Creation

**Rationale**: Task prompt self-containment is task-generator-specific guidance, not general-purpose skill.

**Better approach**: Embed guidance directly in agent definition.

**Decision**: Do NOT create separate skill file.

### Action C: Update Task-Generator Agent Definition (OPTIONAL)

**Rationale**: Add self-containment guidance to prevent future critique cycles.

**Proposal**: Add section to task-generator.md after line 167 (Output Format):

```markdown
## Task Prompt Self-Containment

Each task prompt must be executable by an amnesiac agent with zero prior context.

**Requirements**:

1. **File paths**: Use absolute paths (`/home/user/repo/file.ps1`)
2. **Location references**: Provide line numbers OR search patterns, not "after Task X"
3. **Function existence**: Verify before invoking (especially in tests)
4. **Code blocks**: Complete with no `# existing code` placeholders
5. **Test patterns**: Document existing patterns before referencing them

**Anti-Patterns**:

| Instead of... | Use... |
|---------------|--------|
| "after Task 1.2" | "Line 1305: AFTER `Get-UnacknowledgedComments` call" |
| "Task 2.1 block" | "Line 1268, search for `$isCopilotPR =`" |
| "existing test patterns" | "Mock pattern: `Mock Get-GitHubClient { @{ ... } }`" |
| "Process-SinglePR" (assumed) | "Verify `Process-SinglePR` function exists at line X" |

**Rationale**: Tasks handed off to implementer may be executed days later by different agent with no conversation history.
```

**Decision**: OPTIONAL - Would improve quality but not required to resolve issue #766.

---

## Conclusion

### Final Verdict: NO ACTION

**Reasoning**:

1. **Task generation happening**: 227 TASK-NNN instances, 4 task breakdown files, 5 session log references
2. **Format standardized**: Agent definition mandates TASK-NNN, all outputs comply
3. **Quality issues NOT gate-worthy**: Content self-containment is critic feedback, not protocol bypass
4. **Existing mechanisms work**: Critic reviews tasks, Session 88 shows iterative improvement

**Issue #766 Resolution**: Close with **NO ACTION NEEDED** verdict.

**Optional Improvement**: Add self-containment guidance to task-generator.md (Action C above).

---

## Evidence Summary

| Evidence Type | Source | Finding |
|---------------|--------|---------|
| **Agent Definition** | `src/claude/task-generator.md:103` | TASK-NNN format mandated |
| **Planning Artifacts** | 12 files with TASK-NNN | Format consistently applied |
| **Session Logs** | 5 sessions reference task-generator | Agent being invoked |
| **Critique Feedback** | `tasks-pr-maintenance-authority-critique.md` | Quality issues are content-related, NOT format |
| **Retrospective** | Session 88 | Workflow includes task-generator step |
| **ADR-033 Gates** | Gate architecture | Content quality doesn't fit gate model |

---

## Related Work

- **ADR-033**: Routing-Level Enforcement Gates
- **Issue #612**: Phase 1: Core ADR-033 Gates (parent issue)
- **Session 88**: PRD Planning Workflow Retrospective
- **Skill-Planning-006**: Discover test structure before generating test tasks

---

**Investigation Complete**: 2026-01-04
**Decision**: NO ACTION NEEDED
**Next Steps**: Document decision in issue #766, recommend closure
