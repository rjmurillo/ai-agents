# Human-Agent Collaboration Skills

**Extracted**: 2025-12-16
**Source**: `.agents/retrospective/phase3-p2-learnings.md`

## Skill-Collaboration-001: User Additions as Learning Signals (92%)

**Statement**: User mid-execution additions indicate scope gaps; extract pattern for proactive detection

**Context**: When user adds requirements during implementation phase

**Trigger**: User adds task not in original issue/plan

**Evidence**: Phase 3 (P2): User added P2-6 (template porting) after P2-1 to P2-5 completed. This was NOT in original issue #44 but was required for platform consistency. User intervention improved outcome quality.

**Atomicity**: 92%

- Specific trigger (user mid-execution additions) ✓
- Single concept (scope gap signal) ✓
- Actionable (extract pattern) ✓
- Measurable (can detect when user adds tasks) ✓
- Length: 11 words ✓

**Category**: Human-Agent Collaboration

**Learning Signal**: User intervention = system knowledge gap

**Action**: Extract user addition as new heuristic for future proactive detection

**Impact**: 8/10 - Enables continuous learning from user corrections

**Tag**: helpful

**Created**: 2025-12-16

**Validated**: 1 (P2-6 pattern)

---

## Pattern Recognition

When users add tasks during execution that were NOT in the original scope:

1. **Document the addition**: What was added and why
2. **Analyze the gap**: Why didn't agent surface this proactively?
3. **Extract heuristic**: Create detection rule for future tasks
4. **Update skills**: Add to skillbook for cross-session learning

**Example from Phase 3 P2**:

- Original scope: P2-1 through P2-5 (src/claude/ edits)
- User addition: P2-6 (template porting)
- Gap identified: Agent lacked heuristic "agent doc changes → check templates"
- Skill created: Skill-AgentWorkflow-004 (proactive template verification)

## Anti-Pattern

❌ **Do NOT** treat user additions as "scope creep" or interruptions
✅ **DO** treat them as valuable learning signals indicating system knowledge gaps
