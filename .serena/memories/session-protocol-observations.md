# Skill Sidecar Learnings: Session Protocol

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 1 (Session 07)

## Constraints (HIGH confidence)

- Context compaction does NOT exempt session from protocol - continuation sessions require SAME initialization (Serena activation, HANDOFF.md read, session log creation) as fresh sessions (Session 07, 2026-01-16)
  - Evidence: PR #845 session protocol violation - work started without initialization after context compaction, no HANDOFF read, no Serena activation, no session log creation, HIGH severity protocol violation

## Preferences (MED confidence)

- None yet

## Edge Cases (MED confidence)

- None yet

## Notes for Review (LOW confidence)

- None yet

## Related

- [session-109-export-analysis-findings](session-109-export-analysis-findings.md)
- [session-110-agent-upgrade](session-110-agent-upgrade.md)
- [session-111-investigation-allowlist](session-111-investigation-allowlist.md)
- [session-112-pr-712-review](session-112-pr-712-review.md)
- [session-113-pr-713-review](session-113-pr-713-review.md)
