# Process and Workflow Gap Skills

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

## Related Documents

- Analysis: `.agents/analysis/pr41-issue-analysis.md`
- PRD: `.agents/planning/prd-pre-pr-security-gate.md`
- Retrospective: `.agents/retrospective/2025-12-15-pr41-ci-fix-workflow-analysis.md`
- Issue: #42
