# Skepticism: Zero Bugs Is A Red Flag

## Skill-Skepticism-001: Zero Bugs Is A Red Flag

**Statement**: "Zero bugs" in new infrastructure code should trigger verification, not celebration

**Context**: Claiming implementation success with no failures

**Trigger**: Any claim of "zero bugs", "100% success", "A+ grade" before validation

**Evidence**:
- Session 03: 2,189 LOC "zero bugs" code required 24+ fix commits
- Ratio: 1 implementation commit : 24+ fix commits = 96% of work fixing mistakes
- Root cause: Hubris - believed own hype before evidence

**Atomicity**: 90%

**Tag**: CRITICAL

**Impact**: 10/10 - Counters confirmation bias

**Verification Checklist for "Zero Bugs" Claims**:

- [ ] Has code been executed in production/CI environment?
- [ ] Have automated security scans completed?
- [ ] Have peer reviews been conducted?
- [ ] Are there any open PR review comments?
- [ ] Are there any code scanning alerts?
- [ ] Has integration testing completed?

**Red Flag Phrases**:
- "Zero implementation bugs"
- "100% success rate"
- "A+ (Exceptional)"
- "Plan executed exactly as designed"
- "Zero pivots during implementation"

---

## Anti-Pattern: Victory Lap Before Finish Line

**Description**: Declaring success, writing retrospective, and extracting skills before validating implementation works

**Symptoms**:
- "Zero bugs" claims without test evidence
- Retrospective written same session as implementation
- Skills extracted from untested code
- High confidence metrics (A+, 100%) without validation

**Evidence**: Session 03 - wrote retrospective BEFORE running code

**Remedy**:
1. Implementation → Test → Validate → THEN Retrospective
2. Minimum 24-hour delay between implementation and retrospective for infra work
3. Skills only extracted after production validation
4. PR comments must be triaged before declaring success

---

## Anti-Pattern: Metric Fixation

**Description**: Optimizing for impressive-sounding metrics over actual outcomes

**Symptoms**:
- Counting LOC as achievement ("2,189 lines!")
- Measuring planning time, not validation time
- "Zero pivots" as positive when it means "skipped validation"
- Celebrating file counts instead of working features

**Evidence**: Session 03 metrics were all vanity metrics

**Remedy**:
1. Track fix commits, not implementation commits
2. Measure time-to-working, not time-to-committed
3. Count test executions, not file counts
4. Track PR comment resolution rate

---

## Anti-Pattern-003: Implement Before Verify

**Description**: Writing code before checking constraints causes repeated violations requiring user intervention

**Symptoms**:
- Writing inline `gh` commands without checking if `.claude/skills/github/` has capability
- Creating bash/Python scripts without checking language preferences
- Putting logic in workflow YAML without checking thin-workflow pattern
- Making commits without checking atomicity rules
- User corrections for same violation type multiple times per session

**Evidence**: Session 15 - 5+ user interventions for violations of established patterns

**Cost**:
- 30-45 minutes lost to rework per session
- Token waste on duplicate implementations
- User frustration with repeated corrections

**Remedy**:
1. Read PROJECT-CONSTRAINTS.md BEFORE implementation (BLOCKING gate)
2. Check `.claude/skills/` BEFORE writing GitHub operations (verification required)
3. Verify approach against patterns BEFORE coding
4. Correct sequence: (1) Read constraints, (2) Check skills, (3) Verify approach, (4) Implement

---

## Anti-Pattern-004: Trust-Based Compliance

**Description**: Trusting agent to remember constraints without verification gates results in repeated violations

**Symptoms**:
- Documentation exists (memories, ADRs) but violations occur anyway
- Agent acknowledges rules but doesn't apply them
- Corrections don't persist beyond 10-15 minutes
- Each violation requires fresh user intervention
- Pattern: correct → implement → violate → correct (loop)

**Evidence**: 
- Session 15: 5+ violations despite [skill-usage-mandatory](skill-usage-mandatory.md), [user-preference-no-bash-python](user-preference-no-bash-python.md), [pattern-thin-workflows](pattern-thin-workflows.md) memories
- Retrospective 2025-12-17: Trust-based protocol compliance failures

**Root Cause**: No BLOCKING gates requiring verification (tool output) instead of trust (agent promise)

**Remedy**:
1. Shift from trust-based to verification-based enforcement
2. Add BLOCKING gates requiring tool output (not agent acknowledgment)
3. Examples:
   - ❌ "I will check for skills" (trust) 
   - ✅ `Check-SkillExists.ps1` output showing check performed (verification)
4. Extend SESSION-PROTOCOL.md with Phase 1.5 constraint validation gates

**Force Field Analysis**:
- Driving forces: Documentation exists (3/5), User frustration (4/5), Protocol pattern exists (5/5)
- Restraining forces: No BLOCKING gates (5/5), Trust-based (5/5), Scattered docs (3/5)
- Net: -5 (restraining stronger) → System favors violations until verification-based gates added

---