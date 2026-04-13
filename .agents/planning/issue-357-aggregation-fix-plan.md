# Issue #357: AI PR Quality Gate - Improvement Plan

**Date**: 2025-12-24
**Issue**: [#357](https://github.com/rjmurillo/ai-agents/issues/357)
**RCA**: [issue-357-aggregation-rca.md](../analysis/issue-357-aggregation-rca.md)
**Status**: Ready for Implementation

---

## Related Issues

| Issue | Title | Status | Relationship |
|-------|-------|--------|--------------|
| [#338](https://github.com/rjmurillo/ai-agents/issues/338) | Add retry logic with backoff for Copilot CLI failures | OPEN (P1) | **Addresses transient infrastructure failures** - distinct from code quality findings |
| [#329](https://github.com/rjmurillo/ai-agents/issues/329) | Categorize AI Quality Gate failures | CLOSED | Already implemented infrastructure vs code quality categorization |
| [#358](https://github.com/rjmurillo/ai-agents/issues/358) | Merge ready PRs blocked by process | OPEN (P0) | PRs ready to merge but blocked by process (not quality) |
| [#324](https://github.com/rjmurillo/ai-agents/issues/324) | 10x Velocity Improvement Epic | OPEN | Parent epic for velocity improvements |
| [#359](https://github.com/rjmurillo/ai-agents/issues/359) | Close or split PRs with excessive commit churn | OPEN (P0) | Related velocity blocker |
| [#360](https://github.com/rjmurillo/ai-agents/issues/360) | Prevent bot-on-bot review loops | OPEN (P1) | Bot interaction causing churn |

### Two Distinct Failure Modes

The RCA revealed that "aggregation failures" actually encompasses **two distinct problems**:

| Failure Mode | Root Cause | Solution |
|--------------|------------|----------|
| **Code Quality Findings** | Agents issue legitimate CRITICAL_FAIL for real issues | This plan: bypass label, context-aware review, calibration |
| **Transient Infrastructure** | Copilot CLI timeouts, rate limits, network errors | [#338](https://github.com/rjmurillo/ai-agents/issues/338): Retry with backoff |

Both must be addressed for full resolution.

---

## Problem Statement (Corrected)

The original issue claimed an "aggregation bug." Investigation reveals:
- The aggregation logic works correctly
- PRs are blocked by legitimate AI agent code quality findings
- The actual problem is **agent calibration** and **lack of override mechanism**

This plan addresses the real improvements needed to reduce false positives and provide human oversight.

---

## Proposed Solutions

### ~~Solution 1: Human Override Mechanism~~ (REMOVED)

> **REMOVED**: Bypass label mechanism was rejected. AI agents cannot be trusted with
> an "easy out" - they will exploit it and code quality will rot. Instead of giving
> agents escape hatches, the system must constrain them through design.
>
> Constraints > Trust. If agents can't do the wrong thing, they won't.

---

### Solution 1: Context-Aware Review Skipping (P0)

**Problem**: QA agent requires tests for documentation-only PRs.

**Implementation**:

1. Detect file change patterns in check-changes job
2. Pass context to agents via matrix include
3. Agents adjust thresholds based on context

**Location**: `.github/workflows/ai-pr-quality-gate.yml`

**Changes to check-changes job**:

```yaml
- name: Analyze change types
  id: analyze
  run: |
    # Get changed files
    CHANGED_FILES=$(gh pr diff ${{ env.PR_NUMBER }} --name-only 2>/dev/null || echo "")

    # Categorize changes
    DOC_ONLY=true
    CODE_CHANGES=false
    TEST_CHANGES=false

    while IFS= read -r file; do
      case "$file" in
        *.md|*.txt|*.rst|docs/*|.agents/*)
          # Documentation - keep DOC_ONLY true
          ;;
        *.Tests.ps1|*_test.go|*.test.ts|tests/*)
          TEST_CHANGES=true
          DOC_ONLY=false
          ;;
        *.ps1|*.cs|*.ts|*.go|src/*|scripts/*)
          CODE_CHANGES=true
          DOC_ONLY=false
          ;;
        *)
          DOC_ONLY=false
          ;;
      esac
    done <<< "$CHANGED_FILES"

    echo "doc_only=$DOC_ONLY" >> $GITHUB_OUTPUT
    echo "code_changes=$CODE_CHANGES" >> $GITHUB_OUTPUT
    echo "test_changes=$TEST_CHANGES" >> $GITHUB_OUTPUT
```

**Changes to matrix include**:

```yaml
strategy:
  matrix:
    include:
      - agent: qa
        prompt-file: .github/prompts/pr-quality-gate-qa.md
        context: ${{ needs.check-changes.outputs.doc_only == 'true' && 'doc-only' || 'standard' }}
```

**Changes to QA prompt**:

```markdown
<!-- In pr-quality-gate-qa.md -->

## Context-Aware Behavior

If the PR context is "doc-only":
- Skip test coverage requirements
- Focus on documentation quality, spelling, formatting
- Return WARN instead of CRITICAL_FAIL for missing tests

If the PR context is "standard":
- Enforce full test coverage requirements
- Check for regression risks
- Return CRITICAL_FAIL for missing tests on new code
```

**Effort**: 4 hours
**Risk**: Medium (requires prompt tuning)

---

### Solution 2: Agent Prompt Calibration (P1)

**Problem**: Agents may be too strict, creating false positives.

**Implementation**:

1. Review each agent prompt for severity thresholds
2. Add calibration examples (few-shot learning)
3. Implement "WARN-first" policy for borderline issues

**Files to modify**:

- `.github/prompts/pr-quality-gate-qa.md`
- `.github/prompts/pr-quality-gate-security.md`
- `.github/prompts/pr-quality-gate-analyst.md`
- `.github/prompts/pr-quality-gate-architect.md`
- `.github/prompts/pr-quality-gate-devops.md`
- `.github/prompts/pr-quality-gate-roadmap.md`

**Calibration guidelines**:

| Verdict | Use When |
|---------|----------|
| PASS | No issues found |
| WARN | Minor issues, suggestions for improvement |
| CRITICAL_FAIL | Security vulnerabilities, major bugs, test coverage <50% for new code |
| REJECTED | Malicious code, secrets in code, fundamental architectural flaws |

**Effort**: 6 hours
**Risk**: Medium (requires iteration to find right balance)

---

### Solution 3: Improve PR Comment Clarity (P2)

**Problem**: Findings are not actionable enough.

**Implementation**:

1. Add "How to Fix" column to findings table
2. Include specific file locations with line numbers
3. Add "Quick Fix" suggestions for common issues

**Location**: Agent prompts and report generation

**Example output**:

```markdown
## Findings

| Severity | Issue | Location | How to Fix |
|----------|-------|----------|------------|
| BLOCKING | No tests for new script | `Test-PRMerged.ps1` | Create `Test-PRMerged.Tests.ps1` with unit tests covering lines 70-83 |
| HIGH | Error path untested | Lines 70-72 | Add test case: `Should return exit code 2 when API fails` |
```

**Effort**: 3 hours
**Risk**: Low

---

## Implementation Plan

### Phase 0: Address Transient Failures (Prerequisite)

**Issue**: [#338](https://github.com/rjmurillo/ai-agents/issues/338)

| Task | Owner | Status |
|------|-------|--------|
| Implement retry logic with exponential backoff | implementer | Pending |
| Add fail-fast for expired tokens (exit 1, not verdict) | implementer | Pending |
| Test transient failure recovery | qa | Pending |

This is a **prerequisite** because transient failures mask the true failure rate of code quality findings.

### Phase 1: Immediate Unblock (Today)

| Task | Owner | Status |
|------|-------|--------|
| Implement context-aware review skipping | implementer | Pending |
| Merge ready PRs (#334, #336, #245) per [#358](https://github.com/rjmurillo/ai-agents/issues/358) | devops | Pending |

### Phase 2: Reduce False Positives (This Week)

| Task | Owner | Status |
|------|-------|--------|
| Implement context-aware review skipping | implementer | Pending |
| Calibrate QA agent prompt | analyst | Pending |
| Test with doc-only PR | qa | Pending |

### Phase 3: Improve Experience (Next Week)

| Task | Owner | Status |
|------|-------|--------|
| Calibrate all agent prompts | analyst | Pending |
| Improve PR comment format | implementer | Pending |
| Create calibration test suite | qa | Pending |

---

## Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| False positive rate | Unknown | <10% | Manual review of blocked PRs |
| Bypassed PRs | N/A | <5% | GitHub label usage |
| Time to merge (after fixes) | Blocked | <1 hour | PR merge latency |
| Agent agreement rate | Unknown | >80% | Cross-agent verdict alignment |

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Over-tuning prompts | Miss real issues | Keep security agent strict |
| Context detection errors | Wrong agent behavior | Default to "standard" context |
| Agent exploitation of loopholes | Code quality rot | Design constraints, not escape hatches |

---

## Issue Tracker

### Existing Issues to Prioritize

| Issue | Title | Priority | Action |
|-------|-------|----------|--------|
| [#338](https://github.com/rjmurillo/ai-agents/issues/338) | Add retry logic with backoff for Copilot CLI failures | P1→**P0** | Elevate priority - prerequisite for measuring true false positive rate |
| [#358](https://github.com/rjmurillo/ai-agents/issues/358) | Merge ready PRs blocked by process | P0 | Execute immediately - 3 PRs ready to merge |

### New Issues to Create

1. **Context-Aware AI Review** (P0)
   - Detect doc-only vs code changes
   - Pass context to agents
   - Adjust verdicts accordingly
   - Link to parent epic [#324](https://github.com/rjmurillo/ai-agents/issues/324)

2. **Calibrate AI Agent Prompts** (P1)
   - Review all 6 agent prompts
   - Add calibration examples
   - Test with representative PRs
   - Link to parent epic [#324](https://github.com/rjmurillo/ai-agents/issues/324)

3. **Improve AI Review Findings Format** (P2)
   - Add "How to Fix" column
   - Include line numbers
   - Add quick fix suggestions
   - Link to parent epic [#324](https://github.com/rjmurillo/ai-agents/issues/324)

---

## Appendix: Issue #357 Resolution

### Recommendation

Close Issue #357 as "Not a Bug" with the following comment:

```markdown
## Investigation Complete

After thorough analysis ([RCA document](.agents/analysis/issue-357-aggregation-rca.md)),
we determined that the aggregation logic is working correctly.

### Key Findings

1. **Individual agent jobs complete successfully** (job status: success)
2. **Agents return legitimate code quality verdicts** (e.g., CRITICAL_FAIL for missing tests)
3. **Aggregation correctly blocks PRs** when CODE_QUALITY failures exist
4. **Infrastructure failures are already handled** (downgraded to WARN per #328)

### The Real Issue

PRs are blocked because AI agents identify actual code quality concerns:
- Missing test coverage for new scripts
- Untested error paths
- Security considerations

### Next Steps

We're creating improvement issues to address:
- [ ] #XXX: Context-aware review (doc-only PRs) - P0
- [ ] #XXX: Agent prompt calibration - P1
- [ ] #XXX: Improved findings format - P2

Closing this as "Not a Bug" - the system works as designed, but improvements are planned.

> **Note**: Bypass label mechanism was explicitly rejected. Constraints > Trust.
```

---

**Document Status**: Ready for Review

**Next Action**: Create improvement issues and implement bypass mechanism
