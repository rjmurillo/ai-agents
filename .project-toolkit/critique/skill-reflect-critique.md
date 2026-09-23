# Plan Critique: skill-reflect

## Verdict
**NEEDS REVISION**

## Summary

The skill-reflect skill provides a solid foundation for learning from conversations and updating skill memories. The core workflow (identify → analyze → propose → update) is well-structured and aligns with the user's requirements. However, several critical gaps exist around integration with existing protocols, missing anti-patterns, and unclear handling of edge cases.

## Strengths

- Clear workflow structure with progressive disclosure (Step 1-4)
- Excellent categorization of learning signals by confidence level (HIGH/MED/LOW)
- Well-defined detection patterns for each signal type
- Good examples demonstrating each signal category
- Integration with Session Protocol for session-end retrospectives
- Proper memory format with timestamps and session references
- Accessible color scheme mentioned (WCAG AA)
- Decision tree visualization for skill invocation
- Anti-patterns table addresses common pitfalls

## Issues Found

### Critical (Must Fix)

- [ ] **Missing Session Protocol Integration**: The skill MUST use `mcp__serena__read_memory` and `mcp__serena__write_memory` instead of direct file operations. Current Step 4 shows fallback to git, but Serena should be PRIMARY per SESSION-PROTOCOL.md Phase 1 requirements. (Location: Step 1, Step 4)

- [ ] **Missing Skill Usage Constraint**: The skill creates skill memories in `.serena/memories/skill-{name}.md` but does NOT reference the usage-mandatory memory or verify whether the skill being reflected upon has its own constraints. This could lead to memories conflicting with existing constraints. (Location: Step 1, Integration section)

- [ ] **No Validation of Memory Format**: Step 4 shows memory format but provides NO validation mechanism. The skill MUST verify the memory format is valid Markdown and follows the documented structure before writing. (Location: Step 4)

- [ ] **Missing Commit Verification**: The Commit Convention section (line 345-356) shows commit message format but does NOT verify this is used. The skill MUST integrate with git commit operations or document how commit messages are generated. (Location: Commit Convention section)

- [ ] **No Handling of Multiple Skills in Single Session**: Decision tree (line 219-221) mentions "Multiple skills?" but provides NO workflow details for analyzing and presenting findings for multiple skills. Does each get its own reflection box? Are they combined? (Location: Decision Tree)

### Important (Should Fix)

- [ ] **Unclear Trigger Timing**: "At session end" trigger (line 26) says "Proactive offer if skill was heavily used" but provides NO threshold. What constitutes "heavily used"? 3+ skill invocations? 50%+ of session? (Location: Triggers section)

- [ ] **Missing Integration with session-init Skill**: Session Protocol requires session-init skill for session logs. The skill-reflect SHOULD reference session-init to extract session number for memory annotations. (Location: Integration section)

- [ ] **No Progressive Disclosure for Long Conversations**: Analysis (Step 2) scans "the conversation" but provides NO guidance for handling long sessions (500+ messages). Should it scan the last N messages? Use memory search? (Location: Step 2)

- [ ] **Missing Conflict Resolution**: What happens if HIGH confidence signal contradicts existing HIGH confidence constraint in memory? No conflict resolution protocol documented. (Location: Step 4)

- [ ] **No Quality Gate for LOW Confidence Notes**: LOW confidence notes accumulate but no guidance on when to promote to MED or remove. This could lead to memory bloat. (Location: Step 2, Anti-Patterns)

- [ ] **Missing Security Review for Memory Content**: Memories could contain sensitive data (API keys, tokens) from conversation. No security review step before writing to `.serena/memories/`. (Location: Step 4)

- [ ] **No Rollback Mechanism**: If user approves changes but later wants to undo, what's the rollback path? Git revert? Manual edit? (Location: Step 4)

### Minor (Consider)

- [ ] **Color Key Accessibility**: Claims WCAG AA compliance (line 124) but does NOT provide actual hex codes or contrast ratios. Consider adding specific color values for validation. (Location: Step 3)

- [ ] **Example Consistency**: Examples 1-3 show different skills (github, error-handling, build) but don't demonstrate the SAME skill across multiple sessions to show memory accumulation. (Location: Examples section)

- [ ] **Missing Related Skill**: The Related section (line 332-339) lists `retrospective` but does NOT mention `session-init`, which is directly relevant for session number extraction. (Location: Related section)

- [ ] **No Metrics for Success**: How do we measure if skill-reflect is working? Number of memories created? Reduction in repeated mistakes? (Location: Missing section)

## Questions for Planner

1. **Serena Integration**: Should Serena MCP be REQUIRED or truly optional? Current fallback to git implies optional, but SESSION-PROTOCOL treats Serena as MUST.

2. **Memory Lifecycle**: What's the expected lifecycle of LOW confidence notes? Should they auto-expire after N sessions without promotion?

3. **User Approval Workflow**: Step 3 shows `[Y/n/edit]` prompt but no implementation guidance. Is this a PowerShell prompt? A conversation turn?

4. **Skill Discovery**: How does the skill identify which skill was used in conversation? Is there a session log reference? Memory search?

5. **Conflict Threshold**: What's the threshold for escalating conflicts in memories to high-level-advisor? When HIGH contradicts HIGH?

6. **Session Log Format**: The skill references session numbers (e.g., "Session 106") but doesn't specify if this comes from session log filename or internal field.

## Recommendations

### 1. Add Serena Integration Requirements

Update Step 1 and Step 4 to make Serena PRIMARY:

```markdown
### Step 1: Identify the Skill

**MUST Use Serena MCP (if available)**:

1. Call `mcp__serena__read_memory` with pattern `skill-{name}`
2. If Serena unavailable, fallback to direct file read at `.serena/memories/skill-{name}.md`
3. Document Serena availability in session log
```

### 2. Add Memory Validation Step

Insert between Step 3 and Step 4:

```markdown
### Step 3.5: Validate Memory Format

Before writing, MUST verify:

- [ ] Memory follows documented Markdown structure
- [ ] All sections present (Constraints, Preferences, Edge Cases, Notes)
- [ ] Timestamps are ISO 8601 format
- [ ] Session references are valid
- [ ] No sensitive data (API keys, tokens, credentials)
```

### 3. Add Multiple-Skill Workflow

Expand Decision Tree section:

```markdown
Multiple skills detected?
│
└─► YES → For each skill:
    1. Analyze signals separately
    2. Present findings grouped by skill
    3. Request approval per skill
    4. Write memories sequentially
```

### 4. Define "Heavily Used" Threshold

Update Triggers section:

```markdown
| At session end | Proactive offer if skill was heavily used (3+ invocations OR 50%+ of session actions) |
```

### 5. Add Conflict Resolution Protocol

Add to Step 4:

```markdown
**Conflict Resolution**:

If new HIGH signal conflicts with existing HIGH constraint:

1. Present both to user
2. Request explicit decision
3. Document override in memory with justification
4. Consider escalating to high-level-advisor if pattern/preference conflict
```

### 6. Add Security Review Gate

Add to Step 4:

```markdown
**Security Review (BLOCKING)**:

Before writing memory:

1. Scan for sensitive patterns: `api[_-]?key|password|token|secret|credential`
2. If matches found, redact or request user confirmation
3. Document scan result in session log
```

### 7. Add Quality Gate for LOW Confidence

Add to Anti-Patterns or new Maintenance section:

```markdown
**LOW Confidence Lifecycle**:

- After 5 sessions without promotion: Review for removal or promotion
- If same LOW signal appears 3+ times: Auto-promote to MED
- If contradicted by MED/HIGH: Remove
```

## Approval Conditions

**MUST Address** (blocking approval):

1. Add Serena MCP as PRIMARY integration (with fallback)
2. Add memory format validation step (with security review)
3. Add conflict resolution protocol for contradicting signals
4. Define "heavily used" threshold with specific metrics
5. Document multiple-skill workflow

**SHOULD Address** (conditional approval):

1. Add session-init integration for session number extraction
2. Add rollback mechanism documentation
3. Add progressive disclosure guidance for long conversations
4. Add quality gate for LOW confidence lifecycle

## Impact Analysis Review (if applicable)

**Not Applicable** - This is a skill review, not a plan with specialist consultations.

## Pre-PR Readiness Validation

**Not Applicable** - This is a skill specification, not an implementation plan. However, when implementing this skill, the planner MUST include:

- [ ] Validation tasks for Serena integration
- [ ] Validation tasks for memory format verification
- [ ] Test strategy for conflict resolution scenarios
- [ ] Security review validation for memory content

## Approval Status

- [ ] **APPROVED**: Plan is ready for implementation with full validation coverage
- [ ] **CONDITIONAL**: Approve with validation additions required
- [X] **REJECTED**: Critical validation gaps must be addressed

**Recommendation**: Route to planner for revision addressing Critical and Important issues. Once revised, re-submit for approval.
