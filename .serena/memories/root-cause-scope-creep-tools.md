# Root Cause Pattern: Scope Creep via Tool Side Effects

**Pattern ID**: RootCause-Process-003
**Category**: Cross-Cutting Concerns
**Created**: 2026-01-15
**Source**: PR #908 Comprehensive Retrospective

## Description

Tools with broad scope (markdownlint on all files, git operations on all changes) bundle
unrelated changes into PR. Single-purpose PR becomes multi-purpose due to tool side effects,
not intentional scope expansion.

## Detection Signals

- PR contains files unrelated to stated objective
- Markdownlint reformats 50+ files when changing 1
- Git commit includes files not explicitly added
- "Unrelated changes" in PR description or comments
- File count greatly exceeds intentional change scope

## Prevention Skills

- **Skill-Scoped-Tools-001**: Limit tool scope to changed files:
  `markdownlint $(git diff --name-only '*.md')`, not `**/*.md`
- Apply to session protocol tool commands — replace broad globs with git-scoped lists

## Evidence from PR #908

- **Incident**: PR #908 reformatted 53 memory files unrelated to skill creation
- **Root Cause Path**:
  - Q1: Why 53 memory files? → markdownlint reformatted all
  - Q2: Why all files? → Command: `markdownlint --fix **/*.md`
  - Q3: Why that command? → Session protocol uses broad glob
  - Q4: Why broad glob? → Prioritized simplicity over precision
  - Q5: Why that priority? → Early protocol versions favored "easy to remember"
- **Resolution**: Changed protocol to scope tools to changed files only

## Related Patterns

- **Similar to**: RootCause-Context-Loss-004 (losing track of original objective)
- **Related to**: RootCause-Process-001 (Governance Without Enforcement)
- **Related to**: RootCause-Process-002 (Late Feedback Loop)
- **Case Study**: PR #908 (https://github.com/rjmurillo/ai-agents/pull/908)

## References

- `.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md` (lines 1080-1120)
- PR: https://github.com/rjmurillo/ai-agents/pull/908
