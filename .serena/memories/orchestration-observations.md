# Skill Sidecar Learnings: Orchestration

**Last Updated**: 2026-01-19  
**Sessions Analyzed**: 1

## Preferences (MED confidence)

- **Clarify ADR conflicts before implementation** (Session 14, 2026-01-19)
  - When approved plan conflicts with newer ADRs, pause and ask user for direction
  - Example: Issue #756 plan specified PowerShell scripts, but ADR-042 (accepted 2026-01-17) mandates Python-first
  - Orchestrator identified conflict, presented options, user directed Python implementation
  - Result: Prevented wasted PowerShell implementation that would need immediate rewrite

- **Check existing tools before building custom** (Session 14, 2026-01-19)
  - Before implementing custom detection/analysis, verify no existing solution exists (CodeQL, PSScriptAnalyzer, etc.)
  - Example: Issue #756 initial approach built custom CWE-22/CWE-77 detectors
  - User clarified: "We are using CodeQL--why is building a detector even necessary?"
  - Pivoted to CodeQL integration (fetch SARIF, interpret findings)
  - Result: Avoided reinventing the wheel, leveraged superior automated tooling

- **Documentation organization: CLAUDE.md vs AGENTS.md** (Session 14, 2026-01-19)
  - CLAUDE.md = Claude-specific configuration (tool preferences, behavior settings)
  - AGENTS.md = Shared guidance for ALL AI agents (patterns, workflows, protocols)
  - Example: Issue #756 security review content initially added to CLAUDE.md
  - User corrected: "Place Claude-specific items in CLAUDE.md; otherwise, place in AGENTS.md"
  - Moved security workflow guidance to AGENTS.md (shared), kept Claude-specific refs in CLAUDE.md
  - Result: Proper separation ensures all AI agents benefit from shared knowledge

## Edge Cases (MED confidence)

None yet.

## Notes for Review (LOW confidence)

None yet.

## Related Memories

- `parallel-agent-execution-session-14`: Session 14 execution details
- `adr-042-python-first-enforcement`: ADR conflict resolution pattern
- `codeql-security-integration`: Tool reuse pattern
