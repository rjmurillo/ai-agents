# Validation & Quality Skills

**Extracted**: 2025-12-16
**Source**: `.agents/retrospective/phase1-remediation-pr43.md`

## Skill-Validation-001: Validation Script False Positives

**Statement**: When creating validation scripts, distinguish between examples/anti-patterns and production code to prevent false positives

**Context**: Any validation script or automated checker

**Evidence**: 3/14 path violations were intentional anti-pattern examples in explainer.md

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Mitigation Strategies**:

1. Skip code fence blocks during validation
2. Add `<!-- skip-validation -->` comment mechanism
3. Maintain allowlist for known pedagogical examples
4. Document false positives in validation output

---

## Skill-Validation-002: Pedagogical Error Messages

**Statement**: Validation scripts should be pedagogical - error messages should teach the standard, not just report violations

**Context**: Any validation script or linter

**Evidence**: Path validation script includes remediation steps, examples, references explaining why/what/how

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 9/10

**Pattern**:

```text
ERROR: Incorrect path reference at explainer.md:45
  Found: path/to/file
  Expected: [path/to/file](path/to/file)
  
  WHY: Markdown links enable navigation and prevent broken references
  FIX: Wrap path in link syntax: [display](target)
  REF: See .markdownlint-cli2.yaml for configuration
```

---

## Skill-Validation-003: Pre-Existing Issue Triage

**Statement**: When introducing new validation, establish baseline and triage pre-existing violations separately from new work

**Context**: Adding new validators to existing codebases

**Evidence**: Validation script found 14 pre-existing issues requiring separate triage to avoid scope creep

**Atomicity**: 92%

**Tag**: helpful

**Impact**: 9/10

**Implementation**:

1. Run validator and capture baseline count
2. Create exception list or snapshot for existing violations
3. New code must pass validation (zero tolerance)
4. Schedule separate remediation for pre-existing issues
5. Gradual rollout: warn → error over time

---

## Skill-Validation-004: Test Before Retrospective

**Statement**: Never write a retrospective until implementation has been:
1. Executed and validated in target environment (CI/CD)
2. All PR review comments addressed or acknowledged
3. All security scanning alerts remediated (high/critical = blocking)
4. No findings blocking merge

**Context**: Completing implementation of infrastructure/CI code; any multi-file change

**Trigger**: Declaring "implementation complete" or writing retrospective

**Evidence**: 
- Session 03 (2025-12-18): Claimed "zero bugs" and "A+ grade" for 2,189 LOC
- Reality: 6+ critical bugs, 24+ fix commits across 4 debugging sessions
- PR #60: 30 review comments (19 Copilot security, 9 Gemini high-priority, 2 GitHub Security)
- PR #60: 4 high-severity code scanning alerts (path injection CWE-22) still open

**Atomicity**: 95%

**Tag**: CRITICAL

**Impact**: 10/10 - Prevents false confidence and premature skill extraction

**Checklist Before Retrospective**:

- [ ] Code executed in target environment (not just written)
- [ ] CI/CD pipeline passed
- [ ] All PR review comments triaged (addressed/acknowledged/deferred with reason)
- [ ] Security scanning completed (code-scanning, dependabot)
- [ ] No high/critical security findings blocking
- [ ] Peer review completed (if required)

**Anti-Pattern**: Victory Lap Before Finish Line

---

## Skill-Validation-005: PR Feedback Gate

**Statement**: PR feedback from automated reviewers (Copilot, CodeRabbit, Gemini, cursor, GitHub Security) constitutes validation evidence that must be addressed before claiming completion

**Context**: Any PR with automated review comments

**Trigger**: Before merging PR or claiming implementation success

**Evidence**:
- PR #60: 30 comments ignored when claiming "zero bugs"
- Pattern: Copilot flagged command injection risks (eval with user input)
- Pattern: GitHub Security flagged code injection vulnerabilities
- 4 high-severity path injection alerts require remediation

**Atomicity**: 92%

**Tag**: helpful

**Impact**: 9/10 - PR comments ARE validation data

**Comment Triage Requirements**:

| Action | Description |
|--------|-------------|
| **Addressed** | Code changed to fix issue |
| **Acknowledged** | Valid but deferred (documented reason) |
| **Dismissed** | False positive (with evidence) |
| **Blocked** | High/Critical security = merge blocker |

**Reviewer Signal Quality** (from pr-comment-responder-skills):

| Reviewer | Signal Rate | Priority |
|----------|-------------|----------|
| cursor[bot] | 100% | P0 - Process immediately |
| GitHub Security | ~95% | P0 - Security blocking |
| Copilot | ~44% | P2 - Review carefully |
| CodeRabbit | ~50% | P2 - Check for duplicates |

---

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

## Related Documents

- Source: `.agents/retrospective/phase1-remediation-pr43.md`
- Related: skills-linting (Skill-Lint-002 false positives)
