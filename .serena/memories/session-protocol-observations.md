# Skill Sidecar Learnings: Session Protocol

**Last Updated**: 2026-01-21
**Sessions Analyzed**: 2 (Session 07, PR #908 retrospective)

## Constraints (HIGH confidence)

- Context compaction does NOT exempt session from protocol - continuation sessions require SAME initialization (Serena activation, HANDOFF.md read, session log creation) as fresh sessions (Session 07, 2026-01-16)
  - Evidence: PR #845 session protocol violation - work started without initialization after context compaction, no HANDOFF read, no Serena activation, no session log creation, HIGH severity protocol violation
- Verify no BLOCKING synthesis issues before PR creation - architect blocks MUST be enforced (PR #908, 2026-01-15)
  - Evidence: PR #908 created despite architect P1 BLOCKING review in DESIGN-REVIEW-skill-reflect.md, leading to 228+ comments
  - Reference: Issue #934 (pre-PR validation)
- Check commit count during session against ADR-008 limit (max 20 commits per PR) (PR #908, 2026-01-15)
  - Evidence: PR #908 reached 59 commits (3× limit) without agent awareness, no visibility of limit during session
  - Actionable: Display "Commit X/20 (ADR-008)" after each commit
- Run scoped markdownlint on changed files only, not entire repository (PR #908, 2026-01-15)
  - Evidence: `markdownlint --fix **/*.md` reformatted 53 memory files in PR #908 that were unrelated to the feature
  - Actionable: Use `markdownlint --fix $(git diff --name-only '*.md')` instead

## Preferences (MED confidence)

- None yet

## Edge Cases (MED confidence)

- None yet

## Notes for Review (LOW confidence)

- None yet

## Case Studies

### PR #908 - 228 Comment Failure (2026-01-15)

Key learnings from PR #908 retrospective that inform session protocol:

1. **Pre-PR validation is critical**: PR created with unresolved architect BLOCKING review
2. **Commit limits need visibility**: 59 commits exceeded ADR-008 limit invisibly
3. **Tool scope matters**: Broad markdownlint bundled 53 unrelated files

See: `.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md`

## Related

- [session-109-export-analysis-findings](session-109-export-analysis-findings.md)
- [session-110-agent-upgrade](session-110-agent-upgrade.md)
- [session-111-investigation-allowlist](session-111-investigation-allowlist.md)
- [session-112-pr-712-review](session-112-pr-712-review.md)
- [session-113-pr-713-review](session-113-pr-713-review.md)
- PR #908 retrospective (evidence for constraints above)
