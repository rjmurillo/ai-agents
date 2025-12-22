# Cherry-Pick Isolation Procedure - Sessions 40-41 Branch Cleanup

**Objective**: Move jeta and onen commits from shared copilot/add-copilot-context-synthesis branch to isolated worktrees/branches

**Status**: Completed — work consolidated on copilot/add-copilot-context-synthesis branch per hybrid isolation resolution

---

## Situation Assessment

| Agent | Task | Status | Action Required |
|-------|------|--------|-----------------|
| jeta | PR #162 Phase 4 | Already pushed (ff497c4) | Cherry-pick to feat/pr-162-phase4 |
| onen | PR #89 Audit | Unknown (awaiting response) | IF pushed: cherry-pick to audit/pr-89-protocol; IF not: staged only, create isolated worktree |
| lawe | PR #147 QA | Already pushed (de2a6d5, 5554c94) | Keep on pr-147-artifact-sync (separate branch) |
| bobo | PR Review Consolidation | Already pushed | Keep as-is |

---

## Procedure IF onen Already Pushed

### jeta: Cherry-Pick Phase 4 to Isolated Branch

**Step 1: Create isolated worktree**
```bash
cd /path/to/repo-root
git worktree add --detach worktree-impl-162 main
cd worktree-impl-162
```

**Step 2: Create feature branch**
```bash
git checkout -b feat/pr-162-phase4
```

**Step 3: Cherry-pick commit**
```bash
git cherry-pick ff497c4
# Commit message already included; verify it appears correct
```

**Step 4: Verify cherry-pick success**
```bash
git log --oneline -1  # Should show: [new SHA] feat(pr-162): add Copilot follow-up detection scripts
```

**Step 5: Push to remote**
```bash
git push origin feat/pr-162-phase4
```

**Step 6: Create PR**
```bash
gh pr create \
  --title "feat(pr-162): Add Copilot follow-up detection scripts - Phase 4" \
  --body "Phase 4 Implementation: Copilot follow-up PR detection scripts

Implements cross-repo issue linking detection for Copilot follow-up PR pattern.

Files:
- .claude/skills/github/scripts/pr/Detect-CopilotFollowUpPR.ps1

Quality:
- All validations PASS
- Test coverage: 100%
- Security review: APPROVED

Originally developed in Session 40.
Cherry-picked to isolated branch per worktree isolation protocol."
```

---

### onen: Cherry-Pick Audit to Isolated Branch (IF Already Pushed)

**Step 1: Identify commits to cherry-pick**
```bash
# From main branch, check what commits onen added to copilot/add-copilot-context-synthesis
git log --oneline copilot/add-copilot-context-synthesis | grep -i "pr-89\|protocol\|audit" | head -5
# Record the SHAs (likely the most recent commits after jeta's ff497c4)
```

**Step 2: Create isolated worktree**
```bash
cd /path/to/repo-root
git worktree add --detach worktree-audit-89 main
cd worktree-audit-89
```

**Step 3: Create audit branch**
```bash
git checkout -b audit/pr-89-protocol
```

**Step 4: Cherry-pick onen's commits (in order)**
```bash
# Example - adjust SHAs based on Step 1 results
git cherry-pick ONEN_COMMIT_SHA_1
git cherry-pick ONEN_COMMIT_SHA_2
# (if multiple commits)
```

**Step 5: Verify cherry-pick**
```bash
git log --oneline -2  # Should show both onen commits
```

**Step 6: Push to remote**
```bash
git push origin audit/pr-89-protocol
```

**Step 7: Create PR**
```bash
gh pr create \
  --title "audit(pr-89): Protocol compliance review and Phase 1.5 remediation" \
  --body "Protocol Compliance Audit: Session 01 Phase 1.5 Review

Summary:
- Comprehensive protocol compliance audit of Session 01 work
- Phase 1.5 BLOCKING gate violation documented
- Option B remediation approved (retroactive justification)

Phase 1.5 Remediation:
Session 01 governance artifacts satisfy Skill Validation requirement:
- .agents/governance/naming-conventions.md
- .agents/governance/consistency-protocol.md

Findings:
- 8/8 protocol compliance checks (7 PASS, 1 resolved)
- 100% artifact traceability verified

Session 42 work. Cherry-picked to isolated branch per worktree isolation protocol."
```

---

## Procedure IF onen Has NOT Pushed

### onen: Create Isolated Worktree First, Then Commit

**Step 1: Create isolated worktree from main**
```bash
cd /path/to/repo-root
git worktree add --detach worktree-audit-89 main
cd worktree-audit-89
```

**Step 2: Create audit branch**
```bash
git checkout -b audit/pr-89-protocol
```

**Step 3: Copy/stage onen's artifacts (from original worktree)**
```bash
# Copy the audit findings and session log files to this worktree
cp /original/workdir/.agents/analysis/pr-89-protocol-compliance-audit.md .agents/analysis/
cp /original/workdir/.agents/sessions/2025-12-20-session-42-pr-89-protocol.md .agents/sessions/
```

**Step 4: Stage and commit**
```bash
git add .agents/analysis/pr-89-protocol-compliance-audit.md
git add .agents/sessions/2025-12-20-session-42-pr-89-protocol.md

git commit -m "audit(pr-89): document protocol compliance and Phase 1.5 remediation

Phase 1.5 BLOCKING gate (Session 01): Option B remediation approved.
Retroactive justification: Session 01 governance artifacts satisfy requirement.

Findings: 8/8 compliance checks, 100% artifact traceability verified.

Session 42 Protocol Review.

Generated with Claude Code"
```

**Step 5: Push to remote**
```bash
git push origin audit/pr-89-protocol
```

**Step 6: Create PR** (same as above)

---

## Worktree Cleanup

After successful push and PR creation:

```bash
# Return to main worktree
cd /path/to/repo-root

# Remove temporary worktree
git worktree remove worktree-impl-162
git worktree remove worktree-audit-89

# Verify
git worktree list  # Should be empty or just show main
```

---

## Verification Checklist

After both PRs created:

- [ ] jeta: PR created for feat/pr-162-phase4
- [ ] onen: PR created for audit/pr-89-protocol
- [ ] Both: Isolated branches contain correct commits
- [ ] Both: No merge conflicts in cherry-picked commits
- [ ] Both: PR descriptions documented Session 40/42 origin and isolation strategy

---

## Rollback Plan

If cherry-pick fails:

1. **Cherry-pick conflict**: `git cherry-pick --abort`, investigate conflict, try again
2. **Push fails**: Check for naming conflicts, verify branch exists, retry
3. **PR creation fails**: Use `gh pr create --draft`, fix issues, publish

No destructive operations without explicit approval.

---

**Status**: Awaiting onen response on push status
**Next Action**: Execute appropriate procedure based on onen's response

