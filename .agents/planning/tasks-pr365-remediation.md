# Task Breakdown: PR #365 Remediation

## Source

- PRD: `.agents/planning/PRD-pr365-remediation.md`
- Issue: #356 (fix(memory): Rename legacy skill- prefix files)
- PR: #365 (fix(memory): rename skill- prefix files and add naming validation)

## Summary

| Complexity | Count |
|------------|-------|
| S | 8 |
| M | 4 |
| L | 2 |
| **Total** | **14** |

## Estimate Reconciliation

**Source Document**: PRD-pr365-remediation.md
**Source Estimate**: 30-55 min
**Derived Estimate**: 30-55 min
**Difference**: 0%
**Status**: Aligned
**Rationale**: Task estimates align with PRD phase estimates (Phase 1: 15-30 min, Phase 2: 10-15 min, Phase 3: 5-10 min).

## Tasks

### Milestone 1: Conflict Resolution and Branch Rebase

**Goal**: Resolve merge conflicts and rebase PR #365 onto current main

#### TASK-001: Capture branch state before rebase

**Type**: Chore
**Complexity**: S

**Description**
Capture current branch state for rollback safety before performing rebase operations.

**Acceptance Criteria**
- [ ] Create backup directory `/tmp/pr365-backup/`
- [ ] Save current HEAD commit to `/tmp/pr365-backup/head.txt` using `git rev-parse HEAD`
- [ ] Save last 5 commits to `/tmp/pr365-backup/commits.txt` using `git log --oneline -5`
- [ ] Verify backup files exist and are non-empty

**Dependencies**
None

**Files Affected**
- None (creates temporary backup files only)

---

#### TASK-002: Fetch latest main and start rebase

**Type**: Chore
**Complexity**: S

**Description**
Fetch origin and initiate rebase of fix/memories branch onto origin/main.

**Acceptance Criteria**
- [ ] Run `git fetch origin` successfully
- [ ] Run `git checkout fix/memories` to switch to PR branch
- [ ] Run `git rebase origin/main` to start rebase
- [ ] Git reports conflicts in expected files (5 files per PRD)

**Dependencies**
- TASK-001: Backup created

**Files Affected**
- `.serena/memories/skill-autonomous-execution-guardrails.md` (conflict expected)
- `.serena/memories/skill-index-selection-decision-tree.md` (conflict expected)
- `.serena/memories/skill-init-001-session-initialization.md` (conflict expected)
- `.serena/memories/skills-analysis-index.md` (conflict expected)
- `.serena/memories/skills-architecture-index.md` (conflict expected)

---

#### TASK-003: Resolve file deletion conflicts

**Type**: Chore
**Complexity**: S

**Description**
Resolve conflicts for 3 files deleted in PR but modified on main by accepting main's version.

**Acceptance Criteria**
- [ ] Run `git checkout --theirs .serena/memories/skill-autonomous-execution-guardrails.md`
- [ ] Run `git checkout --theirs .serena/memories/skill-index-selection-decision-tree.md`
- [ ] Run `git checkout --theirs .serena/memories/skill-init-001-session-initialization.md`
- [ ] Verify all 3 files now exist in working directory
- [ ] Run `git add .serena/memories/skill-*.md` to stage resolved files

**Dependencies**
- TASK-002: Rebase started

**Files Affected**
- `.serena/memories/skill-autonomous-execution-guardrails.md`: Accept main version
- `.serena/memories/skill-index-selection-decision-tree.md`: Accept main version
- `.serena/memories/skill-init-001-session-initialization.md`: Accept main version

---

#### TASK-004: Merge skills-analysis-index.md manually

**Type**: Chore
**Complexity**: M

**Description**
Manually merge skills-analysis-index.md by combining table entries from both main and PR branch, removing duplicates, and sorting alphabetically.

**Acceptance Criteria**
- [ ] Extract main's table rows: `git show origin/main:.serena/memories/skills-analysis-index.md | grep -E '^\|.*\|.*\|' > /tmp/main-rows.txt`
- [ ] Extract PR's table rows: `git show HEAD:.serena/memories/skills-analysis-index.md | grep -E '^\|.*\|.*\|' > /tmp/pr-rows.txt`
- [ ] Combine and deduplicate: `cat /tmp/main-rows.txt /tmp/pr-rows.txt | sort -u > /tmp/merged-rows.txt`
- [ ] Edit `.serena/memories/skills-analysis-index.md` to replace table rows with merged content
- [ ] Verify no duplicate entries: `grep -E '^\|.*\|' .serena/memories/skills-analysis-index.md | sort | uniq -d` returns empty
- [ ] Verify no orphan references (files mentioned but don't exist)
- [ ] Run `git add .serena/memories/skills-analysis-index.md`

**Dependencies**
- TASK-003: File deletion conflicts resolved

**Files Affected**
- `.serena/memories/skills-analysis-index.md`: Manual merge

---

#### TASK-005: Merge skills-architecture-index.md manually

**Type**: Chore
**Complexity**: M

**Description**
Manually merge skills-architecture-index.md by combining table entries from both main and PR branch, removing duplicates, and sorting alphabetically.

**Acceptance Criteria**
- [ ] Extract main's table rows: `git show origin/main:.serena/memories/skills-architecture-index.md | grep -E '^\|.*\|.*\|' > /tmp/main-arch-rows.txt`
- [ ] Extract PR's table rows: `git show HEAD:.serena/memories/skills-architecture-index.md | grep -E '^\|.*\|.*\|' > /tmp/pr-arch-rows.txt`
- [ ] Combine and deduplicate: `cat /tmp/main-arch-rows.txt /tmp/pr-arch-rows.txt | sort -u > /tmp/merged-arch-rows.txt`
- [ ] Edit `.serena/memories/skills-architecture-index.md` to replace table rows with merged content
- [ ] Verify no duplicate entries: `grep -E '^\|.*\|' .serena/memories/skills-architecture-index.md | sort | uniq -d` returns empty
- [ ] Verify no orphan references (files mentioned but don't exist)
- [ ] Run `git add .serena/memories/skills-architecture-index.md`

**Dependencies**
- TASK-004: skills-analysis-index.md merged

**Files Affected**
- `.serena/memories/skills-architecture-index.md`: Manual merge

---

#### TASK-006: Complete rebase and verify state

**Type**: Chore
**Complexity**: S

**Description**
Complete git rebase and verify branch state is clean with only intended changes.

**Acceptance Criteria**
- [ ] Run `git rebase --continue` successfully
- [ ] Run `git status` shows clean working tree (no uncommitted changes)
- [ ] Run `git diff origin/main...fix/memories --stat` shows only 26 renamed files + validation script + 2 index files
- [ ] Verify domain index files updated to reference new filenames
- [ ] No files matching `skill-*.md` pattern remain in `.serena/memories/` (except accepted from main)

**Dependencies**
- TASK-005: skills-architecture-index.md merged

**Files Affected**
- All 26 renamed files from PR #365
- `scripts/Validate-SkillFormat.ps1`

---

#### TASK-007: Force push rebased branch

**Type**: Chore
**Complexity**: S

**Description**
Force push rebased branch to origin with lease protection.

**Acceptance Criteria**
- [ ] Run `git push --force-with-lease origin fix/memories` successfully
- [ ] Verify push accepted (no lease violations)
- [ ] Verify remote branch updated: `gh pr view 365 --json headRefOid` shows new commit SHA

**Dependencies**
- TASK-006: Rebase completed and verified

**Files Affected**
- None (updates remote branch only)

---

### Milestone 2: Update PR Documentation and Issue Scope

**Goal**: Update PR and issue documentation to reflect actual work performed and pass spec validation

#### TASK-008: Update PR #365 body

**Type**: Chore
**Complexity**: M

**Description**
Edit PR #365 description via GitHub UI to correct file count, remove out-of-scope issue reference, and document race condition.

**Acceptance Criteria**
- [ ] Run `gh pr view 365` to see current body
- [ ] Update file count from 61 to 26 in summary section
- [ ] Remove "Closes #311" reference (out of scope)
- [ ] Add "Changes" section documenting race condition with PRs #354 and #401
- [ ] Add note that 35 files were already renamed in prior PRs
- [ ] Update specification references table to only reference Issue #356
- [ ] Run `gh pr edit 365 --body-file /tmp/pr365-updated-body.md` to apply changes

**Dependencies**
- TASK-007: Branch pushed successfully

**Files Affected**
- PR #365 description (via GitHub API)

---

#### TASK-009: Add scope clarification comment to Issue #356

**Type**: Chore
**Complexity**: M

**Description**
Add comment to Issue #356 explaining that 35 files were renamed before PR #365 and only 26 remained at implementation time.

**Acceptance Criteria**
- [ ] Create comment file `/tmp/issue356-comment.md` using template from PRD (lines 187-204)
- [ ] Update comment with actual PR numbers (#354, #401) and file counts
- [ ] Run `gh issue comment 356 --body-file /tmp/issue356-comment.md`
- [ ] Verify comment posted successfully: `gh issue view 356 --comments`

**Dependencies**
- TASK-008: PR body updated

**Files Affected**
- Issue #356 comments (via GitHub API)

---

#### TASK-010: Update gap diagnostics document

**Type**: Chore
**Complexity**: S

**Description**
Mark Gap 5 as resolved in QA gap diagnostics document.

**Acceptance Criteria**
- [ ] Read `.agents/qa/PR-402/2025-12-26-gap-diagnostics.md`
- [ ] Locate Gap 5 section (lines 354-492 per PRD)
- [ ] Update status to "RESOLVED" with resolution timestamp
- [ ] Add note referencing PR #365 remediation and this task breakdown
- [ ] Commit change with message: `docs(qa): mark PR #365 Gap 5 as resolved`

**Dependencies**
- TASK-009: Issue comment posted

**Files Affected**
- `.agents/qa/PR-402/2025-12-26-gap-diagnostics.md`: Update Gap 5 status

---

### Milestone 3: Validation and Monitoring

**Goal**: Verify CI checks pass and PR is ready for merge

#### TASK-011: Wait for CI checks to start

**Type**: Chore
**Complexity**: S

**Description**
Wait for GitHub Actions to trigger CI checks on rebased branch.

**Acceptance Criteria**
- [ ] Run `gh pr checks 365` shows checks running (not "no checks")
- [ ] Verify "Validate Spec Coverage" check appears in list
- [ ] Verify "AI PR Quality Gate" check appears in list
- [ ] Wait at least 2 minutes for checks to start processing

**Dependencies**
- TASK-010: Gap diagnostics updated

**Files Affected**
- None (monitoring only)

---

#### TASK-012: Verify spec validation passes

**Type**: Chore
**Complexity**: L

**Description**
Monitor spec validation check and verify it passes with COMPLETENESS_VERDICT: PASS.

**Acceptance Criteria**
- [ ] Run `gh pr checks 365 --watch` until "Validate Spec Coverage" completes
- [ ] Verify check status is "pass" (not "fail")
- [ ] Fetch check logs: `gh run view <run-id> --log`
- [ ] Verify logs contain "COMPLETENESS_VERDICT: PASS"
- [ ] Verify logs contain "TRACE_VERDICT: PASS"
- [ ] No errors related to file count mismatch (61 vs 26)

**Dependencies**
- TASK-011: CI checks started

**Files Affected**
- None (monitoring only)

---

#### TASK-013: Verify all CI checks pass

**Type**: Chore
**Complexity**: L

**Description**
Monitor all remaining CI checks and verify complete green status.

**Acceptance Criteria**
- [ ] Run `gh pr checks 365` shows all checks with status "pass"
- [ ] Verify "AI PR Quality Gate" check passes (dependent on spec validation)
- [ ] Verify no failing checks remain
- [ ] Run `gh pr view 365` shows green merge status
- [ ] Verify PR is mergeable (no conflicts, all checks pass)

**Dependencies**
- TASK-012: Spec validation passed

**Files Affected**
- None (monitoring only)

---

#### TASK-014: Add completion comment and close Issue #356

**Type**: Chore
**Complexity**: S

**Description**
Add final completion comment to Issue #356 and close via PR #365 reference.

**Acceptance Criteria**
- [ ] Create comment: "Remediation complete. All merge conflicts resolved, CI checks passing, scope documentation updated. Closes via #365"
- [ ] Run `gh issue comment 356 --body "<comment text>"`
- [ ] Verify PR #365 is mergeable: `gh pr view 365 --json mergeable`
- [ ] Verify Issue #356 will auto-close when PR merges (GitHub UI shows link)

**Dependencies**
- TASK-013: All CI checks passed

**Files Affected**
- Issue #356 comments (via GitHub API)

---

## Dependency Graph

```text
TASK-001 → TASK-002 → TASK-003 → TASK-004 → TASK-005 → TASK-006 → TASK-007
                                                                      ↓
                                                                  TASK-008 → TASK-009 → TASK-010
                                                                                          ↓
                                                                                      TASK-011 → TASK-012 → TASK-013 → TASK-014
```

**Critical Path**: TASK-001 → TASK-002 → TASK-003 → TASK-004 → TASK-005 → TASK-006 → TASK-007 → TASK-008 → TASK-009 → TASK-010 → TASK-011 → TASK-012 → TASK-013 → TASK-014

**Parallelization Opportunities**: None (sequential dependencies)

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Rebase corrupts branch history | HIGH | TASK-001 creates backup; rollback procedure in PRD section "Rollback Procedure" |
| Manual merge creates duplicate entries | MEDIUM | TASK-004/005 include duplicate detection commands; verify before continuing |
| Orphan file references in index | MEDIUM | TASK-004/005 include orphan detection; fix before git add |
| Force push rejected (lease violation) | LOW | Use `--force-with-lease`; retry with `--force` only if certain branch state is correct |
| CI checks take longer than expected | LOW | TASK-011 waits 2 min minimum; TASK-012/013 use `--watch` mode |
| Spec validation still fails after update | MEDIUM | Review spec validation logs in TASK-012; update Issue #356 comment if criteria mismatch |

## Rollback Procedure

If any task fails critically, execute rollback:

1. **Abort in-progress rebase**: `git rebase --abort`
2. **Restore from backup**: `git reset --hard $(cat /tmp/pr365-backup/head.txt)`
3. **Force push original state**: `git push --force-with-lease origin fix/memories`
4. **Verify restoration**: `git log --oneline -5` matches `/tmp/pr365-backup/commits.txt`

Full rollback details in PRD section "Rollback Procedure" (lines 322-366).

## Verification Checklist

Before marking remediation complete, verify:

- [ ] All 14 tasks completed with acceptance criteria met
- [ ] `git status` on fix/memories branch shows clean tree
- [ ] `gh pr checks 365` shows all green
- [ ] `gh pr view 365` shows mergeable status
- [ ] Issue #356 has scope clarification comment
- [ ] PR #365 body accurately reflects 26 files renamed
- [ ] No `skill-*.md` files remain in changed files (except those accepted from main)
- [ ] Gap 5 marked as resolved in `.agents/qa/PR-402/2025-12-26-gap-diagnostics.md`

## Related Documents

- **PRD**: `.agents/planning/PRD-pr365-remediation.md`
- **Gap Analysis**: `.agents/qa/PR-402/2025-12-26-gap-diagnostics.md` (Gap 5)
- **Issue #356**: https://github.com/rjmurillo/ai-agents/issues/356
- **PR #365**: https://github.com/rjmurillo/ai-agents/pull/365
- **ADR-017**: Naming convention for memory files (referenced in validation)
