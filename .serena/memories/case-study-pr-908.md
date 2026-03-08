# Case Study: PR #908 - 228 Comment Failure

**Pattern ID**: CaseStudy-PR-908
**Category**: Critical Failure Analysis
**Created**: 2026-01-15
**Status**: Closed (unmerged, archived as learning artifact)

---

## Summary

PR #908 ("feat(skill): add reflect skill and auto-learning hook") became the repository's largest failure event: 228+ review interactions, 59 commits (3× ADR-008 limit), 95 files changed (20× healthy limit), and 5,060 additions. The PR was never merged and serves as the primary evidence source for three root cause patterns.

---

## Key Metrics

| Metric | Value | Governance Limit | Violation |
|--------|-------|-----------------|-----------|
| Comments / review interactions | 228+ | N/A | Repository record |
| Commits | 59 | 20 (ADR-008) | 3× over limit |
| Files changed | 95 | 5–10 (best practice) | 20× over limit |
| Additions | 5,060 | N/A | — |
| `.serena/memories/` files | 53 (56% of changes) | N/A | Scope creep |
| Status | Unmerged | — | — |

---

## Root Causes Identified

Three root cause patterns were extracted from this failure:

### 1. Governance Without Enforcement (RootCause-Process-001)
ADR-008 limits (20 commits, 5–10 files) existed but were not enforced programmatically. No commit counter in session protocol. Architect synthesis issued BLOCKING verdict but work continued.

→ See [root-cause-governance-enforcement.md](root-cause-governance-enforcement.md)

### 2. Late Feedback Loop (RootCause-Process-002)
CodeQL security findings (CWE-22 path traversal) discovered in CI, not locally. Session validation failures also caught post-push. Created noise (extra commits to fix CI) and delayed feedback by 10–30 minutes.

→ See [root-cause-late-feedback.md](root-cause-late-feedback.md)

### 3. Scope Creep via Tool Side Effects (RootCause-Process-003)
`markdownlint --fix **/*.md` reformatted 53 `.serena/memories/` files unrelated to the PR objective. A single-purpose PR (reflect skill) became a multi-purpose change due to broad tool glob.

→ See [root-cause-scope-creep-tools.md](root-cause-scope-creep-tools.md)

---

## Learnings Extracted

1. **Commit counter**: Add `git rev-list --count HEAD ^$(git merge-base HEAD main)` check before PR creation
2. **Scoped markdownlint**: Use `markdownlint $(git diff --name-only main... '*.md')` not `**/*.md`
3. **Pre-PR validation script**: Validate governance limits (commits ≤20, files ≤10) before `gh pr create`
4. **Local CodeQL**: Run critical CodeQL rules locally before push
5. **BLOCKING enforcement**: Treat architect BLOCKING synthesis as a hard halt, not advisory

---

## Prevention Implemented

Issues #934–#949 track prevention implementations for each root cause:
- Skill-PR-Size-Validator-001
- Skill-Protocol-Commit-Counter-001
- Skill-Orchestrator-Synthesis-Block-001
- Skill-Security-Pre-Push-001
- Skill-Scoped-Tools-001

---

## References

- **Retrospective**: `.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md`
- **PR**: https://github.com/rjmurillo/ai-agents/pull/908
- **Prevention issues**: #934–#949
- **Root cause patterns**: [root-cause-governance-enforcement.md](root-cause-governance-enforcement.md), [root-cause-late-feedback.md](root-cause-late-feedback.md), [root-cause-scope-creep-tools.md](root-cause-scope-creep-tools.md)
