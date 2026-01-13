# Validation Anti-Patterns

## Anti-Pattern: Victory Lap Before Finish Line

**Description**: Declaring success, writing retrospective, and extracting skills before validating implementation works.

**Symptoms**:

- "Zero bugs" claims without test evidence
- Retrospective written same session as implementation
- Skills extracted from untested code
- High confidence metrics (A+, 100%) without validation

**Remedy**:

1. Implementation → Test → Validate → THEN Retrospective
2. Minimum 24-hour delay between implementation and retrospective for infra work
3. Skills only extracted after production validation
4. PR comments must be triaged before declaring success

## Anti-Pattern: Metric Fixation

**Description**: Optimizing for impressive-sounding metrics over actual outcomes.

**Symptoms**:

- Counting LOC as achievement ("2,189 lines!")
- Measuring planning time, not validation time
- "Zero pivots" as positive when it means "skipped validation"
- Celebrating file counts instead of working features

**Remedy**:

1. Track fix commits, not implementation commits
2. Measure time-to-working, not time-to-committed
3. Count test executions, not file counts
4. Track PR comment resolution rate

## Anti-Pattern: Implement Before Verify

**Description**: Writing code before checking constraints causes repeated violations.

**Symptoms**:

- Writing inline `gh` commands without checking skills capability
- Creating bash/Python scripts without checking language preferences
- Making commits without checking atomicity rules

**Remedy**:

1. Read PROJECT-CONSTRAINTS.md BEFORE implementation (BLOCKING gate)
2. Check `.claude/skills/` BEFORE writing GitHub operations
3. Verify approach against patterns BEFORE coding

## Anti-Pattern: Trust-Based Compliance

**Description**: Trusting agent to remember constraints without verification gates.

**Symptoms**:

- Documentation exists but violations occur anyway
- Agent acknowledges rules but doesn't apply them
- Corrections don't persist beyond 10-15 minutes

**Remedy**:

1. Shift from trust-based to verification-based enforcement
2. Add BLOCKING gates requiring tool output (not agent acknowledgment)
3. Example: ❌ "I will check for skills" (trust) → ✅ `Check-SkillExists.ps1` output (verification)

## Related

- [validation-006-self-report-verification](validation-006-self-report-verification.md)
- [validation-007-cross-reference-verification](validation-007-cross-reference-verification.md)
- [validation-007-frontmatter-validation-compliance](validation-007-frontmatter-validation-compliance.md)
- [validation-474-adr-numbering-qa-final](validation-474-adr-numbering-qa-final.md)
- [validation-baseline-triage](validation-baseline-triage.md)
