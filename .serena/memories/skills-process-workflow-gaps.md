# Process and Workflow Gap Skills

## Skill-Process-001: Validate Process Changes Before Implementation

**Statement**: Consult critic, devops, or architect agents before implementing process changes that affect developer workflow.

**Context**: When retrospective or analysis recommends automation, hooks, or workflow changes.

**Evidence**: PR #212 - Implemented pre-commit warning without agent review; immediately reverted due to devex concerns (warning fatigue, noise, maintenance burden).

**Atomicity**: 96%

**Tag**: helpful (prevents wasted effort)

**Impact**: 8/10 (avoids implement-then-revert cycles)

**Created**: 2025-12-20

**Problem**:

```text
Retrospective says: "Add pre-commit hook for X"
Agent implements immediately without validation
User: "This is annoying, revert it"
```

**Solution**:

```text
Before implementing workflow/process changes:
1. Ask: "Will this fire on every commit/save/action?"
2. If yes, consult devops/critic for alternatives
3. Consider: CI check (once per PR) vs pre-commit (every commit)
4. Consider: Warning vs blocking vs documentation-only
```

**Why It Matters**:

Per-commit warnings become noise that developers ignore. CI-level checks run once per PR and are more appropriate for policy enforcement. Documentation + agent awareness may be sufficient without automation.

**Validation**: 1 (PR #212 pre-commit revert)

Learned from PR #41 CI fix analysis (2025-12-15).

## Skill-Process-InfraDetection-001

- **Statement**: Infrastructure files (.github/workflows/*) require devops and security agent review before commit
- **Context**: When any workflow file is created or modified
- **Evidence**: PR #41 CodeQL alert could have been prevented with pre-commit review
- **Atomicity**: 92%
- **Tag**: helpful

## Skill-Process-QuickFix-001

- **Statement**: Quick fixes bypass formal review process; schedule retroactive review within same session
- **Context**: When urgent CI fix is needed
- **Evidence**: PR #41 fix made without devops/security despite just documenting the gap
- **Atomicity**: 90%
- **Tag**: harmful

## Skill-Meta-SelfAwareness-001

- **Statement**: Documenting a process gap does not prevent repeating it without explicit enforcement
- **Context**: When creating process improvement documentation
- **Evidence**: PR #41 PRD created simultaneously with non-compliant fix
- **Atomicity**: 96%
- **Tag**: neutral

## Skill-Process-ReadPRD-001

- **Statement**: Before modifying agent files, read .agents/planning/ PRD and implementation plan
- **Context**: When modifying agent system files
- **Evidence**: Drift detection disaster - failure to read PRD caused entire wrong-direction implementation where Claude was modified to match templates (backwards)
- **Atomicity**: 95%
- **Tag**: harmful (when skipped)
- **Source**: `.agents/retrospective/2025-12-15-drift-detection-disaster.md`
- **Trigger**: Before modifying agent system files

## Skill-Process-DriftInterpretation-001

- **Statement**: Drift detection shows differences, not update direction; verify source of truth in PRD before making changes
- **Context**: When drift detection reports differences
- **Evidence**: Misinterpreted "drift detected" as "Claude needs fixing" when PRD explicitly stated Claude is source of truth
- **Atomicity**: 92%
- **Tag**: helpful
- **Source**: `.agents/retrospective/2025-12-15-drift-detection-disaster.md`

## Skill-Process-ClarifySourceOfTruth-001

- **Statement**: Ask "which is source of truth?" when update direction is ambiguous
- **Context**: When task involves synchronization between multiple files
- **Evidence**: User message "Claude templates may need to be updated" was ambiguous; clarification would have prevented wrong-direction implementation
- **Atomicity**: 90%
- **Tag**: helpful
- **Source**: `.agents/retrospective/2025-12-15-drift-detection-disaster.md`

## Skill-Process-BaselineTriage-001

- **Statement**: When introducing new validation, establish baseline and triage pre-existing violations separately from new work
- **Context**: Adding new validators to existing codebases
- **Evidence**: Validation script found 14 pre-existing issues requiring separate triage to avoid scope creep
- **Atomicity**: 92%
- **Tag**: helpful
- **Source**: `.agents/retrospective/phase1-remediation-pr43.md`
- **Mitigation**: Baseline snapshot, exception list, gradual rollout

## Related Documents

- Analysis: `.agents/analysis/pr41-issue-analysis.md`
- PRD: `.agents/planning/prd-pre-pr-security-gate.md`
- Retrospective: `.agents/retrospective/2025-12-15-pr41-ci-fix-workflow-analysis.md`
- Retrospective: `.agents/retrospective/2025-12-15-drift-detection-disaster.md`
- Retrospective: `.agents/retrospective/phase1-remediation-pr43.md`
- Issue: #42
